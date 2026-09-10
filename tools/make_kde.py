"""Kernel-smoothed surfaces of candidate support, and of vote density.

What these add over the choropleths
-----------------------------------
The choropleths and cartograms in `maps/national/` and `maps/cartograms/` show
one value per administrative unit, so every boundary is a hard edge that the
vote does not actually have.
These surfaces drop the units: each sample point is a place that voted, and the
value at any point is a distance-weighted average of the samples near it.
Regional structure shows up as regional structure rather than as 2,042 tiles.

Two different fields, because they answer different questions:

- **Support surfaces** (`*_kde`): a vote-weighted, kernel-smoothed *share*. This
  is a Nadaraya-Watson estimator -- weights are kernel times votes -- so a large
  imada pulls the local estimate more than a small one, and the result is a share
  rather than a count. Contoured on the same fixed 0-100% scale as the
  choropleths, so the two are directly comparable.
- **Vote density** (`vote_density_kde`): certified valid votes per square
  kilometre. Not a share at all, and on its own scale, because "where are the
  voters" is the question the share maps cannot answer.

The bandwidth is local, and that is not a preference
----------------------------------------------------
An earlier version smoothed everything with one 25 km Gaussian. That cannot be
right for this point pattern, whose spacing spans a factor of 650: the median
sample has a neighbour 4.2 km away, the densest 0.16 km, the sparsest 104.6 km.
A single 25 km kernel blurs six rings of Tunis imadas together while still
enclosing almost nothing in the deep desert.

So each sample carries its own bandwidth: `h_i` is the distance to its `KNN`-th
nearest neighbour -- at the default `KNN = 1`, literally the distance to the
nearest other place that voted. Chosen by leave-one-out cross-validation
(`--cv`), which estimates each sample's share from every other sample and
weights the error by the votes at stake:

    fixed  25 km (what this tool used to do)   MAE 4.003 pp
    fixed   1 km (the best fixed bandwidth)    MAE 3.077 pp
    local  k = 1 nearest neighbour             MAE 2.718 pp

Local beats *every* fixed bandwidth, not just the one it replaced, and the fixed
family has a genuine interior optimum -- pushed below 1 km it gets worse again
and starts leaving samples inestimable -- so this is a real minimum and not
cross-validation collapsing toward zero. No floor is imposed on `h_i`, because
every floor tested made the error worse.

Kernels are normalised per sample (`1 / 2*pi*h_i^2`), so a sample with a wide
kernel spreads its weight instead of carrying more of it. That keeps the density
surface a density: it integrates to the votes it was built from.

Where the estimate is not supported, it is not drawn
----------------------------------------------------
A local bandwidth widens until it reaches data, so unlike a fixed kernel it
always finds *something* -- which moves the honesty problem rather than solving
it. A cell in the deep desert now gets an estimate built from one imada 100 km
away, and that must not be drawn as though it were measured.

Support is therefore geographic and absolute: a cell is drawn only if the
nearest place that voted is within `SUPPORT_KM`. At 30 km -- about three times
the 95th percentile of the spacing between samples, 9.26 km -- that covers
89.2% of the land. The ladder is printed by `--report` so the trade-off is
visible rather than buried: 20 km keeps 81.1%, 25 km 85.6%, 40 km 94.0%.

An absolute threshold is right for this even though the *bandwidth* must not be
fixed, because the two say different things. The bandwidth is a smoothing scale
and has to follow the local density; the mask is the claim that no observation
of this place exists, and "the nearest imada is 60 km away" is a fact about
geography, not about kernels.

Kish's effective sample size,

    n_eff = (sum_i k_i)^2 / sum_i k_i^2,     k_i = votes_i * phi_i(x)

was tried as the criterion first and measured to be wrong in *both* directions,
which is why it is reported but no longer masks: of the 9,243 land cells it
withheld at n_eff < 1.5, 4,409 had a sample within 30 km -- data right there and
nothing drawn -- while of the 16,773 cells more than 30 km from any observation
it happily drew 11,939. It conflates two opposite situations, an empty desert
and a cell sitting directly on a sample, because a near-interpolating kernel
makes one sample dominate in both.

`local_bandwidth_kde` publishes the smoothing scale as a map, so a reader can
see how far the estimate reached at every point rather than taking it on trust.

On the sample points
--------------------
The samples are imada centroids, because that is the finest geography the
published record supports: `data/pv_presidential_2024.csv` carries no
coordinates, and the finest boundary set available is admin4. Station-level
sampling needs station coordinates from outside this repo -- and note that
putting a station at its own imada's centroid would change nothing at all:
the imada tables are exact sums of their stations, so the Nadaraya-Watson
numerator and denominator come out identical term by term. `load_samples`
is the seam where a real station file would enter.
"""

