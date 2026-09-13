"""Locate the candidate-representatives block on an upright PV form.

The counting record's bottom band carries two tables side by side. The left one
is the polling staff (`أسماء وإمضاءات أعضاء مكتب الاقتراع`); the right one, which
is the one this project had never read, is

    أسماء وإمضاءات ممثلي المترشحين
    (names and signatures of the candidates' representatives)

three rows of `إسم ولقب ممثل المترشح` | `المترشح` | `الإمضاء` — the representative's
name, the candidate they act for, and their signature. Where a candidate sent an
agent to a polling station, that is where the form records it.

Localisation does not reuse the digit-grid registration. That machinery anchors
on the four-cell number boxes, which the bottom band has none of, and it is built
to hit a 20px cell; this block is two orders of magnitude larger in area and can
be found from the printed rules directly.

The form's printed structure is red, so a red-minus-grey signal isolates the
layout from the handwriting and the seal ink. Where a scan is greyscale, or the
red plate is too weak to threshold, the same rules are taken from a dark-ink
mask instead — worse, because handwriting joins the mask, but the rules being
sought are the longest lines on the page and survive it.

Two long horizontal rules bracket the three-stage block at 0.277 and 0.609 of
form height. They are the heaviest lines on the form and the most reliably
found, so everything else is placed as a ratio of the distance between them,
which makes the placement independent of how much of the page the form occupies:

    band top    = A + 1.568 * (B - A)
    band bottom = A + 1.994 * (B - A)

Where the band's own rules are detected they are preferred, and the extrapolation
is only the fallback. A form whose band bottom falls past the page edge is
reported short rather than cropped to the edge, because a crop that silently
loses the third row would read as a station where fewer representatives attended.
"""
import cv2
import numpy as np

# The form's six full-width rules, as ratios of the span between the two that
# bracket the three-stage block. Measured on clean scans, and stable to a
# thousandth across them: masthead, stage top (A), stage bottom (B), the
# results-table foot, the bottom band's top, and the bottom band's foot.
RULE_RATIOS = (-0.500, 0.0, 1.0, 1.438, 1.568, 1.993)
BAND_TOP_R, BAND_BOT_R = 1.568, 1.993
SPAN_MIN = 0.12              # the stage block is never less of the page than this
FIT_TOL = 0.018              # how near a rule must fall to claim a template line

# The representatives table within the frame, x as a fraction of frame width.
REPS_X0 = 0.376
COL_SPLITS = (0.4995, 0.7623)   # signature | candidate | name
# Rows as fractions of band height: title, column headers, then three data rows.
ROW_EDGES = (0.38, 0.586, 0.792, 1.0)

RED_MIN_FRAC = 0.004         # below this the red plate is not usable

# (red threshold, rule length as a fraction of width). A quarter of the corpus
# was published at 560-870px with a washed-out red plate, where the first setting
# finds no rule at all; the ladder drops the threshold before it shortens the
# kernel, because a shorter kernel starts admitting handwriting as a rule.
LADDER = [(40, 0.30), (25, 0.30), (25, 0.20), (15, 0.20)]


def rule_masks(img, red_th=40, frac=0.30):
    """(horizontal mask, vertical mask, source) for the form's printed rules."""
    h, w = img.shape[:2]
    b, g, r = cv2.split(img.astype(np.int16))
    red = np.clip(r - np.maximum(b, g), 0, 255).astype(np.uint8)
    if (red > red_th).mean() >= RED_MIN_FRAC:
        _, m = cv2.threshold(red, red_th, 255, cv2.THRESH_BINARY)
        src = "red"
    else:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        m = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                  cv2.THRESH_BINARY_INV, 25, 10)
        src = "gray"
    hz = cv2.morphologyEx(m, cv2.MORPH_OPEN,
                          cv2.getStructuringElement(cv2.MORPH_RECT,
                                                    (max(20, int(w * frac)), 1)))
    vt = cv2.morphologyEx(m, cv2.MORPH_OPEN,
                          cv2.getStructuringElement(cv2.MORPH_RECT,
                                                    (1, max(15, int(h * 0.20)))))
    return hz, vt, src


