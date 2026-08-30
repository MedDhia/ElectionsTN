"""Place the fields by matching what was detected against the form template.

`pv_fields.map_fields` accepts a column only when every field in it is detected,
so a form where three of five boxes were found contributes nothing. On a clean
1600px scan that is fine — detection finds everything or nearly. On the rest it
throws away most of what was recovered: one failing form yields seven runs at
exactly the right normalised positions and keeps three.

This registers instead of requiring. The runs that *were* detected are landmarks;
fitting them against their known positions in a reference form gives a transform,
and the fields that were missed are then placed through it. Detected cells are
always preferred over placed ones — the point of the transform is only to reach
the boxes detection could not segment.

Registering on detected cells beats registering on pixels. Aligning two scans by
image correlation scores well on the page as a whole while missing the cells by
several pixels, which is enough to crop the wrong ink; anchoring on boxes that
were actually found ties the transform to the geometry that matters.

Mis-registration is self-limiting: badly placed cells contain noise, the form's
identities do not hold, and the row is rejected by the same gate as everything
else. That is what makes it safe to try on every form.
"""
import json
import numpy as np

TEMPLATE = ".cache/pv_template.json"

POS_TOL = 0.055        # normalised distance for a run to claim a template field
MIN_ANCHORS = 3        # below this there is nothing to fit a transform on


def load_template(path=TEMPLATE):
    """{field: (cells, x0, y0, w, h, n)} in normalised reference coordinates."""
    doc = json.load(open(path))
    geo, ref_w, ref_h = doc["fields"], float(doc["width"]), float(doc["height"])
    out = {}
    for f, cells in geo.items():
        cs = [(c[0] / ref_w, c[1] / ref_h, c[2] / ref_w, c[3] / ref_h) for c in cells]
        x0 = min(c[0] for c in cs)
        y0 = min(c[1] for c in cs)
        out[f] = (cs, x0, y0,
                  max(c[0] + c[2] for c in cs) - x0,
                  max(c[1] + c[3] for c in cs) - y0, len(cs))
    return out


def _runs(rows, W, H):
    """Detected runs as (x0, y0, n, cells) in normalised coordinates."""
    out = []
    for _, runs in rows:
        for run in runs:
            if len(run) < 3:
                continue
            out.append((run[0][0] / W, min(c[1] for c in run) / H, len(run), run))
    return out


def _fit(pairs):
    """Least-squares (sx, tx, sy, ty) mapping template -> target, or None."""
    if len(pairs) < 2:
        return None
    tx_ = np.array([[p[0], 1.0] for p in pairs])
    ty_ = np.array([[p[1], 1.0] for p in pairs])
    gx = np.array([p[2] for p in pairs])
    gy = np.array([p[3] for p in pairs])
    (sx, bx), *_ = np.linalg.lstsq(tx_, gx, rcond=None)
    (sy, by), *_ = np.linalg.lstsq(ty_, gy, rcond=None)
    if not (0.7 < sx < 1.4 and 0.7 < sy < 1.4):
        return None
    return float(sx), float(bx), float(sy), float(by)


def register(rows, W, H, template):
    """{field: [cell, ...]} using detected runs where possible, placed elsewhere.

    Returns (fields, n_detected). `n_detected` is how many fields came from real
    detections rather than from the template, which callers use to decide how
    much of the reading to trust.
    """
    runs = _runs(rows, W, H)
    if not runs:
        return {}, 0

    # Round one: claim template fields by position and cell count, unregistered.
    taken, pairs = {}, []
    for x0, y0, n, cells in runs:
        best, bd = None, POS_TOL
        for f, (_, tx, ty, _, _, tn) in template.items():
            if f in taken or abs(tn - n) > 1:
                continue
            d = ((x0 - tx) ** 2 + (y0 - ty) ** 2) ** 0.5
            if d < bd:
                best, bd = f, d
        if best:
            taken[best] = cells
            pairs.append((template[best][1], template[best][2], x0, y0))

    fit = _fit(pairs) if len(pairs) >= MIN_ANCHORS else None
    if fit:
        # Round two: re-claim under the fitted transform, which corrects a scan
        # whose form sits at a different scale or offset from the reference.
        sx, bx, sy, by = fit
        taken, pairs2 = {}, []
        for x0, y0, n, cells in runs:
            best, bd = None, POS_TOL
            for f, (_, tx, ty, _, _, tn) in template.items():
                if f in taken or abs(tn - n) > 1:
                    continue
                d = ((x0 - (sx * tx + bx)) ** 2 + (y0 - (sy * ty + by)) ** 2) ** 0.5
                if d < bd:
                    best, bd = f, d
            if best:
                taken[best] = cells
                pairs2.append((template[best][1], template[best][2], x0, y0))
        refit = _fit(pairs2) if len(pairs2) >= MIN_ANCHORS else None
        fit = refit or fit

    out = dict(taken)
    detected = len(out)
    if fit:
        sx, bx, sy, by = fit
        for f, (cs, *_rest) in template.items():
            if f in out:
                continue
            out[f] = [(int(round((sx * cx + bx) * W)), int(round((sy * cy + by) * H)),
                       max(1, int(round(sx * cw * W))), max(1, int(round(sy * ch * H))))
                      for cx, cy, cw, ch in cs]
    return out, detected
