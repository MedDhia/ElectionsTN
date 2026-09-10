"""Vote-weighted Dorling cartograms of the same four maps.

Why these exist
---------------
The choropleths in `maps/national/` are equal-area, which is right for weighing
colour but means the desert dominates the page: the ten largest delegations cover
**40.6% of the map and cast 2.29% of the votes**, and Remada alone is 17.6% of
the map against 0.08% of the vote. Reading those maps, the eye is drawn to
almost-empty territory.

A Dorling cartogram replaces each delegation with a circle whose **area is its
valid votes**, nudged apart until nothing overlaps but still near where it
belongs. Colour is the same fixed 0-100% scale on the same documented
ramp, so a cartogram and its choropleth are directly comparable: what changes
between them is only how much of the page each delegation is allowed to claim.

They are a companion to the choropleths, not a replacement. A cartogram distorts
shape and adjacency, so it answers "where are the voters, and how did they vote"
while the choropleth answers "what does the territory look like". Both are
published for that reason.

What the reader is owed, and gets
---------------------------------
- A **size legend**, because a cartogram whose circles have no stated scale is
  unreadable. Three reference circles at round vote counts.
- A **faint country outline** for orientation. The circles have moved, so the
  outline is context, not a claim about where they are.
- The **displacement** each circle needed, reported by the tool and bounded, so
  the geography is not quietly rearranged past recognition.
"""

import argparse
import collections
import csv
import itertools
import math
import textwrap
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import PathCollection
from matplotlib.lines import Line2D
from matplotlib.patches import Circle, Patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from make_maps import (GOV_LINE, HILITE, INK, INK_2, PANELS, RAMP,
                       SURFACE, albers, class_of, feature_path, load_layer,
                       quantile_edges, read, figure_dir, save_figure,
                       pct_colour, PCT_VMIN, PCT_VMAX, SIGNED_PP, colour_bar,
                       FITTED_FAMILY, fitted_ticks)

FAMILY = "cartograms"


def _wrap(text, cols=118):
    """Wrap before the figure is sized.

    save_figure uses bbox_inches="tight", which grows the canvas around any
    text that overflows it -- the fitted note pushed these figures 58% wider
    than their fixed twins before this.
    """
    return "\n".join(textwrap.fill(ln, cols) if ln else ""
                     for ln in text.split("\n"))
DELEG_CSV = "data/delegation_margins.csv"

# Circle areas sum to this fraction of the country's projected bounding box.
# Bigger circles are easier to read and displace more, so this was picked by
# measuring rather than by eye (see --report). At 0.30 / 0.36 / 0.42 the median
# displacement is 1.5% / 2.1% / 2.8% of the map diagonal, all with zero
# remaining overlap; 0.36 keeps circles legible while moving the median
# delegation about a fiftieth of the map.
FILL = 0.36
ITERATIONS = 600
SPRING = 0.02          # pull back toward the true centroid, per iteration


def dorling(x, y, r, iterations=ITERATIONS, spring=SPRING):
    """Nudge circles apart until they stop overlapping, staying near home.

    Each pass pushes every overlapping pair apart by half their overlap and
    applies a spring toward the original position, so the layout keeps the
    country's rough shape instead of drifting into a blob.

    The spring **decays to zero** across the run. With it held constant the two
    forces balance and the packing never converges: the first version left a
    worst overlap of 0.98% of the map diagonal, which is plainly visible as
    circles sitting on top of each other. Strong early keeps the geography;
    weakening late lets the last overlaps resolve.
    """
    x, y, r = x.astype(float).copy(), y.astype(float).copy(), r.astype(float)
    x0, y0 = x.copy(), y.copy()
    n = len(x)
    order = np.argsort(-r)          # place the largest first; they move least
    for _it in range(iterations):
        moved = 0.0
        for i in order:
            dx, dy = x - x[i], y - y[i]
            d = np.hypot(dx, dy)
            d[i] = np.inf
            need = r + r[i]
            hit = d < need
            if np.any(hit):
                over = (need[hit] - d[hit]) / 2.0
                ux, uy = dx[hit] / d[hit], dy[hit] / d[hit]
                x[hit] += ux * over
                y[hit] += uy * over
                x[i] -= np.sum(ux * over) / len(over)
                y[i] -= np.sum(uy * over) / len(over)
                moved += float(np.sum(over))
        decay = spring * max(0.0, 1.0 - 1.6 * _it / iterations)
        if decay > 0:
            x += (x0 - x) * decay
            y += (y0 - y) * decay
        if moved < 1e-9 and decay == 0:
            break
    return x, y, np.hypot(x - x0, y - y0)


