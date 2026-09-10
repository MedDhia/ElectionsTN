"""Render the candidate maps from the margin tables and the cached boundaries.

Four maps at each of two granularities: one per candidate showing vote share, and
one showing Saied's margin over his strongest rival. Plus a four-panel composite
as a single figure for a paper.

Design decisions, and why
-------------------------
**Sequential, one hue, not diverging.** The margin map shows Saied's share minus
the runner-up's, and that is positive in all 264 delegations (24.6 to 96.4
points). A diverging scale would assert a polarity the data does not have and
spend half its range on empty territory. Only 2 of 2,042 imadas go the other way,
and they are marked individually instead -- at 2 in 2,042 they would be invisible
at the pale end of any ramp, and they are the substantively interesting cases.

**One documented ramp for all four maps.** The palette instance documents a full
100-700 ramp for blue only, and its rule is that every step is a hex from the
instance file, never an eyeballed value. So blue carries all four maps rather than
inventing orange and aqua ramps. Each figure stands alone and names its candidate
in the title; the composite states each panel's own class breaks. Verified as a
sequential ramp by the check that applies to one -- lightness strictly monotone,
L from 0.905 down to 0.338 in even steps of 0.093-0.095.

**One fixed scale, 0 to 100%, continuous.** Every percentage-valued figure in
this repository reads the same scale: 0% at the pale end of the documented ramp,
100% at the dark end, with a colourbar ticked every 10 rather than seven class
swatches. A signed margin, being a difference of two shares, runs the full
-100 to +100 points it can take. So a shade means one number everywhere --
across candidates, across levels, across families -- which quantile classes
could never offer.

The cost is real and is stated on every figure rather than hidden. Quantile
classes spent the whole ramp on whatever variation a quantity happened to have,
which made a map of Maghzaoui's 1.89% national share look as structured as one
of Saied's 91.12%. On a fixed scale it does not: measured over the 264
delegations, 99.6% of them fall in the palest seventh of the range for
Maghzaoui, 96.6% for Zammel, and 89.0% in the darkest seventh for Saied. Those
maps read flat because the quantity is flat against the range a percentage can
take.

Two things keep that from being a loss of information. The continuous ramp
resolves gradations seven classes would have collapsed, so an outlier like Bou
Abdellah is still visible inside a pale field. And every bar carries a bracket
giving the range its own units occupy, plus a rule at the national figure, so a
reader can see how much of the scale is in use -- the one thing a fitted scale
conveyed by construction and a fixed one has to say out loud.

Three quantities keep classes deliberately, being ordinal or unbounded rather
than percentages: the rank maps (`*_rank_*`), the ratio basis (multiples of a
candidate's national share) and the cluster figures (z-score bands and named
categories). Vote density, the electorate as a head count and the kernel
bandwidth in km are not percentages either.

**Equal-area projection.** Albers conic, standard parallels 32N/36N. A choropleth
asks the reader to weigh coloured area, and Tunisia spans 30-37.6N, where plate
carree would stretch the south.
"""

import argparse
import collections
import csv
import io
import json
import math
import os
import sys
import zipfile

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import PathCollection
from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib.patches import Patch, Rectangle
from matplotlib.path import Path

ARCHIVE = ".cache/boundaries/tun_admin_boundaries.geojson.zip"
DELEG_CSV = "data/delegation_margins.csv"
IMADA_CSV = "data/imada_margins.csv"
MAPS_DIR = "maps"
GEO_DIR = "data/maps"

# The documented blue sequential ramp, steps 100 -> 700.
RAMP = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
NO_DATA = "#e4e3df"          # units with no result; named in every legend
GOV_LINE = "#8a8985"
HILITE = "#e34948"           # marks the units Saied did not win

FORMATS = ("pdf", "png", "svg")

# ---- the fixed percentage scale ------------------------------------------
# Every percentage-valued figure in the repo reads this and nothing else, so a
# shade means one number everywhere: 0% at the pale end, 100% at the dark end.
# `PCT_TICK` is the label interval on the bar.
PCT_VMIN, PCT_VMAX, PCT_TICK = 0.0, 100.0, 10

