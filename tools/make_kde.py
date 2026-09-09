"""Kernel-smoothed surfaces of candidate support, and of vote density.

What these add over the choropleths
-----------------------------------
The choropleths and cartograms in `maps/` show one value per administrative
unit, so every boundary is a hard edge that the vote does not actually have.
These surfaces drop the units: each imada centroid is a sample, and the value at
any point is a distance-weighted average of the samples near it. Regional
structure shows up as regional structure rather than as 2,042 tiles.

Two different fields, because they answer different questions:

- **Support surfaces** (`*_kde`): a vote-weighted, kernel-smoothed *share*. This
  is a Nadaraya-Watson estimator -- weights are kernel times votes -- so a large
  imada pulls the local estimate more than a small one, and the result is a share
  rather than a count. Contoured at the same seven quantile class breaks as the
  choropleths, so the two are directly comparable.
- **Vote density** (`turnout_density_kde`): certified valid votes per square
  kilometre. Not a share at all, and on its own scale, because "where are the
  voters" is the question the share maps cannot answer.

Where the estimate is not supported, it is not drawn
----------------------------------------------------
This is the trap with kernel smoothing on an uneven point pattern, and the
pattern here is very uneven: the median imada centroid has a neighbour 4.2 km
away, but the sparsest has one 104.6 km away. In the deep desert a fixed kernel
encloses almost no data, and a Nadaraya-Watson ratio computed from almost no
weight is noise that looks like signal.

So cells whose kernel-weighted vote total falls below MIN_VOTES are masked and
named in the legend, rather than filled with an extrapolation.
"""

import argparse
import math
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import PathCollection
from matplotlib.patches import Patch
from scipy.spatial import cKDTree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from make_maps import (FORMATS, GOV_LINE, INK, INK_2, MAPS_DIR, PANELS, RAMP,
                       SURFACE, albers, feature_path, load_layer,
                       quantile_edges, read)

IMADA_CSV = "data/imada_margins.csv"
EARTH_KM = 6371.0            # Albers here returns great-circle radians

BANDWIDTH_KM = 25.0
GRID_KM = 2.0
CUTOFF = 3.0                 # Gaussian weight beyond 3h is negligible
MIN_VOTES = 500.0            # kernel-weighted votes needed to draw a cell

NO_DATA = "#e4e3df"


def build_grid(outline_paths, step_km):
    """A masked grid over the country: inside the coastline, nothing outside."""
    xs, ys = [], []
    for p in outline_paths:
        v = p.vertices
        xs.append(v[:, 0]); ys.append(v[:, 1])
    x0, x1 = float(np.min(np.concatenate(xs))), float(np.max(np.concatenate(xs)))
    y0, y1 = float(np.min(np.concatenate(ys))), float(np.max(np.concatenate(ys)))
    step = step_km / EARTH_KM
    gx = np.arange(x0, x1 + step, step)
    gy = np.arange(y0, y1 + step, step)
    GX, GY = np.meshgrid(gx, gy)
    pts = np.column_stack([GX.ravel(), GY.ravel()])
    inside = np.zeros(len(pts), dtype=bool)
    for p in outline_paths:
        inside |= p.contains_points(pts)
    return gx, gy, GX, GY, inside.reshape(GX.shape)


def smooth(px, py, weights, values, GX, GY, h_km):
    """Vote-weighted Gaussian kernel smoothing.

    Returns (estimate, weight) where estimate is sum(w_i K_i v_i)/sum(w_i K_i)
    and weight is sum(w_i K_i) -- the second is what says whether the first
    means anything.
    """
    h = h_km / EARTH_KM
    tree = cKDTree(np.column_stack([px, py]))
    grid = np.column_stack([GX.ravel(), GY.ravel()])
    num = np.zeros(len(grid))
    den = np.zeros(len(grid))
    # Query in chunks: the full pairwise matrix would be 2,042 x ~80,000.
    for lo in range(0, len(grid), 4000):
        chunk = grid[lo:lo + 4000]
        idx = tree.query_ball_point(chunk, CUTOFF * h)
        for j, neigh in enumerate(idx):
            if not neigh:
                continue
            neigh = np.asarray(neigh)
            d = np.hypot(chunk[j, 0] - px[neigh], chunk[j, 1] - py[neigh])
            k = np.exp(-0.5 * (d / h) ** 2)
            w = k * weights[neigh]
            den[lo + j] = w.sum()
            if values is not None:
                num[lo + j] = (w * values[neigh]).sum()
    with np.errstate(invalid="ignore", divide="ignore"):
        est = np.where(den > 0, num / np.maximum(den, 1e-30), np.nan)
    return est.reshape(GX.shape), den.reshape(GX.shape)


