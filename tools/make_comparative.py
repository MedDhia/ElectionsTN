"""Maps built for comparing the candidates against each other.

Why the existing maps cannot do this
------------------------------------
`maps/{saied,zammel,maghzaoui}_*` classify each candidate on quantiles of that
candidate's own distribution, so a shade in one is not the same value in
another -- `maps/README.md` says so, and it is the right warning. Putting them
side by side and reading the colours across is exactly the mistake it warns
about.

The reason it cannot simply be fixed by sharing one scale is arithmetic, not
styling. Saied took 91.12% of the valid vote, so his share is pinned against
the ceiling: the most any unit can give him is 100%, which is only **1.10x his
national average**, and the observed range is 0.48x to 1.10x. Zammel and
Maghzaoui, at 6.98% and 1.89%, have room to multiply -- observed 0.00x to 7.85x
and 0.00x to 21.51x. A single scale wide enough to show the challengers'
variation renders Saied a flat wash, and one narrow enough to show Saied's
variation puts both challengers off the top end.

So there is no one comparative map. There are three, each comparable in a
different and stated sense, and none of them pretends to be the others. Each is
built at three levels -- governorate, delegation and imada. The governorate
level answers the cross-*governorate* question directly: 24 units on one page
can be compared to each other at a glance, where 2,042 cannot. Its totals are
summed from the delegation table rather than from a separate source, and the
sum is exact.

1. `compare_rank_*` -- **the same colour means the same standing within that
   candidate's own distribution.** Seven equal-count classes per candidate, so
   the darkest seventh of Zammel's map and the darkest seventh of Maghzaoui's
   cover the same number of units. This compares *geography*: do the two
   challengers draw from the same places or different ones? It deliberately
   discards level, and each legend still prints the real values behind its
   classes so the level is never lost, only set aside.

2. `compare_ratio_*` -- **the same colour means the same multiple of that
   candidate's own national average.** Shared classes, in half-powers of two
   either side of 1.00x, so a boundary falls exactly at the national average
   and "darker than the middle" means "better here than nationally" for every
   candidate. This compares *levels*, and Saied's near-flatness on it is the
   finding rather than a defect: his ceiling is 1.10x.

   Because the scale is national rather than derived from what is on the page,
   it is also the basis that survives being zoomed: `tools/make_zooms.py` puts
   the same classes on each governorate sheet, so a shade means the same thing
   between candidates *and* between extents. It carries one legend for the
   figure rather than one per panel -- three copies of one statement, each
   costing a gutter the maps could use instead.

3. `compare_opposition_*` -- the two challengers taken as a field. One panel is
   the combined non-Saied share, which is where the incumbent was weakest; the
   other is Zammel's share of that non-Saied vote, with a class boundary at
   exactly **50%**, so the map reads as who came second *and* by how much. This
   needs no scale trickery at all, because both panels are ordinary shares, and
   it is the most directly comparative of the three for Zammel against
   Maghzaoui.

Nationally the non-Saied vote is 8.88% and Zammel takes 78.7% of it. Zammel is
ahead of Maghzaoui in 257 of 264 delegations and 1,729 of 2,037 imadas.

**Do not read the runner-up as a solid fact at imada level.** 72 imadas are
*exact* ties between the two challengers, and every one of them is tiny -- the
tied count runs from 1 vote to 38, mostly under 10. Which challenger came second
in a small imada is routinely decided by single digits, so the categorical
reading is fragile there in a way the delegation panel's is not. The shade,
which gives the margin, is the honest part of that panel; ties fall on the 50%
boundary rather than being assigned to either side.

Colour is the documented blue sequential ramp throughout, as in every other
figure here. The ratio and composition panels are quantities with a meaningful
midpoint, which would ordinarily ask for a diverging ramp, but the palette
documents a full ramp for blue only and its rule is that every step is a
documented hex -- so instead of inventing a second hue the midpoint is placed on
a class boundary and named in the legend.
"""

import argparse
import collections
import math
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from make_maps import (ARCHIVE, GUTTER, INK, INK_2, MAPS_DIR, NO_DATA, RAMP,
                       SURFACE, class_of, draw, feature_path, load_layer,
                       quantile_edges, read, save_figure)

DELEG_CSV = "data/delegation_margins.csv"
IMADA_CSV = "data/imada_margins.csv"
CANDIDATES = [("saied", "Kais Saied"), ("zammel", "Ayachi Zammel"),
              ("maghzaoui", "Zouhair Maghzaoui")]

# Half-powers of two either side of the national average, so 1.00x is a class
# boundary and the ramp's midpoint is "as this candidate did nationally".
RATIO_EDGES = [0.0, 0.25, 0.5, 0.71, 1.0, 1.41, 2.0, float("inf")]
RATIO_LABELS = ["under 0.25×", "0.25 – 0.5×", "0.5 – 0.71×", "0.71 – 1.00×",
                "1.00 – 1.41×", "1.41 – 2.0×", "over 2.0×"]

