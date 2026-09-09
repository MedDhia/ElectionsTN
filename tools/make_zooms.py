"""Zoomed sheets: Greater Tunis and each of the 24 governorates, imada by imada.

Why zoom
--------
The national imada map has 2,084 units on one page. It shows the country's
structure and hides everything inside a city: Greater Tunis alone is 334 imadas
squeezed into about 1% of the page, so the four governorates that cast a fifth
of the vote are unreadable at national scale. These sheets give each governorate
the whole page.

Two sheets per extent, on two bases, because no single basis is comparable in
every direction at once.

`zoom_*` -- four panels, the three candidates and Saied's margin over his
strongest rival, the same quartet as `maps/composite_imada.*`.

**Class breaks are the national imada quantiles, not local ones.** This is the
choice that makes the set worth having. Local breaks would maximise contrast
inside each governorate, but every sheet would then use a different scale and
none could be compared with another or with the national map -- 25 pretty,
mutually unintelligible pictures. With national breaks a shade means the same
share on every sheet, so a governorate that is uniformly pale really is
uniformly weak for that candidate rather than merely flat in its own terms. The
cost is that a homogeneous governorate looks flat, which is true, and the panel
subtitle prints the extent's own observed range so nothing is hidden.

`zoom_ratio_*` -- the three candidates on the shared-ratio basis of
`compare_ratio_*`: local share divided by that candidate's national share, in
half-powers of two either side of 1.00x.

**This is the one basis comparable on both axes at once.** The shares sheets can
be read across governorates but not across candidates, since their breaks are
each candidate's own quantiles. The ratio scale is national, so it does not
depend on the extent: a shade means the same thing between the three panels of
one sheet *and* between any two of the 25 sheets. Ariana's Zammel panel and
Kebili's Maghzaoui panel can be set side by side and read directly.

On these sheets the legend belongs to the figure, not to each panel: on a shared
scale three per-panel legends are three copies of one statement, and the gutter
each occupies is dead width. Sharing it gives that width back to the maps.

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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from make_maps import (ARCHIVE, GOV_LINE, GUTTER, INK, INK_2, MAPS_DIR,
                       NO_DATA, PANELS, RAMP, SURFACE, class_of, draw,
                       feature_path, load_layer, quantile_edges, read,
                       save_figure)
from make_comparative import (CANDIDATES, RATIO_EDGES, RATIO_LABELS,
                              national_shares)

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


CHROME_H = 1.35           # suptitle above, note and provenance below
TARGET_ASPECT = 0.78      # a landscape page; what the grid is chosen to hit


def pick_grid(n_panels, panel_aspect, line_only=False):
    """How many columns to lay the panels out in.

    A fixed grid cannot work here, because the governorates are not the same
    shape: three panels across wide, short Kébili gave a 17-by-3 inch strip with
    postage-stamp maps, while three across tall Tataouine is right. So choose the
    column count whose resulting figure comes closest to a landscape page, which
    is the arrangement that gives the maps the most of it.

    `line_only` keeps the panels in a single row or column. The comparative
    sheets need it: three panels in a 2x2 grid with an empty quadrant puts the
    third out of line with the others, and a set built for reading across should
    not ask the eye to turn a corner.
    """
    options = ([1, n_panels] if line_only and n_panels > 1
               else range(1, n_panels + 1))
    best = None
    for ncols in options:
        nrows = -(-n_panels // ncols)
        if (nrows - 1) * ncols >= n_panels:      # a grid with an empty row
            continue
        aspect = (nrows * PANEL_W * panel_aspect + CHROME_H) / (ncols * PANEL_W)
        score = abs(math.log(aspect / TARGET_ASPECT))
        if best is None or score < best[0]:
            best = (score, ncols, nrows)
    return best[1], best[2]


def sheet(title, paths, others, gov, view, out_stem, panels, note,
          line_only=False, shared=False):
    """One sheet for one extent; the panel grid follows the extent's shape.

    A panel is (label, unit_label, subtitle, value_of, edges, labels); both
    bases below are the same drawing, differing only in what each panel maps.
    """
    vx0, vy0, vx1, vy1 = view
    # With a shared legend there is no gutter, so the visible box is the extent
    # itself: mx0 is its true left edge, vx0 the gutter-widened one.
    mx0 = vx1 - (vx1 - vx0) / GUTTER
    # Size the figure to the visible rectangle so the panels fill their cells
    # instead of shrinking inside them under equal aspect.
    left = mx0 if shared else vx0
    aspect = (vy1 - vy0) / (vx1 - left)
    extra = 0.55 if shared else 0.0          # room for the shared legend strip
    ncols, nrows = pick_grid(len(panels), aspect, line_only)
    fig, axes = plt.subplots(nrows, ncols,
                             figsize=(ncols * PANEL_W,
                                      nrows * PANEL_W * aspect + CHROME_H
                                      + extra),
                             facecolor=SURFACE, squeeze=False)

    n = len(paths)
    for ax, (label, unit_label, sub, value_of, edges, labels) in zip(
            axes.ravel(), panels):
        buckets = collections.defaultdict(list)
        missing = 0
        for code, path in paths.items():
            v = value_of(code)
            if v is None:
                buckets[NO_DATA].append(path)
                missing += 1
            else:
                buckets[RAMP[class_of(v, edges)]].append(path)
        # neighbours first, so the extent's own units sit on top of them
        ax.add_collection(PathCollection(others, facecolors=CONTEXT,
                                         edgecolors="#ffffff", linewidths=0.10,
                                         zorder=1))
        draw(ax, buckets, gov, label, sub, edges, unit_label, n, missing,
             compact=True, units_note=False, labels=labels, legend=not shared)
        # clamp to the extent: draw() autoscaled to everything including the
        # neighbours, which would undo the zoom. Without a per-panel legend
        # there is no gutter to leave room for, so the map takes the full width.
        ax.set_xlim(mx0 if shared else vx0, vx1)
        ax.set_ylim(vy0, vy1)
    for ax in axes.ravel()[len(panels):]:
        ax.set_axis_off()

    if shared:
        # One legend for the sheet, not three copies of it. On a shared scale
        # the copies say the same thing, and the gutters holding them were what
        # made a row of three panels so wide.
        label_, unit_, _s, _v, edges, labels = panels[0]
        texts = labels or [f"{edges[i]:,.1f} – {edges[i+1]:,.1f}"
                           for i in range(len(RAMP))]
        handles = [Patch(facecolor=RAMP[i], edgecolor="#ffffff", linewidth=0.4,
                         label=texts[i]) for i in range(len(RAMP))]
        handles.append(Patch(facecolor=NO_DATA, edgecolor="#ffffff",
                             linewidth=0.4, label="no result"))
        leg = fig.legend(handles=handles, title=unit_ + " — one scale for all "
                         "three panels", loc="upper left", frameon=False,
                         bbox_to_anchor=(0.012, 0.945), ncol=len(handles),
                         fontsize=8.0, title_fontsize=8.5, handlelength=1.0,
                         handleheight=1.0, columnspacing=1.1, borderaxespad=0)
        leg.get_title().set_color(INK_2)
        leg.get_title().set_ha("left")
        for t in leg.get_texts():
            t.set_color(INK_2)

    fig.suptitle(title, fontsize=16, color=INK, x=0.012, ha="left", y=0.992,
                 fontweight="bold")
    # Wrap to the figure's own width. bbox_inches="tight" expands the canvas
    # around anything that overflows, so an unwrapped note made each sheet as
    # wide as its longest sentence -- and these sheets exist to be compared.
    cols = int(fig.get_figwidth() * 15.8)
    body = (note + "\nNeighbouring imadas are drawn in light grey for "
            "orientation and carry no value. " + FOOT)
    body = "\n".join(textwrap.fill(line, cols) if line else ""
                     for line in body.split("\n"))
    fig.text(0.012, 0.012, body, fontsize=7.5, color=INK_2, va="bottom")
    fig.tight_layout(rect=(0, 0.052, 1, 0.905 if shared else 0.968))
    made = save_figure(fig, f"{MAPS_DIR}/{out_stem}")
    plt.close(fig)
    return made


SHARES_NOTE = (
    "Class breaks are the NATIONAL imada quantiles, identical on every sheet, so "
    "a shade means the same share here as anywhere else and as on the national "
    "maps. Each panel's subtitle gives this extent's own range.")

RATIO_NOTE = (
    "ONE shared scale, and it is national — so this basis is comparable on BOTH "
    "axes at once: across the three panels, because a shade means the same "
    "multiple of that candidate's own national share with the boundary at 1.00× "
    "being that average; and across all 25 sheets, because the scale does not "
    "depend on the extent. The shares basis is comparable only across sheets, "
    "its breaks being each candidate's own quantiles.\nSaied is nearly flat "
    "because he cannot exceed 1.10×: at a 91.12% national share, a unit giving "
    "him 100% is only 1.10 times it.")


def shares_panels(paths, rows, edges):
    """The four candidate panels: each on its own national quantile breaks."""
    out = []
    n = len(paths)
    for key, field, label, unit_label in PANELS:
        vals = [float(rows[c][field]) for c in paths
                if c in rows and rows[c][field] != ""]
        # The count goes in the subtitle rather than under the legend: these
        # panels set their own aspect, and draw()'s axes-fraction offset for it
        # only holds at roughly the national map's shape.
        sub = (f"{n} imadas · {min(vals):.1f}–{max(vals):.1f}% here" if vals
               else f"{n} imadas · no result in this extent")

        def value_of(code, field=field):
            r = rows.get(code)
            return None if not r or r[field] == "" else float(r[field])
        out.append((label, unit_label, sub, value_of, edges[key], None))
    return out


def ratio_panels(paths, rows, nat):
    """The three candidates on one shared scale, in multiples of their own
    national share. The only basis here that can be read across panels."""
    out = []
    n = len(paths)
    for key, label in CANDIDATES:
        field = f"{key}_share_pct"
        vals = [float(rows[c][field]) / nat[key] for c in paths
                if c in rows and rows[c][field] != ""]
        sub = (f"{n} imadas · {min(vals):.2f}–{max(vals):.2f}× here · "
               f"national {nat[key]:.2f}%" if vals
               else f"{n} imadas · no result in this extent")

        def value_of(code, field=field, key=key):
            r = rows.get(code)
            if not r or r[field] == "":
                return None
            return float(r[field]) / nat[key]
        out.append((label, "local share ÷ this candidate's national share",
                    sub, value_of, RATIO_EDGES, RATIO_LABELS))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", help="build one extent by slug (e.g. grand_tunis)")
    ap.add_argument("--list", action="store_true", help="list the extents")
    ap.add_argument("--basis", choices=["shares", "ratio", "both"],
                    default="both",
                    help="shares: four panels on national quantile breaks. "
                         "ratio: three candidates on one shared scale, the "
                         "basis that can be read across panels")
    args = ap.parse_args()
    if not os.path.exists(ARCHIVE):
        sys.exit(f"missing {ARCHIVE}; run tools/fetch_boundaries.py")
    os.makedirs(MAPS_DIR, exist_ok=True)

    nat, _ = national_shares()
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
        made = []
        if args.basis in ("shares", "both"):
            made += sheet(title, mine, others, gov_paths, view,
                          f"zoom_{slug}", shares_panels(mine, rows, edges),
                          SHARES_NOTE)
        if args.basis in ("ratio", "both"):
            made += sheet(f"{title} · against each candidate's own average",
                          mine, others, gov_paths, view, f"zoom_ratio_{slug}",
                          ratio_panels(mine, rows, nat), RATIO_NOTE,
                          line_only=True, shared=True)
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
