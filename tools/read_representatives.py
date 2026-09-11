"""Read whether a candidate's representative signed each procès-verbal.

Why this field is not in the dataset already
--------------------------------------------
Every PV carries a block headed `أسماء وإمضاءات ممثلي المرشحين` -- names and
signatures of the candidates' representatives -- with three rows and columns
for the signature, the candidate and the representative's name. It sits *below*
every field the reader has ever touched: the mapped digit cells stop at y=874
of the template's 1168, and this block runs from y=942 to y=1077. So the whole
of it was outside the locator's field map and no column in
`data/pv_presidential_2024.csv` records it.

What this reads, and what it deliberately does not
--------------------------------------------------
**Presence only.** For each of the three rows it decides whether the row was
filled in, and publishes the count of filled rows per station. It does not read
*which* candidate the row names, or the representative's name: both are
handwritten Arabic and a separate problem.

It would be wrong to read the published field as "Saied's representative
signed". In the 45 forms hand-labelled here the candidate cell reads قيس سعيد
in nearly every filled row, but a 90-form strip contains زهير المغزاوي twice --
challengers do field representatives, and an early probe that reported none was
small-sample noise. The count is what is measured, so the count is what is
published.

How the block is located
------------------------
Reused rather than reinvented: `pv_template.align` already registers a scan
against the reference form by ECC on the printed layout, which is what two
scans of the same form share. The block's geometry below is measured from the
reference's own printed rules -- detected, not eyeballed -- and carried onto
each scan by that affine map.

How presence is decided, and the three features that failed first
-----------------------------------------------------------------
The discriminator is a *shape* measure, normalised for scan resolution:

    resample the cell to a fixed height, mask the pen ink, and take the
    fraction of pixel columns carrying at least K pen pixels; a row is filled
    when *both* its candidate cell and its name cell clear a cut.

Writing has vertical extent -- letter stems stack 8-20 pixels in a column --
while everything that fills these cells otherwise does not. Three simpler
features were tried and each was rejected on measurement, not on taste:

* **Mean ink fraction.** Grey scans measure 0.013-0.040 on *empty* background
  against 0.022-0.043 for filled cells. The two overlap outright.
* **Blueness.** Pens are blue or black; one filled cell measured 0.000.
* **Stroke coverage** (locally thresholded, rules opened out). Hand-labelling
  the decision band put filled cells at 0.011-0.020 and empty ones -- a single
  diagonal "none" stroke, an office stamp, scan noise -- at up to 0.021.

The column-thickness measure separates them because the empties are thin: a
strike-through drawn across a 35px row is nearly horizontal, so it contributes
one or two pixels per column wherever it passes, and a stamp is red.

Two details that measurement forced:

* **Cells must be resampled to a common height.** Without it the rule is
  resolution-dependent and silently fails on low-resolution scans: one
  hand-labelled positive presented a 17x188 cell where a clean scan gives
  36x392, and at half scale no column can hold 5 pen pixels. It scored exactly
  0.0000 -- a false negative produced by arithmetic, not by the image.
* **Speckle must go before the profile is taken.** Grey paper texture survives
  adaptive thresholding, and components too small to be a pen stroke were
  enough to lift empty cells into the filled range.

`K` and the cut were chosen on 66 hand-labelled cells (22 forms) by taking the
widest relative margin, then tested once on 66 held-out cells (22 further
forms) with no re-tuning. Both sets come out 66/66; see `--validate`.
"""

import argparse
import csv
import glob
import json
import os
import random
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pv_template as pt

SCANS = ".cache/pv_upright"
PV = "data/pv_presidential_2024.csv"
OUT = "data/representatives_2024.csv"
LOG = "data/verification/representatives.jsonl"

# Template coordinates (1600x1168), from the rules `--geometry` detects.
# The ladder inside the block has an even 35px pitch: 937 / 972 / 1007 / 1042 /
# 1077, and 1077 is the block's bottom border -- printed RED, so a grayscale
# threshold misses it and the first attempt read the ladder one band short. It
# put the three boxes on rows 2, 3 and a strip below the block entirely, which
# the `--overlay` render showed immediately. Four bands, so:
#   937-972   column headers (الإمضاء | المترشح | إسم ولقب ممثل المترشح)
#   972-1077  the three data rows
ROWS = [(972, 1007), (1007, 1042), (1042, 1077)]
COLS = {"signature": (605, 795), "candidate": (795, 1173),
        "rep_name": (1173, 1565)}