# Interpretable rather than quantile: 50% is the runner-up line and 78.7% is the
# national split, so both boundaries mean something a reader can name.
COMP_EDGES = [0.0, 25.0, 50.0, 65.0, 78.7, 87.0, 93.0, 100.0]
COMP_LABELS = ["under 25%", "25 – 50%", "50 – 65%",
               "65 – 78.7%", "78.7 – 87%", "87 – 93%", "over 93%"]

RANK_LABELS = ["weakest seventh", "2nd seventh", "3rd seventh", "middle seventh",
               "5th seventh", "6th seventh", "strongest seventh"]

FOOT = ("2024 Tunisian presidential election · shares of valid votes at "
        "certified stations · boundaries OCHA/HDX COD-AB (CC BY-IGO)")


def national_shares():
    """The candidates' national shares, from the table that totals the published
    certified vote exactly. Used as the reference at both levels, so a ratio
    means the same thing on the delegation and the imada map."""
    rows = list(read(DELEG_CSV))
    tot = {k: sum(int(r[k]) for r in rows) for k, _ in CANDIDATES}
    s = sum(tot.values())
    return {k: 100.0 * v / s for k, v in tot.items()}, s


def geometry(layer, pcode_col, tol):
    paths = {}
    for f in load_layer(layer):
        p = feature_path(f["geometry"], tol)
        if p is not None:
            paths[f["properties"][pcode_col]] = p
    gov = [p for p in (feature_path(f["geometry"], tol * 2)
                       for f in load_layer("tun_admin2.geojson")) if p]
    return paths, gov


def bucket(paths, value_of, edges):
    """Group unit paths by colour class; anything without a value goes to grey."""
    out = collections.defaultdict(list)
    missing = 0
    for code, path in paths.items():
        v = value_of(code)
        if v is None:
            out[NO_DATA].append(path)
            missing += 1
        else:
            out[RAMP[class_of(v, edges)]].append(path)
    return out, missing


# Panel width, and the figure height that leaves no dead space. Tunisia projects
# to an aspect of 2.14 and draw() widens the x-limits by GUTTER to open a legend
# column, so the axes' data box is 2.14/GUTTER tall per unit width. Sizing the
# figure to anything taller than that just pads the row with blank paper, which
# is what the first render did.
PANEL_W = 5.0
PANEL_W_SHARED = 3.6      # no gutter to reserve, so the map takes the width
CHROME_H = 0.95          # suptitle above, the note and provenance below


def panel_row(n, title, note, out_stem, drawers, shared=None):
    """One figure, n panels in a row -- the layout that makes reading across easy.

    `shared` is (unit_label, edges, labels) for a single figure-level legend. On
    a shared scale the per-panel legends are three copies of one statement, and
    the gutters holding them are dead width, so the panels give it back to the
    maps: 3.6 inches of map each against 2.8 with a gutter.
    """
    w = PANEL_W_SHARED if shared else PANEL_W
    height = w * 2.14 / (1.0 if shared else GUTTER) + CHROME_H + (
        0.55 if shared else 0.0)
    fig, axes = plt.subplots(1, n, figsize=(w * n, height), facecolor=SURFACE)
    for ax, fn in zip(axes.ravel() if n > 1 else [axes], drawers):
        fn(ax)
    fig.suptitle(title, fontsize=14, color=INK, x=0.012, ha="left", y=0.988,
                 fontweight="bold")
    if shared:
        unit_label, edges, labels = shared
        texts = labels or [f"{edges[i]:,.1f} – {edges[i+1]:,.1f}"
                           for i in range(len(RAMP))]
        handles = [Patch(facecolor=RAMP[i], edgecolor="#ffffff", linewidth=0.4,
                         label=texts[i]) for i in range(len(RAMP))]
        handles.append(Patch(facecolor=NO_DATA, edgecolor="#ffffff",
                             linewidth=0.4, label="no result"))
        leg = fig.legend(handles=handles,
                         title=unit_label + " — one scale for all three panels",
                         loc="upper left", frameon=False,
                         bbox_to_anchor=(0.012, 0.947), ncol=len(handles),
                         fontsize=8.0, title_fontsize=8.5, handlelength=1.0,
                         handleheight=1.0, columnspacing=1.1, borderaxespad=0)
        leg.get_title().set_color(INK_2)
        leg.get_title().set_ha("left")
        for t in leg.get_texts():
            t.set_color(INK_2)
    fig.text(0.012, 0.012, note + "\n" + FOOT, fontsize=7.5, color=INK_2,
             va="bottom")
    fig.tight_layout(rect=(0, 0.045, 1, 0.90 if shared else 0.965))
    made = save_figure(fig, f"{MAPS_DIR}/{out_stem}")
    plt.close(fig)
    return made