import argparse
import math
import os
import sys
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import PathCollection
from matplotlib.patches import Patch
from scipy.spatial import cKDTree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from make_maps import (CMAP, GOV_LINE, INK, INK_2, PANELS, RAMP, SURFACE,
                       albers, feature_path, load_layer, quantile_edges, read,
                       colour_bar, PCT_VMIN, PCT_VMAX, SIGNED_PP,
                       FITTED_FAMILY, fitted_ticks,
                       figure_dir, save_figure)

FAMILY = "surfaces"
SAMPLE_CSV = "data/imada_margins.csv"
EARTH_KM = 6371.0            # albers() returns great-circle radians

KNN = 1                      # h_i = distance to the k-th nearest sample
GRID_KM = 1.0                # fine enough to resolve the smallest bandwidths
CUTOFF = 4.0                 # Gaussian weight beyond 4h is negligible
SUPPORT_KM = 30.0            # no sample within this: draw nothing
# Vote-weighted leave-one-out MAE, in percentage points, reproducible with --cv.
# Quoted on the fixed-bandwidth figures so a reader can see what the comparison
# set costs against the local rule.
LOCAL_CV_MAE = 2.718
FIXED_CV_MAE = {1.0: 3.077, 2.0: 3.138, 5.0: 3.352, 10.0: 3.548, 15.0: 3.725,
                20.0: 3.883, 25.0: 4.003, 30.0: 4.101, 40.0: 4.242, 60.0: 4.403}
NATIONAL_VALID = 2527415     # the published certified valid total

NO_DATA = "#e4e3df"
FOOT_COLS = 128           # characters per footnote line at 6.5 pt on 6.85 in


# ---- samples -------------------------------------------------------------
def load_samples(path=SAMPLE_CSV):
    """Sample points, their vote weights, and the fields to smooth.

    Returns (rows, P, votes, values) with P in kilometres, one row per place
    that voted. This is the seam for a station-level point file: everything
    downstream only wants coordinates, weights and per-sample values.
    """
    rows = [r for r in read(path)
            if r["lat"] and r["lon"] and r["candidate_sum"]
            and int(r["candidate_sum"]) > 0]
    px, py = albers([float(r["lon"]) for r in rows], [float(r["lat"]) for r in rows])
    P = np.column_stack([px, py]) * EARTH_KM
    votes = np.array([int(r["candidate_sum"]) for r in rows], dtype=float)
    values = np.array([[float(r[col]) for r in rows] for _, col, _, _ in PANELS])
    return rows, P, votes, values


def local_bandwidth(P, knn=KNN):
    """h_i = distance in km to the knn-th nearest sample.

    No floor and no cap: cross-validation rejected every one that was tried.
    """
    d = cKDTree(P).query(P, k=knn + 1)[0][:, knn]
    return d


# ---- estimation ----------------------------------------------------------
def build_grid(outline_paths, step_km):
    """A grid over the country in km, with a mask for what is inside the coast."""
    xs, ys = [], []
    for p in outline_paths:
        v = p.vertices
        xs.append(v[:, 0]); ys.append(v[:, 1])
    x0 = float(np.min(np.concatenate(xs))) * EARTH_KM
    x1 = float(np.max(np.concatenate(xs))) * EARTH_KM
    y0 = float(np.min(np.concatenate(ys))) * EARTH_KM
    y1 = float(np.max(np.concatenate(ys))) * EARTH_KM
    gx = np.arange(x0, x1 + step_km, step_km)
    gy = np.arange(y0, y1 + step_km, step_km)
    GX, GY = np.meshgrid(gx, gy)
    pts = np.column_stack([GX.ravel(), GY.ravel()]) / EARTH_KM
    inside = np.zeros(len(pts), dtype=bool)
    for p in outline_paths:
        inside |= p.contains_points(pts)
    return gx, gy, GX.shape, inside.reshape(GX.shape)


