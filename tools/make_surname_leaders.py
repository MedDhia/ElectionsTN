"""Six maps of the register read across surnames rather than one at a time.

The leader maps: who is largest where
-------------------------------------
`leaders_by_imada`, `leaders_by_delegation` and their `_concentrated`
counterparts fill every unit with its **most common family name**. This is what
the per-surname dot maps cannot draw: each of those shows one name against the
country, and none of them says which name is largest in a given place.

Four maps, because two choices cross. The **unit** is the imada the register
itself names, or the delegation above it, whose counts are the sum of its
imadas -- and the answers do not nest, since a name can lead a delegation
without leading any single imada in it, by coming second everywhere. The
**universe** is every family name, or only the concentrated ones (at least
`CONC_MIN_VOTERS` holders and a Herfindahl index over imadas of `CONC_MIN_HHI`
or more), which turns the question from "which name is largest here" into
"which of the register's local names is largest here".

Two things have to be said out loud, and every one of them says both.

**Leading is not dominating.** No unit has a family name anywhere near a
majority: the median leader holds 8.2% of its imada's electorate and 3.1% of its
delegation's, less than half that where only local names may lead, and in a
sixth of imadas the second name is within ten voters of the first. A leader map
shows the largest share, not a big one, and each figure prints the distribution
of that share so the reader can see how thin it is.

**Most leaders are not on the legend.** 972 different names lead at least one
imada. Colouring them all would need several hundred colours, which is not a
legend but a wall, so the names that lead the most units take a colour each and
everything else is grey. The grey is not "no data" -- it is "the leader here is
one of the other names" -- and the legend says so. Where a unit holds none of
the names in play at all, a third and paler tone says that instead.

The overlays: several names at once
-----------------------------------
`overlay_common_names` and `overlay_concentrated_names` put six names on one map
as dots, each in its own colour: the six commonest, and the six whose holders sit
in the fewest places. Read together they are the point of the whole family --
the common names are everywhere at once, and the concentrated ones each own a
district and cover little of the country.

Patronymics are excluded from "commonest", as they are everywhere else in this
family of figures: `بن محمد` is the fifth commonest string in the register but it
is a father's name standing in for a family name.

Colour, and the two different questions it has to answer
--------------------------------------------------------
The dot overlays need every pair of their colours to be separable, because their
marks are scattered over each other -- so they take the **best six-colour set**
available from five published qualitative palettes, exhaustively searched:
minimum 16.1 CIEDE2000 between any two, under normal vision and under simulated
protanopia, deuteranopia and tritanopia. Seven would drop that to 13.0, which is
why there are six names on each and not seven.

A choropleth asks something different, and demanding the strict floor of every
pair would cut it to four classes. Its legend stacks all the swatches in one
column, so every pair must be distinguishable there -- `GLOBAL_MIN` -- while the
map poses the harder question only of units that **share a border**, which take
`PAIR_MIN`. So colours are assigned by measuring the map's own adjacency: which
units share an edge, hence which leading names sit next to each other, and then
searching the assignment that maximises the worst separation across the pairs
that actually meet.

**How many names carry a colour is measured, not chosen.** Each map starts at
ten and drops one at a time until both floors are met, which lands on six or
seven depending on how the names on it sit against each other. Every trial,
every adjacent pair and its separation go to
`data/verification/surname_leaders.jsonl`, tagged by map, so the claim can be
checked rather than believed.

Usage: python3 tools/make_surname_leaders.py
"""

import argparse
import collections
import csv
import gzip
import itertools
import json
import math
import os
import random
import sys
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import PathCollection

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from arabic_translit import translit
from colour import DICHROMACY, ciede2000, hex_rgb, simulate
from make_maps import (GOV_LINE, INK, INK_2, NO_DATA, figure_dir, load_layer,
                       save_figure)
from make_maps import albers
from make_surname_dots import (FAMILY, GUTTER, IMADA_GZ, LAND, MESH,
                               PATRONYMIC_PREFIXES, XW, Geography, Gutter, base,
                               dot_value, family_key, imada_counts, imada_dots,
                               place_arabic, pooled_national, read_csv, scatter)

LOG = "data/verification/surname_leaders.jsonl"
STATS_GZ = "data/voter_surnames_2024/surname_family_stats.csv.gz"

# What counts as a concentrated name for the concentrated leader map: bunched
# (Herfindahl index over imadas) and big enough for the index to mean anything.
# 425 names clear both, holding 806,068 voters between them.
CONC_MIN_VOTERS = 1000
CONC_MIN_HHI = 0.05

# ... and for the concentrated overlay, which keeps the floor the rest of the
# concentrated figures use, so it names the same families they do.
OVERLAY_CONC_MIN_VOTERS = 3000