def governorate_rows():
    """Governorate totals, summed from the delegation table.

    There is no published governorate margins table and this does not invent
    one: `adm2_pcode` is the first four characters of `adm3_pcode`, so the sum
    is exact and totals the same certified vote as its source. 24 units on one
    page is the level at which governorates can be compared to each other at a
    glance rather than by paging through 25 zoomed sheets.
    """
    agg = {}
    for r in read(DELEG_CSV):
        if not r["candidate_sum"] or int(r["candidate_sum"]) <= 0:
            continue
        code = r["adm3_pcode"][:4]
        a = agg.setdefault(code, {k: 0 for k, _ in CANDIDATES})
        for k, _ in CANDIDATES:
            a[k] += int(r[k])
    out = {}
    for code, a in agg.items():
        total = sum(a.values())
        row = {k: str(v) for k, v in a.items()}
        row["candidate_sum"] = str(total)
        for k, _ in CANDIDATES:
            row[f"{k}_share_pct"] = f"{100.0 * a[k] / total:.4f}"
        row["adm2_pcode"] = code
        out[code] = row
    return out


def build(level, csv_path, layer, pcode_col, tol, prefix, nat,
          outline_flip):
    paths, gov = geometry(layer, pcode_col, tol)
    if csv_path is None:
        rows = governorate_rows()
    else:
        rows = {r[pcode_col]: r for r in read(csv_path)
                if r["candidate_sum"] and int(r["candidate_sum"]) > 0}
    n_total = len(paths)
    made = []

    # ---- 1. rank: same colour, same standing in that candidate's own spread
    drawers, ranges = [], {}
    for key, label in CANDIDATES:
        field = f"{key}_share_pct"
        vals = [float(r[field]) for r in rows.values() if r[field] != ""]
        edges = quantile_edges(vals, len(RAMP))
        ranges[key] = (min(vals), max(vals))

        def make(key=key, label=label, field=field, edges=edges):
            def fn(ax):
                def val(code):
                    r = rows.get(code)
                    return None if not r or r[field] == "" else float(r[field])
                buckets, missing = bucket(paths, val, edges)
                # the legend names the rank AND the values behind it, so setting
                # level aside never means hiding it
                labels = [f"{RANK_LABELS[i]}   {edges[i]:.1f}–{edges[i+1]:.1f}%"
                          for i in range(len(RAMP))]
                draw(ax, buckets, gov, label,
                     f"national {nat[key]:.2f}%", edges,
                     "standing within this candidate's own range", n_total,
                     missing, compact=True, labels=labels)
            return fn
        drawers.append(make())
    made += panel_row(
        3, f"Where each candidate ran strongest, by {level}",
        "Seven equal-count classes PER CANDIDATE: the same shade means the same "
        "standing within that candidate's own distribution, not the same share. "
        "Read across to compare geography, not level — each legend prints the "
        "values behind its classes.",
        f"compare_rank_{prefix}", drawers)

    # ---- 2. ratio: same colour, same multiple of that candidate's own average
    drawers = []
    for key, label in CANDIDATES:
        field = f"{key}_share_pct"

        def make(key=key, label=label, field=field):
            def fn(ax):
                def val(code):
                    r = rows.get(code)
                    if not r or r[field] == "":
                        return None
                    return float(r[field]) / nat[key]
                buckets, missing = bucket(paths, val, RATIO_EDGES)
                lo, hi = ranges[key]
                draw(ax, buckets, gov, label,
                     f"national {nat[key]:.2f}% · observed "
                     f"{lo/nat[key]:.2f}–{hi/nat[key]:.2f}×", RATIO_EDGES,
                     "local share ÷ this candidate's national share",
                     n_total, missing, compact=True, labels=RATIO_LABELS,
                     legend=False)
            return fn
        drawers.append(make())
    made += panel_row(
        3, f"How each candidate did against his own national average, by {level}",
        "ONE shared scale: the same shade means the same multiple of that "
        "candidate's national share, and the boundary at 1.00× is that average. "
        "Saied is nearly flat because he cannot exceed 1.10× — at a 91.12% "
        "national share, a unit giving him 100% is only 1.10 times it.",
        f"compare_ratio_{prefix}", drawers,
        shared=("local share ÷ this candidate's national share", RATIO_EDGES,
                RATIO_LABELS))

    # ---- 3. the two challengers as a field
    opp = {}
    comp = {}
    for code, r in rows.items():
        if r["zammel_share_pct"] == "" or r["maghzaoui_share_pct"] == "":
            continue
        opp[code] = float(r["zammel_share_pct"]) + float(r["maghzaoui_share_pct"])
        z, m = int(r["zammel"]), int(r["maghzaoui"])
        if z + m > 0:
            comp[code] = 100.0 * z / (z + m)
    opp_edges = quantile_edges(list(opp.values()), len(RAMP))

    def opp_panel(ax):
        buckets, missing = bucket(paths, lambda c: opp.get(c), opp_edges)
        draw(ax, buckets, gov, "The non-Saied vote",
             f"national {nat['zammel'] + nat['maghzaoui']:.2f}%", opp_edges,
             "Zammel + Maghzaoui, share of valid votes (%)", n_total, missing,
             compact=True)

    def comp_panel(ax):
        buckets, missing = bucket(paths, lambda c: comp.get(c), COMP_EDGES)
        # Most units sit between 50% and 93%, so the ramp alone leaves the panel
        # close to a uniform wash and the runner-up flip -- the one categorical
        # fact in it -- hard to find. Outlining it in the red this repo already
        # uses for "the expected winner did not win here" fixes that at
        # delegation level, where it is 7 units of 264.
        #
        # It does not scale down a level: 236 red outlines on 2,084 small
        # polygons bury the ramp they are supposed to annotate, so the imada
        # panel leaves the flip to the two palest classes, which is exactly what
        # they are. Hence the switch rather than a threshold on the count.
        flip = ([paths[c] for c, v in comp.items() if v < 50 and c in paths]
                if outline_flip else None)
        draw(ax, buckets, gov, "Who led it",
             "national 78.7% Zammel", COMP_EDGES,
             "Zammel's share of the non-Saied vote (%)", n_total, missing,
             highlight=flip or None,
             hi_label=f"Maghzaoui ahead ({len(flip)})" if flip else None,
             compact=True, labels=COMP_LABELS)

    made += panel_row(
        2, f"The challengers as a field, by {level}",
        "Left: where the incumbent was weakest. Right: how that vote split — the "
        "50% boundary is the runner-up line, so pale means Maghzaoui was ahead "
        "and dark means Zammel was, with the shade giving the margin. Both "
        "panels are ordinary shares, so neither needs a shared-scale caveat."
        + ("\nBeware the runner-up as a category here: 72 imadas are exact ties "
           "between the two challengers, on counts of 1 to 38 votes. The shade, "
           "which is the margin, is the part to trust."
           if level == "imada" else ""),
        f"compare_opposition_{prefix}", drawers=[opp_panel, comp_panel])

    return made, n_total, len(rows), opp, comp


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--level", choices=["governorate", "delegation", "imada",
                                       "all"], default="all")
    args = ap.parse_args()
    if not os.path.exists(ARCHIVE):
        sys.exit(f"missing {ARCHIVE}; run tools/fetch_boundaries.py")
    os.makedirs(MAPS_DIR, exist_ok=True)

    nat, total = national_shares()
    print("national shares (from the delegation table, which totals the "
          f"published {total:,} certified valid votes):")
    for k, label in CANDIDATES:
        ceiling = 100.0 / nat[k]
        print(f"  {label:<20} {nat[k]:7.4f}%   ceiling on the ratio: "
              f"{ceiling:6.2f}×")

    jobs = []
    if args.level in ("governorate", "all"):
        jobs.append(("governorate", None, "tun_admin2.geojson", "adm2_pcode",
                     0.006, "governorate", True))
    if args.level in ("delegation", "all"):
        jobs.append(("delegation", DELEG_CSV, "tun_admin3.geojson", "adm3_pcode",
                     0.004, "delegation", True))
    if args.level in ("imada", "all"):
        jobs.append(("imada", IMADA_CSV, "tun_admin4.geojson", "adm4_pcode",
                     0.002, "imada", False))

    for level, csv_path, layer, col, tol, prefix, outline in jobs:
        made, n_total, n_with, opp, comp = build(level, csv_path, layer, col,
                                                 tol, prefix, nat, outline)
        ahead_z = sum(1 for v in comp.values() if v > 50)
        ahead_m = sum(1 for v in comp.values() if v < 50)
        tied = len(comp) - ahead_z - ahead_m
        print(f"\n{level}: {n_with} units with a result of {n_total} features")
        print(f"  non-Saied share: min {min(opp.values()):.2f}% "
              f"max {max(opp.values()):.2f}%")
        print(f"  the non-Saied vote: Zammel ahead in {ahead_z} of {len(comp)} "
              f"units ({100*ahead_z/len(comp):.1f}%), Maghzaoui ahead in "
              f"{ahead_m}, exactly tied in {tied}")
        if len(comp) < n_with:
            print(f"  {n_with - len(comp)} units where neither challenger took a "
                  f"vote, left as no-result rather than as 0%")
        for m in made:
            print(f"    {os.path.getsize(m):>9,}  {m}")


if __name__ == "__main__":
    main()
