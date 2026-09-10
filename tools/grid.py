"""Find the ruled grid of a scanned results table.

Whole-page OCR of these tables fails the same way conventional OCR failed on
the procès-verbaux: Tesseract's Arabic model reads the list names well but
mangles the Latin digits beside them, and a right-to-left table interleaves the
two. Cutting the page into cells first fixes that — each cell is then read with
the model and the character set that suit it.

Getting the cells means finding the rules, and two things make that awkward.
The scans are photocopies of varying quality, so a rule that is near-black on
one page is mid-grey on another: the cutoff is chosen per page, as the darkest
one at which some row still reads as a full-width line. And the vertical rules
are fainter still, and the pages skewed a few pixels top to bottom, so no single
column is dark all the way down. Within one 70-pixel row band the skew is
nothing, and there a rule is the only thing that runs the band's full height.
Measuring band by band therefore finds all four columns without a per-page
constant anywhere.
"""
import numpy as np
from PIL import Image

# Darkness cutoffs to try, darkest first.
LEVELS = (170, 190, 210, 225)


def _group(xs, gap, thick=25):
    """Collapse runs of adjacent coordinates to one value each.

    A run thicker than a rule is a filled block — these tables shade their
    header row and their total row — and there the two edges are the rules,
    so both ends are kept rather than their midpoint.
    """
    out, cur = [], [xs[0]]
    def flush(run):
        out.extend([int(run[0]), int(run[-1])] if run[-1] - run[0] > thick
                   else [int(np.mean(run))])
    for x in xs[1:]:
        if x - cur[-1] <= gap:
            cur.append(x)
        else:
            flush(cur)
            cur = [x]
    flush(cur)
    return out


def _rules_at(a, thresh, gap):
    rows = (a < thresh).sum(1) / a.shape[1]
    if rows.max() < 0.25:
        return []
    ys = np.where(rows > max(0.30, 0.7 * rows.max()))[0]
    return _group(ys, gap) if len(ys) else []


def horizontal_rules(a, gap=6, min_height=40, want=3):
    """(y of every full-width rule, the cutoff they were found at).

    The darkest cutoff that yields a real table wins; a page whose rules are
    pale grey only produces one at a lighter cutoff, and a page whose rules are
    black produces a mess of text rows if read too light.
    """
    best = ([], LEVELS[-1])
    for thresh in LEVELS:
        rules = _rules_at(a, thresh, gap)
        usable = sum(1 for y0, y1 in zip(rules, rules[1:]) if y1 - y0 >= min_height)
        if usable >= want:
            return rules, thresh
        if usable > sum(1 for y0, y1 in zip(best[0], best[0][1:]) if y1 - y0 >= min_height):
            best = (rules, thresh)
    return best


def deskew(image, limit=2.0, step=0.25, reduce_by=4):
    """Rotate a page upright, by the angle that makes its rules sharpest.

    Some of these pages went through the scanner half a degree off square,
    which is enough to smear a rule across forty pixels of a 2,400-pixel row
    and leave the projection profile with no peak to find at all. The angle is
    searched on a quarter-size copy and applied to the full-resolution page.
    The objective is the thing actually wanted — how many table rows the page
    yields — with the profile's sharpness as a tie-break and a bias towards
    leaving a page that is already square alone.
    """
    small = image.reduce(reduce_by)
    best, angle = None, 0.0
    for candidate in np.arange(-limit, limit + step / 2, step):
        rotated = np.asarray(small.rotate(float(candidate), resample=Image.BILINEAR,
                                          fillcolor=255))
        rules, _ = horizontal_rules(rotated, gap=max(2, 6 // reduce_by),
                                    min_height=40 // reduce_by)
        usable = sum(1 for y0, y1 in zip(rules, rules[1:])
                     if y1 - y0 >= 40 // reduce_by)
        peak = float(((rotated < 190).sum(1) / rotated.shape[1]).max())
        # Rows recovered first, sharpness second; ties go to leaving it alone.
        score = (usable, peak, -abs(float(candidate)))
        if best is None or score > best:
            best, angle = score, float(candidate)
    if abs(angle) < step / 2:
        return image, 0.0
    return image.rotate(angle, resample=Image.BICUBIC, fillcolor=255), angle


def _longest_run(mask):
    """Longest run of True down each column."""
    best = np.zeros(mask.shape[1], int)
    cur = np.zeros(mask.shape[1], int)
    for row in mask:
        cur = np.where(row, cur + 1, 0)
        best = np.maximum(best, cur)
    return best


def vertical_rules(band, thresh, cover=0.8, gap=8):
    """x of every vertical rule crossing one row band."""
    xs = np.where(_longest_run(band < thresh) > cover * band.shape[0])[0]
    return _group(xs, gap) if len(xs) else []


def row_pitch(rules, min_height=40, most=200):
    """Typical distance between two rules, ignoring spurious close pairs."""
    steps = [b - a for a, b in zip(rules, rules[1:]) if min_height <= b - a <= most]
    return int(np.median(steps)) if steps else 0


def bands(a, pad=6, min_height=40, columns=5, tol=20):
    """(y0, y1, columns) for every row band on the page, top to bottom.

    The rules between rows give most of the bands. What they miss is the first
    row of a page: its top rule is the table's own top border, which on these
    scans is often too pale or too near the paper edge to register in the
    profile, and that row is then read as part of the heading and lost. So a
    band of one row's pitch is also offered above the first rule.

    How tall that band is comes from the ink above the rule, not from the
    pitch: a row whose list name wraps to two lines is twice as tall as its
    neighbours, and cutting it at one pitch catches the second line of the name
    and none of the numbers. Inside a row the vertical rules put ink in every
    scan line, so following the ink upwards finds the row's own top border.

    The band is kept only if the table's four columns all reappear in it, each
    within `tol` pixels of where the first real row has it, and it is then cut
    on those columns rather than on its own — a tall glyph can read as a fifth
    rule, which is no reason to reject the row. A heading sits in open paper
    and has no vertical rules at all. Nothing is offered below the last rule:
    no row is ever lost there, and the stamp at the foot of a final page is
    exactly the sort of thing that would be misread as one.
    """
    rules, thresh = horizontal_rules(a, min_height=min_height)
    if not rules:
        return []
    ink = min(thresh + 45, 240)
    # How short a band may be is a property of the page: where the rows are
    # tight, a row is shorter than the 40 pixels the rule search assumes, and
    # the inset has to shrink with it or there is nothing left to read.
    floor = max(24, int(0.55 * row_pitch(rules, min_height)))

    def band(y0, y1):
        inset = min(pad, max(0, (y1 - y0 - 30) // 2))
        y0, y1 = y0 + inset, y1 - inset
        if y1 - y0 < floor - 2 * pad or y0 < 0 or y1 > a.shape[0]:
            return None
        return y0, y1, vertical_rules(a[y0:y1, :], ink)

    out = [b for b in (band(y0, y1) for y0, y1 in zip(rules, rules[1:])) if b]
    reference = next((cols for _, _, cols in out if len(cols) == columns), None)
    pitch = row_pitch(rules, min_height)
    if reference and pitch:
        inked = (a[:rules[0], :] < ink).sum(1) > 5
        top = rules[0]
        while top > 0 and inked[top - 1] and rules[0] - top < 3 * pitch:
            top -= 1
        edge = band(min(top, rules[0] - pitch), rules[0])
        if edge and all(any(abs(x - y) <= tol for y in edge[2]) for x in reference):
            out.insert(0, (edge[0], edge[1], reference))
    return out