# A signed margin is a difference of two shares, so its full range is -100 to
# +100 points, not 0 to 100. Measured: `saied_margin_pp` reaches +100.00 and
# `zammel_margin_pp` -100.00 at imada level, so both ends are attained and
# neither can be clipped. Passed as `colourbar=SIGNED_PP`.
PP_VMIN, PP_VMAX = -100.0, 100.0
SIGNED_PP = (PP_VMIN, PP_VMAX)

# The continuous ramp is interpolated *between* the seven documented steps, in
# the same hue and between the same endpoints -- no new hue, and no hex invented
# outside the ramp's own range. `tools/check_palette.py` asserts the
# interpolation keeps lightness strictly monotone, which is the property that
# made the seven steps a legitimate sequential ramp in the first place.
CMAP = LinearSegmentedColormap.from_list("tn_blue", RAMP, N=256)


def pct_colour(value, vmin=PCT_VMIN, vmax=PCT_VMAX):
    """Hex on the fixed percentage ramp. Values outside the range clamp."""
    span = vmax - vmin
    t = 0.0 if span <= 0 else (float(value) - vmin) / span
    return matplotlib.colors.to_hex(CMAP(min(max(t, 0.0), 1.0)))


def pct_is_dark(value, vmin=PCT_VMIN, vmax=PCT_VMAX):
    """True where the fixed ramp is dark enough to need pale ink on top.

    Replaces the `class_of(...) >= len(colours) - 3` test the classed figures
    used to pick label colour: with no classes there is no class index, and the
    position on the ramp is what actually decides legibility. The cut is at 0.55
    of the ramp, where L* passes about 53.
    """
    span = vmax - vmin
    return span > 0 and (float(value) - vmin) / span > 0.55


def pct_buckets(paths, value_of, vmin=PCT_VMIN, vmax=PCT_VMAX):
    """Group paths by their colour on the fixed ramp.

    Returns `(buckets, n_no_data)` in the shape `draw` already takes. Grouping
    by the quantised hex rather than emitting one collection per unit keeps the
    number of PathCollections at the number of distinct shades, which is what
    the classed version did too.
    """
    buckets = collections.defaultdict(list)
    missing = 0
    for code, path in paths.items():
        v = value_of(code)
        if v is None:
            buckets[NO_DATA].append(path)
            missing += 1
        else:
            buckets[pct_colour(v, vmin, vmax)].append(path)
    return buckets, missing

# Reproducibility. matplotlib stamps a creation time into PDF and SVG output, so
# two identical renders differ in bytes even though the pictures are the same --
# verified: re-rendering changed only /CreationDate, and the files were byte
# identical once it was stripped. Suppressing the stamp and pinning the SVG hash
# salt makes a rebuild byte-for-byte comparable, which is how every other output
# in this repo is checked.
matplotlib.rcParams["svg.hashsalt"] = "electionstn-maps"


def save_figure(fig, stem, formats=FORMATS):
    """Save one figure in every format, without embedding a timestamp."""
    made = []
    for ext in formats:
        path = f"{stem}.{ext}"
        kw = {}
        if ext == "pdf":
            kw["metadata"] = {"CreationDate": None}
        elif ext == "svg":
            kw["metadata"] = {"Date": None}
        fig.savefig(path, dpi=300, facecolor=SURFACE, bbox_inches="tight", **kw)
        made.append(path)
    return made


# The seven figure families, one per producing tool -- except that make_zooms
# produces two. Kept as a closed set so a typo fails at write time: `"surface"`
# would otherwise quietly create `maps/surface/` and the mistake would surface
# only as a pile of deletions plus untracked files in a later `git status`.
FAMILIES = ("national", "cartograms", "surfaces", "comparative", "levels",
            "zoom", "micro", "clusters", "turnout")


def figure_dir(family):
    """`maps/<family>/`, created on demand.

    Figures are grouped by family so a rebuild lands in exactly one directory
    and `maps/` stays navigable at 475 files. The directory is created here
    rather than in each main() because make_kde never created its output
    directory at all -- it worked only because `maps/` already existed, and
    under subfolders that latent bug would have become a real one.
    """
    if family not in FAMILIES:
        raise ValueError(f"unknown figure family {family!r}; "
                         f"expected one of {', '.join(FAMILIES)}")
    path = os.path.join(MAPS_DIR, family)
    os.makedirs(path, exist_ok=True)
    return path


