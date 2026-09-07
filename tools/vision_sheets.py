"""Lay out the unread forms as sheets a person (or a model) can read off.

The reader fails on the fields the form draws small. Candidate cells are 56x38
in reference coordinates and every other field is about 23x24, so on the 560px
scans ISIE published for much of Medenine the candidates land near 20px wide and
`valid` and `q_declared` near 8px. Measured against forms read by eye, the
candidates come back 61-78% correct and `valid` 1 time in 17. Since the votes
identity is `q == valid == the three candidates summed`, two illegible fields
veto a form however well its candidates are read.

Those forms are still legible to a reader who can magnify them, so this crops the
five fields that matter, scales them up, and puts the score each candidate got —
which the form also writes out in Arabic words — beside its digits, so every
number can be checked against a second rendering of itself.

Two deliberate choices. The reader's own guess is *not* printed on the sheet: an
annotator who sees it will drift toward it, and an earlier version of these
sheets had to be rebuilt for that reason. And the sheets carry no arithmetic
hints, because whether a form balances is evidence, not something to assume.

Usage: python3 tools/vision_sheets.py [--out DIR] [--per 6] [--governorate NAME]
"""
import argparse, csv, os, sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

RESULTS = "data/pv_presidential_2024.csv"
UPRIGHT = ".cache/pv_upright"
DONE = "data/verification/lowres_readings.jsonl"
CAND = ("zammel", "maghzaoui", "saied")
W_DIG, W_WRD, HT = 300, 640, 64
# valid and q_declared are drawn about 23x24 on the form against 56x38 for a
# candidate cell, so they need far more magnification to be read at all.
W_TOT, HT_TOT = 470, 108


def geometry():
    import pv_template as T
    return T.reference()


def _box(geo, name):
    c = geo[name]
    x0 = min(b[0] for b in c); x1 = max(b[0] + b[2] for b in c)
    y0 = min(b[1] for b in c); y1 = max(b[1] + b[3] for b in c)
    return (x0, y0, x1 - x0, y1 - y0)


def _words_box(geo, name):
    c = geo[name]
    xr = max(b[0] + b[2] for b in c); run = xr - min(b[0] for b in c)
    y0 = min(b[1] for b in c); y1 = max(b[1] + b[3] for b in c)
    return (xr + int(0.02 * run), y0, int(3.25 * run), y1 - y0)


def _grab(img, A, box, size, pad=2):
    x, y, w, h = box
    p = np.array([[x, y, 1], [x + w, y, 1], [x, y + h, 1], [x + w, y + h, 1]],
                 float) @ A.T
    x0, y0 = int(p[:, 0].min()) - pad, int(p[:, 1].min()) - pad
    x1, y1 = int(p[:, 0].max()) + pad, int(p[:, 1].max()) + pad
    H, W = img.shape[:2]
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(W, x1), min(H, y1)
    if x1 - x0 < 6 or y1 - y0 < 5:
        return None
    return cv2.resize(img[y0:y1, x0:x1], size, interpolation=cv2.INTER_CUBIC)


