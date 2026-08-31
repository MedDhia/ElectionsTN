"""Store a reference form's geometry, for `pv_register` to place fields from.

The PV is a fixed pre-printed template, so the field positions on a scan the
detector cannot segment can be borrowed from one it can. This picks a form that
detection read completely and records where its twenty fields sit.

The reference also supports registering a scan to it by image correlation, for
the forms where too little of the printed grid survives to anchor on the cells
detection found. On its own that does not work — alignment reaches a correlation
of 0.87 while still missing the cells by several pixels, which is enough to crop
the neighbouring digit, and of 40 forms aligned that way only one survived the
form's own checks. It works when the placement is then refined field by field
(`pv_register.refine`): on 80 forms where no grid could be found at all, the two
together certify the candidate votes on about a third.

Registration keys on colour, not luminance. The form's printed structure is red,
so a red-minus-grey signal isolates the layout from the handwriting, which is what
differs between two scans of the same template.

Usage: python3 tools/pv_template.py build [bureau_code]
"""
import json, os, sys
import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pv_grid import find_cells, group_runs, LADDER
from pv_fields import map_fields, COLUMNS

CANON_W = 1600     # the geometry is stored at a fixed width so it can be
                   # scaled onto scans of any size
ECC_W = 560        # registration is done small: it wants the layout, and full
                   # resolution only adds handwriting, which differs per scan
REF_GEO = ".cache/pv_template.json"
REF_IMG = ".cache/pv_template.png"
WANT = sum(len(c[4]) for c in COLUMNS)


def _canon(img):
    s = CANON_W / img.shape[1]
    return cv2.resize(img, (CANON_W, max(1, round(img.shape[0] * s))),
                      interpolation=cv2.INTER_CUBIC if s > 1 else cv2.INTER_AREA), s


def build(code=None):
    """Store the field geometry of a form detection can read completely.

    The candidate list is ordered and walked rather than trusted: a row can show
    twenty fields because a *registered* layout supplied them, and a reference
    has to be a form whose grid detection finds on its own.
    """
    import csv
    if code:
        candidates = [code]
    else:
        rows = [r for r in csv.DictReader(open("data/pv_presidential_2024.csv",
                                                encoding="utf-8"))
                if r["status"] == "read" and (r["cells_corrected"] or "99") == "0"]
        rows.sort(key=lambda r: -float(r["margin"] or 0))
        candidates = [r["bureau_code"] for r in rows[:60]]

    for cand in candidates:
        img = cv2.imread(f".cache/pv_upright/{cand}.jpg")
        if img is None:
            continue
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
            continue
        cv2.imwrite(REF_IMG, work)
        json.dump({"bureau_code": cand, "width": W, "height": H,
                   "fields": {k: [list(map(int, c)) for c in v]
                              for k, v in best.items()}}, open(REF_GEO, "w"))
        print(f"reference {cand}: {len(best)} fields, {W}x{H} "
              f"-> {REF_GEO}, {REF_IMG}")
        return
    raise SystemExit("no candidate form yields a complete field map by detection")


SIGNALS = ("red", "plain")


def _signal(img, mode):
    """What two scans of this form share: its printed layout, not its writing."""
    b, g, r = cv2.split(img.astype(np.int16))
    if mode == "red":
        m = np.clip(r - np.maximum(g, b), 0, 255)
    else:
        m = np.clip(np.maximum(g, b) - r + 40, 0, 255)
    return cv2.GaussianBlur(m.astype(np.float32) / 255.0, (0, 0), 4.0)


def reference():
    """(reference image at CANON_W, field geometry), or (None, None)."""
    if not (os.path.exists(REF_IMG) and os.path.exists(REF_GEO)):
        return None, None
    doc = json.load(open(REF_GEO))
    return cv2.imread(REF_IMG), {k: [tuple(c) for c in v]
                                 for k, v in doc["fields"].items()}


def align(img, ref, mode):
    """Affine mapping reference coordinates to `img`, and its correlation."""
    work, scale = _canon(img)
    fs = ECC_W / CANON_W
    small = cv2.resize(work, (ECC_W, max(1, round(work.shape[0] * fs))))
    rsmall = cv2.resize(ref, (ECC_W, max(1, round(ref.shape[0] * fs))))
    h = min(small.shape[0], rsmall.shape[0])
    warp = np.eye(2, 3, dtype=np.float32)
    try:
        cc, warp = cv2.findTransformECC(
            _signal(rsmall[:h], mode), _signal(small[:h], mode), warp,
            cv2.MOTION_AFFINE,
            (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-6), None, 5)
    except cv2.error:
        return None, 0.0
    if not np.isfinite(warp).all():
        return None, 0.0
    # The warp acts at ECC_W on both sides; undo that and the canonical resize.
    A = warp[:, :2] / scale
    t = warp[:, 2] / (fs * scale)
    return np.hstack([A, t.reshape(2, 1)]).astype(np.float64), float(cc)


def placed_layouts(img, min_cc=0.30):
    """Field maps for `img` obtained by registering it against the reference."""
    ref, geo = reference()
    if ref is None:
        return []
    out = []
    for mode in SIGNALS:
        A, cc = align(img, ref, mode)
        if A is None or cc < min_cc:
            continue
        fields = {}
        for name, cells in geo.items():
            placed = []
            for x, y, w, h in cells:
                pts = np.array([[x, y, 1], [x + w, y, 1],
                                [x, y + h, 1], [x + w, y + h, 1]], np.float64)
                q = pts @ A.T
                x0, y0 = q[:, 0].min(), q[:, 1].min()
                x1, y1 = q[:, 0].max(), q[:, 1].max()
                placed.append((int(round(x0)), int(round(y0)),
                               max(1, int(round(x1 - x0))),
                               max(1, int(round(y1 - y0)))))
            fields[name] = placed
        out.append(fields)
    return out


if __name__ == "__main__":
    build(sys.argv[2] if len(sys.argv) > 2 else None)