FAMILY = "national"

PANELS = [
    ("saied", "saied_share_pct", "Kais Saied", "share of valid votes (%)"),
    ("zammel", "zammel_share_pct", "Ayachi Zammel", "share of valid votes (%)"),
    ("maghzaoui", "maghzaoui_share_pct", "Zouhair Maghzaoui", "share of valid votes (%)"),
    ("margin", "saied_margin_pp", "Saied's margin over his strongest rival",
     "percentage points"),
]


def load_layer(name):
    with zipfile.ZipFile(ARCHIVE) as z, z.open(name) as fh:
        return json.load(io.TextIOWrapper(fh, encoding="utf-8"))["features"]


def read(path):
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


# ---- geometry ------------------------------------------------------------
def albers(lon, lat, lon0=9.5, lat0=34.0, p1=32.0, p2=36.0):
    """Albers equal-area conic. Equal-area is the right family for a choropleth."""
    lon, lat = np.radians(np.asarray(lon)), np.radians(np.asarray(lat))
    lon0, lat0, p1, p2 = map(math.radians, (lon0, lat0, p1, p2))
    n = 0.5 * (math.sin(p1) + math.sin(p2))
    C = math.cos(p1) ** 2 + 2 * n * math.sin(p1)
    rho0 = math.sqrt(C - 2 * n * math.sin(lat0)) / n
    rho = np.sqrt(np.maximum(C - 2 * n * np.sin(lat), 0.0)) / n
    theta = n * (lon - lon0)
    return rho * np.sin(theta), rho0 - rho * np.cos(theta)


def simplify(points, tol):
    """Douglas-Peucker. admin4 is 42 MB raw; drawing it unsimplified is pointless
    at map scale and makes the vector outputs unusable in a document."""
    if len(points) < 4 or tol <= 0:
        return points
    pts = np.asarray(points, dtype=float)
    keep = np.zeros(len(pts), dtype=bool)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        seg = pts[j] - pts[i]
        L = math.hypot(*seg)
        if L == 0:
            d = np.hypot(*(pts[i + 1:j] - pts[i]).T)
        else:
            v = pts[i + 1:j] - pts[i]
            d = np.abs(seg[0] * v[:, 1] - seg[1] * v[:, 0]) / L
        k = int(np.argmax(d))
        if d[k] > tol:
            k += i + 1
            keep[k] = True
            stack += [(i, k), (k, j)]
    out = pts[keep]
    return out if len(out) >= 4 else pts


def ring_area(r):
    x = np.asarray([p[0] for p in r]); y = np.asarray([p[1] for p in r])
    return 0.5 * np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y)


def feature_path(geom, tol):
    """One matplotlib Path per feature, holes wound opposite to their exterior."""
    polys = (geom["coordinates"] if geom["type"] == "MultiPolygon"
             else [geom["coordinates"]])
    verts, codes = [], []
    for poly in polys:
        for i, ring in enumerate(poly):
            r = simplify(ring, tol)
            if len(r) < 3:
                continue
            a = ring_area(r)
            # exterior counter-clockwise, holes clockwise, so the nonzero fill
            # rule cuts the hole out instead of painting over it
            want_ccw = (i == 0)
            if (a > 0) != want_ccw:
                r = r[::-1]
            x, y = albers([p[0] for p in r], [p[1] for p in r])
            pts = list(zip(x, y))
            verts.extend(pts + [pts[0]])
            codes.extend([Path.MOVETO] + [Path.LINETO] * (len(pts) - 1) + [Path.CLOSEPOLY])
    return Path(np.asarray(verts), codes) if verts else None


# ---- classing ------------------------------------------------------------
def quantile_edges(values, k):
    """k quantile classes. Edges are returned so the legend can print them."""
    v = sorted(values)
    edges = [v[0]]
    for i in range(1, k):
        q = (len(v) - 1) * i / k
        lo, hi = math.floor(q), math.ceil(q)
        edges.append(v[lo] if lo == hi else v[lo] + (v[hi] - v[lo]) * (q - lo))
    edges.append(v[-1])
    # Ties can collapse an edge; nudge so bins stay strictly increasing.
    for i in range(1, len(edges)):
        if edges[i] <= edges[i - 1]:
            edges[i] = edges[i - 1] + 1e-9
    return edges


