"""Two maps of the register read across surnames rather than one at a time.

`maps/surnames/leaders_by_imada` -- who leads where
--------------------------------------------------
Every imada's **most common family name**, one fill per imada. This is the map
the per-surname dot maps cannot draw: each of those shows one name against the
country, and none of them says which name is largest in a given place.

Two things have to be said out loud, and the figure says both.

**Leading is not dominating.** The register has no imada where one family name
is anywhere near a majority; the median leader holds about 3% of its imada's
electorate. A leader map shows the largest share, not a big one, and in most
imadas the second name is within a few voters of the first. The figure prints
the distribution of the leading share so the reader can see how thin it is.

**Most leaders are not on the legend.** Several hundred different names lead at
least one imada. Colouring them all would need several hundred colours, which is
not a legend but a wall, so the names that lead the most imadas take a colour
each and everything else is grey. The grey is not "no data" -- it is "the leader
here is one of the other names" -- and the legend says so.

`maps/surnames/overlay_common_names` -- five names at once
---------------------------------------------------------
The six commonest family names in the country, each in its own colour, on one
map, as dots. It is the common-name counterpart of `overlay_four_names`, which
shows the most concentrated ones, and it answers the other half of the question:
the concentrated names each own a district, and these five are everywhere at
once.

Patronymics are excluded from "commonest", as they are everywhere else in this
family of figures: `بن محمد` is the fifth commonest string in the register but it
is a father's name standing in for a family name.

Colour, and the two different questions it has to answer
--------------------------------------------------------
The dot overlay needs every pair of its colours to be separable, because its
marks are scattered over each other -- so it takes the **best six-colour set**
available from five published qualitative palettes, exhaustively searched:
minimum 16.1 CIEDE2000 between any two, under normal vision and under simulated
protanopia, deuteranopia and tritanopia. Seven would drop that to 13.0, which is
why there are six names on it and not seven.

The leader map does not need that, and demanding it of all pairs would cut it to
four classes. What a choropleth needs is that classes which **touch** are
separable: two colours that never share a border can be close without any reader
ever having to tell them apart. So colours are assigned by measuring the map's
own adjacency -- which imadas share an edge, hence which leading names sit next
to each other -- and searching the assignment that maximises the worst separation
across the pairs that actually meet.

**How many names carry a colour is measured, not chosen.** The tool starts at ten
and drops one at a time until the assignment clears the floor: ten leaves two
neighbours 9.0 CIEDE2000 apart, nine 12.1, eight 12.7, and seven clears it at
20.0. Every trial, every adjacent pair and its separation go to
`data/verification/surname_leaders.jsonl`, so the claim can be checked rather
than believed.

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
from check_dot_palette import DICHROMACY, ciede2000, hex_rgb, simulate
from make_maps import (GOV_LINE, INK, INK_2, NO_DATA, figure_dir, load_layer,
                       save_figure)
from make_surname_dots import (FAMILY, GUTTER, IMADA_GZ, LAND, MESH,
                               PATRONYMIC_PREFIXES, XW, Geography, Gutter, base,
                               dot_value, family_key, imada_counts, imada_dots,
                               place_arabic, pooled_national, read_csv, scatter)

LOG = "data/verification/surname_leaders.jsonl"

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
def leaders():
    """The most common family name in every mapped imada.

    Counts are pooled per family *and* per imada before the maximum is taken:
    a family written two ways has two rows in the same imada, and comparing
    rows rather than families would hand the lead to whichever name happens to
    be spelled one way.
    """
    xw = {(r["governorate_ar"], r["constituency_ar"], r["imada_ar"]): r
          for r in read_csv(XW)}
    per_imada = collections.defaultdict(collections.Counter)
    patronymic = collections.defaultdict(collections.Counter)
    with gzip.open(IMADA_GZ, "rt", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["is_diaspora"] == "1":
                continue
            hit = xw.get((row["governorate"], row["constituency"], row["imada"]))
            if hit is None:
                continue
            key = family_key(row["surname_norm"])
            if key and key.split()[0] not in PATRONYMIC_PREFIXES:
                per_imada[hit["adm4_pcode"]][key] += int(row["voter_count"])
            elif key:
                patronymic[hit["adm4_pcode"]][key] += int(row["voter_count"])

    totals = collections.Counter()
    for r in xw.values():
        totals[r["adm4_pcode"]] += int(r["registry_voters"])

    # How often a patronymic would have taken the lead, had they counted.
    # Reported rather than hidden: `بن محمد` is the largest string in a number
    # of imadas and it is a father's name, not a family name.
    beaten = 0
    for pcode, names in per_imada.items():
        top_family = names.most_common(1)[0][1] if names else 0
        top_pat = (patronymic[pcode].most_common(1)[0][1]
                   if patronymic.get(pcode) else 0)
        if top_pat > top_family:
            beaten += 1

    out = {}
    for pcode, names in per_imada.items():
        (key, n), = names.most_common(1)
        runner = names.most_common(2)[1][1] if len(names) > 1 else 0
        out[pcode] = {
            "key": key,
            "voters": n,
            "share": 100.0 * n / totals[pcode] if totals[pcode] else 0.0,
            "lead_over_runner_up": n - runner,
            "names_in_imada": len(names),
        }
    return out, beaten


# ---- which imadas touch ---------------------------------------------------
def adjacency(precision=6):
    """Pairs of imadas that share an edge.

    The boundary file is topologically consistent, so neighbours share vertices
    exactly; two units sharing at least two rounded vertices share a border
    rather than merely touching at a corner.
    """
    at_vertex = collections.defaultdict(set)
    for f in load_layer("tun_admin4.geojson"):
        code = f["properties"]["adm4_pcode"]
        geom = f["geometry"]
        polys = (geom["coordinates"] if geom["type"] == "MultiPolygon"
                 else [geom["coordinates"]])
        for poly in polys:
            for ring in poly:
                for x, y in ring:
                    at_vertex[(round(x, precision), round(y, precision))].add(code)
    shared = collections.Counter()
    for codes in at_vertex.values():
        if len(codes) > 1:
            for a, b in itertools.combinations(sorted(codes), 2):
                shared[(a, b)] += 1
    return {pair for pair, n in shared.items() if n >= 2}


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
def figure_leaders(geo, lead, stats, colours, global_worst, worst, out_dir):
    fig, ax = plt.subplots(figsize=(7.6, 8.4))
    ax.set_aspect("equal")
    ax.set_axis_off()

    buckets = collections.defaultdict(list)
    for pcode, path in geo.paths.items():
        hit = lead.get(pcode)
        colour = colours.get(hit["key"], NO_DATA) if hit else "#f4f3f0"
        buckets[colour].append(path)
    for colour, paths in buckets.items():
        ax.add_collection(PathCollection(paths, facecolors=colour,
                                         edgecolors="#ffffff", linewidths=0.10,
                                         zorder=2))
    ax.add_collection(PathCollection(geo.gov_paths, facecolors="none",
                                     edgecolors=GOV_LINE, linewidths=0.6,
                                     zorder=3))
    ax.autoscale_view()
    x0, x1 = ax.get_xlim()
    ax.set_xlim(x1 - GUTTER * (x1 - x0), x1)

    g = Gutter(fig, ax)
    g.text("The largest family name\nin each imada", size=13.0, colour=INK,
           weight="bold", gap=0.4)
    g.text("2024 ISIE voter register (6 July 2024),\n"
           f"{stats['imadas']:,} imadas, {stats['distinct']:,} different names "
           "leading one\n"
           f"of them. A patronymic is a father's name rather than a\n"
           f"family name and does not count here; one would have\n"
           f"led in {stats['patronymic_wins']} imadas.",
           size=7.4, gap=1.3)

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
        place_arabic(ax, stats["display"][key], (0.235, y + g.frac(1.0)), 11.0)
        g.space(14.0)
        g.text(f"leads {stats['led'][key]:,} imadas · "
               f"{stats['led_voters'][key]:,} voters there", size=6.4, gap=1.4)

    y = g.y
    ax.add_patch(plt.Rectangle((0.016, y - g.frac(10.0)), 0.030, g.frac(9.0),
                               transform=ax.transAxes, facecolor=NO_DATA,
                               edgecolor="#ffffff", linewidth=0.4,
                               clip_on=False, zorder=6))
    ax.text(0.056, y - g.frac(5.5),
            f"{stats['other_imadas']:,} imadas led by one of the other "
            f"{stats['distinct'] - len(colours):,} names",
            transform=ax.transAxes, fontsize=6.6, color=INK_2, va="center",
            ha="left")
    g.space(16.0)

    nxt = ", ".join(f"{translit(stats['display'][k])} ({stats['led'][k]})"
                    for k in stats["next_leaders"])
    g.text("\n".join(textwrap.wrap("Next after these, by imadas led: " + nxt,
                                   58)), size=6.4, gap=1.3)

    q = stats["share_quartiles"]
    g.text(f"Leading is not dominating: the leading name holds a median\n"
           f"{q[1]:.1f}% of its imada's electorate (quartiles {q[0]:.1f}% and "
           f"{q[2]:.1f}%), and in\n{stats['close_pct']:.0f}% of imadas it "
           f"leads the second name by under ten voters.", size=6.4, gap=1.2)
    g.text(f"No two of these {len(colours)} colours are closer than "
           f"{global_worst:.1f} CIEDE2000, and\n"
           f"{worst:.1f} where two share a border — under normal vision and all\n"
           f"three dichromacies. {len(colours)} names carry one because that is "
           f"as\nmany as the published palettes hold to those two floors.",
           size=6.2)

    ax.text(0.012, 0.012,
            "A name written with the definite article and without it is pooled "
            "as one name.\n"
            "Counts: ISIE preliminary voter register, 6 July 2024. "
            "Boundaries: OCHA COD-AB admin4.",
            transform=ax.transAxes, fontsize=6.0, color=INK_2, va="bottom",
            ha="left", linespacing=1.5)
    made = save_figure(fig, os.path.join(out_dir, "leaders_by_imada"))
    plt.close(fig)
    return made


def figure_overlay(geo, families, counts, display, out_dir):
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
    g.text("The six commonest family\nnames, on one map", size=13.0,
           colour=INK, weight="bold", gap=0.4)
    g.text("registered voters bearing each name, 2024 ISIE\n"
           "register — patronymics excluded, since the commonest\n"
           "string of all is a father's name, not a family name",
           size=7.4, gap=1.4)
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
    g.text("These six are everywhere at once — which is what a\n"
           "common name is. The concentrated names, each sitting\n"
           "in one district, are in overlay_four_names.", size=6.4)

    ax.text(0.012, 0.012,
            "Dots fall at random inside the imada that holds them: the count per "
            "imada is data,\nthe position within it is not. "
            "Counts: ISIE preliminary voter register, 6 July 2024.\n"
            "Boundaries: OCHA COD-AB admin4.",
            transform=ax.transAxes, fontsize=6.0, color=INK_2, va="bottom",
            ha="left", linespacing=1.5)
    made = save_figure(fig, os.path.join(out_dir, "overlay_common_names"))
    plt.close(fig)
    return made, dv


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--leaders", type=int, default=N_LEADERS,
                    help="how many leading names get a colour of their own")
    args = ap.parse_args()

    print("reading the imada table ...")
    lead, patronymic_wins = leaders()
    national, spelling = pooled_national()

    led = collections.Counter()
    led_voters = collections.Counter()
    for pcode, hit in lead.items():
        led[hit["key"]] += 1
        led_voters[hit["key"]] += hit["voters"]
    top = [k for k, _ in led.most_common(args.leaders)]   # trimmed below
    shares = sorted(h["share"] for h in lead.values())
    close = sum(1 for h in lead.values() if h["lead_over_runner_up"] < 10)

    def q(p):
        return shares[min(len(shares) - 1, int(p * len(shares)))]

    stats = {
        "imadas": len(lead),
        "distinct": len(led),
        "led": led,
        "led_voters": led_voters,
        "display": {k: spelling.get(k, k) for k in led},
        "other_imadas": sum(v for k, v in led.items() if k not in set(top)),
        "share_quartiles": (q(0.25), q(0.50), q(0.75), shares[-1]),
        "close_pct": 100.0 * close / len(lead),
        "patronymic_wins": patronymic_wins,
        "next_leaders": [],
    }
    print(f"  {len(lead):,} imadas, {len(led):,} different names lead one; "
          f"the top {len(top)} lead {sum(led[k] for k in top):,}")

    print("measuring which imadas share a border ...")
    touch = adjacency()
    print(f"  {len(touch):,} adjacent imada pairs")

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

    # How many names can carry a colour is not a design choice: it is whatever
    # the palette can keep separable across the pairs that meet on this map.
    # Ten leaves two neighbours 9.0 CIEDE2000 apart under protanopia, which is
    # inside the range where a reader sees one colour; seven clears 20.0.
    log = []
    colours = None
    for n in range(len(top), 3, -1):
        names = top[:n]
        touching = meeting(names)
        trial, glob, w, pair = assign_colours(names, touching, POOL)
        ok = trial is not None and w >= PAIR_MIN and glob >= GLOBAL_MIN
        log.append({"kind": "class_count_trial", "classes": n,
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
    stats["other_imadas"] = sum(v for k, v in led.items() if k not in set(top))
    stats["next_leaders"] = [k for k, _ in led.most_common(len(top) + 5)][len(top):]
    print(f"  colouring {len(top)} names; the worst pair that meets is "
          f"{worst:.1f} apart"
          + (f" ({translit(stats['display'][worst_pair[0]])} / "
             f"{translit(stats['display'][worst_pair[1]])})" if worst_pair else ""))

    log.append({"kind": "leader_colour_assignment",
                "classes": len(top), "adjacent_class_pairs": len(touching),
                "worst_pair_anywhere": round(global_worst, 2),
                "worst_adjacent_separation": round(worst, 2),
                "floors": {"anywhere": GLOBAL_MIN, "adjacent": PAIR_MIN},
                "assignment": {translit(stats["display"][k]): v
                               for k, v in colours.items()}})
    for x, y in sorted(meeting(top)):
        log.append({"kind": "adjacent_leaders",
                    "a": translit(stats["display"][x]),
                    "b": translit(stats["display"][y]),
                    "separation": round(sep(colours[x], colours[y]), 2)})

    geo = Geography()
    out_dir = figure_dir(FAMILY)
    made = figure_leaders(geo, lead, stats, colours, global_worst, worst,
                          out_dir)

    print("drawing the commonest names ...")
    common = [k for k, _ in national.most_common()
              if k.split()[0] not in ("بن", "ابن", "ولد")][:N_OVERLAY]
    counts, _, _, _ = imada_counts(set(common))
    made += figure_overlay(geo, common, counts,
                           {k: spelling[k] for k in common}, out_dir)[0]

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