def _centres(mask, axis):
    """Rules as (centre, weight): weight is the longest line the run carries.

    Weight is what separates a printed rule from a stray band of ink at a lower
    threshold. The form's structural rules run most of the page; nothing a clerk
    writes does, so ranking on length picks the layout out of a noisy mask
    without needing a threshold that only the clean scans satisfy.
    """
    lens = mask.sum(axis=axis) / 255.0
    prof = lens > 0
    out, start = [], None
    for i, v in enumerate(prof):
        if v and start is None:
            start = i
        elif not v and start is not None:
            out.append(((start + i - 1) // 2, float(lens[start:i].max())))
            start = None
    if start is not None:
        out.append(((start + len(prof) - 1) // 2, float(lens[start:].max())))
    return out


def fit_rules(ys, h):
    """Fit the six-rule pattern to what was detected: (A, B, hits) or None.

    Picking the stage rules out of a positional window is what fails on a form
    that does not fill its page — the results-table foot drifts into the window
    and, being the longer line, wins. The rules are not independent: their
    spacing is fixed by the template, so every pair of detected rules proposes a
    scale, and the right pair is the one under which the *other* rules land on
    template lines. That is a constraint the individual rule cannot supply, and
    it needs no assumption about where on the page the form sits.
    """
    best = None
    for i, (a, _) in enumerate(ys):
        for j, (b, _) in enumerate(ys):
            span = b - a
            if span < SPAN_MIN * h:
                continue
            hits, score = 0, 0.0
            for ratio in RULE_RATIOS:
                want = a + ratio * span
                near = [(abs(y - want), wt) for y, wt in ys
                        if abs(y - want) <= FIT_TOL * h]
                if near:
                    hits += 1
                    score += min(near)[1]
            if hits >= 4 and (best is None or (hits, score) > (best[2], best[3])):
                best = (a, b, hits, score)
    return best[:3] if best else None


def locate(img):
    """Where the representatives table sits, or None with a reason.

    Returns a dict with the table box, its three column boundaries and its three
    data-row boundaries, all in pixel coordinates of `img`.
    """
    h, w = img.shape[:2]
    fit = None
    for red_th, frac in LADDER:
        hz, vt, src = rule_masks(img, red_th, frac)
        ys, xs = _centres(hz, 1), _centres(vt, 0)
        fit = fit_rules(ys, h)
        if fit:
            break
    if not fit:
        return None, "rule pattern did not fit"
    a, b, hits = fit

    span = b - a
    top_hat, bot_hat = a + BAND_TOP_R * span, a + BAND_BOT_R * span
    near = [y for y, _ in ys if abs(y - top_hat) <= FIT_TOL * h]
    top = min(near, key=lambda y: abs(y - top_hat)) if near else top_hat
    near_bot = [y for y, _ in ys if abs(y - bot_hat) <= FIT_TOL * h]
    bot = min(near_bot, key=lambda y: abs(y - bot_hat)) if near_bot else bot_hat
    if bot > h - 1 or top < 0:
        return None, "band runs past the page edge"

    # The frame's left and right edges: the outermost full-height verticals.
    xs = [x for x, _ in xs]
    if len(xs) >= 2 and (xs[-1] - xs[0]) >= 0.80 * w:
        fx0, fx1 = xs[0], xs[-1]
    else:
        fx0, fx1 = 0, w - 1
    fw = fx1 - fx0

    box = (int(round(fx0 + REPS_X0 * fw)), int(round(top)),
           int(round(fx1)), int(round(bot)))
    cols = [int(round(fx0 + c * fw)) for c in COL_SPLITS]
    band_h = bot - top
    rows = [int(round(top + e * band_h)) for e in ROW_EDGES]
    loc = {"box": box, "cols": cols, "rows": rows, "source": src,
           "band": (int(round(top)), int(round(bot))), "rules_hit": hits,
           "frame": (int(fx0), int(fx1)), "detected_top": bool(near),
           "detected_bot": bool(near_bot), "span_px": int(round(span))}
    return refine(img, loc, red_th, frac)


# The table's own rules, as fractions of its width and of the band height. The
# page's structure is printed red, but the bottom band's interior is ruled in
# grey, so these are found on a dark-ink mask rather than the red plate.
BAND_V_EXPECT = (0.0, 0.200, 0.600, 1.0)   # edge | signature | candidate | name
BAND_H_EXPECT = (0.0, 0.17, 0.365, 0.58, 0.79, 1.0)
V_TOL, H_TOL = 0.06, 0.055
PAD_R = 0.25                                # slack around the estimated band


def _dark(img):
    return cv2.adaptiveThreshold(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), 255,
                                 cv2.ADAPTIVE_THRESH_MEAN_C,
                                 cv2.THRESH_BINARY_INV, 15, 8)


def _snap(found, expect, lo, hi, tol, extent):
    """Place `expect` between lo and hi, moved onto detected rules where near.

    Returns the placed positions and a per-position flag saying which of them a
    rule was actually found for, since which ones matter differs by axis.
    """
    out, hit = [], []
    for e in expect:
        want = lo + e * (hi - lo)
        near = [v for v in found if abs(v - want) <= tol * extent]
        out.append(min(near, key=lambda v: abs(v - want)) if near else want)
        hit.append(bool(near))
    return out, hit


def refine(img, loc, red_th, frac):
    """Snap the table to its own printed rules, and reject a block that has none.

    The six-rule fit places the band from the *page's* structure, and it can be
    wrong in two ways that matter. It can land a few percent out, which walks a
    row boundary through the middle of a handwritten name; and on a form where
    too few page rules survived it can settle on the wrong pair entirely and
    return a box somewhere in the turnout block. Both are caught by the same
    test: the representatives table carries column rules at 0.20 and 0.60 of its
    width and row rules at fixed fractions of the band, and no other part of the
    form is ruled that way. Where they are found the placement is corrected onto
    them; where the column rules are not found at all the box is refused, which
    is the check the page-level fit cannot make for itself.
    """
    x0, y0, x1, y1 = loc["box"]
    bh = y1 - y0
    py0, py1 = max(0, int(y0 - PAD_R * bh)), min(img.shape[0], int(y1 + PAD_R * bh))
    slack = int(0.05 * (x1 - x0))
    px0, px1 = max(0, x0 - slack), min(img.shape[1], x1 + slack)
    band = img[py0:py1, px0:px1]
    if band.shape[0] < 20 or band.shape[1] < 80:
        return None, "band too small to refine"
    BH, BW = band.shape[:2]
    m = _dark(band)
    vt = cv2.morphologyEx(m, cv2.MORPH_OPEN, cv2.getStructuringElement(
        cv2.MORPH_RECT, (1, max(6, int(BH * 0.25)))))
    hz = cv2.morphologyEx(m, cv2.MORPH_OPEN, cv2.getStructuringElement(
        cv2.MORPH_RECT, (max(10, int(BW * 0.45)), 1)))
    vs = [x + px0 for x, _ in _centres(vt, 0)]
    hs = [y + py0 for y, _ in _centres(hz, 1)]

    cols, hit = _snap(vs, BAND_V_EXPECT, x0, x1, V_TOL, x1 - x0)
    vhits = sum(hit)
    # An interior rule is the discriminating one. The table's outer edges are
    # shared with the band and with the staff table beside it, so a box placed
    # anywhere along the band's height can find them; only the representatives
    # table is divided at 0.20 and 0.60 of its own width.
    if vhits < 2 or not (hit[1] or hit[2]):
        return None, "no column rules: not the representatives table"
    # Rescale onto the two found rules that sit furthest apart.
    idx = [i for i in range(4) if hit[i]]
    lo_i, hi_i = idx[0], idx[-1]
    r_lo, r_hi = BAND_V_EXPECT[lo_i], BAND_V_EXPECT[hi_i]
    if r_hi - r_lo < 0.15:
        return None, "column rules too close to rescale"
    scale = (cols[hi_i] - cols[lo_i]) / (r_hi - r_lo)
    left = cols[lo_i] - r_lo * scale
    cols = [int(round(left + e * scale)) for e in BAND_V_EXPECT]

    rows, hhit = _snap(hs, BAND_H_EXPECT, y0, y1, H_TOL, bh)
    hhits = sum(hhit)
    rows = [int(round(v)) for v in rows]
    if hhits < 3 or any(rows[i] >= rows[i + 1] for i in range(len(rows) - 1)):
        rows = [int(round(y0 + e * bh)) for e in BAND_H_EXPECT]
        hhits = 0

    loc["box"] = (cols[0], rows[0], cols[-1], rows[-1])
    loc["cols"] = cols[1:3]
    loc["rows"] = rows[2:]          # the three data rows: 4 boundaries
    loc["col_rules"] = vhits
    loc["row_rules"] = hhits
    return loc, None


ROTATIONS = {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180,
             270: cv2.ROTATE_90_COUNTERCLOCKWISE}


def locate_any(img):
    """Locate the table, retrying the other rotations if the form is sideways.

    The counting record is a landscape form, and the orientation stage decides
    which way is up from the printed masthead. It is wrong on a small remainder
    — a scan whose masthead is faint, or a page holding the form at 90 degrees —
    and there the rule pattern cannot fit because the form's horizontal rules are
    running down the page. Rather than a second masthead pass, the fit is simply
    tried at each rotation: the pattern is asymmetric (the table is divided at
    0.20 and 0.60 of its width, which mirrors to 0.40 and 0.80), so a rotation
    that is upside-down does not satisfy the column check that a right-way-up one
    does. Returns (loc, image, degrees).
    """
    loc, err = locate(img)
    if loc is not None:
        return loc, img, 0, None
    best = None
    for deg, code in ROTATIONS.items():
        turned = cv2.rotate(img, code)
        loc, _ = locate(turned)
        if loc is None:
            continue
        score = (loc["col_rules"], loc["row_rules"], loc["rules_hit"])
        if best is None or score > best[0]:
            best = (score, loc, turned, deg)
    if best is None:
        return None, img, 0, err
    return best[1], best[2], best[3], None


def crop(img, loc):
    x0, y0, x1, y1 = loc["box"]
    return img[max(0, y0):y1, max(0, x0):x1]


def cells(img, loc):
    """The nine (row, column) crops of the table.

    Columns are returned in the order the form is read, right to left:
    0 = the representative's name, 1 = the candidate, 2 = the signature.
    """
    x_left, _, x_right, _ = loc["box"]
    c1, c2 = loc["cols"]
    spans = [(c2, x_right), (c1, c2), (x_left, c1)]
    rows = loc["rows"]
    out = []
    for i in range(3):
        y0, y1 = rows[i], rows[i + 1]
        out.append([img[max(0, y0):y1, max(0, a):b] for a, b in spans])
    return out


def ink(cell):
    """Fraction of the cell covered by handwriting, and where it sits.

    The seal is printed in the same red as the layout and lands on this block
    on most forms, so ink is counted as dark pixels that are *not* red — a
    stamp crossing the candidate column must not read as a representative. The
    printed rules are excluded the same way. What is left is pen.
    """
    if cell.size == 0 or cell.shape[0] < 4 or cell.shape[1] < 8:
        return None
    b, g, r = cv2.split(cell.astype(np.int16))
    red = np.clip(r - np.maximum(b, g), 0, 255)
    gray = cv2.cvtColor(cell, cv2.COLOR_BGR2GRAY)
    dark = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                 cv2.THRESH_BINARY_INV, 15, 12)
    pen = (dark > 0) & (red < 30)
    # Trim a rule-width margin: a row boundary clipped into the crop would count
    # as ink on every form, filled or not.
    m = max(1, int(round(0.10 * cell.shape[0])))
    core = pen[m:-m or None, m:-m or None]
    if core.size == 0:
        return None
    frac = float(core.mean())
    cols_used = float((core.any(axis=0)).mean())
    rows_used = float((core.any(axis=1)).mean())
    return {"frac": frac, "cols": cols_used, "rows": rows_used}
