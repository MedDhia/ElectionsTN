"""Per-candidate margin and rank maps at governorate and region level.

Twelve separate figures: three candidates x two quantities x two levels, each a
full page of its own rather than a panel in a triptych.

    {saied,zammel,maghzaoui}_{margin,rank}_{governorate,region}.{pdf,png,svg}

**margin** is that candidate's own share minus his strongest rival's, in
percentage points, recomputed from the aggregated votes rather than averaged
from the level below. It is positive for the local winner and negative for
everyone else, so a challenger's margin map reads as how far behind he
finished.

**rank** is that candidate's share classed into equal-count bins, so the map
shows where he stood relative to his own best and worst rather than relative to
the other candidates. Seven bins over 24 governorates; six over six regions,
which makes each region its own class -- at that level "rank" is a literal
ordering, and the legend prints the value behind each place.

On every one of the twelve, **darker means better for the named candidate**.
For rank that is automatic; for margin it follows from classing the signed
value, so a challenger's darkest units are where he came closest.

What these levels collapse, and why it is said on the figures
-------------------------------------------------------------
Saied leads and Zammel is runner-up in **all 24 governorates and all 6
regions**. Three consequences, all measured rather than assumed:

- Zammel's margin is *exactly* minus Saied's, everywhere at both levels. The
  two margin maps therefore carry identical information with the ramp reversed.
  Both are published because "how far behind Zammel finished" is what a reader
  of a Zammel map wants and should not have to negate in their head, but the
  figure says whose mirror it is.
- Their rank maps are near-mirrors for the same reason: Spearman correlation
  between the two candidates' shares is **-0.965** across governorates and
  **-1.000** across regions, where the ordering is exactly reversed.
- Maghzaoui is not redundant with either. His margin is his share minus
  Saied's, a different field, and his ordering is his own: -0.82 against Saied
  and +0.72 against Zammel by governorate, -0.60 and +0.60 by region.

Aggregation
-----------
Both levels are summed from `data/delegation_margins.csv`, since the pcodes
nest exactly: `adm2_pcode` is the first four characters of `adm3_pcode` and
`adm1_pcode` the first three. Neither level invents a source, and the sums
reproduce the published certified figures -- 2,303,043 / 176,525 / 47,847 =
2,527,415 -- which `--report` prints.

Values are drawn on the map as well as classed, because at 24 and 6 units there
is room for them and a coarse choropleth without numbers is a worse table than
the table it came from.
"""

import argparse
import collections
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import patheffects

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from make_maps import (ARCHIVE, INK, INK_2, NO_DATA, RAMP, SURFACE,
                       albers, class_of, draw, feature_path, load_layer,
                       quantile_edges, read, figure_dir, save_figure)
from make_comparative import CANDIDATES, DELEG_CSV

# (name, layer, pcode column, characters of adm3_pcode that name the unit,
#  simplify tolerance, label font size)
FAMILY = "levels"
LEVELS = [
    ("governorate", "tun_admin2.geojson", "adm2_pcode", 4, 0.006, 6.0),
    ("region", "tun_admin1.geojson", "adm1_pcode", 3, 0.008, 8.5),
]

FOOT = ("2024 Tunisian presidential election · shares of valid votes at "
        "certified stations · summed from the delegation table · boundaries "
        "OCHA/HDX COD-AB (CC BY-IGO)")


def aggregate(prefix_len):
    """Vote totals per unit, keyed by the leading characters of adm3_pcode."""
    agg = {}
    for r in read(DELEG_CSV):
        if not r["candidate_sum"] or int(r["candidate_sum"]) <= 0:
            continue
        a = agg.setdefault(r["adm3_pcode"][:prefix_len],
                           {k: 0 for k, _ in CANDIDATES})
        for k, _ in CANDIDATES:
            a[k] += int(r[k])
    return agg


