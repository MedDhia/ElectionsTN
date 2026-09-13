"""Render the representatives table as contact sheets to be read.

The candidate column is three lines of Arabic handwriting drawn from a set of
three names, which is a reading task rather than a recognition one, and the only
reader available to this project that can do it is the model driving the session.
Turns are the constraint, not tokens, so the crops are packed: one tile per
polling station carrying the candidate column and the representative's name
beside it, which is what settles an ambiguous hand — a clerk who wrote the
representative's own name in the candidate box is visible only if both columns
are on the sheet.

The signature column is left out. It says a representative signed, not who for,
and it is the widest of the three.

Usage:
    python3 tools/reps_sheets.py <manifest.csv> <out_dir> [per_sheet]
"""
import csv, os, sys

import cv2
import numpy as np

UPRIGHT = ".cache/pv_upright"
TILE_W, ROW_H = 440, 40
COLS = int(os.environ.get("REPS_SHEET_COLS", "4"))
LABEL_H = 17


def tile(code, geo):
    """The candidate and name columns of one station's table, three rows tall."""
    img = cv2.imread(os.path.join(UPRIGHT, code + ".jpg"))
    if img is None:
        return None
    deg = int(geo.get("rotation") or 0)
    if deg:
        img = cv2.rotate(img, {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180,
                               270: cv2.ROTATE_90_COUNTERCLOCKWISE}[deg])
    x1, c1 = int(geo["x1"]), int(geo["c1"])
    rows = [int(geo[f"r{i}"]) for i in range(4)]
    parts = []
    for i in range(3):
        crop = img[max(0, rows[i]):rows[i + 1], max(0, c1):x1]
        if crop.size == 0:
            crop = np.full((ROW_H, TILE_W, 3), 255, np.uint8)
        crop = cv2.resize(crop, (TILE_W, ROW_H), interpolation=cv2.INTER_CUBIC)
        parts.append(crop)
        parts.append(np.full((1, TILE_W, 3), 190, np.uint8))
    body = np.vstack(parts[:-1])
    lab = np.full((LABEL_H, TILE_W, 3), 255, np.uint8)
    cv2.putText(lab, code, (3, LABEL_H - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                (0, 0, 0), 1, cv2.LINE_AA)
    return np.vstack([lab, body])


def sheets(rows, out_dir, per_sheet=21):
    os.makedirs(out_dir, exist_ok=True)
    made, batch, n = [], [], 0
    for geo in rows:
        t = tile(geo["bureau_code"], geo)
        if t is None:
            continue
        batch.append(t)
        if len(batch) == per_sheet:
            made.append(_write(batch, out_dir, len(made)))
            batch = []
    if batch:
        made.append(_write(batch, out_dir, len(made)))
    return made


def _write(batch, out_dir, idx):
    h = max(t.shape[0] for t in batch)
    pad = [np.vstack([t, np.full((h - t.shape[0], TILE_W, 3), 255, np.uint8)])
           if t.shape[0] < h else t for t in batch]
    lines = []
    for i in range(0, len(pad), COLS):
        row = pad[i:i + COLS]
        while len(row) < COLS:
            row.append(np.full((h, TILE_W, 3), 255, np.uint8))
        lines.append(np.hstack([np.hstack([r, np.full((h, 6, 3), 0, np.uint8)])
                                for r in row]))
        lines.append(np.full((6, lines[-1].shape[1], 3), 0, np.uint8))
    path = os.path.join(out_dir, f"sheet_{idx:04d}.png")
    cv2.imwrite(path, np.vstack(lines))
    return path


def main():
    man, out_dir = sys.argv[1], sys.argv[2]
    per = int(sys.argv[3]) if len(sys.argv) > 3 else 21
    rows = list(csv.DictReader(open(man, encoding="utf-8")))
    made = sheets(rows, out_dir, per)
    print(f"{len(made)} sheets from {len(rows)} stations -> {out_dir}")


if __name__ == "__main__":
    main()
