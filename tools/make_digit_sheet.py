"""Tile digit cells from many forms into one sheet, to look at what the pipeline sees.

Written to support hand-labelling at scale, which turned out not to be needed —
`tools/certify_cells.py` labels the corpus from its own arithmetic instead. It is
kept as an inspection tool, and it earned that: the first sheet it produced showed
that most cells were fragments of the printed rules rather than digits, which is
how the cropping bug in `pv_grid.digit_image` was found. Numbers in a confusion
matrix would not have shown it.

Sampling is balanced using whatever classifier already exists, since the pool is
about 58% zeros (fields are zero-padded to four columns) and drawing at random
wastes most of the sheet. A weak model is enough to sort the pool — it only has to
be better than chance.

Usage: python3 tools/make_digit_sheet.py <sheet_index> [n_forms]
"""
import glob, json, os, random, sys
import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pv_grid import find_fields, digit_image
from pv_fields import map_fields
from pv_montage import ORDER

ORIENT = ".cache/pv_upright"
OUT_DIR = ".cache/digit_sheets"
COLS, ROWS = 20, 10
CELL = 44
GAP = 6
MARGIN = 34


def collect(paths, per_form=20, seed=0):
    """Digit crops with provenance from forms whose field map is complete."""
    rng = random.Random(seed)
    out = []
    for p in paths:
        img = cv2.imread(p)
        if img is None:
            continue
        fields, _ = find_fields(img, map_fields, len(ORDER))
        if len(fields) != len(ORDER):
            continue
        items = [(n, i, c) for n, run in fields.items() for i, c in enumerate(run)]
        rng.shuffle(items)
        code = os.path.basename(p)[:-4]
        for name, idx, cell in items[:per_form]:
            d = digit_image(img, cell)
            if d is not None and d.max() > 0:
                out.append((d, code, name, idx))
    return out


def balance(items, k):
    """Spread the draw across predicted classes using an existing model."""
    model_path = ".cache/digit_model.pkl"
    if not os.path.exists(model_path):
        random.Random(1).shuffle(items)
        return items[:k]
    import pickle
    clf = pickle.load(open(model_path, "rb"))
    X = np.array([d for d, *_ in items]).reshape(len(items), -1) / 255.0
    pred = clf.predict(X)
    buckets = {}
    for it, p in zip(items, pred):
        buckets.setdefault(int(p), []).append(it)
    for v in buckets.values():
        random.Random(2).shuffle(v)
    out, i = [], 0
    while len(out) < k and any(buckets.values()):
        for c in sorted(buckets):
            if buckets[c] and len(out) < k:
                out.append(buckets[c].pop())
        i += 1
    return out


def render(items):
    w = MARGIN + COLS * (CELL + GAP) + GAP
    h = MARGIN + ROWS * (CELL + GAP) + GAP
    canvas = np.full((h, w), 255, np.uint8)
    for c in range(COLS):
        cv2.putText(canvas, str(c + 1), (MARGIN + c * (CELL + GAP) + 8, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, 0, 1, cv2.LINE_AA)
    for r in range(ROWS):
        cv2.putText(canvas, "ABCDEFGHIJ"[r], (6, MARGIN + r * (CELL + GAP) + CELL - 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, 0, 1, cv2.LINE_AA)
    for i, (d, *_) in enumerate(items):
        r, c = divmod(i, COLS)
        y = MARGIN + r * (CELL + GAP)
        x = MARGIN + c * (CELL + GAP)
        canvas[y:y + CELL, x:x + CELL] = 255 - cv2.resize(d, (CELL, CELL),
                                                          interpolation=cv2.INTER_NEAREST)
    return canvas


def main():
    idx = int(sys.argv[1])
    n_forms = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    os.makedirs(OUT_DIR, exist_ok=True)
    paths = sorted(glob.glob(os.path.join(ORIENT, "*.jpg")))
    rng = random.Random(1000 + idx)
    rng.shuffle(paths)
    items = collect(paths[:n_forms * 3], per_form=20, seed=idx)
    items = balance(items, COLS * ROWS)
    if len(items) < COLS * ROWS:
        print(f"only {len(items)} cells found; sheet will be short")
    png = os.path.join(OUT_DIR, f"sheet{idx:02d}.png")
    cv2.imwrite(png, render(items))
    np.savez_compressed(os.path.join(OUT_DIR, f"sheet{idx:02d}.npz"),
                        X=np.array([d for d, *_ in items], np.uint8))
    json.dump([{"code": c, "field": f, "i": i} for _, c, f, i in items],
              open(os.path.join(OUT_DIR, f"sheet{idx:02d}.json"), "w"))
    print(f"{png}  {len(items)} cells  ({os.path.getsize(png)//1024} KB)")


if __name__ == "__main__":
    main()