def smooth(P, h, votes, values, gx, gy, cutoff=CUTOFF):
    """Adaptive-bandwidth Gaussian smoothing, accumulated sample by sample.

    Each sample gets its own kernel, normalised to unit mass, so the returned
    `den` is votes per square kilometre and the ratio `num/den` is a share.

    Returns (num, den, sumsq, hbar_num):
      den       sum_i votes_i phi_i          -- vote density
      num       sum_i votes_i phi_i v_i      -- one plane per field in `values`
      sumsq     sum_i (votes_i phi_i)^2      -- for the effective sample size
      hbar_num  sum_i votes_i phi_i h_i      -- for the bandwidth actually used

    Anchoring the kernel at the sample rather than querying per grid cell is
    what makes a per-sample bandwidth cheap: each sample touches only the window
    its own kernel reaches.
    """
    shape = (len(gy), len(gx))
    nf = 0 if values is None else len(values)
    num = np.zeros((nf,) + shape)
    den = np.zeros(shape)
    sumsq = np.zeros(shape)
    hbar = np.zeros(shape)
    step = gx[1] - gx[0]
    cell = step * step

    for i in range(len(P)):
        x, y, hi, wi = P[i, 0], P[i, 1], h[i], votes[i]
        r = cutoff * hi
        i0, i1 = np.searchsorted(gx, x - r), np.searchsorted(gx, x + r, "right")
        j0, j1 = np.searchsorted(gy, y - r), np.searchsorted(gy, y + r, "right")
        if i0 >= i1 or j0 >= j1:
            # The kernel is narrower than one grid cell and fell between nodes.
            # Drop it on the nearest cell instead of losing its votes: this is
            # discretisation, and it is what keeps the density integrable.
            i0 = min(max(int(np.searchsorted(gx, x)) - 1, 0), len(gx) - 1)
            j0 = min(max(int(np.searchsorted(gy, y)) - 1, 0), len(gy) - 1)
            i1, j1 = i0 + 1, j0 + 1
            k = np.array([[wi / cell]])
        else:
            dx = gx[i0:i1] - x
            dy = gy[j0:j1] - y
            d2 = dy[:, None] ** 2 + dx[None, :] ** 2
            k = wi * np.exp(-0.5 * d2 / hi ** 2) / (2 * math.pi * hi ** 2)
        den[j0:j1, i0:i1] += k
        sumsq[j0:j1, i0:i1] += k * k
        hbar[j0:j1, i0:i1] += k * hi
        for f in range(nf):
            num[f, j0:j1, i0:i1] += k * values[f][i]
    return num, den, sumsq, hbar


def ratio(num, den):
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(den > 0, num / np.maximum(den, 1e-300), np.nan)


def effective_n(den, sumsq):
    """Kish's effective sample size: how many samples actually speak here."""
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(sumsq > 0, den ** 2 / np.maximum(sumsq, 1e-300), 0.0)


# ---- cross-validation ----------------------------------------------------
def cross_validate(P, votes, values, field=0):
    """Leave-one-out: estimate each sample's value from all the others.

    Errors are weighted by the sample's votes, because getting Tunis wrong
    matters more than getting a 300-vote oasis wrong. Printed rather than
    asserted, so the bandwidth choice stays auditable.
    """
    n = len(P)
    D = np.sqrt(((P[:, None, :] - P[None, :, :]) ** 2).sum(-1))
    np.fill_diagonal(D, np.inf)
    tree = cKDTree(P)
    v = values[field]

    def score(h):
        h = np.broadcast_to(np.asarray(h, float), (n,))
        K = np.exp(-0.5 * (D / h[None, :]) ** 2) / (h[None, :] ** 2)
        est = ratio((K * (votes * v)[None, :]).sum(1), (K * votes[None, :]).sum(1))
        ok = np.isfinite(est)
        mae = np.average(np.abs(est[ok] - v[ok]), weights=votes[ok])
        rmse = math.sqrt(np.average((est[ok] - v[ok]) ** 2, weights=votes[ok]))
        return mae, rmse, int(ok.sum())

    _, col, label, _ = PANELS[field]
    print(f"leave-one-out cross-validation on {label} ({col}), "
          f"{n:,} samples, errors weighted by votes\n")
    print("  fixed bandwidth")
    for hk in (0.5, 1, 2, 5, 10, 15, 20, 25, 30, 40, 60):
        mae, rmse, m = score(float(hk))
        note = "   <- what this tool used to do" if hk == 25 else ""
        print(f"    h = {hk:>5} km    MAE {mae:6.3f} pp   RMSE {rmse:6.3f} pp"
              f"   estimable {m:>5}{note}")
    print("\n  local bandwidth: h_i = distance to the k-th nearest sample")
    best = None
    for kk in (1, 2, 3, 5, 8, 12, 20, 30):
        h = local_bandwidth(P, kk)
        mae, rmse, m = score(h)
        if best is None or mae < best[0]:
            best = (mae, kk)
        print(f"    k = {kk:>5}       MAE {mae:6.3f} pp   RMSE {rmse:6.3f} pp"
              f"   estimable {m:>5}   h km p50 {np.percentile(h, 50):6.2f}"
              f"  max {h.max():7.2f}")
    print(f"\n  best: k = {best[1]} at MAE {best[0]:.3f} pp")
    h = local_bandwidth(P, best[1])
    print("  floors on h_i, to show why none is imposed:")
    for floor in (1.0, 2.0, 3.0, 5.0):
        mae, _, _ = score(np.maximum(h, floor))
        print(f"    h_i >= {floor:>4} km   MAE {mae:6.3f} pp")


