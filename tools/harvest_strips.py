"""Harvest whole field strips, not single cells, with the digits that fill them.

The cell classifier reads each box alone, which throws away everything the four
boxes of a field share: one hand, one pen, one scan, and a strong joint prior —
counts are zero-padded, so a leading 9 is rare and a leading 0 is not. It is also
brittle in exactly the way the remaining failures are. Those forms have their
cells located but misread, and a per-cell crop that is three pixels out clips its
digit, while a strip crop three pixels out barely changes.

So this stores the field as one image, labelled with all four digits, for a model
that reads it in one go (`tools/strip_model.py`). Labels come the same way cell
labels do: from the fields the form's own arithmetic vouches for, via the
production reader, so degraded scans are represented too.

Usage: python3 tools/harvest_strips.py [--limit N]
"""
import argparse, os, sys
from concurrent.futures import ProcessPoolExecutor

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

UPRIGHT = ".cache/pv_upright"
OUT = ".cache/digit_strips.npz"
W, H = 128, 36          # a four-cell field, kept wide enough to hold its rules
NDIG = 4

_net = None


def strip_image(img, cells, pad_frac=0.10, size=(W, H)):
    """One image of a whole field: the run's bounding box, ink white on black."""
    xs = [c[0] for c in cells] + [c[0] + c[2] for c in cells]
    ys = [c[1] for c in cells] + [c[1] + c[3] for c in cells]
    px = max(1, int(round(pad_frac * min(c[3] for c in cells))))
    x0, y0 = max(0, min(xs) + px), max(0, min(ys) + px)
    x1, y1 = min(img.shape[1], max(xs) - px), min(img.shape[0], max(ys) - px)
    if x1 - x0 < 8 or y1 - y0 < 6:
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
        if not got or not got["certified"]:
            return None
        # The reader hands back crops, not rectangles, so recover the geometry
        # from whichever layout supplied the same fields.
        out = []
        for fields in list(layouts(img)) + list(placed_layouts(img)):
            for name in got["certified"]:
                if name not in fields or len(fields[name]) != NDIG:
                    continue
                val = got["raw"].get(name)
                if val is None:
                    continue
                s = str(int(val)).zfill(NDIG)
                if len(s) != NDIG:
                    continue
                im = strip_image(img, fields[name])
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
    print(f"\n{len(y)} strips from {forms} forms -> {OUT}")


if __name__ == "__main__":
    main()