INSET = 4          # px, to keep the printed rules out of the measurement

# The block's five printed rules, and the window the ladder is searched in.
# Spacing is 30/35/35/35 -- deliberately non-uniform, which is what stops the
# comb sliding onto a neighbouring band. Two things were measured into these:
# the search window must be narrower than half the smallest spacing (at +-22
# and +-30 the comb locked onto other rules at a perfect score, flipping forms
# that were already right), and the strip must cover only the representatives
# block, because the bureau-members table to its left carries rules of its own.
LADDER = [942, 972, 1007, 1042, 1077]
SHIFT_SPAN = 16
LADDER_Y = (900, 1130)

CELL_H = 32        # every cell is measured at this height, so the rule is
                   # scale-free; see the docstring on the 17px false negative
MIN_AREA = 8       # px, the smallest component that can be a pen stroke
COL_INK = 7        # pen pixels in a column for it to count as "thick"
CUT = 0.0101       # fraction of thick columns for a cell to read as written
MIN_CC = 0.30      # ECC correlation below which a scan is not placed

# The two hand-labelled sets. `TUNING` chose COL_INK and CUT; `HELD_OUT` was
# labelled from a separate random sample and scored once, without re-tuning.
# Values are the 1-based rows found to contain writing, read off the contact
# sheets `--sheet` renders: `--sheet 24 --seed 7` and `--sheet 24 --seed 23`
# regenerate exactly the two sheets these were read from. Each drew 24 forms
# and each set holds 22, because a sheet only shows the blocks that place:
# 03020510105 and (for the held-out sheet) 01110210103 and 04030410204 did
# not, and 02100710107 placed on the printed header rather than the data rows
# -- a real registration failure, excluded rather than labelled, and the
# reason `--overlay` exists.
TUNING = {
    "14010310302": {1}, "06070410101": {1}, "18051110102": {1},
    "02010110204": set(), "22130310203": set(), "03040710201": set(),
    "15120510202": {1}, "02040310105": set(), "21130110202": {1},
    "09041010201": {1, 2}, "01160710101": {1}, "19090910201": {1},
    "19020210102": {1}, "02100210101": {1}, "10090220104": set(),
    "03040110201": set(), "23050710402": set(), "19040410101": {1},
    "02040410305": {1}, "24010310101": set(), "05030110201": set(),
    "09091610101": {1, 2},
}
HELD_OUT = {
    "12090210303": {1}, "03020110202": {1}, "01080410301": {1},
    "13070410101": {1}, "19040310101": {1}, "17030410301": {1},
    "22090310301": {1}, "15060110102": set(), "05050110301": set(),
    "08080510405": set(), "11030110401": {1}, "20030710402": set(),
    "01070510101": {1}, "09090310101": {1}, "20080510201": {1},
    "03020510102": set(), "21110110201": {1}, "19030310301": {1},
    "01090910103": set(), "21150410101": {1, 2, 3}, "19070810203": set(),
    "15070210101": set(),
}


def scan_paths():
    """The cached upright scans, sidecar JSON excluded."""
    return sorted(f for f in glob.glob(f"{SCANS}/*")
                  if f.lower().endswith((".jpg", ".png", ".jpeg")))


def joinable_codes():
    """The bureau codes the published PV dataset actually carries.

    The scan cache is keyed by whatever the PV index named each file, and that
    is not always a bureau code: `download_all_pvs.py` writes `nocode` where
    the index row has an empty one. Nor is a code a fixed width -- the
    published file runs 8 to 12 characters, 11 for 9,129 of 9,448 -- so a
    length test is the wrong filter and membership is the right one. A scan
    that cannot join to a result cannot be analysed, so it is excluded here
    and logged rather than published with nothing to join to.
    """
    with open(PV, encoding="utf-8") as fh:
        return {r["bureau_code"] for r in csv.DictReader(fh)}


def scan_for(code):
    hits = [f for f in glob.glob(f"{SCANS}/{code}.*")
            if f.lower().endswith((".jpg", ".png", ".jpeg"))]
    return hits[0] if hits else None


