"""Harvest the candidate scores as the form spells them out in Arabic words.

The seven identities constrain the candidate total but not the split between the
three candidates: `valid == zammel + maghzaoui + saied` is one equation in three
unknowns, so a misreading that moves votes between candidates while preserving
their sum closes every identity on the form and is certified. Bureau 01080310102
was published as Saied 329 / Zammel 85 and reads Saied 389 / Zammel 25 — a 2/8
confusion in two tens columns, cancelling in the total.

The form already carries the fix. Beside the digit cells, each candidate's score
is written out in words (`ثلاثمائة و تسعة و ثمانين` beside `0389`), under the
heading الأصوات المصرح بها بلسان القلم. That column is a second, independent
encoding of precisely the quantity the arithmetic leaves unprotected, and nothing
in this pipeline has ever read it.

Labels come the same way every other label here does — from the arithmetic. Only
the *raw* reading is used, never a decoded one: a raw certification means the
classifier read all three candidates unaided and they summed to the declared
total, which a compensating pair of errors would have to survive twice over. The
decoded rows are exactly the ones under suspicion, so they are not used to teach.

Usage: python3 tools/harvest_words.py [--limit N]
"""
import argparse, os, sys
from concurrent.futures import ProcessPoolExecutor

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

UPRIGHT = ".cache/pv_upright"
OUT = ".cache/word_strips.npz"
W, H = 512, 28          # the column is about 19:1; keep close to it
NDIG = 4
CANDIDATES = ("zammel", "maghzaoui", "saied")
GAP_RATIO = 0.02        # clear the rule between the cells and the words
# The words column is 3.25 times as wide as the run of digit cells beside it, in
# the reference layout. Taking it as a ratio rather than a pixel count keeps the
# crop framing the same words whatever the scan's scale.
SPAN_RATIO = 3.25

_net = None


def word_image(img, cells, size=(W, H)):
    """The words written beside a candidate's digit cells, ink white on black.

    Taken relative to the cells rather than from its own template entry, so it
    follows the same registration the digits did and needs no extra geometry.
    """
    xr = max(c[0] + c[2] for c in cells)
    run = xr - min(c[0] for c in cells)
    y0, y1 = min(c[1] for c in cells), max(c[1] + c[3] for c in cells)
    x0 = xr + max(1, int(round(GAP_RATIO * run)))
    x1 = x0 + int(round(SPAN_RATIO * run))
    h, w = img.shape[:2]
    x0, x1 = max(0, x0), min(w, x1)
    y0, y1 = max(0, y0), min(h, y1)
    if x1 - x0 < 80 or y1 - y0 < 8:
        return None
    g = cv2.cvtColor(img[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
    ink = cv2.adaptiveThreshold(g, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                cv2.THRESH_BINARY_INV, 15, 10)
    return cv2.resize(ink, size, interpolation=cv2.INTER_AREA)


def _work(args):
    code, path, model = args
    global _net
    try:
        if _net is None:
            import torch
            from digit_model import Net
            torch.set_num_threads(1)
            _net = Net()
            _net.load_state_dict(torch.load(model, map_location="cpu"))
            _net.eval()
        from digit_model import predict_proba
        from decode_all import read_image, layouts
        from pv_template import placed_layouts
        img = cv2.imread(path)
        if img is None:
            return None
        got = read_image(img, lambda X: predict_proba(_net, X))
        if not got:
            return None
        # Raw certification only: the decoded split is the thing in question.
        want = [c for c in CANDIDATES if c in got["certified"]]
        if len(want) != len(CANDIDATES):
            return None
        out = []
        for fields in list(layouts(img)) + list(placed_layouts(img)):
            for name in want:
                if name not in fields or len(fields[name]) != NDIG:
                    continue
                val = got["raw"].get(name)
                if val is None:
                    continue
                s = str(int(val)).zfill(NDIG)
                if len(s) != NDIG:
                    continue
                im = word_image(img, fields[name])
                if im is not None:
                    out.append((im, [int(d) for d in s]))
            if out:
                break
        return code, out
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--model", default=".cache/digit_cnn.pt")
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 4)
    a = ap.parse_args()
    codes = sorted(f[:-4] for f in os.listdir(UPRIGHT)
                   if f.endswith(".jpg") and f[:-4].isdigit())
    if a.limit:
        codes = list(np.random.default_rng(0).permutation(codes)[:a.limit])
    jobs = [(c, os.path.join(UPRIGHT, f"{c}.jpg"), a.model) for c in codes]
    print(f"{len(jobs)} forms, {a.workers} workers", flush=True)
    X, y, src, forms = [], [], [], 0
    with ProcessPoolExecutor(a.workers) as ex:
        for i, res in enumerate(ex.map(_work, jobs, chunksize=8), 1):
            if res and res[1]:
                code, items = res
                forms += 1
                for im, lab in items:
                    X.append(im); y.append(lab); src.append(code)
            if i % 500 == 0:
                print(f"  {i}/{len(jobs)}  {forms} forms, {len(y)} strips", flush=True)
    np.savez_compressed(OUT, X=np.array(X, np.uint8), y=np.array(y, np.int8),
                        code=np.array(src))
    print(f"\n{len(y)} word strips from {forms} forms -> {OUT}")


if __name__ == "__main__":
    main()
