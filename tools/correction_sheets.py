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
import argparse, csv, glob, os

import cv2
import numpy as np

FOUND = ".cache/corrections.csv"
BOX = (0.09, 0.06, 0.89, 0.96)   # the table, with a margin
INK = (0.09, 0.45)               # the الخطأ and الإصلاح columns, as page fractions
WIDE = 760


def ink(bgr):
    """How much handwriting sits in the two value columns.

    Printed text is black and the pen is usually blue, but not always, so this
    counts dark pixels and simply ignores the rows the section headers occupy —
    those are wide dark bands, and no correction is written inside one.
    """
    g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    h, w = g.shape
    band = g[:, int(w * INK[0]):int(w * INK[1])]
    dark = band < 140
    rows = dark.mean(axis=1)
    return float(dark[rows < 0.5].mean())


def tile(path, caption):
    img = cv2.imread(path)
    if img is None:
        return None, 0.0
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
        t, s = tile(p, f"{code}   {stem}")
        if t is not None:
            scored.append((s, code, t))
    scored.sort(key=lambda x: -x[0])

    idx = []
    for i in range(0, len(scored), a.per):
        chunk = scored[i:i + a.per]
        h = max(t.shape[0] for _s, _n, t in chunk)
        tiles = [cv2.copyMakeBorder(t, 0, h - t.shape[0], 0, 8,
                                    cv2.BORDER_CONSTANT, value=(255, 255, 255))
                 for _s, _n, t in chunk]
        name = "sheet_%03d.png" % (i // a.per + 1)
        cv2.imwrite(os.path.join(a.out, name), np.hstack(tiles))
        for _s, n, _t in chunk:
            idx.append((name, n, round(_s, 5)))
    with open(os.path.join(a.out, "index.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["sheet", "bureau_code", "ink"])
        w.writerows(idx)
    print(f"{len(scored)} tables on {(len(scored)+a.per-1)//a.per} sheets -> {a.out}")


if __name__ == "__main__":
    main()