# ---- drawing -------------------------------------------------------------
def draw_field(field, mask, inside, gx, gy, edges, colours, title, subtitle,
               unit_label, gov, outline, footnote, out_stem, masked_label,
               fmt="{:,.1f}", open_top=False, family=FAMILY, colourbar=None,
               observed=None, marker=None, ticks=None, context=None):
    fig, ax = plt.subplots(figsize=(6.85, 8.1), facecolor=SURFACE)
    ax.set_aspect("equal")
    ax.set_axis_off()
    ax.set_facecolor(SURFACE)

    # contourf wants the same units as the boundary paths, which are radians
    cx, cy = gx / EARTH_KM, gy / EARTH_KM
    shown = np.ma.masked_where(~mask, field)
    if colourbar:
        # 193 levels over the fixed range is a half-point step on 0-100: fine
        # enough to read as continuous at print size, and contourf is the only
        # way to fill a gridded field here.
        vmin, vmax = colourbar
        ax.contourf(cx, cy, shown, levels=np.linspace(vmin, vmax, 193),
                    cmap=CMAP, vmin=vmin, vmax=vmax, extend="both", zorder=1)
    else:
        ax.contourf(cx, cy, shown, levels=edges, colors=colours, extend="both",
                    zorder=1)
    # Grey means "inside the country but too little data to estimate". It must
    # be clipped to the coastline: filled over the whole bounding box it painted
    # the sea as well, which reads as a data category rather than as absence.
    unsupported = np.ma.masked_where(~(inside & ~mask), np.ones_like(field))
    ax.contourf(cx, cy, unsupported, levels=[0.5, 1.5], colors=[NO_DATA], zorder=2)

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

    if colourbar:
        colour_bar(ax, colourbar[0], colourbar[1], unit_label, False,
                   observed, marker, ticks, context)
        leg = ax.legend(handles=[Patch(facecolor=NO_DATA, edgecolor="none",
                                       label=masked_label)],
                        loc="upper left", bbox_to_anchor=(0.01, 0.365),
                        frameon=False, fontsize=8.0, handlelength=1.0,
                        handleheight=1.0, labelspacing=0.30, borderaxespad=0)
        for t in leg.get_texts():
            t.set_color(INK_2)
        return _finish(fig, footnote, family, out_stem)
    handles = [Patch(facecolor=colours[i], edgecolor="none",
                     label=f"{fmt.format(edges[i])} – {fmt.format(edges[i+1])}")
               for i in range(len(edges) - 1)]
    if open_top:
        # A near-interpolating kernel makes the density surface very peaked, so
        # the top class runs to a maximum no reader needs: label it open-ended
        # rather than printing "18.2 – 6,944.6" and calling it a class.
        handles[-1] = Patch(facecolor=colours[len(edges) - 2], edgecolor="none",
                            label=f"{fmt.format(edges[-2])} and above")
    handles.append(Patch(facecolor=NO_DATA, edgecolor="none", label=masked_label))
    leg = ax.legend(handles=handles, title=unit_label, loc="upper left",
                    bbox_to_anchor=(0.01, 0.83), frameon=False, fontsize=8.0,
                    title_fontsize=8.5, handlelength=1.0, handleheight=1.0,
                    labelspacing=0.30, borderaxespad=0)
    leg.get_title().set_color(INK_2)
    for t in leg.get_texts():
        t.set_color(INK_2)

    return _finish(fig, footnote, family, out_stem)


