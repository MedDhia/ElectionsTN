"""Render the pages `reps_pages.py` found, so the rows can be read.

One tile per bureau: the bottom of the archived page that carries a
representatives table, turned the way the locator had to turn it. Where more
than one page fits, the one with the most of the table's own rules is used --
that is the locator's own confidence, and it separates the counting record from
a correction form whose blocks happen to fit the pattern.

Usage: python3 tools/reps_page_sheets.py <hits.json> <out_dir> [per_sheet]
"""
import json, os, sys

import cv2
import numpy as np

TILE_W, TILE_H = 1000, 190
COLS = 2
LABEL_H = 18
# The band is a thin strip near the foot of a tall page, so a fixed fraction of
# the page wastes most of the tile on blank paper and leaves the handwriting too
# small to read. The locator already knows where the table is; run it again on
# the page that was chosen and crop to its box with a margin.
PAD = 0.9                      # extra band-heights above and below
FALLBACK_TOP, FALLBACK_LEFT = 0.62, 0.28
PDF_DPI = 200
ROTATIONS = {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180,
             270: cv2.ROTATE_90_COUNTERCLOCKWISE}


def page_image(path, page):
    if not path.lower().endswith(".pdf"):
        return cv2.imread(path)
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(path)
    pil = doc[page].render(scale=PDF_DPI / 72).to_pil().convert("RGB")
    return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)


def best(hits):
    return max(hits, key=lambda h: (h["col_rules"], h["row_rules"]))


def band(img):
    """The table's own box on this page, widened, or None."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import pv_reps_geom as G
    try:
        loc, _ = G.locate(img)
    except Exception:
        loc = None
    if loc is None:
        return None
    x0, y0, x1, y1 = loc["box"]
    bh = max(20, y1 - y0)
    h, w = img.shape[:2]
    return (max(0, int(y0 - PAD * bh)), min(h, int(y1 + PAD * bh)),
            max(0, int(x0 - 0.04 * w)), w)


def tile(code, hit):
    img = page_image(hit["path"], hit["page"])
    if img is None:
        return None
    if hit["rotation"]:
        img = cv2.rotate(img, ROTATIONS[hit["rotation"]])
    h, w = img.shape[:2]
    box = band(img)
    if box:
        y0, y1, x0, x1 = box
        crop = img[y0:y1, x0:x1]
    else:
        crop = img[int(FALLBACK_TOP * h):h, int(FALLBACK_LEFT * w):w]
    if crop.size == 0:
        return None
    crop = cv2.resize(crop, (TILE_W, TILE_H), interpolation=cv2.INTER_CUBIC)
    lab = np.full((LABEL_H, TILE_W, 3), 255, np.uint8)
    cv2.putText(lab, code, (3, LABEL_H - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                (0, 0, 0), 1, cv2.LINE_AA)
    return np.vstack([lab, crop])


def main():
    hits = json.load(open(sys.argv[1]))
    out_dir = sys.argv[2]
    per = int(sys.argv[3]) if len(sys.argv) > 3 else 8
    os.makedirs(out_dir, exist_ok=True)
    tiles, order = [], []
    for code in sorted(hits):
        t = tile(code, best(hits[code]))
        if t is not None:
            tiles.append(t)
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
                lines.append(np.hstack([np.hstack(
                    [r, np.full((r.shape[0], 6, 3), 0, np.uint8)]) for r in row]))
                lines.append(np.full((6, lines[-1].shape[1], 3), 0, np.uint8))
            cv2.imwrite(os.path.join(out_dir, f"rescue_{made:03d}.png"),
                        np.vstack(lines))
            for code in order[i:i + per]:
                fh.write(f"{made} {code}\n")
            made += 1
    print(f"{made} sheets from {len(order)} bureaux -> {out_dir}")


if __name__ == "__main__":
    main()