def class_of(value, edges):
    for i in range(len(edges) - 1):
        if value <= edges[i + 1]:
            return i
    return len(edges) - 2


def fmt(v):
    return f"{v:.1f}"


# Tunisia projects to an aspect (height/width) of 2.14 -- tall and narrow -- so a
# map-only figure would be 4.1 x 8.8 inches and half of any reasonable page width
# would sit empty on either side. Instead the x-limits are widened to the left by
# this factor, which flushes the map right and turns that dead space into a
# legend column.
GUTTER = 1.80


# Where the bar sits in the gutter, in axes fractions: (x, y, w, h). Fixed
# rather than computed so every figure puts the scale in the same place.
CBAR_RECT = (0.075, 0.40, 0.042, 0.40)


def colour_bar(ax, vmin, vmax, unit_label, compact, observed=None,
               marker=None):
    """A vertical continuous bar in the gutter, ticked every `PCT_TICK`.

    Drawn as an inset on the map axes rather than a figure-level colorbar so it
    lands in the gutter the map already reserves, and so a compact panel in a
    composite gets its own bar in the same relative place.

    `observed` brackets the range the mapped values actually occupy and
    `marker` rules a named value across the bar. Both exist because a fixed
    0-100 scale hides the one thing a fitted scale made obvious: how much of
    the range is in use. Saied's shares span 59.7-97.7%, so without the bracket
    a reader cannot tell whether the near-uniform blue means little variation
    or a scale far wider than the data.
    """
    x, y, w, h = CBAR_RECT
    if compact:
        w, h = w * 1.15, h * 0.92
    cax = ax.inset_axes([x, y, w, h])
    sm = plt.cm.ScalarMappable(norm=Normalize(vmin=vmin, vmax=vmax), cmap=CMAP)
    cb = ax.get_figure().colorbar(sm, cax=cax, orientation="vertical")
    # Aim for a readable number of ticks whatever the span: 0-100 gets every
    # 10, and the -100..+100 signed scale would get 21 at that step, so it
    # coarsens to 25.
    step = PCT_TICK
    if vmax - vmin <= 4 * PCT_TICK:
        step = (vmax - vmin) / 5.0
    while step > 0 and (vmax - vmin) / step > 12:
        step *= 2.5
    ticks = np.arange(vmin, vmax + step / 2.0, step)
    cb.set_ticks(ticks)
    cb.set_ticklabels([f"{t:g}" for t in ticks])
    cb.outline.set_visible(False)
    cb.ax.tick_params(length=2.0, width=0.5, pad=1.8, colors=INK_2,
                      labelsize=5.5 if compact else 7.0)
    fs = 5.2 if compact else 6.8
    # x is in axes fractions of the bar, y in the bar's own data units, which is
    # what get_yaxis_transform gives -- so these sit beside the bar and track
    # the value, without having to convert anything by hand.
    tr = cax.get_yaxis_transform()
    if observed:
        lo, hi = float(observed[0]), float(observed[1])
        bx = 2.45 if compact else 2.20
        cax.plot([bx, bx], [lo, hi], transform=tr, color=INK_2, lw=0.9,
                 clip_on=False, zorder=6)
        for yv in (lo, hi):
            cax.plot([bx - 0.30, bx + 0.30], [yv, yv], transform=tr,
                     color=INK_2, lw=0.9, clip_on=False, zorder=6)
        cax.text(bx + 0.55, (lo + hi) / 2.0,
                 f"observed\n{lo:.1f}–{hi:.1f}", transform=tr, color=INK_2,
                 fontsize=fs, va="center", ha="left", clip_on=False,
                 linespacing=1.25)
    if marker:
        mv, mlabel = float(marker[0]), marker[1]
        # The rule has to read against whatever shade it happens to land on, and
        # one ink colour cannot: white vanishes at the pale end, ink at the dark
        # end. So it takes its colour from the ramp underneath it.
        t = (mv - vmin) / (vmax - vmin) if vmax > vmin else 0.0
        cax.plot([0.0, 1.0], [mv, mv], transform=tr,
                 color="#ffffff" if t > 0.55 else INK, lw=1.1,
                 clip_on=False, zorder=6)
        cax.text(-0.35, mv, mlabel, transform=tr, color=INK_2, fontsize=fs,
                 va="center", ha="right", clip_on=False)
    # The title goes above the bar as text, left-aligned with everything else in
    # the gutter, because a colorbar label rotates or centres and neither lines
    # up with the title and the counts.
    ax.text(0.01, y + h + (0.022 if compact else 0.018), unit_label,
            transform=ax.transAxes, fontsize=6.5 if compact else 8.5,
            color=INK_2, ha="left", va="bottom")
    return cb


