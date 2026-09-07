"""Lay out the decision tables for reading, busiest first.

`find_corrections.py` locates the page of each *قرار تصحيح محضر فرز* that carries
the table of corrections. Most of those tables are mostly empty: a decision ticks
one or two rows and leaves the rest blank, and some are blank throughout. So the
pages are ordered by how much handwriting sits in the two value columns, which
puts the decisions that actually change something first and lets a run of empty
ones be confirmed at a glance.

The crop keeps the printed row labels. It would be narrower without them — the
handwriting is all in the left 40% of the page — but then a row would have to be
identified by its position in the table, and the whole point of the exercise is
to know *which* field a number replaces.

Usage: python3 tools/correction_sheets.py [--pages DIR] [--out DIR] [--per 2]
"""
import argparse, csv, glob, os, sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

FOUND = ".cache/corrections.csv"
BOX = (0.09, 0.06, 0.89, 0.96)   # the table, with a margin
INK = (0.09, 0.45)               # the الخطأ and الإصلاح columns, as page fractions
WIDE = 760


def ink(bgr):
    """How much of the two value columns is covered, relative to the label column.

    An absolute ink measure does not survive the range of scans here: a page
    scanned to bilevel reads as 20% dark whether or not anything is written in
    it, and a page scanned in colour loses nothing but reads as 1%. Dividing by
    the coverage of the label column — printed text on every page, and so a
    per-page baseline — makes the numbers comparable. It is still only an
    ordering hint, not a test: a blank table on a heavy scan can outrank a filled
    one on a light scan, so every table gets looked at regardless.
    """
    g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    h, w = g.shape
    rows = slice(int(h * 0.10), int(h * 0.95))
    vals = (g[rows, int(w * INK[0]):int(w * INK[1])] < 140).mean()
    base = (g[rows, int(w * 0.50):int(w * 0.86)] < 140).mean()
    return float(vals / (base + 1e-6))


_REFS = None


def refs():
    global _REFS
    if _REFS is None:
        import find_corrections
        _REFS = find_corrections.references()
    return _REFS


def looks_like_a_page(im):
    """Best correlation of this image against the decision's three page types."""
    import find_corrections
    t = find_corrections.thumb(im)
    return max(float((t * v).sum()) for v in refs().values())


def halves(img):
    """The decision's pages, one per returned image.

    Some bundles scan two A4 pages onto one landscape sheet. Arabic booklet order
    puts the earlier page on the right, so the table of corrections — page 2 of
    the decision — is the left half and the cover, with the station code and the
    stage-1 fields, is the right half. Both are wanted, so both are returned.

    Aspect ratio alone is not enough to decide: plenty of single pages are simply
    scanned onto a wide sheet with white beside them, and splitting one of those
    cuts the value columns off the table. So a split is kept only if both halves
    then look like a page of the decision, which is the same correlation test
    that found these pages in the first place.
    """
    h, w = img.shape[:2]
    if w > h * 1.25:
        mid = w // 2
        left, right = img[:, :mid], img[:, mid:]
        if min(looks_like_a_page(left), looks_like_a_page(right)) >= 0.20:
            return [("left", left), ("right", right)]
    return [("", img)]


def tile(img, caption):
    h, w = img.shape[:2]
    x0, y0, x1, y1 = BOX
    im = img[int(h * y0):int(h * y1), int(w * x0):int(w * x1)]
    if im.size == 0:
        return None, 0.0
    score = ink(img)
    f = WIDE / im.shape[1]
    im = cv2.resize(im, (WIDE, max(1, int(round(im.shape[0] * f)))),
                    interpolation=cv2.INTER_AREA)
    bar = np.full((26, WIDE, 3), 235, np.uint8)
    cv2.putText(bar, caption, (6, 19), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                (0, 0, 0), 1, cv2.LINE_AA)
    return np.vstack([bar, im, np.full((4, WIDE, 3), 110, np.uint8)]), score


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", default=".cache/corrtab")
    ap.add_argument("--out", default=".cache/corrsheets")
    ap.add_argument("--per", type=int, default=2)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    # the rendered files are named for the source file, which is not the bureau
    # code: one is 120607107__120607107-01_p2 for bureau 12060710701. Captioning
    # with the code is the difference between a reading that can be applied and
    # one that has to be traced back by hand.
    owner = {}
    for r in csv.DictReader(open(FOUND, encoding="utf-8")):
        owner[f"{r['stem']}_p{r['page']}"] = r["bureau_code"]

    scored = []
    for p in sorted(glob.glob(os.path.join(a.pages, "*.png"))):
        stem = os.path.basename(p)[:-4]
        code = owner.get(stem, "?")
        img = cv2.imread(p)
        if img is None:
            continue
        for side, half in halves(img):
            t, s = tile(half, f"{code}  {stem}{'  ' + side if side else ''}")
            if t is not None:
                scored.append((s, code, t))
    scored.sort(key=lambda x: (-x[0], x[1]))

    idx = []
    for i in range(0, len(scored), a.per):
        chunk = scored[i:i + a.per]
        h = max(t.shape[0] for _s, _n, t in chunk)
        tiles = [cv2.copyMakeBorder(t, 0, h - t.shape[0], 0, 8,
                                    cv2.BORDER_CONSTANT, value=(255, 255, 255))
                 for _s, _n, t in chunk]
        name = "sheet_%03d.png" % (i // a.per + 1)
        # two across, then wrap: a single row of four is scaled down twice as far
        # by anything that views it as two rows of two are.
        rows_of = [np.hstack(tiles[j:j + 2]) for j in range(0, len(tiles), 2)]
        w = max(r.shape[1] for r in rows_of)
        rows_of = [r if r.shape[1] == w else
                   cv2.copyMakeBorder(r, 0, 0, 0, w - r.shape[1],
                                      cv2.BORDER_CONSTANT, value=(255, 255, 255))
                   for r in rows_of]
        cv2.imwrite(os.path.join(a.out, name), np.vstack(rows_of))
        for _s, n, _t in chunk:
            idx.append((name, n, round(_s, 5)))
    with open(os.path.join(a.out, "index.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["sheet", "bureau_code", "ink"])
        w.writerows(idx)
    print(f"{len(scored)} tables on {(len(scored)+a.per-1)//a.per} sheets -> {a.out}")


if __name__ == "__main__":
    main()
