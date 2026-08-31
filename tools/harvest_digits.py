"""Build a labelled digit set from the hand-verified pilot PVs.

Every one of the 30 pilot bureaux passed the bureau-code check, so their field
values are known. Mapping fields to cells therefore labels each cell for free —
about 90 digits per form, in the exact handwriting and print of this corpus,
which beats a generic handwritten-digit corpus for this task.

Usage: python3 tools/harvest_digits.py
"""
import json, os, sys
import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pv_grid import find_cells, group_runs, digit_image, LADDER
from pv_fields import map_fields, digits_of, COLUMNS

READINGS = ".cache/pv_pilot/readings.jsonl"
UPRIGHT = ".cache/pv_upright"
PILOT_DIR = ".cache/pv_pilot"
OUT = ".cache/digit_train.npz"

FIELD_LEN = 4


def source_image(code):
    for path in (os.path.join(UPRIGHT, f"{code}.jpg"),
                 os.path.join(PILOT_DIR, "upright", f"{code}.jpg")):
        if os.path.exists(path):
            return path
    return None


def main():
    recs = [json.loads(l) for l in open(READINGS, encoding="utf-8")]
    X, y, meta = [], [], []
    used = skipped = 0
    for rec in recs:
        path = source_image(rec["bureau_code"])
        if not path:
            skipped += 1
            continue
        img = cv2.imread(path)
        if img is None:
            skipped += 1
            continue
        H, W = img.shape[:2]
        # Same detection ladder the production reader uses: a form the first
        # setting cannot read is not a form without labels, it is a faint scan.
        fields, want = {}, sum(len(c[4]) for c in COLUMNS)
        for cfg in LADDER:
            f = map_fields(group_runs(find_cells(img, settings=cfg)), W, H)
            if len(f) > len(fields):
                fields = f
            if len(fields) == want:
                break
        if not fields:
            skipped += 1
            continue
        used += 1
        for name, run in fields.items():
            labels = digits_of(rec.get(name), len(run))
            if labels is None or len(labels) != len(run):
                continue
            for cell, lab in zip(run, labels):
                d = digit_image(img, cell)
                if d is None:
                    continue
                X.append(d)
                y.append(lab)
                meta.append((rec["bureau_code"], name))
    X = np.array(X, np.uint8)
    y = np.array(y, np.int8)
    codes = np.array([m[0] for m in meta])
    names = np.array([m[1] for m in meta])
    np.savez_compressed(OUT, X=X, y=y, code=codes, field=names)
    import collections
    print(f"forms used {used}, skipped {skipped}")
    print(f"labelled digits: {len(y)} -> {OUT}")
    print("class counts:", dict(sorted(collections.Counter(y.tolist()).items())))
    print("fields covered:", len({m[1] for m in meta}))


if __name__ == "__main__":
    main()
