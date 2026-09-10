"""Re-crop the stations whose located box did not frame the representatives table.

Localization fits a six-rule pattern to the page, and on about one form in
seventy it fits the pattern one block out: the crop then frames the results
table or the band's own header instead of the three writing rows. Those stations
are not unreadable, only mis-framed — the table is a fixed distance away on the
same page — so this renders a generous window around the located box, wide
enough to contain the table wherever within a block or two it actually sits, and
tall enough that the reader can see which band is which.

The window is deliberately not re-fitted. A second automatic guess would put the
same class of error back into the data silently; a human-read window cannot,
because the reader sees the header and the rules and knows when the table is not
there.

Usage: python3 tools/reps_rescue.py <codes.txt> <out_dir> [per_sheet]
"""
import csv, os, sys

import cv2
import numpy as np

UPRIGHT = ".cache/pv_upright"
GEO = ".cache/reps_geometry.csv"
TILE_W, TILE_H = 800, 250
COLS = 2
LABEL_H = 18
# The stored rotation is deliberately not applied. `locate_any` retries the
# other rotations when the fit fails at zero, and on a page already upright a
# 180-degree retry can still satisfy the pattern — the form is nearly symmetric
# top to bottom once the band and the results block are both in play. Eighty-
# seven of the hundred stations left unread carry rotation 180 for that reason,
# and honouring it puts the window on the masthead. The cached images are
# upright, so the page is read as it is.
#
# The window is anchored on the *page*, not on the box that was got wrong. A
# window around a mis-placed box inherits the mistake: on the first pass, ten of
# twelve rescued crops framed the results table again, because that is where the
# bad fit had put them. The representatives table is the last thing on the form,
# so the bottom third of the page contains it however badly the rules were fitted.
TOP_R = float(os.environ.get("REPS_RESCUE_TOP", "0.62"))
LEFT_R = 0.30
# ... except where the page really is sideways. Set REPS_RESCUE_ROTATE=1 to
# honour the stored rotation: the two windows are complementary, one reading the
# pages whose rotation was a bad retry and the other the pages that are genuinely
# turned, and a station unreadable under one is often plain under the other.
ROTATE = os.environ.get("REPS_RESCUE_ROTATE") == "1"


def geometry():
    return {r["bureau_code"]: r for r in csv.DictReader(open(GEO, encoding="utf-8"))}


def window(code, geo):
    img = cv2.imread(os.path.join(UPRIGHT, code + ".jpg"))
    if img is None:
        return None
    deg = int(geo.get("rotation") or 0) if ROTATE else 0
    if deg:
        img = cv2.rotate(img, {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180,
                               270: cv2.ROTATE_90_COUNTERCLOCKWISE}[deg])
    h, w = img.shape[:2]
    crop = img[int(TOP_R * h):h, int(LEFT_R * w):w]
    if crop.size == 0:
        return None
    return cv2.resize(crop, (TILE_W, TILE_H), interpolation=cv2.INTER_CUBIC)


def main():
    codes = [l.strip() for l in open(sys.argv[1], encoding="utf-8") if l.strip()]
    out_dir = sys.argv[2]
    per = int(sys.argv[3]) if len(sys.argv) > 3 else 12
    geo = geometry()
    os.makedirs(out_dir, exist_ok=True)
    tiles, order = [], []
    for code in codes:
        if code not in geo:
            continue
        im = window(code, geo[code])
        if im is None:
            continue
        lab = np.full((LABEL_H, TILE_W, 3), 255, np.uint8)
        cv2.putText(lab, code, (3, LABEL_H - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                    (0, 0, 0), 1, cv2.LINE_AA)
        tiles.append(np.vstack([lab, im]))
        order.append(code)
    made = 0
    with open(os.path.join(out_dir, "order.txt"), "w", encoding="utf-8") as fh:
        for i in range(0, len(tiles), per):
            batch = tiles[i:i + per]
            lines = []
            for j in range(0, len(batch), COLS):
                row = batch[j:j + COLS]
                while len(row) < COLS:
                    row.append(np.full(batch[0].shape, 255, np.uint8))
                lines.append(np.hstack([np.hstack([r, np.full((r.shape[0], 6, 3), 0,
                                                              np.uint8)])
                                        for r in row]))
                lines.append(np.full((6, lines[-1].shape[1], 3), 0, np.uint8))
            cv2.imwrite(os.path.join(out_dir, f"rescue_{made:03d}.png"),
                        np.vstack(lines))
            for code in order[i:i + per]:
                fh.write(f"{made} {code}\n")
            made += 1
    print(f"{made} sheets from {len(order)} stations -> {out_dir}")


if __name__ == "__main__":
    main()