# The candidate pool: five published qualitative palettes -- Okabe-Ito,
# ColorBrewer Dark2, Set1 and Paired, and Tableau 10 -- plus ink black. Nothing
# is eyeballed, and nothing is chosen by hand either: the sets below are the
# exhaustive best over this pool under the floors.
#
# It is wider than the Okabe-Ito-only pool `tools/check_dot_palette.py` searches,
# and that is the whole difference between four names on `overlay_four_names`
# and six here. The floors are the same; there are simply more candidates to
# meet them.
POOL = [
    # Okabe-Ito
    "#e69f00", "#56b4e9", "#009e73", "#0072b2", "#d55e00", "#cc79a7", "#000000",
    # ColorBrewer Dark2
    "#1b9e77", "#d95f02", "#7570b3", "#e7298a", "#66a61e", "#e6ab02", "#a6761d",
    # ColorBrewer Set1
    "#e41a1c", "#377eb8", "#4daf4a", "#984ea3", "#ff7f00", "#a65628", "#f781bf",
    # ColorBrewer Paired (the dark half)
    "#1f78b4", "#33a02c", "#e31a1c", "#6a3d9a", "#b15928",
    # Tableau 10
    "#4e79a7", "#f28e2b", "#e15759", "#76b7b2", "#59a14f", "#edc948",
    "#b07aa1", "#9c755f",
]

# Exhaustively searched over that pool: the six-colour set with the largest
# minimum separation under all four conditions, 16.1. Seven falls to 13.0, below
# the floor a scattered dot needs, so the overlay carries six names.
OVERLAY_COLOURS = ["#000000", "#009e73", "#e6ab02", "#e41a1c", "#b07aa1",
                   "#6a3d9a"]

N_LEADERS = 10          # leading names that get a colour; the rest go grey
N_OVERLAY = 6           # one per colour above

GROUND_MIN = 25.0       # a fill has to be this far from the land
PAIR_MIN = 15.0         # ... adjacent classes this far from each other
# ... and every pair this far, adjacent or not, because the legend stacks all of
# them in one column: two swatches a reader cannot tell apart there make the map
# unreadable however far apart those units sit on the ground. The first version
# enforced only the adjacency floor and gave two never-touching names the same
# yellow, which looked like a mistake in the legend and was one.
GLOBAL_MIN = 12.0
CONDITIONS = ("normal",) + tuple(DICHROMACY)


def sep(h1, h2):
    """Worst CIEDE2000 between two colours across normal and dichromat vision."""
    a, b = hex_rgb(h1), hex_rgb(h2)
    return min(ciede2000(a, b) if c == "normal"
               else ciede2000(simulate(a, c), simulate(b, c))
               for c in CONDITIONS)


