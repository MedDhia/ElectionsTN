"""Zoomed maps: Greater Tunis, each of the 24 governorates, each of the 6
regions, imada by imada.

Why zoom
--------
The national imada map has 2,084 units on one page. It shows the country's
structure and hides everything inside a city: Greater Tunis alone is 334 imadas
squeezed into about 1% of the page, so the four governorates that cast a fifth
of the vote are unreadable at national scale. These give each extent the whole
page.

31 extents: Greater Tunis, the 24 governorates (selected by `adm2_pcode`) and
the 6 regions (by `adm1_pcode`, 155 to 585 imadas each). `--list` prints them
with the bases each one takes, `--only <slug>` builds one, `--extent` restricts
to a level.

Three bases, because no single one is comparable in every direction at once. The
25 governorate-scale extents take all three; the 6 regions take `micro` only,
for the reason recorded beside the extent table.

`zoom_*` -- four panels, the three candidates and Saied's margin over his
strongest rival, the same quartet as `maps/national/composite_imada.*`.

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

`micro_<extent>_<candidate>` -- one map per candidate per extent, 93 in all, on
**local** breaks: quantiles of that candidate's share among the imadas of that
extent alone.

**This is the basis that shows the variation inside an extent, which the other
two are built to suppress.** National breaks are what make a shade mean the same
thing everywhere, and the price is that a homogeneous governorate lands in one or
two classes with everything inside it flattened. Local breaks pay the opposite
price -- a shade means nothing outside its own map -- and buy the detail.

What that buys is not cosmetic. On national breaks Kebili's Maghzaoui panel is a
wash; on local breaks it runs 2.17% to **40.72%**, and the top imada is Bou
Abdellah, where he took 542 of 1,331 votes across 7 stations and outpolled Saied
in three of them (159-127, 129-91, 98-89). Every one of those stations matched
its imada exactly, score 1.0000, so this is a real local stronghold for a
candidate who took 1.89% nationally -- and it is invisible on every national map
in this directory.

These render to PDF and PNG rather than all three formats: 93 figures in three
formats would add about 80 MB to a `maps/` directory already at 300 MB, and the
PDF already carries the vector. `--formats pdf,png,svg` overrides that.

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

from make_maps import (ARCHIVE, GOV_LINE, GUTTER, INK, INK_2, NO_DATA, PANELS,
                       RAMP, SURFACE, class_of, draw, feature_path,
                       figure_dir, load_layer, quantile_edges, read,
                       save_figure)
from make_comparative import (CANDIDATES, RATIO_EDGES, RATIO_LABELS,
                              national_shares)

IMADA_CSV = "data/imada_margins.csv"
TOL = 0.0015              # finer than the national map: there is room for it
CONTEXT = "#eeedea"       # neighbouring imadas, present for orientation only
PANEL_W = 5.6
PAD = 0.04                # of the extent's larger side

# (slug, title, which pcode selects the imadas, the codes, which bases apply)
#
# Regions take the micro basis only, and that is a judgement about what zooming
# is for rather than about disk. Zooming recovers detail that national scale
# loses: Greater Tunis is 1% of the national page, so its four-panel sheet earns
# its place. A region is 15-30% of that page and already legible there, so a
# region sheet on national breaks would mostly restate the national map. What a
# region does need is the other thing these tools vary -- the breaks -- and that
# is exactly what micro changes.
ALL_BASES = ("shares", "ratio", "micro")
GRAND_TUNIS = ("grand_tunis", "Greater Tunis", "adm2_pcode",
               ["TN11", "TN12", "TN13", "TN14"], ALL_BASES)

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
          line_only=False, shared=False, formats=None, adaptive_chrome=False,
          panel_titles=True, family="zoom"):
    """One sheet for one extent; the panel grid follows the extent's shape.

    A panel is (label, unit_label, subtitle, value_of, edges, labels, ramp);
    every basis below is the same drawing, differing only in what each panel
    maps and which breaks it maps against.
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

    # Wrap the note before sizing the figure, not after. The wrap width follows
    # from the figure width, which is known once the grid is; the height then has
    # to follow from the line count. A single-panel figure is a quarter the width
    # of a sheet, so the same note wraps to three times as many lines -- with a
    # fixed chrome height it printed straight over the map.
    fig_w = ncols * PANEL_W
    body = (note + "\nNeighbouring imadas are drawn in light grey for "
            "orientation and carry no value. " + FOOT)
    body = "\n".join(textwrap.fill(line, int(fig_w * 15.8)) if line else ""
                      for line in body.split("\n"))
    nlines = body.count("\n") + 1
    chrome = (0.40 + 0.118 * nlines + extra) if adaptive_chrome else (
        CHROME_H + extra)
    fig_h = nrows * PANEL_W * aspect + chrome
    fig, axes = plt.subplots(nrows, ncols, figsize=(fig_w, fig_h),
                             facecolor=SURFACE, squeeze=False)

    n = len(paths)
    for ax, (label, unit_label, sub, value_of, edges, labels, ramp) in zip(
            axes.ravel(), panels):
        buckets = collections.defaultdict(list)
        missing = 0
        for code, path in paths.items():
            v = value_of(code)
            if v is None:
                buckets[NO_DATA].append(path)
                missing += 1
            else:
                buckets[ramp[class_of(v, edges)]].append(path)
        # neighbours first, so the extent's own units sit on top of them
        ax.add_collection(PathCollection(others, facecolors=CONTEXT,
                                         edgecolors="#ffffff", linewidths=0.10,
                                         zorder=1))
        draw(ax, buckets, gov, label if panel_titles else "", sub, edges,
             unit_label, n, missing, compact=True, units_note=False,
             labels=labels, legend=not shared, colours=ramp)
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
        label_, unit_, _s, _v, edges, labels, _r = panels[0]
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
    # The note was wrapped above, before the figure was sized: bbox_inches
    # "tight" expands the canvas around anything that overflows, so an unwrapped
    # note made each sheet as wide as its longest sentence.
    fig.text(0.012, 0.012, body, fontsize=7.5, color=INK_2, va="bottom")
    bottom = ((0.118 * nlines + 0.10) / fig_h if adaptive_chrome else 0.052)
    fig.tight_layout(rect=(0, bottom, 1, 0.905 if shared else 0.968))
    out = f"{figure_dir(family)}/{out_stem}"
    made = (save_figure(fig, out, formats) if formats else save_figure(fig, out))
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