def pen_mask(bgr):
    """Binary handwriting mask for one cell, at CELL_H.

    Red-dominant pixels go first: the table is printed red and on some forms a
    round office stamp overlaps the block -- calibration caught one scoring
    above several genuinely written cells. Then the cell's own printed rules
    are opened out, and finally speckle smaller than a pen stroke.
    """
    if bgr.shape[0] != CELL_H:
        w = max(8, round(bgr.shape[1] * CELL_H / bgr.shape[0]))
        bgr = cv2.resize(bgr, (w, CELL_H),
                         interpolation=cv2.INTER_AREA if bgr.shape[0] > CELL_H
                         else cv2.INTER_CUBIC)
    b, g, r = [c.astype(np.int16) for c in cv2.split(bgr)]
    red = (r - np.maximum(g, b)) > 18
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    bw = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                               cv2.THRESH_BINARY_INV, 15, 9)
    bw[red] = 0
    for kern in ((1, 31), (15, 1)):
        bw = cv2.subtract(bw, cv2.morphologyEx(
            bw, cv2.MORPH_OPEN, np.ones(kern, np.uint8)))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(bw, connectivity=8)
    keep = np.zeros(n, bool)
    keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= MIN_AREA
    return np.where(keep[lab], 255, 0).astype(np.uint8)


def thick_fraction(bgr):
    """Fraction of pixel columns carrying at least COL_INK pen pixels."""
    m = pen_mask(bgr)
    colsum = (m > 0).sum(axis=0)
    return float((colsum >= COL_INK).sum()) / len(colsum)


def cell(img, A, box):
    """The image under a template-coordinate box, placed by `A`, or None."""
    x0, y0, x1, y1 = box
    pts = np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], dtype=np.float64)
    w = (A[:, :2] @ pts.T).T + A[:, 2]
    px0, py0 = int(w[:, 0].min()), int(w[:, 1].min())
    px1, py1 = int(w[:, 0].max()), int(w[:, 1].max())
    if px0 < 0 or py0 < 0 or px1 > img.shape[1] or py1 > img.shape[0]:
        return None
    crop = img[py0:py1, px0:px1]
    if crop.shape[0] < 6 or crop.shape[1] < 12:
        return None
    return crop


def place(img, ref):
    """The best affine placing template coordinates on `img`, and its cc."""
    best = None
    for mode in pt.SIGNALS:
        A, cc = pt.align(img, ref, mode)
        if A is not None and (best is None or cc > best[1]):
            best = (A, cc)
    if best is None or best[1] < MIN_CC:
        return None, 0.0 if best is None else best[1]
    return best


def ladder_shift(img, A):
    """Vertical correction in template px from the block's own rules, or None.

    A whole-page affine gets the block roughly right and not exactly: measured
    over 296 scans, only 15% land with no vertical error at all, 94% within
    4px and the tail reaches 16px -- half a row, enough to put row 1 on the
    printed header and read the header as handwriting. So the placement is
    refined against the ladder the block prints itself.

    None means no interior optimum was found (the best shift sits on the edge
    of the search window), which is how a form whose layout differs from the
    template is rejected rather than measured in the wrong place. `cc` does
    not catch those: the one that prompted this registered at 0.87.
    """
    inv = cv2.invertAffineTransform(A.astype(np.float32))
    flat = cv2.warpAffine(img, inv, (pt.CANON_W, 1200),
                          borderValue=(255, 255, 255))
    y0, y1 = LADDER_Y
    strip = flat[y0:y1, COLS["candidate"][0]:COLS["rep_name"][1]]
    if strip.size == 0:
        return None
    b, g, r = [c.astype(np.int16) for c in cv2.split(strip)]
    gray = cv2.cvtColor(strip, cv2.COLOR_BGR2GRAY)
    # a printed rule is a dark or red row spanning the strip; writing is not
    prof = ((gray < 200) | ((r - np.maximum(g, b)) > 18)
            ).astype(np.float32).mean(axis=1)
    score = []
    for d in range(-SHIFT_SPAN, SHIFT_SPAN + 1):
        idx = [y - y0 + d for y in LADDER]
        if min(idx) < 1 or max(idx) >= len(prof) - 1:
            score.append(-1.0)
        else:
            # the local max over +-1px, so a one-pixel wobble is not a penalty
            score.append(float(np.mean([prof[i - 1:i + 2].max() for i in idx])))
    d = int(np.argmax(score)) - SHIFT_SPAN
    return None if abs(d) >= SHIFT_SPAN else d


