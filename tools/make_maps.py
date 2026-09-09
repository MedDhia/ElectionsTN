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

**Quantile classes, edges printed.** The shares are severely skewed (Saied's
median 93.8 against a floor of 59.7), so equal-interval classes would put almost
every unit in one bin and show nothing. Seven quantile classes map onto the seven
documented ramp steps, and the legend prints the actual range of each class, so
the reader is never guessing what a shade means. Because the classes are
per-candidate, shades are NOT comparable between panels; the caption says so.

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


def draw(ax, paths_colors, gov_paths, title, subtitle, edges, unit_label,
         n_units, no_data, highlight=None, hi_label=None, compact=False):
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

    # legend: one swatch per class, printing the class's real range, because a
    # bare gradient bar leaves the reader to guess what a shade means
    handles = [Patch(facecolor=RAMP[i], edgecolor="#ffffff", linewidth=0.4,
                     label=f"{fmt(edges[i])} – {fmt(edges[i+1])}")
               for i in range(len(edges) - 1)]
    if no_data:
        handles.append(Patch(facecolor=NO_DATA, edgecolor="#ffffff", linewidth=0.4,
                             label=f"no result ({no_data})"))
    if highlight:
        handles.append(Patch(facecolor="none", edgecolor=HILITE, linewidth=1.4,
                             label=hi_label))
    leg = ax.legend(handles=handles, title=unit_label, loc="upper left",
                    bbox_to_anchor=(0.01, 0.80 if compact else 0.83),
                    frameon=False, fontsize=(6.0 if compact else 8.0),
                    title_fontsize=(6.5 if compact else 8.5),
                    handlelength=1.0, handleheight=1.0, labelspacing=0.30,
                    borderaxespad=0)
    leg.get_title().set_color(INK_2)
    leg.get_title().set_ha("left")
    for t in leg.get_texts():
        t.set_color(INK_2)
    n_y = 0.80 if compact else 0.83
    ax.text(0.01, n_y - (0.030 if compact else 0.026) * (len(handles) + 1.6),
            f"{n_units} mapped units", transform=ax.transAxes,
            fontsize=6.0 if compact else 7.5, color=INK_2, ha="left", va="top")


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
    for key, field, label, unit_label in PANELS:
        vals = [float(v[field]) for v in values.values() if v and v[field] != ""]
        edges = quantile_edges(vals, len(RAMP))
        buckets = collections.defaultdict(list)
        for code, path in paths.items():
            v = values.get(code)
            if not v or v[field] == "":
                buckets[NO_DATA].append(path)
            else:
                buckets[RAMP[class_of(float(v[field]), edges)]].append(path)

        fig, ax = plt.subplots(figsize=(6.85, 8.1), facecolor=SURFACE)
        hl = [paths[c] for c in lost] if key == "margin" and lost else None
        nat = sum(int(v[key]) for v in values.values() if v and key in v) if key != "margin" else None
        sub = (f"{level} level · quantile classes · "
               f"national {nat/sum(sum(int(v[c]) for v in values.values() if v) for c in ('saied','zammel','maghzaoui'))*100:.2f}%"
               if nat is not None else f"{level} level · quantile classes")
        draw(ax, buckets, gov, label, sub, edges, unit_label, n_total,
             n_total - n_with, hl,
             f"Saied did not lead ({len(lost)})" if hl else None)
        fig.text(0.015, 0.012,
                 "2024 Tunisian presidential election · shares of valid votes at "
                 "certified stations · boundaries OCHA/HDX COD-AB (CC BY-IGO)",
                 fontsize=6.5, color=INK_2, va="bottom")
        fig.tight_layout(rect=(0, 0.028, 1, 1))
        for ext in FORMATS:
            out = f"{MAPS_DIR}/{key}_{out_prefix}.{ext}"
            fig.savefig(out, dpi=300, facecolor=SURFACE, bbox_inches="tight")
            made.append(out)
        plt.close(fig)

    # four-panel composite
    fig, axes = plt.subplots(2, 2, figsize=(12.2, 14.0), facecolor=SURFACE)
    for ax, (key, field, label, unit_label) in zip(axes.ravel(), PANELS):
        vals = [float(v[field]) for v in values.values() if v and v[field] != ""]
        edges = quantile_edges(vals, len(RAMP))
        buckets = collections.defaultdict(list)
        for code, path in paths.items():
            v = values.get(code)
            if not v or v[field] == "":
                buckets[NO_DATA].append(path)
            else:
                buckets[RAMP[class_of(float(v[field]), edges)]].append(path)
        hl = [paths[c] for c in lost] if key == "margin" and lost else None
        draw(ax, buckets, gov, label, None, edges, unit_label, n_total,
             n_total - n_with, hl,
             f"Saied did not lead ({len(lost)})" if hl else None, compact=True)
    fig.suptitle("2024 Tunisian presidential election: candidate support by "
                 f"{level}", fontsize=15, color=INK, x=0.02, ha="left", y=0.985,
                 fontweight="bold")
    fig.text(0.02, 0.012,
             "Shares of valid votes at certified stations. Classes are quantiles "
             "computed separately per panel, so a shade in one panel does NOT mean "
             "the same value in another — read each legend.\n"
             "Boundaries: OCHA/HDX COD-AB (CC BY-IGO).",
             fontsize=7.5, color=INK_2, va="bottom")
    fig.tight_layout(rect=(0, 0.03, 1, 0.97))
    for ext in FORMATS:
        out = f"{MAPS_DIR}/composite_{out_prefix}.{ext}"
        fig.savefig(out, dpi=300, facecolor=SURFACE, bbox_inches="tight")
        made.append(out)
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
    os.makedirs(MAPS_DIR, exist_ok=True)

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
