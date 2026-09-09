"""Zoomed sheets: Greater Tunis and each of the 24 governorates, imada by imada.

Why zoom
--------
The national imada map has 2,084 units on one page. It shows the country's
structure and hides everything inside a city: Greater Tunis alone is 334 imadas
squeezed into about 1% of the page, so the four governorates that cast a fifth
of the vote are unreadable at national scale. These sheets give each governorate
the whole page.

One sheet per extent, four panels: the three candidates and Saied's margin over
his strongest rival, the same quartet as `maps/composite_imada.*`.

**Class breaks are the national imada quantiles, not local ones.** This is the
choice that makes the set worth having. Local breaks would maximise contrast
inside each governorate, but every sheet would then use a different scale and
none could be compared with another or with the national map -- 25 pretty,
mutually unintelligible pictures. With national breaks a shade means the same
share on every sheet, so a governorate that is uniformly pale really is
uniformly weak for that candidate rather than merely flat in its own terms. The
cost is that a homogeneous governorate looks flat, which is true, and the panel
subtitle prints the extent's own observed range so nothing is hidden.

Context, not islands
--------------------
Each panel draws the extent's imadas in colour and its neighbours in a light
grey, then clamps the view to the extent. Without the neighbours a small
governorate floats on white paper with nothing to place it against; with them
the coastline and the borders read normally. Only imadas whose bounding box
touches the padded extent are drawn, so a sheet carries its surroundings rather
than all 2,084 units.
"""

import argparse
import collections
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import PathCollection

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from make_maps import (ARCHIVE, GOV_LINE, GUTTER, INK, INK_2, MAPS_DIR,
                       NO_DATA, PANELS, RAMP, SURFACE, class_of, draw,
                       feature_path, load_layer, quantile_edges, read,
                       save_figure)

IMADA_CSV = "data/imada_margins.csv"
TOL = 0.0015              # finer than the national map: there is room for it
CONTEXT = "#eeedea"       # neighbouring imadas, present for orientation only
PANEL_W = 5.6
PAD = 0.04                # of the extent's larger side

GRAND_TUNIS = ("grand_tunis", "Greater Tunis",
               ["TN11", "TN12", "TN13", "TN14"])

FOOT = ("2024 Tunisian presidential election · shares of valid votes at "
        "certified stations · imada level · boundaries OCHA/HDX COD-AB "
        "(CC BY-IGO)")


def bbox(paths):
    xs = np.concatenate([p.vertices[:, 0] for p in paths])
    ys = np.concatenate([p.vertices[:, 1] for p in paths])
    return xs.min(), ys.min(), xs.max(), ys.max()


def window(paths):
    """The visible rectangle for an extent, and the extent's padded box.

    draw() opens a legend column by widening the x-limits, so the view reaches
    further left than the extent itself -- which is also the region a context
    layer has to cover, and the reason the context is selected against this
    rectangle rather than against a distance guessed in projection units.
    """
    x0, y0, x1, y1 = bbox(paths)
    pad = PAD * max(x1 - x0, y1 - y0)
    x0, y0, x1, y1 = x0 - pad, y0 - pad, x1 + pad, y1 + pad
    return (x1 - GUTTER * (x1 - x0), y0, x1, y1)