def _finish(fig, footnote, family, out_stem):
    # Wrap to the figure's own width. bbox_inches="tight" expands the canvas
    # around anything that overflows, so an unwrapped footnote made each figure
    # as wide as its longest sentence -- and a comparison set whose members are
    # different sizes is a poor comparison set. Wrapped, every figure in this
    # family comes out identical in size whatever its caption says.
    footnote = "\n".join(textwrap.fill(line, FOOT_COLS) if line else ""
                         for line in footnote.split("\n"))
    fig.text(0.015, 0.012, footnote, fontsize=6.5, color=INK_2, va="bottom")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    made = save_figure(fig, f"{figure_dir(family)}/{out_stem}")
    plt.close(fig)
    return made


def percentile_edges(values, k=len(RAMP)):
    """Class breaks from the surface's own percentiles, strictly increasing."""
    qs = np.linspace(0, 100, k + 1)
    edges = [float(np.percentile(values, q)) for q in qs]
    for i in range(1, len(edges)):
        if edges[i] <= edges[i - 1]:
            edges[i] = edges[i - 1] + 1e-9
    return edges


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scale", choices=["fixed", "fitted", "both"],
                    default="fixed",
                    help="fitted also writes the share and margin surfaces "
                         "with the ramp spanning only the values each reaches, "
                         "into maps/fitted/. Vote density and the bandwidth "
                         "field are not percentages and have no fitted twin.")
    ap.add_argument("--knn", type=int, default=KNN,
                    help="h_i is the distance to this many nearest samples")
    ap.add_argument("--fixed", type=float, default=None,
                    help="use one fixed bandwidth in km instead (for comparison)")
    ap.add_argument("--grid", type=float, default=GRID_KM)
    ap.add_argument("--support-km", type=float, default=SUPPORT_KM,
                    help="draw nothing where the nearest sample is farther")
    ap.add_argument("--cv", action="store_true",
                    help="run the leave-one-out bandwidth comparison and exit")
    ap.add_argument("--report", action="store_true",
                    help="print coverage diagnostics and exit")
    args = ap.parse_args()

    rows, P, votes, values = load_samples()
    if args.cv:
        cross_validate(P, votes, values)
        return

    outline = [p for p in (feature_path(f["geometry"], 0.01)
                           for f in load_layer("tun_admin0.geojson")) if p]
    gov = [p for p in (feature_path(f["geometry"], 0.008)
                       for f in load_layer("tun_admin2.geojson")) if p]

    if args.fixed:
        h = np.full(len(P), float(args.fixed))
        band_desc = f"fixed {args.fixed:.0f} km bandwidth"
        band_line = f"fixed bandwidth · {args.fixed:.0f} km"
    else:
        h = local_bandwidth(P, args.knn)
        band_desc = ("nearest-neighbour distance" if args.knn == 1
                     else f"{args.knn}th-nearest-neighbour distance")
        band_line = ("local bandwidth · nearest neighbour" if args.knn == 1
                     else f"local bandwidth · {args.knn}th neighbour")

    gx, gy, shape, inside = build_grid(outline, args.grid)
    # The imada table omits the stations whose sector never matched an imada,
    # so this surface rests on slightly fewer votes than the national total. Say
    # which total is which rather than reporting "100%" of a subset.
    print(f"{len(rows):,} sample points · {votes.sum():,.0f} certified valid votes "
          f"({100*votes.sum()/NATIONAL_VALID:.2f}% of the national "
          f"{NATIONAL_VALID:,}; the remainder is stations whose imada is "
          f"unmatched)")
    print(f"grid {shape[1]}x{shape[0]} at {args.grid} km, "
          f"{int(inside.sum()):,} cells inside the coastline")
    print(f"bandwidth: {band_desc} · km  min {h.min():.2f}  p05 {np.percentile(h,5):.2f}"
          f"  p50 {np.percentile(h,50):.2f}  p95 {np.percentile(h,95):.2f}"
          f"  max {h.max():.2f}")

    num, den, sumsq, hbar = smooth(P, h, votes, values, gx, gy)
    GXs, GYs = np.meshgrid(gx, gy)
    reach = cKDTree(P).query(np.column_stack([GXs.ravel(), GYs.ravel()]))[0]
    reach = reach.reshape(den.shape)
    supported = inside & (reach <= args.support_km)
    land = int(inside.sum())
    print(f"support: a sample within {args.support_km:.0f} km on "
          f"{int(supported.sum()):,} of {land:,} cells inside the coast "
          f"({100*supported.sum()/land:.1f}%)")
    for t in (10, 15, 20, 25, 30, 40, 60):
        s = inside & (reach <= t)
        print(f"    within {t:>3} km -> {100*s.sum()/land:5.1f}% of the land")
    # Reported, not used: measured wrong in both directions as a support test.
    n_eff = effective_n(den, sumsq)
    m = inside & (n_eff < 1.5)
    print(f"effective sample size on land: p01 {np.percentile(n_eff[inside],1):.2f} "
          f"p50 {np.percentile(n_eff[inside],50):.2f} "
          f"max {n_eff[inside].max():.2f}. Rejected as the support test: of the "
          f"{int(m.sum()):,} cells it would withhold, "
          f"{int((m & (reach <= args.support_km)).sum()):,} have a sample within "
          f"{args.support_km:.0f} km; and of the "
          f"{int((inside & (reach > args.support_km)).sum()):,} cells with none, "
          f"it would still draw "
          f"{int((inside & (reach > args.support_km) & (n_eff >= 1.5)).sum()):,}")

    # Mass: the density surface should still total the votes it was built from.
    cell = args.grid ** 2
    print(f"mass: {den.sum()*cell:,.0f} votes integrated over the grid "
          f"({100*den.sum()*cell/votes.sum():.2f}% of the {votes.sum():,.0f} "
          f"sampled); {100*den[inside].sum()*cell/votes.sum():.2f}% of it falls "
          f"on land, the rest is kernel mass pushed offshore or over the border")
    # how much of the electorate sits under the supported area
    if supported.any():
        tree = cKDTree(np.column_stack([GXs[supported], GYs[supported]]))
        near = tree.query(P)[0] <= args.grid * 1.5
        print(f"votes inside the supported area: {votes[near].sum():,.0f} "
              f"({100*votes[near].sum()/votes.sum():.2f}% of the sampled votes, "
              f"{100*votes[near].sum()/NATIONAL_VALID:.2f}% of the national total)")
    if args.report:
        return

    masked = f"no imada within {args.support_km:.0f} km"
    # A fixed-bandwidth render is a comparison set, not a replacement, so it
    # goes to its own filenames instead of overwriting the local-bandwidth maps.
    suffix = "" if not args.fixed else f"_{args.fixed:.0f}km"
    if args.fixed:
        # Say what it is and what it costs. Calling a fixed kernel
        # cross-validated would be false: cross-validation rejected it.
        cost = FIXED_CV_MAE.get(round(float(args.fixed), 1))
        # Kept to about the width of the local set's longest line: with
        # bbox_inches="tight" a longer footnote widens the whole canvas, and a
        # comparison set that does not match the figures it is compared against
        # is a poor comparison set.
        band_sentence = (
            f"The bandwidth is a fixed {args.fixed:.0f} km, the same "
            "everywhere — published for comparison with the local-bandwidth "
            "maps.\nCross-validation prefers those"
            + (f": {LOCAL_CV_MAE:.3f} pp weighted MAE against {cost:.3f} pp "
               f"at {args.fixed:.0f} km." if cost else "."))
    else:
        band_sentence = (
            f"The bandwidth is local: every sample is smoothed over its own "
            f"{band_desc} (median {np.percentile(h,50):.1f} km, max "
            f"{h.max():.0f} km), chosen by leave-one-out cross-validation.")
    provenance = (
        "2024 Tunisian presidential election · each imada centroid is a sample, "
        "weighted by its certified valid votes.\n" + band_sentence +
        "\nGrey: the nearest place that voted is more than "
        f"{args.support_km:.0f} km away, so no estimate is drawn. "
        "Boundaries: OCHA/HDX COD-AB (CC BY-IGO)."
    )
    # Two lines: one long subtitle overran the gutter and printed across Bizerte.
    subtitle = f"kernel-smoothed surface · vote-weighted\n{band_line}"

    made = []
    scales = ("fixed", "fitted") if args.scale == "both" else (args.scale,)
    for f, (key, col, label, unit_label) in enumerate(PANELS):
        est = ratio(num[f], den)
        obs = est[supported]
        tot = sum(sum(int(r[c]) for r in rows)
                  for c in ("saied", "zammel", "maghzaoui"))
        nat = {c: 100.0 * sum(int(r[c]) for r in rows) / tot
               for c in ("saied", "zammel", "maghzaoui")}
        # The margin panel is a difference of shares, so its scale is the
        # signed one and its reference is Saied's national lead over Zammel.
        signed = key == "margin"
        bar = SIGNED_PP if signed else (PCT_VMIN, PCT_VMAX)
        nat_share = (nat["saied"] - nat["zammel"]) if signed else nat[key]
        lo, hi = float(obs.min()), float(obs.max())
        for sc in scales:
            fit = sc == "fitted"
            gain = (bar[1] - bar[0]) / (hi - lo)
            note = (
                provenance + "\n" + (
                    f"THE SCALE IS FITTED TO THIS SURFACE: the ramp spans "
                    f"{lo:.1f} to {hi:.1f}, not the full "
                    f"{bar[0]:.0f} to {bar[1]:.0f}, which is about {gain:.1f} "
                    f"times the contrast of the fixed-scale version. The price "
                    f"is that a shade means nothing on any other figure; the "
                    f"strip beside the bar shows the window. For a comparable "
                    f"shade use maps/surfaces/{key}_kde{suffix}.*"
                    if fit else
                    "The scale is the fixed one every share figure here uses — "
                    "0–100% for a share, \u2212100 to +100 points for the "
                    "margin — so a shade means the same value as on the "
                    "choropleths; the bracket on the bar gives the range this "
                    "surface reaches"
                    # The fixed-10 km set exists to vary the bandwidth, not the
                    # scale, so it has no fitted twin and must not claim one.
                    + (f", and maps/fitted/{key}_kde.* is the same surface with "
                       "the ramp fitted to it." if not suffix else ".")))
            made += draw_field(
                est, supported, inside, gx, gy, None, RAMP, label, subtitle,
                unit_label, gov, outline, note,
                f"{key}_kde{suffix}", masked,
                colourbar=(lo, hi) if fit else bar,
                observed=None if fit else (lo, hi),
                marker=(nat_share, "national"),
                ticks=fitted_ticks(lo, hi) if fit else None,
                context=bar if fit else None,
                family=FITTED_FAMILY if fit else FAMILY)

    # vote density: the question a share surface cannot answer. `den` already is
    # votes per km^2, because every kernel was normalised to unit mass.
    made += draw_field(
        den, supported, inside, gx, gy, percentile_edges(den[supported]), RAMP,
        "Vote density", subtitle, "certified valid votes per km²", gov, outline,
        provenance + "\nClass breaks are percentiles of the surface itself. A "
        "local kernel concentrates each imada's votes into roughly its own "
        f"footprint, so the surface peaks near {den[supported].max():,.0f}/km².",
        f"vote_density_kde{suffix}", masked, open_top=True)

    # The bandwidth itself, published as a map rather than left as a claim: the
    # whole argument for a local kernel is that this field is not flat -- which
    # is also why there is no such map in fixed mode, where it would be.
    if args.fixed:
        print(f"    (no local_bandwidth map: at a fixed {args.fixed:.0f} km the "
              f"field is constant)")
    else:
      made += draw_field(
          ratio(hbar, den), supported, inside, gx, gy,
          percentile_edges(ratio(hbar, den)[supported]), RAMP,
          "Local bandwidth", f"the smoothing actually applied\n{band_line}",
          "kernel width in force (km)", gov, outline,
          provenance + "\nThe vote-weighted mean bandwidth of the samples "
          "contributing at each point: how far the estimate had to reach.",
          "local_bandwidth_kde", masked, fmt="{:,.1f}")

    for m in made:
        print(f"    {os.path.getsize(m):>9,}  {m}")


if __name__ == "__main__":
    main()
