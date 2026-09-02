"""Render the stations that are still uncertified, so the register can be checked.

`data/verification/unreadable_scans.jsonl` says in words why each of the last
stations cannot be published. Words are cheap; the claim is only as good as the
scans behind it, and anyone who wants to disagree needs to see them. This lays
them out one group at a time, labelled with the code and with whatever the
register asserts, so the assertion and the evidence sit in the same frame.

The four groups want different crops, because they fail differently. A form that
does not balance needs its candidate block and its total, large enough to read.
A bundle with no counting record needs the whole page, small, because the point
is what document it is rather than what it says. A truncated scan needs the
bottom edge, where the table stops. A scan below resolution needs its own pixels.

Usage: python3 tools/remaining_sheets.py [--out DIR]
"""
import argparse, csv, json, os

import cv2
import numpy as np

RESULTS = "data/pv_presidential_2024.csv"
REGISTER = "data/verification/unreadable_scans.jsonl"
READINGS = "data/verification/lowres_readings.jsonl"
UPRIGHT = ".cache/pv_upright"

# x0, y0, x1, y1 as page fractions, the width each tile is scaled to, tiles per
# row, and tiles per sheet. The last number matters: a single tall strip of nine
# forms gets scaled down to nothing by whatever views it, which defeats the point
# of rendering them large in the first place.
CROPS = {
    "read_but_does_not_balance": ((0.0, 0.40, 0.68, 0.82), 1500, 1, 3),
    "no_counting_record":        ((0.0, 0.00, 1.00, 1.00),  740, 3, 9),
    "truncated_scan":            ((0.0, 0.70, 0.75, 1.00), 1100, 2, 6),
    "below_resolution":          ((0.0, 0.30, 0.70, 0.85), 1100, 2, 4),
    "faint_scan":                ((0.0, 0.40, 0.68, 0.82), 1500, 1, 3),
}
ROTATE = {"08040810102": 90}   # scans that reach the cache still on their side


def tile(code, box, width, caption):
    p = os.path.join(UPRIGHT, f"{code}.jpg")
    img = cv2.imread(p) if os.path.exists(p) else None
    if img is None:
        return None
    if code in ROTATE:
        img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
    h, w = img.shape[:2]
    x0, y0, x1, y1 = box
    im = img[int(h * y0):int(h * y1), int(w * x0):int(w * x1)]
    if im.size == 0:
        return None
    f = width / im.shape[1]
    im = cv2.resize(im, (width, max(1, int(round(im.shape[0] * f)))),
                    interpolation=cv2.INTER_CUBIC)
    bar = np.full((30, width, 3), 235, np.uint8)
    cv2.putText(bar, caption[:110], (8, 21), cv2.FONT_HERSHEY_SIMPLEX,
                0.55, (0, 0, 0), 1, cv2.LINE_AA)
    return np.vstack([bar, im,
                      np.full((6, width, 3), 120, np.uint8)])


def grid(tiles, per_row):
    rows = []
    for i in range(0, len(tiles), per_row):
        chunk = tiles[i:i + per_row]
        h = max(t.shape[0] for t in chunk)
        chunk = [cv2.copyMakeBorder(t, 0, h - t.shape[0], 0, 8,
                                    cv2.BORDER_CONSTANT, value=(255, 255, 255))
                 for t in chunk]
        rows.append(np.hstack(chunk))
    w = max(r.shape[1] for r in rows)
    rows = [r if r.shape[1] == w else
            cv2.copyMakeBorder(r, 0, 0, 0, w - r.shape[1],
                               cv2.BORDER_CONSTANT, value=(255, 255, 255))
            for r in rows]
    return np.vstack(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=".cache/remaining")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    rows = {r["bureau_code"]: r for r in csv.DictReader(open(RESULTS, encoding="utf-8"))}
    left = {c for c, r in rows.items() if r["votes_certified"] != "1"}
    reg = {}
    for l in open(REGISTER, encoding="utf-8"):
        d = json.loads(l)
        reg[d["bureau_code"]] = d
    read = {}
    for l in open(READINGS, encoding="utf-8"):
        d = json.loads(l)
        read[d["bureau_code"]] = d

    groups = {}
    for code in sorted(left):
        r = reg.get(code)
        reason = r["reason"] if r else "read_but_does_not_balance"
        groups.setdefault(reason, []).append(code)

    for reason, codes in groups.items():
        box, width, per_row, per_sheet = CROPS[reason]
        tiles = []
        for code in codes:
            d = read.get(code) or reg.get(code) or {}
            cand = [d.get(k) for k in ("zammel", "maghzaoui", "saied")]
            if all(c is not None for c in cand):
                tot = d.get("valid") if d.get("valid") is not None else d.get("q_declared")
                cap = (f"{code}  read {cand[0]}+{cand[1]}+{cand[2]}={sum(cand)}"
                       + (f"  form says {tot}" if tot is not None else ""))
            else:
                cap = f"{code}  {reason.replace('_', ' ')}"
            t = tile(code, box, width, cap)
            if t is not None:
                tiles.append(t)
        if not tiles:
            continue
        sheets = [tiles[i:i + per_sheet] for i in range(0, len(tiles), per_sheet)]
        for n, chunk in enumerate(sheets, 1):
            suffix = "" if len(sheets) == 1 else f"_{n}"
            dest = os.path.join(a.out, f"{reason}{suffix}.png")
            cv2.imwrite(dest, grid(chunk, per_row))
            print(dest, len(chunk), "stations")


if __name__ == "__main__":
    main()