def nice_sizes(vmax):
    """Three round reference values for the size legend."""
    step = 10 ** math.floor(math.log10(vmax))
    for cand in ([step, step * 2, step * 5], [step / 2, step, step * 2]):
        vals = [v for v in cand if v <= vmax]
        if len(vals) == 3:
            return [int(v) for v in vals]
    return [int(vmax / 4), int(vmax / 2), int(vmax)]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scale", choices=["fixed", "fitted", "both"],
                    default="fixed",
                    help="fitted also writes each cartogram with the ramp "
                         "spanning only the values it contains, into "
                         "maps/fitted/.")
    ap.add_argument("--report", action="store_true",
                    help="print packing diagnostics and exit without drawing")
    args = ap.parse_args()

    # Sized by the certified candidate sum, not the `valid` column, so area and
    # colour rest on the same basis. They differ by 601 votes (0.02%), all of it
    # from stations that publish a valid total but whose candidate figures are
    # not certified -- small, but sizing on one basis and colouring on another
    # would be a needless inconsistency to explain.
    rows = [r for r in read(DELEG_CSV)
            if r["candidate_sum"] and int(r["candidate_sum"]) > 0]
    outline = [p for p in (feature_path(f["geometry"], 0.01)
                           for f in load_layer("tun_admin0.geojson")) if p]
    gov = [p for p in (feature_path(f["geometry"], 0.008)
                       for f in load_layer("tun_admin2.geojson")) if p]

    lon = np.array([float(r["lon"]) for r in rows])
    lat = np.array([float(r["lat"]) for r in rows])
    votes = np.array([int(r["candidate_sum"]) for r in rows], dtype=float)
    x, y = albers(lon, lat)

    # scale radii so the circles fill FILL of the bounding box
    bbox = (x.max() - x.min()) * (y.max() - y.min())
    k = math.sqrt(FILL * bbox / (math.pi * votes.sum()))
    r = k * np.sqrt(votes)

    px, py, disp = dorling(x, y, r)

    # did the packing actually succeed?
    worst = 0.0
    for i in range(len(px)):
        d = np.hypot(px - px[i], py - py[i])
        d[i] = np.inf
        worst = max(worst, float(np.max((r + r[i]) - d)))
    scale = math.hypot(x.max() - x.min(), y.max() - y.min())
    print(f"{len(rows)} delegations · {votes.sum():,.0f} certified valid votes")
    print(f"  worst remaining overlap: {worst:.5f} ({100*worst/scale:.3f}% of the map diagonal)")
    print(f"  displacement: median {100*np.median(disp)/scale:.2f}%, "
          f"p90 {100*np.percentile(disp,90)/scale:.2f}%, "
          f"max {100*disp.max()/scale:.2f}% of the diagonal")
    print(f"  radius range: {r.min():.5f} to {r.max():.5f} "
          f"({r.max()/r.min():.1f}x, votes {votes.max()/votes.min():.1f}x)")
    if args.report:
        return

    lost = [i for i, rr in enumerate(rows)
            if rr.get("winner") and rr["winner"] != "saied"]

    tot = sum(sum(int(rr[c]) for rr in rows)
              for c in ("saied", "zammel", "maghzaoui"))
    nat_share = {c: 100.0 * sum(int(rr[c]) for rr in rows) / tot
                 for c in ("saied", "zammel", "maghzaoui")}

    scales = ("fixed", "fitted") if args.scale == "both" else (args.scale,)
    # Iterated as (panel, scale) pairs rather than nested, so the body below
    # needs no reindentation: the scale only changes `bar` and where it lands.
    for (key, field, label, unit_label), scale in itertools.product(PANELS,
                                                                   scales):
        vals = [float(rr[field]) for rr in rows if rr[field] != ""]
        signed = key == "margin"
        full = SIGNED_PP if signed else (PCT_VMIN, PCT_VMAX)
        fit = scale == "fitted" and vals and max(vals) > min(vals)
        bar = (min(vals), max(vals)) if fit else full
        ref = (nat_share["saied"] - nat_share["zammel"] if signed
               else nat_share[key])
        fig, ax = plt.subplots(figsize=(6.85, 8.1), facecolor=SURFACE)
        ax.set_aspect("equal")
        ax.set_axis_off()
        ax.set_facecolor(SURFACE)

        # context only: the circles have moved, so this is not a claim about
        # where any of them now sits
        ax.add_collection(PathCollection(gov, facecolors="none",
                                         edgecolors="#dedcd6", linewidths=0.4, zorder=1))
        ax.add_collection(PathCollection(outline, facecolors="none",
                                         edgecolors=GOV_LINE, linewidths=0.6, zorder=1))
        for i, rr in enumerate(rows):
            colour = (pct_colour(float(rr[field]), *bar)
                      if rr[field] != "" else "#e4e3df")
            ax.add_patch(Circle((px[i], py[i]), r[i], facecolor=colour,
                                edgecolor="#ffffff", linewidth=0.35, zorder=2))
        for i in lost:
            ax.add_patch(Circle((px[i], py[i]), r[i], facecolor="none",
                                edgecolor=HILITE, linewidth=1.4, zorder=3))

        ax.autoscale_view()
        x0, x1 = ax.get_xlim()
        ax.set_xlim(x1 - 1.80 * (x1 - x0), x1)

        ax.text(0.01, 0.985, label, transform=ax.transAxes, fontsize=13,
                color=INK, va="top", ha="left", fontweight="bold")
        ax.text(0.01, 0.945,
                "delegation cartogram · circle area = valid votes · "
                + (f"scale fitted to this map "
                   f"({100.0*(bar[1]-bar[0])/(full[1]-full[0]):.0f}% of the "
                   f"full range)" if fit else "fixed scale"),
                transform=ax.transAxes, fontsize=9, color=INK_2, va="top", ha="left")

        colour_bar(ax, bar[0], bar[1], unit_label, False,
                   None if fit else ((min(vals), max(vals)) if vals else None),
                   (ref, "national"),
                   fitted_ticks(*bar) if fit else None, full if fit else None)
        handles = []
        if lost:
            handles.append(Patch(facecolor="none", edgecolor=HILITE, linewidth=1.4,
                                 label=f"Saied did not lead ({len(lost)})"))
        if handles:
            leg = ax.legend(handles=handles, loc="upper left",
                            bbox_to_anchor=(0.01, 0.365), frameon=False,
                            fontsize=8.0, handlelength=1.0, handleheight=1.0,
                            labelspacing=0.30, borderaxespad=0)
            for t in leg.get_texts():
                t.set_color(INK_2)

        # Size legend: without a stated scale the circles mean nothing. Drawn
        # side by side rather than nested -- nested circles put their tops
        # within a fifth of a radius of each other, and at this figure size the
        # three labels overlapped into an illegible smear.
        sizes = nice_sizes(votes.max())
        xlo, xhi = ax.get_xlim()
        ylo, yhi = ax.get_ylim()
        rads = [k * math.sqrt(v) for v in sizes]
        # The pitch is set by the LABEL, not the circle. Spacing by radius put
        # "20,000" -- wider than the biggest circle -- straight through its
        # neighbours; a fixed pitch as a fraction of the axes width always fits.
        pitch = 0.085 * (xhi - xlo)
        cx = xlo + 0.045 * (xhi - xlo)
        cy = ylo + 0.115 * (yhi - ylo)
        ax.text(cx, cy + max(rads) * 2.9, "certified valid votes per delegation",
                fontsize=8.5, color=INK_2, ha="left", va="bottom")
        for i, (v, rad) in enumerate(zip(sizes, rads)):
            slot = cx + (i + 0.5) * pitch
            ax.add_patch(Circle((slot, cy + rad), rad, facecolor="none",
                                edgecolor=INK_2, linewidth=0.7, zorder=4))
            ax.text(slot, cy - max(rads) * 0.55, f"{v:,}", fontsize=7.5,
                    color=INK_2, ha="center", va="top")
        ax.plot([cx, cx + len(sizes) * pitch], [cy, cy], color=INK_2,
                linewidth=0.5, zorder=4)

        fig.text(0.015, 0.012,
                 _wrap(
                 (f"SCALE FITTED TO THIS MAP: the ramp spans {bar[0]:.1f} to "
                  f"{bar[1]:.1f}, not {full[0]:.0f} to {full[1]:.0f}, so a "
                  f"shade means nothing on any other figure. The strip beside "
                  f"the bar shows the window; maps/cartograms/{key}_cartogram.* "
                  f"is the comparable version.\n" if fit else "")
                 + "2024 Tunisian presidential election · circle area is valid votes at "
                 "certified stations, so area tracks the electorate rather than the "
                 "terrain.\nPositions are nudged apart from true centroids and are "
                 "approximate; the outline is orientation only. Boundaries: "
                 "OCHA/HDX COD-AB (CC BY-IGO)."),
                 fontsize=6.5, color=INK_2, va="bottom")
        fig.tight_layout(rect=(0, 0.035, 1, 1))
        for out in save_figure(
                fig,
                f"{figure_dir(FITTED_FAMILY if fit else FAMILY)}/"
                f"{key}_cartogram"):
            print(f"    {os.path.getsize(out):>9,}  {out}")
        plt.close(fig)


if __name__ == "__main__":
    main()
