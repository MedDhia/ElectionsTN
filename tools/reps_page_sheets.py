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

TILE_W, TILE_H = 800, 250
COLS = 2
LABEL_H = 18
TOP_R, LEFT_R = 0.58, 0.28
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


def tile(code, hit):
    img = page_image(hit["path"], hit["page"])
    if img is None:
        return None
    if hit["rotation"]:
        img = cv2.rotate(img, ROTATIONS[hit["rotation"]])
    h, w = img.shape[:2]
    crop = img[int(TOP_R * h):h, int(LEFT_R * w):w]
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