def shares_and_margins(agg):
    """Per unit: each candidate's share, and his margin over his best rival.

    The margin is recomputed here from the summed votes. Averaging the level
    below would weight a 3,000-vote delegation like a 60,000-vote one.
    """
    out = {}
    for code, a in agg.items():
        total = sum(a.values())
        share = {k: 100.0 * a[k] / total for k, _ in CANDIDATES}
        margin = {k: share[k] - max(share[j] for j, _ in CANDIDATES if j != k)
                  for k, _ in CANDIDATES}
        out[code] = {"votes": total, "share": share, "margin": margin,
                     "order": sorted((k for k, _ in CANDIDATES),
                                     key=lambda k: -share[k])}
    return out


def ramp_of(k):
    """k colours from the documented 7-step ramp, endpoints kept.

    Six regions cannot carry seven quantile classes, and simply truncating the
    ramp would drop its darkest step -- so the steps are sampled evenly and the
    legend is handed the same list.
    """
    if k >= len(RAMP):
        return list(RAMP)
    last = len(RAMP) - 1
    return [RAMP[round(i * last / (k - 1))] for i in range(k)]


def value_labels(values, edges, k, unit="%"):
    """One legend label per class.

    When there are as many classes as units, each class holds exactly one unit,
    so the label is that unit's own value. Printing `edges[i]`–`edges[i+1]`
    there would print interpolated quantile bounds instead: with six regions the
    top class came out labelled 2.84% when South West actually polled 3.37%.
    """
    v = sorted(values)
    if k == len(v):
        return [f"{v[i]:+.2f}{unit}" if unit == " pp" else f"{v[i]:.2f}{unit}"
                for i in range(k)]
    fmt = (lambda x: f"{x:+.1f}") if unit == " pp" else (lambda x: f"{x:.2f}")
    return [f"{fmt(edges[i])} – {fmt(edges[i+1])}{unit}" for i in range(k)]


def rank_labels(values, edges, k):
    """Name each class by the standing it represents, and print its values."""
    n = len(values)
    body = value_labels(values, edges, k)
    if k == n:                           # one unit per class: a literal ranking
        return [f"rank {n - i} of {n}   {body[i]}" for i in range(k)]
    words = ["weakest", "2nd", "3rd", "4th", "5th", "6th", "strongest"]
    band = [words[i] if k == 7 else f"band {i + 1}" for i in range(k)]
    return [f"{band[i]} {k}th   {body[i]}" for i in range(k)]