MICRO_NOTE = (
    "Class breaks are LOCAL: quantiles of this candidate's share among the "
    "imadas of THIS extent only, so the whole ramp is spent on the variation "
    "inside it. A shade therefore means nothing outside this map — for "
    "comparisons across extents use zoom_* or zoom_ratio_*. The subtitle gives "
    "this extent's own range and the national share.")


def micro_panel(paths, rows, key, label, nat, k=len(RAMP)):
    """One candidate over one extent, classed against that extent alone.

    The only difference from `shares_panels` is where the breaks come from, and
    it is the whole difference in what the map shows.
    """
    field = f"{key}_share_pct"
    vals = [float(rows[c][field]) for c in paths
            if c in rows and rows[c][field] != ""]
    if not vals:
        return None
    edges = quantile_edges(vals, min(k, len(set(vals))))
    ramp = RAMP if len(edges) - 1 == len(RAMP) else [
        RAMP[round(i * (len(RAMP) - 1) / max(len(edges) - 2, 1))]
        for i in range(len(edges) - 1)]

    def value_of(code):
        r = rows.get(code)
        return None if not r or r[field] == "" else float(r[field])

    # Two lines: one overran the gutter and printed onto the context layer.
    sub = (f"{len(paths)} imadas · {min(vals):.2f}–{max(vals):.2f}% here\n"
           f"national {nat[key]:.2f}%")
    return [(label, "share of valid votes (%), local quantile classes", sub,
             value_of, edges, None, ramp)]


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
        out.append((label, unit_label, sub, value_of, edges[key], None, RAMP))
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
                    sub, value_of, RATIO_EDGES, RATIO_LABELS, RAMP))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", help="build one extent by slug (e.g. grand_tunis)")
    ap.add_argument("--list", action="store_true", help="list the extents")
    ap.add_argument("--basis", choices=["shares", "ratio", "micro", "all"],
                    default="all",
                    help="shares: four panels on national quantile breaks. "
                         "ratio: three candidates on one shared scale, the "
                         "basis that can be read across panels. micro: one map "
                         "per candidate per extent on LOCAL breaks, which is "
                         "what shows the variation inside an extent")
    ap.add_argument("--extent", choices=["governorate", "region", "all"],
                    default="all")
    ap.add_argument("--formats", default="pdf,png",
                    help="formats for the micro family (default pdf,png: 93 "
                         "figures in three formats would add ~100 MB, and PDF "
                         "already carries the vector)")
    args = ap.parse_args()
    if not os.path.exists(ARCHIVE):
        sys.exit(f"missing {ARCHIVE}; run tools/fetch_boundaries.py")

    nat, _ = national_shares()
    feats = load_layer("tun_admin4.geojson")
    rows = {r["adm4_pcode"]: r for r in read(IMADA_CSV)
            if r["candidate_sum"] and int(r["candidate_sum"]) > 0}

    # Build every imada path once; the extents only partition them.
    paths, boxes = {}, {}
    member = {"adm2_pcode": {}, "adm1_pcode": {}}
    for f in feats:
        p = f["properties"]
        path = feature_path(f["geometry"], TOL)
        if path is None:
            continue
        code = p["adm4_pcode"]
        paths[code] = path
        member["adm2_pcode"][code] = p["adm2_pcode"]
        member["adm1_pcode"][code] = p["adm1_pcode"]
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

    def slugify(name):
        return (name.lower().replace(" ", "_").replace("é", "e")
                .replace("è", "e"))

    extents = []
    if args.extent in ("governorate", "all"):
        gnames = {f["properties"]["adm2_pcode"]: f["properties"]["adm2_name"]
                  for f in load_layer("tun_admin2.geojson")}
        extents.append(GRAND_TUNIS)
        for code in sorted(gnames):
            extents.append((slugify(gnames[code]),
                            f"{gnames[code]} governorate", "adm2_pcode",
                            [code], ALL_BASES))
    if args.extent in ("region", "all"):
        rnames = {f["properties"]["adm1_pcode"]: f["properties"]["adm1_name"]
                  for f in load_layer("tun_admin1.geojson")}
        for code in sorted(rnames):
            extents.append((slugify(rnames[code]), f"{rnames[code]} region",
                            "adm1_pcode", [code], ("micro",)))

    if args.list:
        for slug, title, level, codes, bases in extents:
            print(f"  {slug:<14} {title:<28} {level:<11} "
                  f"{','.join(bases):<18} {' '.join(codes)}")
        return
    formats = tuple(f.strip() for f in args.formats.split(",") if f.strip())

    total = 0
    for slug, title, level, codes, bases in extents:
        if args.only and args.only != slug:
            continue
        want = set(codes)
        mine = {c: p for c, p in paths.items() if member[level][c] in want}
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
        if args.basis in ("shares", "all") and "shares" in bases:
            made += sheet(title, mine, others, gov_paths, view,
                          f"zoom_{slug}", shares_panels(mine, rows, edges),
                          SHARES_NOTE)
        if args.basis in ("ratio", "all") and "ratio" in bases:
            made += sheet(f"{title} · against each candidate's own average",
                          mine, others, gov_paths, view, f"zoom_ratio_{slug}",
                          ratio_panels(mine, rows, nat), RATIO_NOTE,
                          line_only=True, shared=True)
        if args.basis in ("micro", "all") and "micro" in bases:
            for key, cl in CANDIDATES:
                panel = micro_panel(mine, rows, key, cl, nat)
                if panel is None:
                    print(f"  {slug}/{key}: no result in this extent, skipped")
                    continue
                made += sheet(f"{cl} — {title}", mine, others, gov_paths, view,
                              f"micro_{slug}_{key}", panel, MICRO_NOTE,
                              formats=formats, adaptive_chrome=True,
                              panel_titles=False, family="micro")
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
