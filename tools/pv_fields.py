"""Map detected digit-cell runs on a PV form to named fields.

The form is a fixed template, so once a scan is upright the fields sit at stable
normalised positions. The three data blocks are columns, read right-to-left as
Arabic is: stage 1 on the right, stage 2 in the middle, stage 3 on the left.
Within a column, fields run top to bottom in printed order.
"""
import numpy as np

# (name, x range as a fraction of width, y range, expected run length)
COLUMNS = [
    ("stage1", (0.60, 0.78), (0.27, 0.56), 4, ["a_registered", "b_delivered",
                                               "c_signed", "d_damaged", "r_remaining"]),
    ("stage2", (0.28, 0.48), (0.27, 0.56), 4, ["s_extracted", "valid", "blank", "spoilt"]),
    ("stage3", (0.00, 0.16), (0.27, 0.56), 4, ["match1", "w_voted", "m_total",
                                               "match2", "n_total", "match3"]),
    ("cands", (0.00, 0.12), (0.58, 0.80), 4, ["zammel", "maghzaoui", "saied"]),
    ("q", (0.48, 0.66), (0.70, 0.82), 4, ["q_declared"]),
    ("match4", (0.14, 0.32), (0.70, 0.82), 4, ["match4"]),
]


def map_fields(rows, width, height):
    """rows from pv_grid.group_runs -> {field_name: [cell, ...]}."""
    out = {}
    for _, (x0, x1), (y0, y1), want_len, names in COLUMNS:
        found = []
        for y, runs in rows:
            yf = y / height
            if not (y0 <= yf <= y1):
                continue
            for run in runs:
                xf = run[0][0] / width
                if x0 <= xf <= x1 and len(run) >= want_len - 1:
                    found.append((y, run[:want_len] if len(run) > want_len else run))
        found.sort(key=lambda t: t[0])
        # A column is only trustworthy when it yields exactly the printed number
        # of fields; a short or long read means detection dropped or split a row.
        if len(found) == len(names):
            for name, (_, run) in zip(names, found):
                out[name] = run
    return out


def digits_of(value, n):
    """Zero-padded digit list for a known field value, or None if it will not fit."""
    if value is None:
        return None
    s = str(int(value))
    return [int(c) for c in s.zfill(n)] if len(s) <= n else None