def _label(text, width, h=20):
    im = np.full((h, width, 3), 255, np.uint8)
    cv2.putText(im, text, (5, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (140, 0, 0), 1)
    return im


def card_from_cells(img, fields, code):
    """A card built from cells the grid detector found, with no template fit.

    The reader has always had two ways to locate fields — detect the printed
    rules, or register the page against the reference layout — and falls back
    from one to the other. This laid out only what registered, so 88 of the 137
    forms it called "could not be laid out" were forms whose grid the detector
    finds perfectly well. That was a hole in this tool, not a property of the
    scans.
    """
    def cut(name, size, pad=2):
        cells = fields.get(name)
        if not cells or len(cells) != 4:
            return None
        x0 = min(c[0] for c in cells) - pad
        x1 = max(c[0] + c[2] for c in cells) + pad
        y0 = min(c[1] for c in cells) - pad
        y1 = max(c[1] + c[3] for c in cells) + pad
        H, W = img.shape[:2]
        x0, y0, x1, y1 = max(0, x0), max(0, y0), min(W, x1), min(H, y1)
        if x1 - x0 < 6 or y1 - y0 < 5:
            return None
        return cv2.resize(img[y0:y1, x0:x1], size, interpolation=cv2.INTER_CUBIC)

    def words(name, size):
        cells = fields.get(name)
        if not cells or len(cells) != 4:
            return None
        xr = max(c[0] + c[2] for c in cells)
        run = xr - min(c[0] for c in cells)
        y0, y1 = min(c[1] for c in cells), max(c[1] + c[3] for c in cells)
        x0 = xr + max(1, int(0.02 * run))
        x1 = x0 + int(3.25 * run)
        H, W = img.shape[:2]
        x0, y0, x1, y1 = max(0, x0), max(0, y0), min(W, x1), min(H, y1)
        if x1 - x0 < 40 or y1 - y0 < 5:
            return None
        return cv2.resize(img[y0:y1, x0:x1], size, interpolation=cv2.INTER_CUBIC)

    lines = []
    for n in CAND:
        d, w = cut(n, (W_DIG, HT)), words(n, (W_WRD, HT))
        if d is None or w is None:
            return None
        lines.append(np.hstack([_label(n, W_DIG),
                                np.full((20, W_WRD, 3), 255, np.uint8)]))
        lines.append(np.hstack([d, w]))
    v, q = cut("valid", (W_TOT, HT_TOT), 3), cut("q_declared", (W_TOT, HT_TOT), 3)
    if v is None or q is None:
        return None
    rest = W_DIG + W_WRD - 2 * W_TOT
    lines.append(np.hstack([_label("valid (n)", W_TOT), _label("q_declared", W_TOT),
                            np.full((20, rest, 3), 255, np.uint8)]))
    lines.append(np.hstack([v, q, np.full((HT_TOT, rest, 3), 255, np.uint8)]))
    head = np.full((30, W_DIG + W_WRD, 3), 245, np.uint8)
    cv2.putText(head, code + "  [grid]", (6, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                (0, 0, 0), 2)
    return np.vstack([np.full((3, W_DIG + W_WRD, 3), 60, np.uint8), head] + lines)


def card(img, geo, A, code):
    lines = []
    for n in CAND:
        d = _grab(img, A, _box(geo, n), (W_DIG, HT))
        w = _grab(img, A, _words_box(geo, n), (W_WRD, HT))
        if d is None or w is None:
            return None
        lines.append(np.hstack([_label(n, W_DIG),
                                np.full((20, W_WRD, 3), 255, np.uint8)]))
        lines.append(np.hstack([d, w]))
    v = _grab(img, A, _box(geo, "valid"), (W_TOT, HT_TOT), pad=3)
    q = _grab(img, A, _box(geo, "q_declared"), (W_TOT, HT_TOT), pad=3)
    if v is None or q is None:
        return None
    rest = W_DIG + W_WRD - 2 * W_TOT
    lines.append(np.hstack([_label("valid (n)", W_TOT), _label("q_declared", W_TOT),
                            np.full((20, rest, 3), 255, np.uint8)]))
    lines.append(np.hstack([v, q, np.full((HT_TOT, rest, 3), 255, np.uint8)]))
    head = np.full((30, W_DIG + W_WRD, 3), 245, np.uint8)
    cv2.putText(head, code, (6, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)
    return np.vstack([np.full((3, W_DIG + W_WRD, 3), 60, np.uint8), head] + lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=".cache/vision_sheets")
    ap.add_argument("--per", type=int, default=6)
    ap.add_argument("--governorate")
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()

    import pv_template as T
    ref, geo = geometry()
    done = set()
    if os.path.exists(DONE):
        import json
        done = {json.loads(l)["bureau_code"] for l in open(DONE, encoding="utf-8")}

    rows = [r for r in csv.DictReader(open(RESULTS, encoding="utf-8"))
            if r["votes_certified"] != "1" and r["bureau_code"] not in done]
    if a.governorate:
        rows = [r for r in rows if r["governorate"] == a.governorate]
    rows.sort(key=lambda r: r["bureau_code"])
    if a.limit:
        rows = rows[:a.limit]
    os.makedirs(a.out, exist_ok=True)
    print(f"{len(rows)} bureaux still without certified votes", flush=True)

    cards, codes = [], []
    for r in rows:
        p = os.path.join(UPRIGHT, f"{r['bureau_code']}.jpg")
        img = cv2.imread(p) if os.path.exists(p) else None
        if img is None:
            continue
        # Some scans are laid down mirrored, which reverses the Arabic and
        # defeats registration. Flipping is one line and recovers the form, so
        # try both and keep whichever fits the reference layout better.
        best = (None, 0.0, img)
        for cand in (img, cv2.flip(img, 1)):
            for mode in ("red", "plain"):
                A, cc = T.align(cand, ref, mode)
                if A is not None and cc > best[1]:
                    best = (A, cc, cand)
        A, cc, img = best
        if A is not None and cc > 0.5:
            c = card(img, geo, A, r["bureau_code"])
        else:
            # Registration failed; fall back to the detected grid, as the
            # reader itself does.
            from decode_all import layouts
            c = None
            for fields in layouts(img):
                c = card_from_cells(img, fields, r["bureau_code"])
                if c is not None:
                    break
        if c is not None:
            cards.append(c); codes.append(r["bureau_code"])

    n = 0
    for i in range(0, len(cards), a.per):
        chunk = cards[i:i + a.per]
        cv2.imwrite(os.path.join(a.out, "sheet_%03d.png" % (i // a.per + 1)),
                    np.vstack(chunk))
        n += len(chunk)
    with open(os.path.join(a.out, "index.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["sheet", "position", "bureau_code"])
        for i, code in enumerate(codes):
            w.writerow(["sheet_%03d.png" % (i // a.per + 1), i % a.per + 1, code])
    print(f"{n} cards on {(len(cards)+a.per-1)//a.per} sheets -> {a.out}")
    print(f"{len(rows)-len(cards)} bureaux could not be laid out "
          f"(no image, or the form would not register)")


if __name__ == "__main__":
    main()
