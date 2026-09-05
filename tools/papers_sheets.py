"""Lay out the ballots column for the stations whose papers block is unpublished.

`decode_all` publishes the papers block for the bureaux it can read whole. The
stations read by eye have their candidate votes but not their ballots: reading
those forms, the papers column was used as a cross-check and thrown away — the
note "papers block agrees (400=373+13+14)" is in the readings file 59 times, but
as prose, not as fields.

So the column gets read properly this time. It is four numbers in one place —
extracted from the box, valid, blank, spoilt — which is why six forms fit on a
sheet where the candidate rows needed two.

The crop is the same band the candidate reading used, narrowed to the middle
column. Nothing here locates fields; the band is a page fraction, and a form
whose block sits outside it is re-rendered by hand, as before.

Usage: python3 tools/papers_sheets.py [--out DIR] [--per 6]
"""
import argparse, csv, json, os

import cv2
import numpy as np

RESULTS = "data/pv_presidential_2024.csv"
READINGS = "data/verification/lowres_readings.jsonl"
UPRIGHT = ".cache/pv_upright"
BOX = (0.30, 0.32, 0.64, 0.61)      # the ballots column, as page fractions
# The band has to be generous vertically. A first attempt at 0.40-0.56 framed the
# column on some forms and cut the extracted-ballots row off the top of others,
# which is the row the other three have to add up to.
WIDE = 700


def tile(code, caption):
    p = os.path.join(UPRIGHT, f"{code}.jpg")
    img = cv2.imread(p) if os.path.exists(p) else None
    if img is None:
        return None
    h, w = img.shape[:2]
    x0, y0, x1, y1 = BOX
    im = img[int(h * y0):int(h * y1), int(w * x0):int(w * x1)]
    if im.size == 0:
        return None
    f = WIDE / im.shape[1]
    im = cv2.resize(im, (WIDE, max(1, int(round(im.shape[0] * f)))),
                    interpolation=cv2.INTER_CUBIC)
    bar = np.full((24, WIDE, 3), 235, np.uint8)
    cv2.putText(bar, caption, (6, 17), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                (0, 0, 0), 1, cv2.LINE_AA)
    return np.vstack([bar, im, np.full((4, WIDE, 3), 110, np.uint8)])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=".cache/papersheets")
    ap.add_argument("--per", type=int, default=6)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    rows = {r["bureau_code"]: r for r in csv.DictReader(open(RESULTS, encoding="utf-8"))}
    want = []
    for line in open(READINGS, encoding="utf-8"):
        d = json.loads(line)
        c = d["bureau_code"]
        if d.get("extracted") is not None:
            continue                      # already read
        if rows.get(c, {}).get("papers_certified") == "1":
            continue                      # the pipeline already has it
        if c in rows:
            want.append(c)
    want = sorted(dict.fromkeys(want))
    print(f"{len(want)} stations need their ballots column read")

    tiles, kept = [], []
    for c in want:
        t = tile(c, c)
        if t is not None:
            tiles.append(t)
            kept.append(c)

    idx = []
    for i in range(0, len(tiles), a.per):
        chunk = tiles[i:i + a.per]
        # Tiles differ by a pixel or two in height because the crop is a page
        # fraction and the pages are not all the same size; pad before stacking.
        def row(ts):
            h = max(t.shape[0] for t in ts)
            return np.hstack([cv2.copyMakeBorder(t, 0, h - t.shape[0], 0, 6,
                                                 cv2.BORDER_CONSTANT,
                                                 value=(255, 255, 255)) for t in ts])
        rows_of = [row(chunk[j:j + 3]) for j in range(0, len(chunk), 3)]
        w = max(r.shape[1] for r in rows_of)
        rows_of = [r if r.shape[1] == w else
                   cv2.copyMakeBorder(r, 0, 0, 0, w - r.shape[1],
                                      cv2.BORDER_CONSTANT, value=(255, 255, 255))
                   for r in rows_of]
        name = "papers_%03d.png" % (i // a.per + 1)
        cv2.imwrite(os.path.join(a.out, name), np.vstack(rows_of))
        for c in kept[i:i + a.per]:
            idx.append((name, c))
    with open(os.path.join(a.out, "index.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["sheet", "bureau_code"])
        w.writerows(idx)
    print(f"{len(tiles)} on {(len(tiles)+a.per-1)//a.per} sheets -> {a.out}")


if __name__ == "__main__":
    main()
