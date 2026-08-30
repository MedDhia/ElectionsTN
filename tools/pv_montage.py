"""Render a PV's digit cells as a compact labelled montage.

A full page at 1600px costs roughly 2,400 image tokens. The digits themselves
occupy a tiny fraction of that, so cropping the located cells and tiling them —
one field per row, in a fixed order — carries the same information at a fraction
of the size. Useful for any model-based read: same fields, far fewer tokens.

Usage: python3 tools/pv_montage.py <bureau_code> [out.png]
"""
import os, sys
import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pv_grid import find_fields, digit_image
from pv_fields import map_fields

CELL = 40
GAP = 6
LABEL_W = 190
ORDER = ["a_registered", "b_delivered", "c_signed", "d_damaged", "r_remaining",
         "s_extracted", "valid", "blank", "spoilt",
         "match1", "w_voted", "m_total", "match2", "n_total", "match3",
         "q_declared", "match4", "zammel", "maghzaoui", "saied"]


def montage(img, fields, order=ORDER):
    present = [f for f in order if f in fields]
    if not present:
        return None, []
    width = LABEL_W + 4 * (CELL + GAP)
    height = len(present) * (CELL + GAP) + GAP
    canvas = np.full((height, width), 255, np.uint8)
    for i, name in enumerate(present):
        y = GAP + i * (CELL + GAP)
        cv2.putText(canvas, name[:20], (4, y + CELL - 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, 0, 1, cv2.LINE_AA)
        for j, cell in enumerate(fields[name][:4]):
            d = digit_image(img, cell, size=CELL)
            if d is None:
                continue
            x = LABEL_W + j * (CELL + GAP)
            canvas[y:y + CELL, x:x + CELL] = 255 - d      # dark ink on white
    return canvas, present


def build(code, out=None):
    path = f".cache/pv_upright/{code}.jpg"
    img = cv2.imread(path)
    if img is None:
        raise SystemExit(f"no image for {code}")
    fields, _ = find_fields(img, map_fields, len(ORDER))
    canvas, present = montage(img, fields)
    out = out or f"/tmp/montage_{code}.png"
    cv2.imwrite(out, canvas)
    return out, present, canvas.shape


if __name__ == "__main__":
    out, present, shape = build(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
    px = shape[0] * shape[1]
    print(f"{out}  {shape[1]}x{shape[0]} ({px/750:.0f} image tokens)  fields: {len(present)}")
    print("  ", ", ".join(present))