def draw(ax, paths_colors, gov_paths, title, subtitle, edges, unit_label,
         n_units, no_data, highlight=None, hi_label=None, compact=False,
         labels=None, units_note=True, legend=True, colours=None,
         no_data_label=None, colourbar=None, observed=None, marker=None):
    ax.set_aspect("equal")
    ax.set_axis_off()
    ax.set_facecolor(SURFACE)

    for colour, paths in paths_colors.items():
        if paths:
            ax.add_collection(PathCollection(
                paths, facecolors=colour, edgecolors="#ffffff",
                linewidths=0.10 if compact else 0.13, zorder=2))
    # governorate outlines, recessive: orientation without competing for attention
    ax.add_collection(PathCollection(
        gov_paths, facecolors="none", edgecolors=GOV_LINE,
        linewidths=0.5 if compact else 0.7, zorder=3))
    if highlight:
        ax.add_collection(PathCollection(
            highlight, facecolors="none", edgecolors=HILITE,
            linewidths=1.1 if compact else 1.5, zorder=4))

    ax.autoscale_view()
    # The gutter exists to hold the legend, so the two travel together: a panel
    # with no legend of its own -- one sharing a figure-level legend with the
    # panels beside it -- gives the space back to the map.
    if legend:
        x0, x1 = ax.get_xlim()
        ax.set_xlim(x1 - GUTTER * (x1 - x0), x1)

    ts = 10 if compact else 13
    # Title and subtitle live in the gutter, as text rather than as a title, so
    # they cannot collide with each other the way set_title plus an offset text
    # did on the first render.
    ax.text(0.01, 0.985, title, transform=ax.transAxes, fontsize=ts, color=INK,
            va="top", ha="left", fontweight="bold", wrap=True)
    if subtitle:
        ax.text(0.01, 0.945, subtitle, transform=ax.transAxes, fontsize=ts - 3.5,
                color=INK_2, va="top", ha="left")

    if not legend:
        return
    # `colourbar` switches the legend from classes to a continuous bar over a
    # fixed range. Percentage quantities take it, so a shade means one number on
    # every figure in the repo and no two maps disagree about what dark blue is.
    # The classed path stays for everything a percentage scale cannot carry:
    # ranks, ratios, z-score bands and named categories.
    handles = []
    if colourbar:
        vmin, vmax = ((PCT_VMIN, PCT_VMAX) if colourbar is True
                      else (float(colourbar[0]), float(colourbar[1])))
        colour_bar(ax, vmin, vmax, unit_label, compact, observed, marker)
    else:
        # `labels` lets a caller name the classes in its own units -- ranks, or
        # multiples of a national average -- instead of the default numeric range.
        texts = labels or [f"{fmt(edges[i])} – {fmt(edges[i+1])}"
                           for i in range(len(edges) - 1)]
        # `colours` lets a caller class into fewer than len(RAMP) bins -- 6
        # regions cannot carry 7 classes -- and still have the legend match.
        ramp = colours or RAMP
        handles = [Patch(facecolor=ramp[i], edgecolor="#ffffff", linewidth=0.4,
                         label=texts[i])
                   for i in range(len(edges) - 1)]
    if no_data:
        # "no result" is the usual reason a unit is grey, but not the only one:
        # the turnout maps grey units that have a result whose coverage is too
        # thin to draw, and calling that "no result" would be false.
        handles.append(Patch(facecolor=NO_DATA, edgecolor="#ffffff", linewidth=0.4,
                             label=(no_data_label or "no result").format(n=no_data)
                                   + f" ({no_data})"))
    if highlight:
        handles.append(Patch(facecolor="none", edgecolor=HILITE, linewidth=1.4,
                             label=hi_label))
    # In colourbar mode the bar carries the scale and its title, so what is
    # left here is only the things a bar cannot express -- the grey and the
    # outline -- and they hang below it rather than where the classes were.
    top = (CBAR_RECT[1] - 0.035 if colourbar
           else (0.80 if compact else 0.83))
    if handles:
        leg = ax.legend(handles=handles,
                        title=None if colourbar else unit_label,
                        loc="upper left", bbox_to_anchor=(0.01, top),
                        frameon=False, fontsize=(6.0 if compact else 8.0),
                        title_fontsize=(6.5 if compact else 8.5),
                        handlelength=1.0, handleheight=1.0, labelspacing=0.30,
                        borderaxespad=0)
        if leg.get_title().get_text():
            leg.get_title().set_color(INK_2)
            leg.get_title().set_ha("left")
        for t in leg.get_texts():
            t.set_color(INK_2)
    # The offset below the legend is in axes fractions, which only tracks the
    # legend's real height while the axes keeps roughly the national map's
    # shape. On a short, wide panel it lands inside the legend, so callers with
    # their own aspect say where the count goes instead.
    if units_note:
        ax.text(0.01, top - (0.030 if compact else 0.026) * (len(handles) + 1.6),
                f"{n_units} mapped units", transform=ax.transAxes,
                fontsize=6.0 if compact else 7.5, color=INK_2, ha="left",
                va="top")