def sheet(title, paths, others, gov, rows, edges, view, out_stem):
    """One four-panel sheet for one extent."""
    vx0, vy0, vx1, vy1 = view
    # Size the figure to the visible rectangle so the panels fill their cells
    # instead of shrinking inside them under equal aspect.
    aspect = (vy1 - vy0) / (vx1 - vx0)
    fig, axes = plt.subplots(2, 2, figsize=(2 * PANEL_W,
                                            2 * PANEL_W * aspect + 1.35),
                             facecolor=SURFACE)

    n = len(paths)
    for ax, (key, field, label, unit_label) in zip(axes.ravel(), PANELS):
        vals = [float(rows[c][field]) for c in paths
                if c in rows and rows[c][field] != ""]
        buckets = collections.defaultdict(list)
        for code, path in paths.items():
            r = rows.get(code)
            if not r or r[field] == "":
                buckets[NO_DATA].append(path)
            else:
                buckets[RAMP[class_of(float(r[field]), edges[key])]].append(path)
        # neighbours first, so the extent's own units sit on top of them
        ax.add_collection(PathCollection(others, facecolors=CONTEXT,
                                         edgecolors="#ffffff", linewidths=0.10,
                                         zorder=1))
        # The count goes in the subtitle rather than under the legend: these
        # panels set their own aspect, and draw()'s axes-fraction offset for it
        # only holds at roughly the national map's shape.
        sub = (f"{n} imadas · {min(vals):.1f}–{max(vals):.1f}% here" if vals
               else f"{n} imadas · no result in this extent")
        draw(ax, buckets, gov, label, sub, edges[key], unit_label, n,
             n - len(vals), compact=True, units_note=False)
        # clamp to the extent: draw() autoscaled to everything including the
        # neighbours, which would undo the zoom
        ax.set_xlim(vx0, vx1)
        ax.set_ylim(vy0, vy1)

    fig.suptitle(title, fontsize=16, color=INK, x=0.012, ha="left", y=0.992,
                 fontweight="bold")
    fig.text(0.012, 0.012,
             "Class breaks are the NATIONAL imada quantiles, identical on every "
             "sheet, so a shade means the same share here as anywhere else and "
             "as on the national maps. Each panel's subtitle gives this extent's "
             "own range.\nNeighbouring imadas are drawn in light grey for "
             "orientation and carry no value. " + FOOT,
             fontsize=7.5, color=INK_2, va="bottom")
    fig.tight_layout(rect=(0, 0.052, 1, 0.968))
    made = save_figure(fig, f"{MAPS_DIR}/{out_stem}")
    plt.close(fig)
    return made


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", help="build one extent by slug (e.g. grand_tunis)")
    ap.add_argument("--list", action="store_true", help="list the extents")
    args = ap.parse_args()
    if not os.path.exists(ARCHIVE):
        sys.exit(f"missing {ARCHIVE}; run tools/fetch_boundaries.py")
    os.makedirs(MAPS_DIR, exist_ok=True)

    feats = load_layer("tun_admin4.geojson")
    rows = {r["adm4_pcode"]: r for r in read(IMADA_CSV)
            if r["candidate_sum"] and int(r["candidate_sum"]) > 0}

    # Build every imada path once; the extents only partition them.
    paths, gov_of, boxes = {}, {}, {}
    for f in feats:
        p = f["properties"]
        path = feature_path(f["geometry"], TOL)
        if path is None:
            continue
        code = p["adm4_pcode"]
        paths[code] = path
        gov_of[code] = p["adm2_pcode"]
        v = path.vertices
        boxes[code] = (v[:, 0].min(), v[:, 1].min(), v[:, 0].max(), v[:, 1].max())
    gov_paths = [p for p in (feature_path(f["geometry"], TOL * 3)
                             for f in load_layer("tun_admin2.geojson")) if p]

    # National breaks, computed once over every imada with a result -- the same
    # numbers the national imada maps use.
    edges = {}
    for key, field, _, _ in PANELS:
        vals = [float(r[field]) for r in rows.values() if r[field] != ""]
        edges[key] = quantile_edges(vals, len(RAMP))

    names = {f["properties"]["adm2_pcode"]: f["properties"]["adm2_name"]
             for f in load_layer("tun_admin2.geojson")}
    extents = [GRAND_TUNIS]
    for code in sorted(names):
        slug = (names[code].lower().replace(" ", "_").replace("é", "e")
                .replace("è", "e"))
        extents.append((slug, f"{names[code]} governorate", [code]))

    if args.list:
        for slug, title, govs in extents:
            print(f"  {slug:<14} {title:<26} {' '.join(govs)}")
        return

    total = 0
    for slug, title, govs in extents:
        if args.only and args.only != slug:
            continue
        want = set(govs)
        mine = {c: p for c, p in paths.items() if gov_of[c] in want}
        if not mine:
            print(f"  {slug}: no imadas, skipped")
            continue
        view = window(list(mine.values()))
        vx0, vy0, vx1, vy1 = view
        others = [p for c, p in paths.items()
                  if c not in mine
                  and boxes[c][2] >= vx0 and boxes[c][0] <= vx1
                  and boxes[c][3] >= vy0 and boxes[c][1] <= vy1]

        votes = sum(int(rows[c]["candidate_sum"]) for c in mine if c in rows)
        cand = {k: sum(int(rows[c][k]) for c in mine if c in rows)
                for k, _, _, _ in PANELS if k != "margin"}
        made = sheet(title, mine, others, gov_paths, rows, edges, view,
                     f"zoom_{slug}")
        total += len(made)
        shares = " / ".join(f"{100*cand[k]/votes:.1f}" for k in
                            ("saied", "zammel", "maghzaoui"))
        print(f"{title}: {len(mine)} imadas, {votes:,} certified valid votes, "
              f"shares {shares}, {len(others)} neighbours for context")
        for m in made:
            print(f"    {os.path.getsize(m):>9,}  {m}")
    print(f"\n{total} files")


if __name__ == "__main__":
    main()