def row_scores(img, A, shift=0):
    """Per row, the score of each of the two written columns, or None."""
    out = []
    for ry0, ry1 in [(a + shift, b + shift) for a, b in ROWS]:
        vals = []
        for col in ("candidate", "rep_name"):
            cx0, cx1 = COLS[col]
            c = cell(img, A, (cx0 + INSET, ry0 + INSET,
                              cx1 - INSET, ry1 - INSET))
            if c is None:
                vals = None
                break
            vals.append(thick_fraction(c))
        out.append(vals)
    return out


def read_form(path, ref):
    """Presence per row for one scan, or a string naming why it was not read."""
    img = cv2.imread(path)
    if img is None:
        return "unreadable"
    A, cc = place(img, ref)
    if A is None:
        return "unregistered"
    shift = ladder_shift(img, A)
    if shift is None:
        return "no_ladder"
    rec = {"cc": round(cc, 4), "shift": shift, "rows": []}
    for vals in row_scores(img, A, shift):
        if vals is None:
            rec["rows"].append(None)
        else:
            rec["rows"].append({
                "candidate": round(vals[0], 5),
                "rep_name": round(vals[1], 5),
                "present": int(min(vals) >= CUT),
            })
    return rec


def overlay(code, ref, out_png):
    """Draw the placed block on one scan, so the geometry can be checked."""
    path = scan_for(code)
    img = cv2.imread(path) if path else None
    if img is None:
        return False
    A, cc = place(img, ref)
    if A is None:
        return False
    shift = ladder_shift(img, A)
    vis = img.copy()
    colours = {"signature": (0, 160, 0), "candidate": (255, 0, 0),
               "rep_name": (0, 140, 255)}
    for ry0, ry1 in [(a + (shift or 0), b + (shift or 0)) for a, b in ROWS]:
        for cname, (cx0, cx1) in COLS.items():
            pts = np.array([[cx0, ry0], [cx1, ry0], [cx1, ry1], [cx0, ry1]],
                           dtype=np.float64)
            w = (A[:, :2] @ pts.T).T + A[:, 2]
            cv2.polylines(vis, [w.astype(np.int32)], True, colours[cname], 2)
    cv2.putText(vis, f"{code}  cc={cc:.3f}  shift="
                + ("rejected" if shift is None else f"{shift:+d}"), (10, 26),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
    cv2.imwrite(out_png, vis)
    return True


def sheet(ref, n, seed, out_png):
    """Contact sheet of the whole block, one tile per form, for hand-labelling.

    The tile is the candidate and name columns across all three rows, drawn
    large enough to read the writing -- which is what makes a label a label
    rather than a guess about a 35px strip.
    """
    bx0, bx1 = COLS["candidate"][0], COLS["rep_name"][1]
    by0, by1 = ROWS[0][0], ROWS[-1][1]
    random.seed(seed)
    tiles = []
    for path in random.sample(scan_paths(), n):
        img = cv2.imread(path)
        if img is None:
            continue
        A, _ = place(img, ref)
        if A is None:
            continue
        shift = ladder_shift(img, A)
        if shift is None:
            continue
        crop = cell(img, A, (bx0, by0 + shift, bx1, by1 + shift))
        if crop is None:
            continue
        tiles.append((os.path.basename(path).rsplit(".", 1)[0], crop))
    tw, lbl = 760, 40
    rs = [(c, cv2.resize(t, (tw, max(12, round(tw * t.shape[0] / t.shape[1])))))
          for c, t in tiles]
    canvas = np.full((sum(t.shape[0] + 26 for _, t in rs), tw + lbl, 3),
                     255, np.uint8)
    y = 0
    for code, t in rs:
        cv2.putText(canvas, code, (4, y + 16), cv2.FONT_HERSHEY_SIMPLEX,
                    0.5, (0, 0, 180), 1)
        canvas[y + 22:y + 22 + t.shape[0], lbl:lbl + tw] = t
        y += t.shape[0] + 26
    cv2.imwrite(out_png, canvas)
    return len(rs)


FIG_STEM = "docs/figures/pv_representatives_block"


def figure(ref, out_stem=FIG_STEM):
    """Annotate the block on real forms: where it is, and what the cut sees.

    The repo documents every field it reads against a real form, and this
    block has never been drawn: it lies outside the locator's field map, which
    is the whole reason no column recorded it. Three panels -- the block in
    place on a page, a written row, an empty row -- with the measured score
    under each, so a reader can see what the number is responding to.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    def block(code, row=None):
        path = scan_for(code)
        img = cv2.imread(path) if path else None
        if img is None:
            return None, None, None
        A, cc = place(img, ref)
        if A is None:
            return None, None, None
        d = ladder_shift(img, A)
        if d is None:
            return None, None, None
        if row is None:
            crop = cell(img, A, (COLS["signature"][0] - 12, ROWS[0][0] + d - 42,
                                 COLS["rep_name"][1] + 12, ROWS[-1][1] + d + 12))
            return crop, cc, None
        ry0, ry1 = ROWS[row - 1]
        vals = row_scores(img, A, d)[row - 1]
        crop = cell(img, A, (COLS["candidate"][0], ry0 + d,
                             COLS["rep_name"][1], ry1 + d))
        return crop, cc, (None if vals is None else min(vals))

    # a form with a written first row, and one with the block left blank
    panels = [("21150410101", None, "the block in place, all three rows written"),
              ("21150410101", 1, "written"),
              ("02010110204", 1, "empty")]
    drawn = [(block(c, r), f"bureau {c} - {lab}") for c, r, lab in panels]

    # Panel heights come from the crops' own aspect ratios. These strips are
    # very wide and short, so equal-height axes would leave most of the figure
    # blank -- the first attempt did exactly that.
    WIDTH = 7.4
    PANEL_W = WIDTH - 0.9
    heights = [PANEL_W * (c.shape[0] / c.shape[1]) if c is not None else 0.5
               for (c, _, _), _ in drawn]
    TOP, BOT, GAP = 0.55, 1.05, 0.34
    total = sum(heights) + TOP + BOT + GAP * (len(heights) - 1)
    fig = plt.figure(figsize=(WIDTH, total))
    y = 1.0 - TOP / total
    for (crop, cc, score), label in drawn:
        h = (PANEL_W * (crop.shape[0] / crop.shape[1]) if crop is not None
             else 0.5) / total
        ax = fig.add_axes([0.5 / WIDTH, y - h, PANEL_W / WIDTH, h])
        ax.axis("off")
        if crop is None:
            ax.text(0.5, 0.5, "did not place", ha="center", va="center")
        else:
            ax.imshow(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB), aspect="auto")
        note = label
        if score is not None:
            note += (f";  score {score:.4f}  "
                     f"{'>= the cut' if score >= CUT else '< the cut'} {CUT}")
        ax.set_title(note, fontsize=8.5, loc="left", pad=3.5)
        y -= h + GAP / total
    fig.suptitle("The candidate-representatives block, and what the presence "
                 "cut responds to", fontsize=10.5, y=1 - 0.14 / total)
    fig.text(0.5, 0.30 / total,
             "Read by tools/read_representatives.py. The block sits at "
             "template y=942-1077, below every cell in the locator's field "
             "map\n(which stops at y=874), which is why no column in "
             "data/pv_presidential_2024.csv records it. Presence only: the "
             "field does not\nread which candidate a row names. The score is "
             "the smaller of the two cells' thick-column fractions.",
             ha="center", va="bottom", fontsize=7.2, color="#333333")
    os.makedirs(os.path.dirname(out_stem), exist_ok=True)
    written = []
    for ext in ("png", "pdf"):
        f = f"{out_stem}.{ext}"
        fig.savefig(f, dpi=200 if ext == "png" else None)
        written.append(f)
    plt.close(fig)
    return written


def validate(ref):
    """Score the rule against both hand-labelled sets and report."""
    ok = True
    for name, labels in (("tuning", TUNING), ("held-out", HELD_OUT)):
        tp = fp = fn = tn = 0
        pos, neg, errs = [], [], []
        for code, filled in labels.items():
            path = scan_for(code)
            img = cv2.imread(path) if path else None
            if img is None:
                print(f"  {name}: {code} not cached")
                continue
            A, cc = place(img, ref)
            if A is None:
                print(f"  {name}: {code} would not register (cc {cc:.2f})")
                continue
            shift = ladder_shift(img, A)
            if shift is None:
                print(f"  {name}: {code} placed but its ladder was rejected")
                continue
            for i, vals in enumerate(row_scores(img, A, shift), start=1):
                if vals is None:
                    continue
                s = min(vals)
                y = 1 if i in filled else 0
                (pos if y else neg).append(s)
                p = 1 if s >= CUT else 0
                if y and p:
                    tp += 1
                elif y:
                    fn += 1
                    errs.append(("FN", code, i, s))
                elif p:
                    fp += 1
                    errs.append(("FP", code, i, s))
                else:
                    tn += 1
        n = tp + fp + fn + tn
        print(f"  {name}: {n} cells, {tp + fn} written | "
              f"TP {tp} FP {fp} FN {fn} TN {tn} | accuracy {(tp + tn) / n:.4f}")
        if pos and neg:
            lo, hi = min(pos), max(neg)
            gap = f"{lo / hi:.2f}x" if hi > 0 else "no empty cell scored above 0"
            print(f"    written min {lo:.4f}  empty max {hi:.4f}  margin {gap}")
        for tag, code, i, s in errs:
            print(f"    {tag} {code} row{i} {s:.4f}")
            ok = False
    return ok


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--geometry", action="store_true",
                    help="re-detect the block's rules on the reference and exit")
    ap.add_argument("--overlay", metavar="CODE",
                    help="draw the placed block on one scan")
    ap.add_argument("--sheet", type=int, metavar="N",
                    help="render N whole blocks large enough to hand-label")
    ap.add_argument("--figure", action="store_true",
                    help=f"write {FIG_STEM}.{{png,pdf}} for the docs")
    ap.add_argument("--validate", action="store_true",
                    help="score the rule against both hand-labelled sets")
    ap.add_argument("--sample", type=int,
                    help="measure this many random scans and print the spread")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--write", action="store_true",
                    help="measure every scan and write the dataset")
    args = ap.parse_args()

    if args.geometry:
        img = cv2.imread(pt.REF_IMG)
        H, W = img.shape[:2]
        g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        bw = cv2.adaptiveThreshold(g, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                   cv2.THRESH_BINARY_INV, 25, 12)
        roi = bw[920:H, 580:W]
        rh, rw = roi.shape
        # The red borders have to be included or the ladder comes out one band
        # short: see the note on ROWS.
        b_, g_, r_ = cv2.split(img[920:H, 580:W].astype(np.int16))
        red = ((r_ - np.maximum(g_, b_)) > 30).astype(np.uint8) * 255
        roi = cv2.bitwise_or(roi, red)
        for name, kern, axis, off, span in (
                ("horizontal y", (150, 1), 1, 920, rw),
                ("vertical   x", (1, 40), 0, 580, rh)):
            m = cv2.morphologyEx(roi, cv2.MORPH_OPEN,
                                 cv2.getStructuringElement(cv2.MORPH_RECT, kern))
            proj = m.sum(axis=axis) / 255
            on = proj > span * 0.45
            hits, s = [], None
            for i, v in enumerate(on):
                if v and s is None:
                    s = i
                elif not v and s is not None:
                    hits.append((s + i - 1) // 2 + off)
                    s = None
            if s is not None:
                hits.append((s + len(on) - 1) // 2 + off)
            print(f"  {name}: {hits}")
        print(f"  in use: rows={ROWS} cols={COLS}")
        return 0

    ref, _ = pt.reference()
    if ref is None:
        sys.exit("no reference; run tools/pv_template.py first")

    if args.overlay:
        out = f".cache/reps_overlay_{args.overlay}.png"
        ok = overlay(args.overlay, ref, out)
        print(f"  {'wrote ' + out if ok else 'could not place ' + args.overlay}")
        return 0 if ok else 1

    if args.sheet:
        out = f".cache/reps_sheet_{args.seed}.png"
        n = sheet(ref, args.sheet, args.seed, out)
        print(f"  wrote {out}: {n} blocks")
        return 0

    if args.figure:
        for f in figure(ref):
            print(f"  wrote {f} ({os.path.getsize(f) / 1024:.0f} KB)")
        return 0

    if args.validate:
        print(f"rule: min over the candidate and name cells of the fraction of "
              f"columns\n      with >= {COL_INK} pen pixels at height "
              f"{CELL_H}, cut at {CUT}")
        return 0 if validate(ref) else 1

    scans = scan_paths()
    known = joinable_codes()
    unjoinable = [p for p in scans
                  if os.path.basename(p).rsplit(".", 1)[0] not in known]
    scans = [p for p in scans if p not in set(unjoinable)]
    if unjoinable:
        print(f"  {len(unjoinable)} scan(s) excluded: no bureau code in {PV}"
              f" ({', '.join(os.path.basename(p) for p in unjoinable[:4])})")
    if args.sample:
        random.seed(args.seed)
        scans = random.sample(scans, min(args.sample, len(scans)))

    rows, failed, partial = [], [], 0
    for i, path in enumerate(scans, start=1):
        code = os.path.basename(path).rsplit(".", 1)[0]
        rec = read_form(path, ref)
        if isinstance(rec, str):
            failed.append((code, rec))
            continue
        if any(r is None for r in rec["rows"]):
            partial += 1
        rows.append((code, rec))
        if args.write and i % 500 == 0:
            print(f"    {i}/{len(scans)}")

    counts = [sum(r["present"] for r in rec["rows"] if r) for _, rec in rows]
    n = len(rows)
    why = {}
    for _, reason in failed:
        why[reason] = why.get(reason, 0) + 1
    print(f"{n} scans read of {len(scans)}, {len(failed)} not read"
          + (" (" + ", ".join(f"{k} {v}" for k, v in sorted(why.items())) + ")"
             if why else "")
          + f", {partial} with a row off the page")
    shifts = [rec["shift"] for _, rec in rows]
    if shifts:
        import statistics
        print(f"  ladder shift: |d|<=2 on "
              f"{100.0 * sum(1 for d in shifts if abs(d) <= 2) / len(shifts):.1f}%"
              f", |d|<=4 on "
              f"{100.0 * sum(1 for d in shifts if abs(d) <= 4) / len(shifts):.1f}%"
              f", median {statistics.median(shifts):+.0f}"
              f", max |d| {max(abs(d) for d in shifts)}")
    if n:
        for k in range(4):
            c = counts.count(k)
            print(f"  {k} representative row(s) filled: {c:5d}  "
                  f"({100.0 * c / n:5.2f}%)")
        print(f"  any: {sum(1 for c in counts if c):5d}  "
              f"({100.0 * sum(1 for c in counts if c) / n:5.2f}%)")
    if not args.write:
        return 0

    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["bureau_code", "reps_rows_filled", "rep_row1", "rep_row2",
                    "rep_row3", "row1_score", "row2_score", "row3_score",
                    "register_cc", "row_shift"])
        for code, rec in rows:
            rs = rec["rows"]
            w.writerow([code,
                        sum(r["present"] for r in rs if r),
                        *["" if r is None else r["present"] for r in rs],
                        *["" if r is None else f"{min(r['candidate'], r['rep_name']):.5f}"
                          for r in rs],
                        f"{rec['cc']:.4f}", rec["shift"]])
    with open(LOG, "w", encoding="utf-8") as fh:
        json.dump({"record": "method", "rule": "min over the candidate and "
                   "name cells of the fraction of pixel columns carrying at "
                   f"least {COL_INK} pen pixels, at cell height {CELL_H}",
                   "cut": CUT, "min_cc": MIN_CC, "rows": ROWS, "cols": COLS,
                   "tuning_cells": 3 * len(TUNING),
                   "held_out_cells": 3 * len(HELD_OUT)}, fh)
        fh.write("\n")
        for path in unjoinable:
            json.dump({"record": "excluded",
                       "file": os.path.basename(path),
                       "why": f"its name is not a bureau_code in {PV}"}, fh)
            fh.write("\n")
        json.dump({"record": "coverage", "scans": len(scans), "placed": n,
                   "excluded_unjoinable": len(unjoinable),
                   "unplaced": len(failed), "unplaced_reasons": why,
                   "partial_rows": partial,
                   "filled_row_counts": {str(k): counts.count(k)
                                         for k in range(4)}}, fh)
        fh.write("\n")
        for code, reason in failed:
            json.dump({"record": "unplaced", "bureau_code": code,
                       "reason": reason}, fh)
            fh.write("\n")
    print(f"wrote {OUT} ({n} rows) and {LOG}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