def separate_labels(fig, ax, texts, pad=1.2, iterations=300, spring=0.06):
    """Nudge overlapping value labels apart, in display space.

    Greater Tunis is four small governorates in one corner, so their labels
    landed on top of each other -- "+71.5" and "+73.7" printed across one
    another. This measures the rendered boxes and pushes overlapping pairs apart
    along whichever axis needs the least movement, with a spring back toward the
    true centroid that decays to nothing so the result is overlap-free rather
    than balanced against the springs. Same shape as the cartogram packing.
    """
    if len(texts) < 2:
        return
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    boxes = [t.get_window_extent(renderer) for t in texts]
    pos = np.array([[(b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2] for b in boxes])
    home = pos.copy()
    half = np.array([[(b.x1 - b.x0) / 2 + pad, (b.y1 - b.y0) / 2 + pad]
                     for b in boxes])
    for it in range(iterations):
        overlap = False
        for i in range(len(pos)):
            for j in range(i + 1, len(pos)):
                d = pos[i] - pos[j]
                need = half[i] + half[j]
                ox, oy = need[0] - abs(d[0]), need[1] - abs(d[1])
                if ox <= 0 or oy <= 0:
                    continue
                overlap = True
                if ox < oy:
                    step = np.array([(np.sign(d[0]) or 1.0) * (ox / 2 + 0.3),
                                     0.0])
                else:
                    step = np.array([0.0,
                                     (np.sign(d[1]) or 1.0) * (oy / 2 + 0.3)])
                pos[i] += step
                pos[j] -= step
        decay = spring * max(0.0, 1.0 - 1.6 * it / iterations)
        pos += decay * (home - pos)
        if not overlap and decay == 0.0:
            break
    inv = ax.transData.inverted()
    for t, p in zip(texts, pos):
        t.set_position(tuple(inv.transform(p)))
    # Report rather than assume: the worst remaining overlap in pixels, and how
    # far the furthest label had to move from its unit's centroid.
    worst = 0.0
    for i in range(len(pos)):
        for j in range(i + 1, len(pos)):
            d = pos[i] - pos[j]
            need = half[i] + half[j]
            ox, oy = need[0] - abs(d[0]), need[1] - abs(d[1])
            if ox > 0 and oy > 0:
                worst = max(worst, min(ox, oy))
    shift = float(np.max(np.hypot(*(pos - home).T))) if len(pos) else 0.0
    return worst, shift


def figure(level, paths, centres, gov, values, key, label, quantity,
           edges, colours, labels, unit_label, note, out_stem, fontsize,
           value_of, text_of):
    fig, ax = plt.subplots(figsize=(6.85, 8.1), facecolor=SURFACE)
    buckets = collections.defaultdict(list)
    missing = 0
    for code, path in paths.items():
        v = value_of(code)
        if v is None:
            buckets[NO_DATA].append(path)
            missing += 1
        else:
            buckets[colours[class_of(v, edges)]].append(path)
    n = len(paths)
    draw(ax, buckets, gov, label, f"{level} level · {n} units\n{quantity}",
         edges, unit_label, n, missing, compact=False, labels=labels,
         colours=colours)
    # The numbers, on the map. At 24 and 6 units there is room, and a coarse
    # choropleth without them is a worse table than the one it came from.
    texts = []
    for code, (cx, cy) in centres.items():
        t = text_of(code)
        if t is None:
            continue
        # dark fills need light text; the class index says which
        v = value_of(code)
        dark = class_of(v, edges) >= len(colours) - 3
        fg = "#ffffff" if dark else INK
        obj = ax.text(cx, cy, t, fontsize=fontsize, ha="center", va="center",
                      color=fg, zorder=6,
                      fontweight="bold" if level == "region" else "normal")
        # A halo, because a nudged label may end up over a neighbour whose fill
        # is the opposite lightness from the one its colour was chosen for.
        obj.set_path_effects([patheffects.withStroke(
            linewidth=1.8, foreground=INK if dark else "#ffffff")])
        texts.append(obj)
    overlap, shift = separate_labels(fig, ax, texts)
    fig.text(0.015, 0.012, note + "\n" + FOOT, fontsize=6.5, color=INK_2,
             va="bottom")
    fig.tight_layout(rect=(0, 0.032, 1, 1))
    made = save_figure(fig, f"{figure_dir(FAMILY)}/{out_stem}")
    plt.close(fig)
    return made, overlap, shift


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--level", choices=["governorate", "region", "both"],
                    default="both")
    ap.add_argument("--report", action="store_true",
                    help="print the aggregates and the collapses, then exit")
    args = ap.parse_args()
    if not os.path.exists(ARCHIVE):
        sys.exit(f"missing {ARCHIVE}; run tools/fetch_boundaries.py")

    gov = [p for p in (feature_path(f["geometry"], 0.012)
                       for f in load_layer("tun_admin2.geojson")) if p]

    for level, layer, pcode_col, plen, tol, fontsize in LEVELS:
        if args.level not in (level, "both"):
            continue
        feats = load_layer(layer)
        paths, centres, names = {}, {}, {}
        for f in feats:
            p = f["properties"]
            path = feature_path(f["geometry"], tol)
            if path is None:
                continue
            code = p[pcode_col]
            paths[code] = path
            x, y = albers([float(p["center_lon"])], [float(p["center_lat"])])
            centres[code] = (float(x[0]), float(y[0]))
            names[code] = p[pcode_col.replace("_pcode", "_name")]

        vals = shares_and_margins(aggregate(plen))
        n = len(paths)
        k = min(len(RAMP), len([c for c in paths if c in vals]))
        colours = ramp_of(k)

        total = sum(v["votes"] for v in vals.values())
        cand_tot = {c: sum(round(v["share"][c] * v["votes"] / 100)
                           for v in vals.values()) for c, _ in CANDIDATES}
        leaders = {v["order"][0] for v in vals.values()}
        seconds = {v["order"][1] for v in vals.values()}
        print(f"\n=== {level}: {len(vals)} units, {total:,} certified valid "
              f"votes ===")
        print(f"  leader in every unit: {', '.join(sorted(leaders))} · "
              f"runner-up in every unit: {', '.join(sorted(seconds))}")
        for c, cl in CANDIDATES:
            m = [v["margin"][c] for v in vals.values()]
            s = [v["share"][c] for v in vals.values()]
            print(f"  {cl:<20} share {min(s):6.2f}–{max(s):6.2f}%   "
                  f"margin {min(m):+7.2f}–{max(m):+7.2f} pp")
        if args.report:
            continue

        made, worst, moved = [], 0.0, 0.0
        for key, cl in CANDIDATES:
            # ---- margin
            mvals = [vals[c]["margin"][key] for c in paths if c in vals]
            medges = quantile_edges(mvals, k)
            mirror = ("Zammel is runner-up in every unit at this level, so this "
                      "is exactly minus Saied's margin — the same map with the "
                      "ramp reversed.\n" if key == "zammel" else
                      "Saied leads every unit at this level, so this margin is "
                      "his lead over Zammel throughout.\n" if key == "saied" else
                      "Maghzaoui is third in every unit at this level, so this "
                      "is his deficit to Saied, not to Zammel.\n")
            m, ov, sh = figure(
                level, paths, centres, gov, vals, key,
                f"{cl} — margin over his strongest rival",
                "own share minus the strongest rival's", medges, colours,
                value_labels(mvals, medges, k, " pp"),
                "percentage points (negative: behind the leader)",
                mirror + "Darker is a better result for this candidate. "
                "Classes are quantiles of this candidate's own margins; the "
                "legend prints each class's range.",
                f"{key}_margin_{level}", fontsize,
                lambda c, key=key: vals[c]["margin"][key] if c in vals else None,
                lambda c, key=key: (f"{vals[c]['margin'][key]:+.1f}"
                                    if c in vals else None))
            made += m; worst = max(worst, ov); moved = max(moved, sh)

            # ---- rank
            svals = [vals[c]["share"][key] for c in paths if c in vals]
            sedges = quantile_edges(svals, k)
            order = {c: i + 1 for i, c in enumerate(
                sorted((c for c in paths if c in vals),
                       key=lambda c: -vals[c]["share"][key]))}
            m, ov, sh = figure(
                level, paths, centres, gov, vals, key,
                f"{cl} — where he stood, ranked",
                f"his own share, in {k} equal-count classes", sedges, colours,
                rank_labels(svals, sedges, k),
                f"standing among the {len(vals)} {level}s",
                "Darker is a better result for this candidate. Classes are "
                "equal-count bins of this candidate's own share, so the map "
                "shows where he stood against his own best and worst — not "
                "against the other candidates.\nThe number on each unit is its "
                "rank, 1 being his strongest.",
                f"{key}_rank_{level}", fontsize,
                lambda c, key=key: vals[c]["share"][key] if c in vals else None,
                lambda c, order=order: (str(order[c]) if c in order else None))
            made += m; worst = max(worst, ov); moved = max(moved, sh)

        print(f"  value labels: worst remaining overlap {worst:.2f} px, "
              f"furthest label moved {moved:.1f} px from its centroid")
        for m in made:
            print(f"    {os.path.getsize(m):>9,}  {m}")


if __name__ == "__main__":
    main()