def draw_field(field, mask, inside, gx, gy, edges, colours, title, subtitle,
               unit_label, gov, outline, footnote, out_stem, masked_label):
    fig, ax = plt.subplots(figsize=(6.85, 8.1), facecolor=SURFACE)
    ax.set_aspect("equal")
    ax.set_axis_off()
    ax.set_facecolor(SURFACE)

    shown = np.ma.masked_where(~mask, field)
    # Filled contours at the choropleths' own class breaks, so the surface and
    # the tiles can be read against each other.
    ax.contourf(gx, gy, shown, levels=edges, colors=colours, extend="both",
                zorder=1)
    # Grey means "inside the country but too little data to estimate". It must
    # be clipped to the coastline: filled over the whole bounding box it painted
    # the sea as well, which reads as a data category rather than as absence.
    unsupported = np.ma.masked_where(~(inside & ~mask), np.ones_like(field))
    ax.contourf(gx, gy, unsupported, levels=[0.5, 1.5], colors=[NO_DATA], zorder=2)

    ax.add_collection(PathCollection(gov, facecolors="none", edgecolors=GOV_LINE,
                                     linewidths=0.5, zorder=3))
    ax.add_collection(PathCollection(outline, facecolors="none",
                                     edgecolors="#6f6e6a", linewidths=0.8, zorder=3))
    ax.autoscale_view()
    x0, x1 = ax.get_xlim()
    ax.set_xlim(x1 - 1.80 * (x1 - x0), x1)

    ax.text(0.01, 0.985, title, transform=ax.transAxes, fontsize=13, color=INK,
            va="top", ha="left", fontweight="bold")
    ax.text(0.01, 0.945, subtitle, transform=ax.transAxes, fontsize=9,
            color=INK_2, va="top", ha="left")

    handles = [Patch(facecolor=colours[i], edgecolor="none",
                     label=f"{edges[i]:,.1f} – {edges[i+1]:,.1f}")
               for i in range(len(edges) - 1)]
    handles.append(Patch(facecolor=NO_DATA, edgecolor="none", label=masked_label))
    leg = ax.legend(handles=handles, title=unit_label, loc="upper left",
                    bbox_to_anchor=(0.01, 0.83), frameon=False, fontsize=8.0,
                    title_fontsize=8.5, handlelength=1.0, handleheight=1.0,
                    labelspacing=0.30, borderaxespad=0)
    leg.get_title().set_color(INK_2)
    for t in leg.get_texts():
        t.set_color(INK_2)

    fig.text(0.015, 0.012, footnote, fontsize=6.5, color=INK_2, va="bottom")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    made = []
    for ext in FORMATS:
        out = f"{MAPS_DIR}/{out_stem}.{ext}"
        fig.savefig(out, dpi=300, facecolor=SURFACE, bbox_inches="tight")
        made.append(out)
    plt.close(fig)
    return made


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bandwidth", type=float, default=BANDWIDTH_KM,
                    help="Gaussian bandwidth in km")
    ap.add_argument("--grid", type=float, default=GRID_KM)
    ap.add_argument("--report", action="store_true",
                    help="print coverage diagnostics and exit")
    args = ap.parse_args()

    rows = [r for r in read(IMADA_CSV)
            if r["lat"] and r["lon"] and r["candidate_sum"]
            and int(r["candidate_sum"]) > 0]
    outline = [p for p in (feature_path(f["geometry"], 0.01)
                           for f in load_layer("tun_admin0.geojson")) if p]
    gov = [p for p in (feature_path(f["geometry"], 0.008)
                       for f in load_layer("tun_admin2.geojson")) if p]

    px, py = albers([float(r["lon"]) for r in rows], [float(r["lat"]) for r in rows])
    votes = np.array([int(r["candidate_sum"]) for r in rows], dtype=float)

    gx, gy, GX, GY, inside = build_grid(outline, args.grid)
    # The imada table omits the 41 stations whose sector never matched an imada,
    # so this surface rests on slightly fewer votes than the national total. Say
    # which total is which rather than reporting "100%" of a subset.
    national = 2527415
    print(f"{len(rows)} imada samples · {votes.sum():,.0f} certified valid votes "
          f"({100*votes.sum()/national:.2f}% of the national {national:,}; the "
          f"remainder is stations whose imada is unmatched)")
    print(f"grid {GX.shape[1]}x{GX.shape[0]} at {args.grid} km, "
          f"{int(inside.sum()):,} cells inside the coastline")

    _, weight = smooth(px, py, votes, None, GX, GY, args.bandwidth)
    supported = inside & (weight >= MIN_VOTES)
    print(f"bandwidth {args.bandwidth} km · supported cells "
          f"{int(supported.sum()):,} of {int(inside.sum()):,} inside "
          f"({100*supported.sum()/inside.sum():.1f}%)")
    # how much of the electorate sits under the supported area
    tree = cKDTree(np.column_stack([GX[supported], GY[supported]]))
    near = tree.query(np.column_stack([px, py]))[0] <= args.grid / EARTH_KM * 1.5
    print(f"  votes inside the supported area: {votes[near].sum():,.0f} "
          f"({100*votes[near].sum()/votes.sum():.2f}% of the sampled votes, "
          f"{100*votes[near].sum()/national:.2f}% of the national total)")
    if args.report:
        return

    cell_km2 = args.grid ** 2
    made = []
    for key, field_col, label, unit_label in PANELS:
        vals = np.array([float(r[field_col]) for r in rows])
        est, _w = smooth(px, py, votes, vals, GX, GY, args.bandwidth)
        edges = quantile_edges([v for v in vals], len(RAMP))
        made += draw_field(
            est, supported, inside, gx, gy, edges, RAMP, label,
            f"kernel-smoothed surface · {args.bandwidth:.0f} km Gaussian · "
            f"vote-weighted",
            unit_label, gov, outline,
            "2024 Tunisian presidential election · each imada centroid is a sample, "
            "weighted by its certified valid votes.\nClass breaks are the imada "
            f"quantiles, as in the choropleths. Grey: fewer than {MIN_VOTES:,.0f} "
            "votes within the kernel, so no estimate is drawn.\n"
            "Boundaries: OCHA/HDX COD-AB (CC BY-IGO).",
            f"{key}_kde", f"under {MIN_VOTES:,.0f} votes in kernel")

    # vote density: the question a share surface cannot answer
    h = args.bandwidth / EARTH_KM
    _, wdens = smooth(px, py, votes, None, GX, GY, args.bandwidth)
    # Gaussian kernel normalised to a density: votes per km^2
    dens = wdens / (2 * math.pi * (args.bandwidth ** 2))
    dvals = dens[supported]
    edges = [float(np.percentile(dvals, q)) for q in (0, 20, 40, 60, 75, 87, 95, 100)]
    for i in range(1, len(edges)):
        if edges[i] <= edges[i - 1]:
            edges[i] = edges[i - 1] + 1e-9
    made += draw_field(
        dens, supported, inside, gx, gy, edges, RAMP,
        "Vote density", f"kernel-smoothed surface · {args.bandwidth:.0f} km Gaussian",
        "certified valid votes per km²", gov, outline,
        "2024 Tunisian presidential election · certified valid votes per square "
        "kilometre, from imada centroids.\nClass breaks are percentiles of the "
        f"surface itself. Grey: fewer than {MIN_VOTES:,.0f} votes within the "
        "kernel.\nBoundaries: OCHA/HDX COD-AB (CC BY-IGO).",
        "vote_density_kde", f"under {MIN_VOTES:,.0f} votes in kernel")

    for m in made:
        print(f"    {os.path.getsize(m):>9,}  {m}")


if __name__ == "__main__":
    main()
