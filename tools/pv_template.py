"""Store a reference form's geometry, for `pv_register` to place fields from.

The PV is a fixed pre-printed template, so the field positions on a scan the
detector cannot segment can be borrowed from one it can. This picks a form that
detection read completely and records where its twenty fields sit.

An earlier version also tried registering scans to this reference by image
correlation (ECC over the pixels). That does not work and is not kept: grayscale
alignment reaches a correlation of 0.87 while still missing the cells by several
pixels, which is enough to crop the neighbouring digit — of 40 forms aligned that
way, 35 decoded and 1 survived the form's own consistency checks. Registering on
the *cells detection did find*, which is what `pv_register` does, is what works.

Usage: python3 tools/pv_template.py build [bureau_code]
"""
import json, os, sys
import cv2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pv_grid import find_cells, group_runs, LADDER
from pv_fields import map_fields, COLUMNS

CANON_W = 1600     # the geometry is stored at a fixed width so it can be
                   # scaled onto scans of any size
REF_GEO = ".cache/pv_template.json"
WANT = sum(len(c[4]) for c in COLUMNS)


def _canon(img):
    s = CANON_W / img.shape[1]
    return cv2.resize(img, (CANON_W, max(1, round(img.shape[0] * s))),
                      interpolation=cv2.INTER_CUBIC if s > 1 else cv2.INTER_AREA), s


def build(code=None):
    """Store the field geometry of a form detection could read completely."""
    import csv
    if code is None:
        rows = [r for r in csv.DictReader(open("data/pv_presidential_2024.csv",
                                                encoding="utf-8"))
                if r["status"] == "read" and int(r["fields_located"] or 0) == 20
                and int(r["cells_corrected"]) == 0]
        rows.sort(key=lambda r: -float(r["margin"]))
        code = rows[0]["bureau_code"]
    img = cv2.imread(f".cache/pv_upright/{code}.jpg")
    work, _ = _canon(img)
    H, W = work.shape[:2]
    best = {}
    for cfg in LADDER:
        f = map_fields(group_runs(find_cells(work, settings=cfg)), W, H)
        if len(f) > len(best):
            best = f
        if len(best) == WANT:
            break
    if len(best) != WANT:
        raise SystemExit(f"reference {code} only yields {len(best)} fields")
    json.dump({"bureau_code": code, "width": W, "height": H,
               "fields": {k: [list(map(int, c)) for c in v]
                          for k, v in best.items()}}, open(REF_GEO, "w"))
    print(f"reference {code}: {len(best)} fields, {W}x{H} -> {REF_GEO}")


if __name__ == "__main__":
    build(sys.argv[2] if len(sys.argv) > 2 else None)
