"""Render whole pages for the forms no field-finder can lay out.

Every sheet built so far crops individual fields, which needs the geometry to
work — either the printed rules detected, or the page registered against the
reference. For 91 bureaux neither succeeds, and the tooling has been reporting
them as "could not be laid out" as though that were a fact about the scans. It
is not: their median long edge is over 4,000px and most are perfectly sharp.

So stop asking where the fields are and just show the page. The counting record
puts the candidate rows and the two totals in the lower-left of an upright form,
so that region is rendered large; if a scan is rotated, folded or cropped oddly
the whole page is rendered instead and the eye can find the block itself.

Nothing here depends on registration, grid detection, or the template. That is
the point — it is the fallback of last resort, and the only reason a form should
survive it is that the information genuinely is not on the page.

Usage: python3 tools/page_sheets.py [--codes FILE] [--out DIR] [--per 2]
"""
import argparse, csv, json, os, sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

RESULTS = "data/pv_presidential_2024.csv"
UPRIGHT = ".cache/pv_upright"
DONE = "data/verification/lowres_readings.jsonl"
WIDE = 1850          # width each rendered region is scaled to


def region(img):
    """The middle-and-lower band of the page, full width.

    The candidate rows sit at the left and the declared total at the right, so a
    left-hand crop cuts the total off — which is what made the first pass look
    like the totals were missing when they were merely outside the frame.

    The band is generous vertically for the same reason: the counting block does
    not sit at a fixed height, and a crop tight enough to look tidy sliced the
    third candidate off forms whose block starts low. A row cut in half is worse
    than a row rendered small — the eye can cope with small.
    """
    h, w = img.shape[:2]
    return img[int(h * 0.28):int(h * 0.92), 0:w]


def scale_to(im, width=WIDE):
    h, w = im.shape[:2]
    if w == 0 or h == 0:
        return None
    f = width / w
    return cv2.resize(im, (width, max(1, int(round(h * f)))),
                      interpolation=cv2.INTER_CUBIC)


def banner(code, width, note=""):
    im = np.full((34, width, 3), 240, np.uint8)
    cv2.putText(im, code + ("  " + note if note else ""), (8, 24),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)
    return im


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--codes", help="file of bureau codes, one per line")
    ap.add_argument("--out", default=".cache/page_sheets")
    ap.add_argument("--per", type=int, default=2)
    a = ap.parse_args()

    if a.codes:
        codes = [l.strip() for l in open(a.codes) if l.strip()]
    else:
        done = set()
        if os.path.exists(DONE):
            done = {json.loads(l)["bureau_code"] for l in open(DONE, encoding="utf-8")}
        codes = [r["bureau_code"] for r in csv.DictReader(open(RESULTS, encoding="utf-8"))
                 if r["votes_certified"] != "1" and r["bureau_code"] not in done]
    os.makedirs(a.out, exist_ok=True)
    print(f"{len(codes)} forms to render whole", flush=True)

    tiles, kept = [], []
    for code in codes:
        p = os.path.join(UPRIGHT, f"{code}.jpg")
        img = cv2.imread(p) if os.path.exists(p) else None
        if img is None:
            print("  no image", code); continue
        im = scale_to(region(img))
        if im is None:
            continue
        tiles.append(np.vstack([banner(code, im.shape[1]), im]))
        kept.append(code)

    n = 0
    for i in range(0, len(tiles), a.per):
        chunk = tiles[i:i + a.per]
        w = max(t.shape[1] for t in chunk)
        chunk = [t if t.shape[1] == w else
                 cv2.copyMakeBorder(t, 0, 0, 0, w - t.shape[1],
                                    cv2.BORDER_CONSTANT, value=(255, 255, 255))
                 for t in chunk]
        cv2.imwrite(os.path.join(a.out, "page_%03d.png" % (i // a.per + 1)),
                    np.vstack(chunk))
        n += len(chunk)
    with open(os.path.join(a.out, "index.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["sheet", "position", "bureau_code"])
        for i, c in enumerate(kept):
            w.writerow(["page_%03d.png" % (i // a.per + 1), i % a.per + 1, c])
    print(f"{n} forms on {(len(tiles)+a.per-1)//a.per} sheets -> {a.out}")


if __name__ == "__main__":
    main()