# ---- who leads each imada -------------------------------------------------
def concentrated_universe(min_voters=CONC_MIN_VOTERS, min_hhi=CONC_MIN_HHI,
                          count_field="domestic_voters"):
    """The family names that sit in few places, from the statistics table.

    A concentrated name is one whose holders are bunched: Herfindahl index over
    imadas at or above `min_hhi`, with at least `min_voters` holders so the
    index means something -- a name with four holders in one imada scores 1.0
    and says nothing. Patronymics are excluded, as everywhere else here.
    """
    out = {}
    with gzip.open(STATS_GZ, "rt", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if int(row["is_patronymic"]) or not row["domestic_voters"]:
                continue
            if (int(row[count_field]) >= min_voters
                    and float(row["hhi_imada"] or 0.0) >= min_hhi):
                out[row["family_key"]] = row
    return out


def leaders(universe=None, level="imada"):
    """The most common family name in every mapped unit.

    `level` picks the unit: the imada the register itself names, or the
    delegation or governorate above it, whose counts are the sums of the imadas
    inside them. The question is the same and the answers are not -- a name can
    lead a delegation without leading any single imada in it, by being second
    everywhere, and the same holds a level up again.

    `universe` restricts which names may lead: passed the concentrated set, the
    map answers "which of the register's local names is largest here" rather
    than "which name is largest here", and an imada holding none of them is
    drawn as holding none rather than as led by something.

    Counts are pooled per family *and* per imada before the maximum is taken:
    a family written two ways has two rows in the same imada, and comparing
    rows rather than families would hand the lead to whichever name happens to
    be spelled one way.
    """
    code = {"imada": "adm4_pcode", "delegation": "adm3_pcode"}.get(level)
    xw = {(r["governorate_ar"], r["constituency_ar"], r["imada_ar"]): r
          for r in read_csv(XW)}
    if code is None:
        # The crosswalk stops at the delegation, so the governorate comes from
        # the boundary file rather than from slicing a p-code string.
        code = "adm2_pcode"
        up = {f["properties"]["adm3_pcode"]: f["properties"]["adm2_pcode"]
              for f in load_layer("tun_admin3.geojson")}
        for r in xw.values():
            r["adm2_pcode"] = up[r["adm3_pcode"]]
    per_unit = collections.defaultdict(collections.Counter)
    patronymic = collections.defaultdict(collections.Counter)
    with gzip.open(IMADA_GZ, "rt", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["is_diaspora"] == "1":
                continue
            hit = xw.get((row["governorate"], row["constituency"], row["imada"]))
            if hit is None:
                continue
            key = family_key(row["surname_norm"])
            if not key:
                continue
            if key.split()[0] in PATRONYMIC_PREFIXES:
                patronymic[hit[code]][key] += int(row["voter_count"])
            elif universe is None or key in universe:
                per_unit[hit[code]][key] += int(row["voter_count"])

    totals = collections.Counter()
    for r in xw.values():
        totals[r[code]] += int(r["registry_voters"])

    # How often a patronymic would have taken the lead, had they counted.
    # Reported rather than hidden: `بن محمد` is the largest string in a number
    # of imadas and it is a father's name, not a family name.
    beaten = 0
    for pcode, names in per_unit.items():
        top_family = names.most_common(1)[0][1] if names else 0
        top_pat = (patronymic[pcode].most_common(1)[0][1]
                   if patronymic.get(pcode) else 0)
        if top_pat > top_family:
            beaten += 1

    out = {}
    for pcode, names in per_unit.items():
        (key, n), = names.most_common(1)
        runner = names.most_common(2)[1][1] if len(names) > 1 else 0
        out[pcode] = {
            "key": key,
            "voters": n,
            "share": 100.0 * n / totals[pcode] if totals[pcode] else 0.0,
            "lead_over_runner_up": n - runner,
            "names_in_unit": len(names),
        }
    return out, beaten


# ---- which imadas touch ---------------------------------------------------
def adjacency(layer="tun_admin4.geojson", code="adm4_pcode", precision=6):
    """Pairs of units that share an edge.

    The boundary file is topologically consistent, so neighbours share vertices
    exactly; two units sharing at least two rounded vertices share a border
    rather than merely touching at a corner.
    """
    at_vertex = collections.defaultdict(set)
    for f in load_layer(layer):
        pcode = f["properties"][code]
        geom = f["geometry"]
        polys = (geom["coordinates"] if geom["type"] == "MultiPolygon"
                 else [geom["coordinates"]])
        for poly in polys:
            for ring in poly:
                for x, y in ring:
                    at_vertex[(round(x, precision),
                               round(y, precision))].add(pcode)
    shared = collections.Counter()
    for codes in at_vertex.values():
        if len(codes) > 1:
            for a, b in itertools.combinations(sorted(codes), 2):
                shared[(a, b)] += 1
    return {pair for pair, n in shared.items() if n >= 2}


def coarser_paths(layer, code, tol):
    """One mesh above the imada, projected and simplified as the choropleths are.

    `make_surname_dots.Geography` carries the imada mesh, which every dot map
    needs; these are the levels above it, which only the leader maps want. The
    tolerances are the ones `tools/make_maps.py` uses for the same layers.
    """
    from make_maps import feature_path
    out = {}
    for f in load_layer(layer):
        path = feature_path(f["geometry"], tol)
        if path is not None:
            out[f["properties"][code]] = path
    return out


# ---- colouring the leader map --------------------------------------------
def assign_colours(classes, touching, pool, seed=20240706, restarts=60):
    """Colour the classes against two floors, one global and one local.

    The global floor is what the legend needs: every pair of swatches in one
    column has to be distinguishable, whatever the map does. The local floor is
    what the map needs, and it is stricter, because a reader comparing two units
    that share a border is doing the harder task -- so the assignment maximises
    the worst separation over `touching`, the pairs of classes that actually
    adjoin, inside a colour set that already clears the global floor.

    Requiring the strict floor of every pair instead would cap the map at four
    classes; requiring only the local one gave two never-touching names the same
    yellow. Both floors, and the count of classes falls out of what they allow.
    """
    candidates = [h for h in pool
                  if min(ciede2000(hex_rgb(h), hex_rgb(LAND)) if c == "normal"
                         else ciede2000(simulate(hex_rgb(h), c),
                                        simulate(hex_rgb(LAND), c))
                         for c in CONDITIONS) >= GROUND_MIN
                  and sep(h, NO_DATA) >= 20.0]
    table = {}
    for a, b in itertools.combinations(candidates, 2):
        table[(a, b)] = table[(b, a)] = sep(a, b)

    # The best colour set of this size by its own worst pair. Exhaustive while
    # that is cheap, and a seeded greedy with restarts when it is not: 32
    # candidates choose 10 is 64 million subsets, and the answer there is a
    # foregone failure anyway.
    best_set, best_global = None, -1.0
    if math.comb(len(candidates), len(classes)) <= 1_500_000:
        for combo in itertools.combinations(candidates, len(classes)):
            worst = min(table[(a, b)]
                        for a, b in itertools.combinations(combo, 2))
            if worst > best_global:
                best_set, best_global = combo, worst
    else:
        rng0 = random.Random(seed)
        for _ in range(400):
            combo = [rng0.choice(candidates)]
            while len(combo) < len(classes):
                combo.append(max((h for h in candidates if h not in combo),
                                 key=lambda h: min(table[(h, c)] for c in combo)))
            worst = min(table[(a, b)]
                        for a, b in itertools.combinations(combo, 2))
            if worst > best_global:
                best_set, best_global = tuple(combo), worst
    if best_global < GLOBAL_MIN:
        return None, best_global, -1.0, None

    def score(assign):
        worst, pair = 1e9, None
        for x, y in touching:
            d = table.get((assign[x], assign[y]), 1e9)
            if d < worst:
                worst, pair = d, (x, y)
        return worst, pair

    rng = random.Random(seed)
    best = None
    for _ in range(restarts):
        pick = list(best_set)
        rng.shuffle(pick)
        assign = dict(zip(classes, pick))
        current, _ = score(assign)
        improved = True
        while improved:
            improved = False
            for a, b in itertools.combinations(classes, 2):
                assign[a], assign[b] = assign[b], assign[a]
                trial, _ = score(assign)
                if trial > current:
                    current, improved = trial, True
                else:
                    assign[a], assign[b] = assign[b], assign[a]
        if best is None or current > best[0]:
            best = (current, dict(assign))
    worst, pair = score(best[1])
    return best[1], best_global, worst, pair


# ---- the figures ----------------------------------------------------------
def figure_leaders(paths_by_code, gov_paths, lead, stats, colours, global_worst,
                   worst, out_dir, stem, title, subtitle, other_label, unit):
    fig, ax = plt.subplots(figsize=(7.6, 8.4))
    ax.set_aspect("equal")
    ax.set_axis_off()

    buckets = collections.defaultdict(list)
    for pcode, path in paths_by_code.items():
        hit = lead.get(pcode)
        colour = colours.get(hit["key"], NO_DATA) if hit else "#f4f3f0"
        buckets[colour].append(path)
    for colour, paths in buckets.items():
        ax.add_collection(PathCollection(paths, facecolors=colour,
                                         edgecolors="#ffffff",
                                         linewidths=0.10 if unit == "imada" else 0.25,
                                         zorder=2))
    ax.add_collection(PathCollection(gov_paths, facecolors="none",
                                     edgecolors=GOV_LINE, linewidths=0.6,
                                     zorder=3))
    ax.autoscale_view()
    x0, x1 = ax.get_xlim()
    ax.set_xlim(x1 - GUTTER * (x1 - x0), x1)

    g = Gutter(fig, ax)
    g.text(title, size=13.0, colour=INK, weight="bold", gap=0.4)
    g.text(subtitle, size=7.4, gap=1.3)

    for key, colour in sorted(colours.items(),
                              key=lambda kv: -stats["led"][kv[0]]):
        y = g.y
        ax.add_patch(plt.Rectangle((0.016, y - g.frac(10.0)), 0.030,
                                   g.frac(9.0), transform=ax.transAxes,
                                   facecolor=colour, edgecolor="#ffffff",
                                   linewidth=0.4, clip_on=False, zorder=6))
        ax.text(0.056, y - g.frac(5.5), translit(stats["display"][key]),
                transform=ax.transAxes, fontsize=8.2, color=INK, va="center",
                ha="left", fontweight="bold")
        place_arabic(ax, stats["display"][key], (0.235, y + g.frac(1.0)), 10.5)
        g.space(13.0)
        g.text(f"leads {stats['led'][key]:,} {unit}s · "
               f"{stats['led_voters'][key]:,} voters there", size=6.3, gap=1.1)

    y = g.y
    ax.add_patch(plt.Rectangle((0.016, y - g.frac(10.0)), 0.030, g.frac(9.0),
                               transform=ax.transAxes, facecolor=NO_DATA,
                               edgecolor="#ffffff", linewidth=0.4,
                               clip_on=False, zorder=6))
    ax.text(0.056, y - g.frac(5.5),
            other_label.format(n=stats["other_imadas"],
                               names=stats["distinct"] - len(colours)),
            transform=ax.transAxes, fontsize=6.6, color=INK_2, va="center",
            ha="left")
    g.space(16.0)
    if stats.get("none_present"):
        y = g.y
        ax.add_patch(plt.Rectangle((0.016, y - g.frac(10.0)), 0.030,
                                   g.frac(9.0), transform=ax.transAxes,
                                   facecolor="#f4f3f0", edgecolor=MESH,
                                   linewidth=0.4, clip_on=False, zorder=6))
        ax.text(0.056, y - g.frac(5.5),
                f"{stats['none_present']} {unit}s hold none of them at all",
                transform=ax.transAxes, fontsize=6.6, color=INK_2,
                va="center", ha="left")
        g.space(16.0)

    nxt = ", ".join(f"{translit(stats['display'][k])} ({stats['led'][k]})"
                    for k in stats["next_leaders"])
    g.text("\n".join(textwrap.wrap(f"Next after these, by {unit}s led: " + nxt,
                                   60)), size=6.1, gap=1.0)

    q = stats["share_quartiles"]
    g.text(f"Leading is not dominating: the leading name holds a median\n"
           f"{q[1]:.1f}% of its {unit}'s electorate (quartiles {q[0]:.1f}% and "
           f"{q[2]:.1f}%), and in\n{stats['close_pct']:.0f}% of {unit}s it "
           f"leads the second name by under ten voters.", size=6.1, gap=0.9)
    g.text(f"No two of these {len(colours)} colours are closer than "
           f"{global_worst:.1f} CIEDE2000, and {worst:.1f}\n"
           f"where two share a border, under normal vision and all three\n"
           f"dichromacies. {len(colours)} carry one because that is what the "
           f"palettes allow.", size=6.1)

    ax.text(0.012, 0.012,
            "A name written with the definite article and without it is pooled "
            "as one name.\n"
            "Counts: ISIE preliminary voter register, 6 July 2024, summed to "
            f"the {unit} through\ndata/surname_imada_crosswalk.csv. Boundaries: "
            f"OCHA COD-AB {'admin4' if unit == 'imada' else 'admin3'}.",
            transform=ax.transAxes, fontsize=6.0, color=INK_2, va="bottom",
            ha="left", linespacing=1.5)
    made = save_figure(fig, os.path.join(out_dir, stem))
    plt.close(fig)
    return made


def figure_overlay(geo, families, counts, display, out_dir, stem, title,
                   subtitle, closing):
    dv = dot_value(max(sum(counts[k].values()) for k in families))
    fig, ax = plt.subplots(figsize=(7.6, 8.4))
    base(ax, geo)
    drawn = []
    for i, key in enumerate(families):
        colour = OVERLAY_COLOURS[i]
        xy, n_dots, _ = imada_dots(geo, counts[key], dv,
                                   abs(hash(key)) % (2 ** 20))
        scatter(ax, xy, colour=colour, size=1.6, alpha=0.70, zorder=4 + i)
        drawn.append((colour, key, sum(counts[key].values()), len(counts[key]),
                      n_dots))
    x0, x1 = ax.get_xlim()
    ax.set_xlim(x1 - GUTTER * (x1 - x0), x1)

    g = Gutter(fig, ax)
    g.text(title, size=13.0, colour=INK, weight="bold", gap=0.4)
    g.text(subtitle, size=7.4, gap=1.4)
    for colour, key, voters, units, n_dots in drawn:
        y = g.y
        ax.scatter([0.020], [y - g.frac(6.0)], transform=ax.transAxes, s=16,
                   c=colour, linewidths=0, zorder=6, clip_on=False)
        ax.text(0.040, y - g.frac(6.0), translit(display[key]),
                transform=ax.transAxes, fontsize=8.4, color=INK, va="center",
                ha="left", fontweight="bold")
        place_arabic(ax, display[key], (0.245, y + g.frac(1.5)), 11.0)
        g.space(15.0)
        g.text(f"{voters:,} voters · {units:,} imadas", size=6.4, gap=1.5)
    g.dots(dv, 0)
    g.text("Six rather than seven: exhaustively searched over five\n"
           "published qualitative palettes, the best six colours stay\n"
           "16.1 CIEDE2000 apart under normal vision and all three\n"
           "dichromacies, where the best seven fall to 13.0.",
           size=6.4, gap=1.2)
    g.text(closing, size=6.4)

    ax.text(0.012, 0.012,
            "Dots fall at random inside the imada that holds them: the count per "
            "imada is data,\nthe position within it is not. "
            "Counts: ISIE preliminary voter register, 6 July 2024.\n"
            "Boundaries: OCHA COD-AB admin4.",
            transform=ax.transAxes, fontsize=6.0, color=INK_2, va="bottom",
            ha="left", linespacing=1.5)
    made = save_figure(fig, os.path.join(out_dir, stem))
    plt.close(fig)
    return made, dv


# The five governorates too small to hold a label inside themselves, and where
# each label goes instead: Greater Tunis is four governorates inside 2,500 km²,
# and Monastir is 1,027. The offsets are fractions of the map's width and height,
# and a hairline runs from the label back to the unit it names.
LABEL_OFFSETS = {
    "TN11": (0.30, 0.010),    # Tunis
    "TN12": (0.30, 0.065),    # Ariana
    "TN13": (0.30, -0.042),   # Ben Arous
    "TN14": (-0.20, 0.095),   # Manouba
    "TN32": (0.20, -0.016),   # Monastir
    "TN31": (0.17, 0.020),    # Sousse
}

# How far apart two labels have to stay, and how far one may drift from the
# unit it names before it is given a leader line back to it. Both in points.
LABEL_PAD = 3.5
LEADER_AT = 4.0


def relax_labels(fig, ax, labels, fixed, rounds=400):
    """Push overlapping labels apart, measured rather than guessed.

    Six hand-set offsets move Greater Tunis, Sousse and Monastir out to sea,
    where their units are too small to hold a label at all. The rest collided in
    ways no table of offsets converged on -- Beja printed through Jendouba,
    Siliana through Kairouan -- so this measures the rendered boxes and relaxes
    them along y until nothing overlaps.

    Every label may move vertically, the hand-placed ones included: pinning
    those left Ben Arous printing through Sousse, since the pass had nothing it
    was allowed to move. What the offsets fix is the horizontal placement, which
    is what takes a label off a unit too small to hold it; `fixed` keeps a label
    from being the one *chosen* to move when it has a free partner.
    """
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()

    def box(pair):
        bb = [t.get_window_extent(renderer) for t in pair]
        return (min(b.x0 for b in bb), min(b.y0 for b in bb),
                max(b.x1 for b in bb), max(b.y1 for b in bb))

    shift = {k: 0.0 for k in labels}
    boxes = {k: box(v) for k, v in labels.items()}
    for _ in range(rounds):
        moved = False
        keys = sorted(labels)
        for i, a in enumerate(keys):
            for b in keys[i + 1:]:
                ax0, ay0, ax1, ay1 = boxes[a][0], boxes[a][1] + shift[a], \
                    boxes[a][2], boxes[a][3] + shift[a]
                bx0, by0, bx1, by1 = boxes[b][0], boxes[b][1] + shift[b], \
                    boxes[b][2], boxes[b][3] + shift[b]
                if ax1 + LABEL_PAD <= bx0 or bx1 + LABEL_PAD <= ax0:
                    continue
                if ay1 + LABEL_PAD <= by0 or by1 + LABEL_PAD <= ay0:
                    continue
                overlap = min(ay1, by1) - max(ay0, by0) + LABEL_PAD
                up, down = (a, b) if (ay0 + ay1) > (by0 + by1) else (b, a)
                free = [k for k in (up, down) if k not in fixed] or [up, down]
                step = overlap / len(free)
                if up in free:
                    shift[up] += step
                if down in free:
                    shift[down] -= step
                moved = True
        if not moved:
            break

    inv = ax.transData.inverted()
    for key, pair in labels.items():
        if not shift[key]:
            continue
        for t in pair:
            x, y = ax.transData.transform(t.get_position())
            t.set_position(inv.transform((x, y + shift[key])))
    return {k: v for k, v in shift.items() if abs(v) > LEADER_AT}


def figure_leaders_labelled(paths_by_code, centroids, lead, stats, out_dir,
                            stem, title, subtitle, unit):
    """The leader map at a level coarse enough to name every unit on its face.

    At 24 governorates the class machinery the finer maps use stops earning its
    keep: 21 different names lead one, so six colours would leave three units in
    four grey with a leader the reader cannot see. A label answers every unit,
    and needs no palette at all -- which is why these two figures carry no
    legend and no measured colour assignment, and say so.
    """
    fig, ax = plt.subplots(figsize=(7.6, 8.4))
    ax.set_aspect("equal")
    ax.set_axis_off()
    ax.add_collection(PathCollection(list(paths_by_code.values()),
                                     facecolors=LAND, edgecolors=GOV_LINE,
                                     linewidths=0.6, zorder=2))
    ax.autoscale_view()
    (x0, x1), (y0, y1) = ax.get_xlim(), ax.get_ylim()
    w, h = x1 - x0, y1 - y0

    ax.set_xlim(x1 - GUTTER * w, x1)

    labels, anchors = {}, {}
    for pcode in paths_by_code:
        hit = lead.get(pcode)
        if not hit:
            continue
        cx, cy = centroids[pcode]
        dx, dy = LABEL_OFFSETS.get(pcode, (0.0, 0.0))
        lx, ly = cx + dx * w, cy + dy * h
        ha = "center" if not dx else ("left" if dx > 0 else "right")
        labels[pcode] = (
            ax.text(lx, ly + 0.006 * h, translit(stats["display"][hit["key"]]),
                    fontsize=6.6, color=INK, ha=ha, va="bottom",
                    fontweight="bold", zorder=6),
            ax.text(lx, ly - 0.004 * h,
                    f"{hit['share']:.2f}% of {stats['gov_name'][pcode]}",
                    fontsize=5.0, color=INK_2, ha=ha, va="top", zorder=6))
        anchors[pcode] = (cx, cy)

    fixed = set(LABEL_OFFSETS)
    moved = relax_labels(fig, ax, labels, fixed)
    for pcode in sorted(set(moved) | fixed):
        if pcode not in labels:
            continue
        cx, cy = anchors[pcode]
        lx, ly = labels[pcode][0].get_position()
        ax.plot([cx, lx], [cy, ly], color=INK_2, lw=0.4, zorder=4,
                solid_capstyle="round")
        ax.plot([cx], [cy], marker="o", markersize=1.4, color=INK_2, zorder=5)
    g = Gutter(fig, ax)
    g.text(title, size=13.0, colour=INK, weight="bold", gap=0.4)
    g.text(subtitle, size=7.4, gap=1.2)

    q = stats["share_quartiles"]
    g.text(f"Leading is not dominating, least of all here: the leading\n"
           f"name holds a median {q[1]:.2f}% of its {unit}'s electorate\n"
           f"(quartiles {q[0]:.2f}% and {q[2]:.2f}%). A {unit} pools every\n"
           f"quarter and village inside it, each with its own largest\n"
           f"name, so the winner is whichever name is common\n"
           f"across all of them rather than dominant in any.",
           size=6.2, gap=1.2)
    g.text("Every unit is named on its face rather than coloured: at\n"
           f"{stats['distinct']} different names over {len(lead)} {unit}s, "
           f"a legend of six or seven\ncolours would leave most of the map "
           "grey with a leader the\nreader could not see. A label too big for "
           f"its {unit}, or\npushed aside so two would not print through each "
           "other,\ncarries a line back to the unit it names.", size=6.2,
           gap=1.2)

    ax.text(0.012, 0.012,
            "A name written with the definite article and without it is pooled "
            "as one name.\n"
            "Counts: ISIE preliminary voter register, 6 July 2024, summed to "
            f"the {unit} through\ndata/surname_imada_crosswalk.csv. Boundaries: "
            "OCHA COD-AB admin2.",
            transform=ax.transAxes, fontsize=6.0, color=INK_2, va="bottom",
            ha="left", linespacing=1.5)
    made = save_figure(fig, os.path.join(out_dir, stem))
    plt.close(fig)
    return made


def leader_stats(lead, patronymic_wins, spelling, paths_by_code, n_start):
    """The numbers every leader map prints, whatever it does with colour."""
    led, led_voters = collections.Counter(), collections.Counter()
    for hit in lead.values():
        led[hit["key"]] += 1
        led_voters[hit["key"]] += hit["voters"]
    shares = sorted(h["share"] for h in lead.values())
    close = sum(1 for h in lead.values() if h["lead_over_runner_up"] < 10)

    def q(p):
        return shares[min(len(shares) - 1, int(p * len(shares)))]

    top = [k for k, _ in led.most_common(n_start)]
    stats = {
        "imadas": len(lead),
        "delegations": len(lead),
        "governorates": len(lead),
        "distinct": len(led),
        "led": led,
        "led_voters": led_voters,
        "display": {k: spelling.get(k, k) for k in led},
        "share_quartiles": (q(0.25), q(0.50), q(0.75), shares[-1]),
        "close_pct": 100.0 * close / len(lead),
        "patronymic_wins": patronymic_wins,
        "none_present": len(paths_by_code) - len(lead),
        "next_leaders": [],
        "other_imadas": 0,
    }
    return stats, top


def leader_map(paths_by_code, gov_paths, touch, universe, level, n_start,
               spelling, out_dir, stem, title, subtitle, other_label, log):
    """One leader map: who is largest in each unit, over a set of names."""
    lead, patronymic_wins = leaders(universe=universe, level=level)
    stats, top = leader_stats(lead, patronymic_wins, spelling, paths_by_code,
                              n_start)
    print(f"  {len(lead):,} {level}s, {stats['distinct']:,} different names "
          f"lead one")

    def meeting(names):
        cls = set(names)
        out = set()
        for a, b in touch:
            ka, kb = lead.get(a), lead.get(b)
            if not ka or not kb:
                continue
            x, y = ka["key"], kb["key"]
            if x in cls and y in cls and x != y:
                out.add(tuple(sorted((x, y))))
        return out

    colours = None
    for n in range(len(top), 3, -1):
        names = top[:n]
        touching = meeting(names)
        trial, glob, w, pair = assign_colours(names, touching, POOL)
        ok = trial is not None and w >= PAIR_MIN and glob >= GLOBAL_MIN
        log.append({"kind": "class_count_trial", "map": stem, "classes": n,
                    "adjacent_class_pairs": len(touching),
                    "worst_pair_anywhere": round(glob, 2),
                    "worst_adjacent_separation": round(w, 2) if trial else None,
                    "clears_floors": ok})
        print(f"  {n:>2} coloured names: worst pair anywhere {glob:5.1f}, "
              + (f"worst pair that meets {w:5.1f}" if trial else
                 "no set clears the legend floor")
              + ("" if ok else "   (below a floor)"))
        if ok:
            top, colours, global_worst, worst, worst_pair = (
                names, trial, glob, w, pair)
            break
    if colours is None:
        sys.exit("no class count clears the separation floor")

    led = stats["led"]
    stats["other_imadas"] = sum(v for k, v in led.items() if k not in set(top))
    stats["next_leaders"] = [k for k, _ in led.most_common(len(top) + 5)][len(top):]
    print(f"  colouring {len(top)} names; the worst pair that meets is "
          f"{worst:.1f} apart"
          + (f" ({translit(stats['display'][worst_pair[0]])} / "
             f"{translit(stats['display'][worst_pair[1]])})" if worst_pair else ""))

    log.append({"kind": "leader_colour_assignment", "map": stem,
                "classes": len(top),
                "adjacent_class_pairs": len(meeting(top)),
                "worst_pair_anywhere": round(global_worst, 2),
                "worst_adjacent_separation": round(worst, 2),
                "floors": {"anywhere": GLOBAL_MIN, "adjacent": PAIR_MIN},
                "assignment": {translit(stats["display"][k]): v
                               for k, v in colours.items()}})
    for x, y in sorted(meeting(top)):
        log.append({"kind": "adjacent_leaders", "map": stem,
                    "a": translit(stats["display"][x]),
                    "b": translit(stats["display"][y]),
                    "separation": round(sep(colours[x], colours[y]), 2)})

    return figure_leaders(paths_by_code, gov_paths, lead, stats, colours,
                          global_worst, worst, out_dir, stem, title,
                          subtitle.format(**stats), other_label, level)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--leaders", type=int, default=N_LEADERS,
                    help="how many leading names get a colour of their own")
    args = ap.parse_args()

    national, spelling = pooled_national()
    conc = concentrated_universe()
    print(f"{len(conc):,} concentrated names "
          f"(HHI >= {CONC_MIN_HHI}, at least {CONC_MIN_VOTERS:,} holders)")

    print("measuring which units share a border ...")
    touch = {"imada": adjacency(),
             "delegation": adjacency("tun_admin3.geojson", "adm3_pcode"),
             "governorate": adjacency("tun_admin2.geojson", "adm2_pcode")}
    for level, pairs in touch.items():
        print(f"  {len(pairs):,} adjacent {level} pairs")

    geo = Geography()
    meshes = {"imada": geo.paths,
              "delegation": coarser_paths("tun_admin3.geojson", "adm3_pcode",
                                          0.004),
              "governorate": coarser_paths("tun_admin2.geojson", "adm2_pcode",
                                           0.004)}
    out_dir = figure_dir(FAMILY)
    log, made = [], []

    # The same two questions at all three levels. Each unit is the sum of the
    # imadas inside it, and the answers are not the sum of the imadas' answers:
    # a name can lead a delegation, or a governorate, without leading any single
    # imada in it, by coming second everywhere in it.
    conc_note = ("the same register read over its {0:,} concentrated names\n"
                 "only — those with at least {1:,} holders and a Herfindahl\n"
                 "index over imadas of {2} or more, which is what makes a\n"
                 "name local rather than national").format(
                     len(conc), CONC_MIN_VOTERS, CONC_MIN_HHI)
    conc_note = conc_note.replace("{", "{{").replace("}", "}}")

    # The governorate maps are labelled rather than coloured; everything else
    # they print is the same measurement.
    gov_meta = {f["properties"]["adm2_pcode"]: f["properties"]
                for f in load_layer("tun_admin2.geojson")}
    gov_centroids = {}
    for pcode, meta in gov_meta.items():
        x, y = albers([float(meta["center_lon"])], [float(meta["center_lat"])])
        gov_centroids[pcode] = (float(x[0]), float(y[0]))
    gov_names = {pcode: meta["adm2_name"] for pcode, meta in gov_meta.items()}

    for level in ("imada", "delegation", "governorate"):
        unit = level
        stem = "leaders_by_imada" if level == "imada" else f"leaders_by_{level}"
        conc_stem = ("leaders_concentrated_by_imada" if level == "imada"
                     else f"leaders_concentrated_by_{level}")
        if level == "governorate":
            for universe, conc_stem_flag in ((None, False), (set(conc), True)):
                which = "local " if conc_stem_flag else ""
                print(f"\nthe largest {which}name in each governorate ...")
                lead, pat = leaders(universe=universe, level=level)
                stats, _ = leader_stats(lead, pat, spelling, meshes[level],
                                        args.leaders)
                stats["gov_name"] = gov_names
                print(f"  24 governorates, {stats['distinct']} different names "
                      f"lead one")
                log.append({"kind": "labelled_leader_map",
                            "map": conc_stem if conc_stem_flag else stem,
                            "units": len(lead), "distinct_leaders": stats["distinct"],
                            "median_share_pct": round(stats["share_quartiles"][1], 3),
                            "note": "labelled rather than coloured: more "
                                    "leading names than a palette can carry"})
                made += figure_leaders_labelled(
                    meshes[level], gov_centroids, lead, stats, out_dir,
                    conc_stem if conc_stem_flag else stem,
                    f"The largest {which}family\nname in each governorate",
                    (conc_note.replace("{{", "{").replace("}}", "}")
                     if conc_stem_flag else
                     "2024 ISIE voter register (6 July 2024), the 24\n"
                     "governorates, with the largest family name in each\n"
                     "named on its face. Patronymics do not count: a\n"
                     "father's name is not a family name."),
                    unit)
            continue

        print(f"\nthe largest name in each {unit} ...")
        made += leader_map(
            meshes[level], geo.gov_paths, touch[level], None, level,
            args.leaders, spelling, out_dir,
            stem, f"The largest family name\nin each {unit}",
            "2024 ISIE voter register (6 July 2024), {" + level + "s:,} "
            + f"{unit}s,\n"
            + "{distinct:,} different names leading one of them. A patronymic\n"
            "is a father's name rather than a family name and does not\n"
            "count here; one would have led in {patronymic_wins} " + f"{unit}s.",
            "{n:,} " + f"{unit}s led by one of the other " + "{names:,} names",
            log)

        print(f"\nthe largest local name in each {unit} ...")
        made += leader_map(
            meshes[level], geo.gov_paths, touch[level], set(conc), level,
            args.leaders, spelling, out_dir,
            conc_stem, f"The largest local family\nname in each {unit}",
            conc_note,
            "{n:,} " + f"{unit}s led by one of the other "
            + "{names:,} local names", log)

    print(f"\ndrawing the {N_OVERLAY} commonest names ...")
    common = [k for k, _ in national.most_common()
              if k.split()[0] not in PATRONYMIC_PREFIXES][:N_OVERLAY]
    counts, _, _, _ = imada_counts(set(common))
    made += figure_overlay(
        geo, common, counts, {k: spelling[k] for k in common}, out_dir,
        "overlay_common_names", "The six commonest family\nnames, on one map",
        "registered voters bearing each name, 2024 ISIE\n"
        "register — patronymics excluded, since the commonest\n"
        "string of all is a father's name, not a family name",
        "These six are everywhere at once — which is what a common\n"
        "name is. Their opposites, each sitting in one district, are in\n"
        "overlay_concentrated_names.")[0]

    print(f"drawing the {N_OVERLAY} most concentrated names ...")
    pool = concentrated_universe(min_voters=OVERLAY_CONC_MIN_VOTERS,
                                 min_hhi=0.0, count_field="national_voters")
    conc_names = sorted(pool, key=lambda k: -float(pool[k]["hhi_imada"]))[:N_OVERLAY]
    counts, _, _, _ = imada_counts(set(conc_names))
    made += figure_overlay(
        geo, conc_names, counts, {k: spelling[k] for k in conc_names}, out_dir,
        "overlay_concentrated_names",
        "The six most concentrated\nfamily names, on one map",
        f"the names whose holders sit in the fewest places: highest\n"
        f"Herfindahl index over imadas among those with at least\n"
        f"{OVERLAY_CONC_MIN_VOTERS:,} holders worldwide — the count on each line "
        f"is the part\nof them the map can place",
        "Each of these six owns a district, and together they cover\n"
        "little of the country — the opposite of the commonest names,\n"
        "which are in overlay_common_names. Concentration is where\n"
        "a name is registered in 2024, not proof its holders never moved.")[0]

    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "w", encoding="utf-8") as fh:
        for r in log:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\nwrote {len(made)} files into maps/{FAMILY}/ and {LOG}")
    for m in made:
        print(f"  {os.path.getsize(m):>10,}  {m}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
