"""Find the ruled digit cells on an upright PV form.

Every number on the form is written one digit per cell in a printed grid, so the
task is line detection, not handwriting segmentation. Contour detection picks up
ink strokes instead of rules; extracting long horizontal and vertical runs
morphologically finds the printed grid itself.
"""
import cv2
import numpy as np


def line_masks(gray, h_len=25, v_len=18):
    """Separate the long horizontal and vertical printed rules from the ink."""
    th = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                               cv2.THRESH_BINARY_INV, 15, 8)
    horiz = cv2.morphologyEx(th, cv2.MORPH_OPEN,
                             cv2.getStructuringElement(cv2.MORPH_RECT, (h_len, 1)))
    vert = cv2.morphologyEx(th, cv2.MORPH_OPEN,
                            cv2.getStructuringElement(cv2.MORPH_RECT, (1, v_len)))
    return horiz, vert


def find_cells(img, min_w=12, max_w=70, min_h=14, max_h=70):
    """Return digit cells as (x, y, w, h), ordered top-to-bottom, left-to-right.

    Cells are the enclosed regions of the printed grid: the union of the two
    line masks is dilated to close small gaps, then the holes it encloses are
    the cells.
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    horiz, vert = line_masks(gray)
    grid = cv2.dilate(cv2.bitwise_or(horiz, vert),
                      cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)))
    # Cells are the connected components of everything the grid does not cover.
    n, labels, stats, _ = cv2.connectedComponentsWithStats(cv2.bitwise_not(grid), 8)
    cells = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if (min_w < w < max_w and min_h < h < max_h
                and 0.35 < w / h < 1.8 and area > 0.45 * w * h):
            cells.append((int(x), int(y), int(w), int(h)))
    cells.sort(key=lambda c: (c[1], c[0]))
    return cells


def group_runs(cells, row_tol=10, gap=14):
    """Group cells into rows, then into runs of adjacent cells (one number)."""
    if not cells:
        return []
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
            if c[0] - (p[0] + p[2]) < gap and abs(c[3] - p[3]) < 10:
                runs[-1].append(c)
            else:
                runs.append([c])
        out.append((int(np.mean([c[1] for c in row])), runs))
    return out


def digit_image(img, cell, pad=3, size=28):
    """Normalised 28x28 crop of one cell: ink white, paper black, centred."""
    x, y, w, h = cell
    x0, y0 = x + pad, y + pad
    x1, y1 = x + w - pad, y + h - pad
    if x1 - x0 < 4 or y1 - y0 < 4:
        return None
    g = cv2.cvtColor(img[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
    ink = cv2.adaptiveThreshold(g, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                cv2.THRESH_BINARY_INV, 15, 10)
    ys, xs = np.nonzero(ink)
    if len(xs) < 8:                       # empty cell
        return np.zeros((size, size), np.uint8)
    ink = ink[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    s = max(ink.shape)
    sq = np.zeros((s, s), np.uint8)
    oy, ox = (s - ink.shape[0]) // 2, (s - ink.shape[1]) // 2
    sq[oy:oy + ink.shape[0], ox:ox + ink.shape[1]] = ink
    return cv2.resize(sq, (size, size), interpolation=cv2.INTER_AREA)
