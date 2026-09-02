"""Manufacture the training domain the loop cannot reach: low-resolution forms.

The reader fails on 478 stations, 195 of them in Medenine, where ISIE published
at a median 560px. Those forms are not illegible — magnified, a person reads them
easily, and on 23030110101 the reader already gets all three candidates right and
fails only because `valid` is misread. The information is on the page.

What is missing is training data. Labels here come from forms the identities
vouch for, and no 560px form has ever certified, so no 560px crop has ever been
a label. The classifier is out of domain on precisely the forms that fail. This
is the same bootstrapping bias that has bitten this project twice: the labels
worth harvesting are the ones the loop cannot currently get.

So take the 3,100 forms that read at 1600px with no cell overruled, degrade the
**page** to the resolution that fails, and re-crop through the normal pipeline.
Degrading the page rather than the crop is the whole point — a strip downsampled
after cropping keeps the sharp edges the crop was taken from, while a strip cut
out of a 560px page is upsampled from a handful of pixels and carries the JPEG
artefacts of the page it came from. Only the second resembles Medenine.

One honest limit, already recorded in the method notes: downsampled forms are
easier than genuinely low-resolution ones. Forms shrunk to 868px still locate a
mean of 14.9 fields where real 868px scans yield about 3, and that gap is
uncharacterised. So this is a closer approximation of the failing domain, not a
substitute for it, and whether it helps must be judged on real low-resolution
forms rather than on more of these.

Usage: python3 tools/harvest_degraded.py [--limit N] [--workers 4]
"""
import argparse, csv, os, sys
from concurrent.futures import ProcessPoolExecutor

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

RESULTS = "data/pv_presidential_2024.csv"
UPRIGHT = ".cache/pv_upright"
OUT = ".cache/digit_strips_degraded.npz"
OUT_WORDS = ".cache/word_strips_degraded.npz"
NDIG = 4
# The failing forms sit around 560px; the band is wider so the net sees the
# approach to it rather than one operating point.
LONG_EDGE = (480, 1000)
QUALITY = (52, 88)
FIELDS = ("zammel", "maghzaoui", "saied", "valid", "q_declared", "w_voted",
          "n_total", "b_delivered", "c_signed", "a_registered")


def degrade(img, rng):
    """The page as ISIE would have published it small: resized, then re-encoded."""
    h, w = img.shape[:2]
    target = int(rng.integers(*LONG_EDGE))
    if max(h, w) <= target:
        return None
    f = target / max(h, w)
    small = cv2.resize(img, (max(1, round(w * f)), max(1, round(h * f))),
                       interpolation=cv2.INTER_AREA)
    q = int(rng.integers(*QUALITY))
    ok, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, q])
    if not ok:
        return None
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


def _work_words(args):
    """The words column at low resolution, for the same reason as the digits.

    On a 560px page the candidate cells land at about 20px wide and the other
    fields at about 8px, so `valid` and `q_declared` are unreadable while the
    candidates are not. That makes the words the only independent witness left
    for the candidate split there - and the word reader has never seen a
    degraded form either.
    """
    code, path, values, seed = args
    try:
        from harvest_words import word_image, CANDIDATES
        from decode_all import layouts
        from pv_template import placed_layouts
        img = cv2.imread(path)
        if img is None:
            return None
        rng = np.random.default_rng(seed)
        small = degrade(img, rng)
        if small is None:
            return None
        out = []
        for fields in list(layouts(small)) + list(placed_layouts(small)):
            for name in CANDIDATES:
                cells = fields.get(name)
                val = values.get(name)
                if not cells or len(cells) != NDIG or val is None:
                    continue
                im = word_image(small, cells)
                if im is not None:
                    out.append((im, [int(d) for d in str(val).zfill(NDIG)]))
            if out:
                break
        return code, out
    except Exception:
        return None


def _work(args):
    code, path, values, seed = args
    try:
        from harvest_strips import strip_image
        from decode_all import layouts
        from pv_template import placed_layouts
        img = cv2.imread(path)
        if img is None:
            return None
        rng = np.random.default_rng(seed)
        small = degrade(img, rng)
        if small is None:
            return None
        out = []
        for fields in list(layouts(small)) + list(placed_layouts(small)):
            for name, val in values.items():
                cells = fields.get(name)
                if not cells or len(cells) != NDIG:
                    continue
                im = strip_image(small, cells)
                if im is not None:
                    out.append((im, [int(d) for d in str(val).zfill(NDIG)]))
            if out:
                break
        return code, out
    except Exception:
        return None


def jobs(limit):
    out = []
    for r in csv.DictReader(open(RESULTS, encoding="utf-8")):
        if r["votes_certified"] != "1" or r["cells_corrected"] not in ("0", ""):
            continue
        p = os.path.join(UPRIGHT, f"{r['bureau_code']}.jpg")
        if not os.path.exists(p):
            continue
        vals = {}
        for n in FIELDS:
            v = r.get(n, "")
            if v.isdigit() and len(v) <= NDIG:
                vals[n] = int(v)
        if len(vals) >= 4:
            out.append((r["bureau_code"], p, vals, len(out)))
    return out[:limit] if limit else out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 4)
    ap.add_argument("--words", action="store_true",
                    help="crop the words column rather than the digit cells")
    a = ap.parse_args()
    todo = jobs(a.limit)
    work, dest = (_work_words, OUT_WORDS) if a.words else (_work, OUT)
    print(f"{len(todo)} clean forms to degrade, {a.workers} workers", flush=True)
    X, y, src, forms = [], [], [], 0
    with ProcessPoolExecutor(a.workers) as ex:
        for i, res in enumerate(ex.map(work, todo, chunksize=8), 1):
            if res and res[1]:
                code, items = res
                forms += 1
                for im, lab in items:
                    X.append(im); y.append(lab); src.append(code)
            if i % 250 == 0:
                print(f"  {i}/{len(todo)}  {forms} forms, {len(y)} strips", flush=True)
    np.savez_compressed(dest, X=np.array(X, np.uint8), y=np.array(y, np.int8),
                        code=np.array(src))
    print(f"\n{len(y)} degraded strips from {forms} forms -> {dest}")
    print(f"({forms} of {len(todo)} survived registration after degrading, "
          f"{forms/max(len(todo),1):.0%})")


if __name__ == "__main__":
    main()
