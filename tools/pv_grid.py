"""Find the ruled digit cells on an upright PV form.

Every number on the form is written one digit per cell in a printed grid, so the
task is line detection, not handwriting segmentation. Contour detection picks up
ink strokes instead of rules; extracting long horizontal and vertical runs
morphologically finds the printed grid itself.
"""
import cv2
import numpy as np


def line_masks(gray, h_len=25, v_len=18, blk=15, c=8):
    """Separate the long horizontal and vertical printed rules from the ink."""
    th = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                               cv2.THRESH_BINARY_INV, blk, c)
    horiz = cv2.morphologyEx(th, cv2.MORPH_OPEN,
                             cv2.getStructuringElement(cv2.MORPH_RECT, (h_len, 1)))
    vert = cv2.morphologyEx(th, cv2.MORPH_OPEN,
                            cv2.getStructuringElement(cv2.MORPH_RECT, (1, v_len)))
    return horiz, vert


# Detection settings to try in order, best-performing first. Faint or broken
# rules need shorter opening kernels; the ladder is cheap because a form stops
# at the first setting that yields a complete field map. Measured on 120 random
# forms: the first alone completes 35%, the ladder 40%.
LADDER = [
    dict(h_len=25, v_len=18, blk=15, c=8, dil=3),
    dict(h_len=18, v_len=12, blk=15, c=8, dil=3),
    dict(h_len=18, v_len=12, blk=25, c=6, dil=3),
    dict(h_len=25, v_len=18, blk=31, c=4, dil=5),
]


WORK_WIDTH = 1600      # thresholds below are calibrated at this width


def find_cells(img, min_w=12, max_w=70, min_h=14, max_h=70, work_width=WORK_WIDTH,
               settings=None):
    """Return digit cells as (x, y, w, h), ordered top-to-bottom, left-to-right.

    Cells are the enclosed regions of the printed grid: the union of the two
    line masks is dilated to close small gaps, then the holes it encloses are
    the cells.

    Detection is done at a fixed working width. Only about half the corpus
    arrives at 1600px — a fifth is under 900px — and at those sizes the cells
    fall below the size thresholds and the morphological line lengths, so
    detection collapses. Resampling first makes the thresholds scale-invariant;
    cells are mapped back to the caller's coordinates.
    """
    scale = work_width / img.shape[1]
    if abs(scale - 1.0) > 0.02:
        work = cv2.resize(img, (work_width, max(1, round(img.shape[0] * scale))),
                          interpolation=cv2.INTER_CUBIC if scale > 1 else cv2.INTER_AREA)
    else:
        work, scale = img, 1.0

    cfg = settings or LADDER[0]
    gray = cv2.cvtColor(work, cv2.COLOR_BGR2GRAY)
    horiz, vert = line_masks(gray, cfg["h_len"], cfg["v_len"], cfg["blk"], cfg["c"])
    d = cfg["dil"]
    grid = cv2.dilate(cv2.bitwise_or(horiz, vert),
                      cv2.getStructuringElement(cv2.MORPH_RECT, (d, d)))
    # Cells are the connected components of everything the grid does not cover.
    n, labels, stats, _ = cv2.connectedComponentsWithStats(cv2.bitwise_not(grid), 8)
    cells = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if (min_w < w < max_w and min_h < h < max_h
                and 0.35 < w / h < 1.8 and area > 0.45 * w * h):
            cells.append((int(x / scale), int(y / scale),
                          max(1, int(w / scale)), max(1, int(h / scale))))
    cells.sort(key=lambda c: (c[1], c[0]))
    return cells


def group_runs(cells, row_tol=None, gap=None):
    """Group cells into rows, then into runs of adjacent cells (one number).

    Tolerances default to fractions of the median cell height so grouping works
    at whatever resolution the caller's page happens to be.
    """
    if not cells:
        return []
    pitch = float(np.median([c[3] for c in cells]))
    row_tol = row_tol if row_tol is not None else max(4.0, 0.40 * pitch)
    gap = gap if gap is not None else max(5.0, 0.55 * pitch)
    cells = sorted(cells, key=lambda c: c[1] + c[3] / 2)
    rows, cur = [], [cells[0]]
    for c in cells[1:]:
        if abs((c[1] + c[3] / 2) - (cur[-1][1] + cur[-1][3] / 2)) < row_tol:
            cur.append(c)
        else:
            rows.append(cur)
            cur = [c]
    rows.append(cur)
    out = []
    for row in rows:
        row.sort(key=lambda c: c[0])
        runs = [[row[0]]]
        for c in row[1:]:
            p = runs[-1][-1]
            if c[0] - (p[0] + p[2]) < gap and abs(c[3] - p[3]) < max(4, 0.4 * pitch):
                runs[-1].append(c)
            else:
                runs.append([c])
        out.append((int(np.mean([c[1] for c in row])), runs))
    return out


def digit_image(img, cell, pad=0.10, size=28, keep=0.25):
    """Normalised 28x28 crop of one cell: ink white, paper black, centred.

    Two things have to be removed without removing the digit. The printed rules
    bounding the cell come off with a padding fraction — a fixed pixel pad is
    wrong because the corpus spans a 3x range of scan widths. What is left of a
    rule after padding, plus ink bleeding in from a neighbouring cell, is dropped
    by component: anything touching the crop edge that is small relative to the
    largest component is a fragment. Dropping *everything* that touches the edge
    is what does not work — handwriting in a tight box touches the rules all the
    time, and the filter then deletes three cells in four.
    """
    x, y, w, h = cell
    px = max(1, int(round(pad * min(w, h))))
    x0, y0 = x + px, y + px
    x1, y1 = x + w - px, y + h - px
    if x1 - x0 < 4 or y1 - y0 < 4:
        return None
    g = cv2.cvtColor(img[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
    ink = cv2.adaptiveThreshold(g, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                cv2.THRESH_BINARY_INV, 15, 10)
    n_lbl, lbl, stats, _ = cv2.connectedComponentsWithStats((ink > 0).astype(np.uint8), 8)
    if n_lbl > 2:
        areas = stats[1:, cv2.CC_STAT_AREA]
        biggest = areas.max()
        H, W = ink.shape
        for k in range(1, n_lbl):
            xs, ys, ws, hs, area = stats[k]
            edge = xs == 0 or ys == 0 or xs + ws == W or ys + hs == H
            if edge and area < keep * biggest:
                ink[lbl == k] = 0

    ys, xs = np.nonzero(ink)
    if len(xs) < 8:                       # empty cell
        return np.zeros((size, size), np.uint8)
    ink = ink[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    s = max(ink.shape)
    sq = np.zeros((s, s), np.uint8)
    oy, ox = (s - ink.shape[0]) // 2, (s - ink.shape[1]) // 2
    sq[oy:oy + ink.shape[0], ox:ox + ink.shape[1]] = ink
    return cv2.resize(sq, (size, size), interpolation=cv2.INTER_AREA)


def find_fields(img, mapper, want):
    """Run the detection ladder until the field map is complete.

    `mapper(rows, width, height)` returns the field dict; `want` is how many
    fields a complete map has. Returns (fields, setting_index); the index is 0
    when the first setting sufficed, -1 when none produced a complete map (in
    which case the best partial map is returned).
    """
    H, W = img.shape[:2]
    best, best_i = {}, -1
    for i, cfg in enumerate(LADDER):
        fields = mapper(group_runs(find_cells(img, settings=cfg)), W, H)
        if len(fields) == want:
            return fields, i
        if len(fields) > len(best):
            best, best_i = fields, -1
    return best, best_i