def build(level, csv_path, layer, pcode_col, tol, name_col, out_prefix, log):
    feats = load_layer(layer)
    rows = {r[pcode_col]: r for r in read(csv_path)}
    gov = [feature_path(f["geometry"], tol * 2)
           for f in load_layer("tun_admin2.geojson")]
    gov = [p for p in gov if p]

    paths, values = {}, {}
    for f in feats:
        p = f["properties"]
        code = p[pcode_col]
        path = feature_path(f["geometry"], tol)
        if path is None:
            continue
        paths[code] = path
        values[code] = rows.get(code)

    n_total = len(paths)
    n_with = sum(1 for v in values.values() if v)
    log.append({"level": level, "features": n_total, "with_result": n_with,
                "no_result": n_total - n_with,
                "simplify_tolerance_deg": tol})

    # units Saied did not win, called out on the margin map
    lost = [c for c, v in values.items() if v and v.get("winner") and v["winner"] != "saied"]

    made = []
    def value_of(field):
        def f(code):
            v = values.get(code)
            return None if not v or v[field] == "" else float(v[field])
        return f

    for key, field, label, unit_label in PANELS:
        vals = [float(v[field]) for v in values.values() if v and v[field] != ""]
        buckets, _ = pct_buckets(paths, value_of(field))

        fig, ax = plt.subplots(figsize=(6.85, 8.1), facecolor=SURFACE)
        hl = [paths[c] for c in lost] if key == "margin" and lost else None
        nat = sum(int(v[key]) for v in values.values() if v and key in v) if key != "margin" else None
        # The observed range is named because a fixed 0-100 bar cannot show it:
        # the reader can see the shade but not how much of the bar is in use.
        span = f"observed {min(vals):.1f}–{max(vals):.1f}%"
        sub = (f"{level} level · fixed 0–100% scale · {span} · "
               f"national {nat/sum(sum(int(v[c]) for v in values.values() if v) for c in ('saied','zammel','maghzaoui'))*100:.2f}%"
               if nat is not None else
               f"{level} level · fixed 0–100 point scale · {span}")
        nat_pct = (nat / sum(sum(int(v[c]) for v in values.values() if v)
                             for c in ("saied", "zammel", "maghzaoui")) * 100
                   if nat is not None else None)
        draw(ax, buckets, gov, label, sub, None, unit_label, n_total,
             n_total - n_with, hl,
             f"Saied did not lead ({len(lost)})" if hl else None,
             colourbar=True, observed=(min(vals), max(vals)),
             marker=(nat_pct, "national") if nat_pct is not None else None)
        fig.text(0.015, 0.012,
                 "2024 Tunisian presidential election · shares of valid votes at "
                 "certified stations · boundaries OCHA/HDX COD-AB (CC BY-IGO)",
                 fontsize=6.5, color=INK_2, va="bottom")
        fig.tight_layout(rect=(0, 0.028, 1, 1))
        made += save_figure(fig, f"{figure_dir(FAMILY)}/{key}_{out_prefix}")
        plt.close(fig)

    # four-panel composite
    fig, axes = plt.subplots(2, 2, figsize=(12.2, 14.0), facecolor=SURFACE)
    for ax, (key, field, label, unit_label) in zip(axes.ravel(), PANELS):
        vals = [float(v[field]) for v in values.values() if v and v[field] != ""]
        buckets, _ = pct_buckets(paths, value_of(field))
        hl = [paths[c] for c in lost] if key == "margin" and lost else None
        draw(ax, buckets, gov, label, None, None, unit_label, n_total,
             n_total - n_with, hl,
             f"Saied did not lead ({len(lost)})" if hl else None, compact=True,
             colourbar=True, observed=(min(vals), max(vals)))
    fig.suptitle("2024 Tunisian presidential election: candidate support by "
                 f"{level}", fontsize=15, color=INK, x=0.02, ha="left", y=0.985,
                 fontweight="bold")
    fig.text(0.02, 0.012,
             "Shares of valid votes at certified stations. All four panels use "
             "the same fixed 0–100% scale, so a shade means the same value in "
             "every panel and across every other figure in this repository.\n"
             "The cost is that a panel whose values occupy a narrow part of the "
             "range looks flat: each subtitle names the range actually observed.\n"
             "Boundaries: OCHA/HDX COD-AB (CC BY-IGO).",
             fontsize=7.5, color=INK_2, va="bottom")
    fig.tight_layout(rect=(0, 0.03, 1, 0.97))
    made += save_figure(fig, f"{figure_dir(FAMILY)}/composite_{out_prefix}")
    plt.close(fig)

    # GeoJSON with the results joined on, simplified to the same tolerance
    os.makedirs(GEO_DIR, exist_ok=True)
    out_feats = []
    for f in feats:
        p = f["properties"]
        code = p[pcode_col]
        v = values.get(code)
        geom = f["geometry"]
        polys = (geom["coordinates"] if geom["type"] == "MultiPolygon"
                 else [geom["coordinates"]])
        simp = [[[[round(c[0], 5), round(c[1], 5)] for c in simplify(ring, tol)]
                 for ring in poly] for poly in polys]
        props = {pcode_col: code, "name": p.get(name_col), "name_ar": p.get(name_col + "1")}
        if v:
            props.update({k: v[k] for k in v if k not in (pcode_col,)})
        out_feats.append({"type": "Feature", "properties": props,
                          "geometry": {"type": "MultiPolygon", "coordinates": simp}})
    gj = f"{GEO_DIR}/{out_prefix}_results.geojson"
    with open(gj, "w", encoding="utf-8") as fh:
        json.dump({"type": "FeatureCollection", "features": out_feats}, fh,
                  ensure_ascii=False)
    made.append(gj)
    return made, n_total, n_with, lost


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--level", choices=["delegation", "imada", "both"], default="both")
    args = ap.parse_args()
    if not os.path.exists(ARCHIVE):
        sys.exit(f"missing {ARCHIVE}; run tools/fetch_boundaries.py")

    log = []
    jobs = []
    if args.level in ("delegation", "both"):
        jobs.append(("delegation", DELEG_CSV, "tun_admin3.geojson", "adm3_pcode",
                     0.004, "adm3_name", "delegation"))
    if args.level in ("imada", "both"):
        jobs.append(("imada", IMADA_CSV, "tun_admin4.geojson", "adm4_pcode",
                     0.002, "adm4_name", "imada"))

    for level, csv_path, layer, col, tol, name_col, prefix in jobs:
        made, n, w, lost = build(level, csv_path, layer, col, tol, name_col, prefix, log)
        print(f"{level}: {w}/{n} units with a result; "
              f"Saied did not lead in {len(lost)}")
        for m in made:
            print(f"    {os.path.getsize(m):>9,}  {m}")
    print()
    for r in log:
        print(f"  {r}")


if __name__ == "__main__":
    main()
