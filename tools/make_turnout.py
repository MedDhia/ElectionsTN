"""Turnout maps, on a basis that had to be repaired before it could carry one.

Why this family needed a data fix first
---------------------------------------
Turnout is the central fact of this election -- about 30% against Saied's 91% --
but the published `turnout_pct` could not carry a map. Three defects, all
measured before anything was drawn:

- **The quality gate had been dropped.** `pv_presidential_2024.csv` blanks
  turnout on every row whose registered count is known bad;
  `build_margins.py` recomputed it from the raw columns and lost that, so 40
  stations published impossible turnout, the worst at **13,133%** (3
  registered, 394 voters).
- **Numerator and denominator were summed over different stations.** In 167 of
  264 delegations `registered` and `voters` covered different station sets, so
  the ratio was nobody's turnout. Houmt Souk published **1.1%** -- `registered`
  from 47 stations over `voters` from 3 -- against 17.3% on the matched subset.
- **Four rows carried a flag their own columns refuted**, with a stale turnout
  to match. `tools/fix_registered_flags.py` withdrew them.

After the repair: stations over 100% go from 44 to **0**, delegation turnout
runs **13.8% to 44.8%** rather than a spurious 1.1% to 48.3%, and 47 delegations
moved by more than 3 points. Mapping the column as it stood would have drawn a
turnout collapse across the south that does not exist.

The caveat that belongs on every one of these figures
------------------------------------------------------
`docs/CODEBOOK.md` is explicit: **`a_registered` is the only field in the
dataset with no arithmetic backup.** "It appears in none of the form's
identities, so nothing on the paper checks it and the decoder cannot correct it
-- it is the one field read by classifier alone." Every other published column
is certified by an identity or determined by ones that are.

So turnout here is a **certified numerator over an uncertified denominator**,
and that is weaker evidence than anything else mapped in this repo. It is
printed on the figures rather than buried.

Coverage, and why some units are drawn grey
--------------------------------------------
A unit's turnout rests only on the stations where both figures survived, and
that subset is not random -- the codebook warns that the forms which fail are
the low-resolution scans, and missingness runs from 8.1% of Nabeul's stations
to 18.1% of Medenine's. `turnout_coverage_pct` travels with every figure.

Units below `COVERAGE_MIN` are drawn in the no-data grey and named in the
legend, exactly as the 42 result-less imadas already are elsewhere. The floor is
50%: at delegation level there is a real cliff there -- five delegations sit at
5-6% coverage and every other one is at 60% or above -- and at imada level it
greys 75 of 2,042. The ladder is printed by `--report`.

The scale, and the national rate on it
--------------------------------------
Turnout genuinely straddles its national rate in both directions: 13.8% to 44.8%
around 30.38%, with 110 delegations below and 154 above, a spread of
-16.6/+14.4pp and a skew of -0.68pp. That is the polarity a diverging scale
exists to encode, and it is exactly what the margin maps lacked -- "Saied's
margin is positive in all 264 delegations, so there is no polarity for a
diverging scale to encode". The palette documents one hue, so rather than
inventing a second the rate is **ruled across the colourbar and labelled**, and
the two-sided reading survives on the documented blue ramp.

These figures come in two scales, and the pair is the point. In `maps/turnout/`
the bar is the fixed 0-100%, so a shade means the same turnout as on any other
figure in the repo -- at the price that 13.8-44.8% is about a third of the bar
and the map reads flat. In `maps/fitted/` the bar spans only the values the map
contains, which is about 3.2 times the contrast at delegation level and is what
makes the geography legible -- at the price that a shade means nothing anywhere
else. Neither is the honest one on its own; each names what it gave up.

Turnout against Saied's share
------------------------------
The relationship most often assumed about this election is not in the data.
Pearson r is **+0.06** across stations and **+0.20** across delegations -- so
Saied did not do better where turnout collapsed; if anything, very mildly the
reverse. The gap between the two figures is itself worth seeing: it is a
modifiable-areal-unit effect, the same values aggregated differently, and
`turnout_vs_saied_*` plots both.
"""

import argparse
import collections
import csv
import json
import os
import math
import statistics as st
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from make_maps import (ARCHIVE, GOV_LINE, HILITE, INK, INK_2, NO_DATA, RAMP,
                       SURFACE, class_of, draw, feature_path, figure_dir,
                       load_layer, quantile_edges, read, save_figure,
                       pct_buckets, pct_colour, colour_bar,
                       PCT_VMIN, PCT_VMAX, FITTED_FAMILY, fitted_ticks)

FAMILY = "turnout"

# Below this share of a unit's stations, the turnout figure rests on too thin a
# remnant to draw. Measured rather than picked: see the module docstring and
# `--report`.
COVERAGE_MIN = 50.0

LEVELS = [
    ("delegation", "tun_admin3.geojson", "adm3_pcode",
     "data/delegation_margins.csv", "adm3_name", 0.004),
    ("imada", "tun_admin4.geojson", "adm4_pcode",
     "data/imada_margins.csv", "adm4_name", 0.002),
]

# No Arabic in figure text: matplotlib has no bidi or shaping support, so the
# column letters render mangled and jump position -- "(أ)" came out as "(Ĭ)"
# in the middle of a sentence. The letters belong in the codebook, not here.
FOOT = ("Source: ISIE procès-verbaux · boundaries OCHA/HDX COD-AB (CC BY-IGO) · "
        "turnout is voters over registered, on the stations where both "
        "figures survived the read")

UNCERTIFIED = (
    "The registered count is the only field in this dataset that no identity "
    "on the form checks — the one field read by classifier alone — so turnout "
    "is a "
    "certified numerator over an uncertified denominator, and is weaker "
    "evidence than any candidate figure mapped elsewhere in this directory.")

VERIFY = "data/verification/turnout.jsonl"


# ---- the basis ------------------------------------------------------------
def national_rate(rows):
    """Turnout over the matched, gated subset — the only defensible total."""
    r = sum(int(x["turnout_registered"]) for x in rows if x["turnout_registered"])
    v = sum(int(x["turnout_voters"]) for x in rows if x["turnout_voters"])
    return 100.0 * v / r, r, v


def usable(row):
    """Rows whose turnout rests on enough of the unit to draw."""
    return (row.get("turnout_pct") not in (None, "", "NA")
            and row.get("turnout_coverage_pct") not in (None, "", "NA")
            and float(row["turnout_coverage_pct"]) >= COVERAGE_MIN)


# `anchored_edges` and `pct_labels` lived here: they put the national rate on a
# class boundary so a one-hue ramp could be read two-sidedly. With the scale
# fixed at 0-100 there are no class boundaries to place it on, so the rate is
# ruled across the colourbar instead and both are gone rather than left
# unreferenced.


def count_labels(edges, unit="voters"):
    def f(v):
        return f"{v/1000:.0f}k" if v >= 10000 else f"{v:,.0f}"
    return [f"{f(edges[i])} – {f(edges[i+1])}" for i in range(len(edges) - 1)]


COVER_EDGES = [0.0, 50.0, 70.0, 80.0, 90.0, 95.0, 99.0, 100.0]
COVER_LABELS = ["under 50% — not drawn", "50 – 70%", "70 – 80%", "80 – 90%",
                "90 – 95%", "95 – 99%", "99 – 100%"]


# ---- figures --------------------------------------------------------------
def _wrap(text, cols):
    import textwrap
    return "\n".join(textwrap.fill(line, cols) if line else ""
                     for line in text.split("\n"))


def _save(fig, stem, formats=None):
    return save_figure(fig, stem, formats) if formats else save_figure(fig, stem)


def _paths(feats, keep, tol):
    return [feature_path(feats[i]["geometry"], tol) for i in keep]


def _gov_paths(tol):
    return [p for p in (feature_path(f["geometry"], tol * 2)
                        for f in load_layer("tun_admin2.geojson")) if p]


def choropleth(res, key, tol, paths, gov_paths, formats=None, scale="fixed"):
    """One quantity, one level.

    `scale="fitted"` spans the ramp over exactly the values this map contains
    and writes to `maps/fitted/`. Turnout is the quantity where that buys the
    most here -- 13.8-44.8% across delegations is a third of the fixed bar, so
    fitting it roughly triples the contrast -- and the figure carries a
    reference strip so the exaggeration stays visible.
    """
    rows, nat = res["rows"], res["national"]
    spec = {
        "turnout": dict(
            title="Turnout", value=lambda r: float(r["turnout_pct"]),
            unit="turnout (% of registered)", anchored=True),
        "registered": dict(
            title="Registered electorate",
            value=lambda r: float(r["turnout_registered"]),
            unit="registered voters (matched basis)", anchored=False),
    }[key]

    drawn = [r for r in rows if usable(r)] if key == "turnout" else \
            [r for r in rows if r.get("turnout_registered") not in ("", None)]
    vals = [spec["value"](r) for r in drawn]
    # Turnout is a percentage, so it takes the fixed 0-100 bar. The registered
    # electorate is a head count and cannot: it keeps quantile classes.
    # Only turnout is a percentage; the registered electorate is a head count
    # and stays on quantile classes, which already fit their own data.
    on_bar = spec["anchored"]
    fitted = on_bar and scale == "fitted"
    bar = (min(vals), max(vals)) if fitted else (PCT_VMIN, PCT_VMAX)
    ticks = fitted_ticks(*bar) if fitted else None
    ctx = (PCT_VMIN, PCT_VMAX) if fitted else None
    edges = None if on_bar else quantile_edges(vals, len(RAMP))
    labels = None if on_bar else count_labels(edges)

    idx = {r[res["pcode"]]: r for r in drawn}
    buckets = collections.defaultdict(list)
    nodata = []
    for i, code in enumerate(res["codes"]):
        p = paths[i]
        if p is None:
            continue
        if code in idx:
            v = spec["value"](idx[code])
            buckets[pct_colour(v, *bar) if on_bar
                    else RAMP[class_of(v, edges)]].append(p)
        else:
            nodata.append(p)
    if nodata:
        buckets[NO_DATA] = nodata

    fig, ax = plt.subplots(figsize=(7.8, 9.4))
    basis = (f" · scale fitted to this map "
             f"({100.0*(bar[1]-bar[0])/100.0:.0f}% of the full range)"
             if fitted else "")
    sub = (f"{res['level']} level · national rate {nat:.2f}%{basis}"
           if key == "turnout" else f"{res['level']} level")
    draw(ax, dict(buckets), gov_paths, spec["title"], sub, edges, spec["unit"],
         len(drawn), len(nodata), labels=labels,
         no_data_label=("coverage under "
                        f"{COVERAGE_MIN:.0f}%, withheld"
                        if key == "turnout" else "no result"),
         colourbar=bar if on_bar else None,
         observed=(min(vals), max(vals)) if (on_bar and not fitted) else None,
         marker=(nat, "national rate") if on_bar else None,
         ticks=ticks, context=ctx)
    if fitted:
        note = (
            f"SCALE FITTED TO THIS MAP: the ramp spans {bar[0]:.1f}% to "
            f"{bar[1]:.1f}%, not 0 to 100, which is about "
            f"{100.0/(bar[1]-bar[0]):.1f} times the contrast of the fixed-scale "
            f"version — and the reason the geography is legible here and flat "
            f"there. The price is that a shade means nothing on any other "
            f"figure. The strip beside the bar shows the window; the rule is "
            f"still the national rate, {nat:.2f}%, with "
            f"{sum(1 for v in vals if v < nat)} units below it and "
            f"{sum(1 for v in vals if v >= nat)} above.\n"
            f"For a shade that means one number everywhere, use "
            f"maps/turnout/turnout_{res['level']}.*\n"
            f"{len(nodata)} unit(s) are drawn grey because their turnout would "
            f"rest on under {COVERAGE_MIN:.0f}% of their stations.\n"
            f"{UNCERTIFIED}\n{FOOT}")
    elif key == "turnout":
        note = (
            f"The scale is fixed at 0–100%, so a shade means the same turnout "
            f"here as on every other figure in this repository. The rule "
            f"across the bar is the national rate, {nat:.2f}%: "
            f"{sum(1 for v in vals if v < nat)} units fall below it and "
            f"{sum(1 for v in vals if v >= nat)} above. The bracket beside the "
            f"bar is the observed range, {min(vals):.1f}% to {max(vals):.1f}% "
            f"— a third of the scale, which is why the map reads flat.\n"
            f"{len(nodata)} unit(s) are drawn grey because their turnout would "
            f"rest on under {COVERAGE_MIN:.0f}% of their stations — see the "
            f"coverage map beside this one.\n{UNCERTIFIED}\n{FOOT}")
    else:
        note = (f"The electorate itself, summed over the same matched stations "
                f"the turnout ratio uses, so the two maps rest on one basis. "
                f"{len(nodata)} unit(s) have none.\n{UNCERTIFIED}\n{FOOT}")
    fig.text(0.012, 0.012, _wrap(note, 116), fontsize=6.8, color=INK_2,
             va="bottom")
    fig.tight_layout(rect=(0, 0.075, 1, 1))
    made = _save(fig, f"{figure_dir(FITTED_FAMILY if fitted else FAMILY)}/"
                 f"{key}_{res['level']}", formats)
    plt.close(fig)
    return made


def coverage_figure(res, tol, paths, gov_paths, formats=None):
    """How much of each unit the turnout figure actually rests on.

    Published as a map of its own rather than a footnote, because the gaps are
    spatially structured: missingness runs from 8.1% of Nabeul's stations to
    18.1% of Medenine's, so a reader comparing two governorates is also
    comparing two different levels of evidence.
    """
    rows = res["rows"]
    idx = {r[res["pcode"]]: r for r in rows}
    counts = [0] * (len(COVER_EDGES) - 1)
    covs = []
    buckets = collections.defaultdict(list)
    nodata = []
    for i, code in enumerate(res["codes"]):
        p = paths[i]
        if p is None:
            continue
        r = idx.get(code)
        if r is None or r.get("turnout_coverage_pct") in ("", None):
            nodata.append(p)
            continue
        cv = float(r["turnout_coverage_pct"])
        counts[class_of(cv, COVER_EDGES)] += 1
        covs.append(cv)
        buckets[pct_colour(cv)].append(p)
    if nodata:
        buckets[NO_DATA] = nodata
    fig, ax = plt.subplots(figsize=(7.8, 9.4))
    draw(ax, dict(buckets), gov_paths, "Turnout coverage",
         f"share of each unit's stations carrying both figures · "
         f"{res['level']} level", None,
         "stations on the turnout basis (%)", len(rows), len(nodata),
         no_data_label="no stations read", colourbar=True,
         observed=(min(covs), max(covs)) if covs else None,
         marker=(COVERAGE_MIN, "withholding floor"))
    below = sum(1 for r in rows if r.get("turnout_coverage_pct") not in ("", None)
                and float(r["turnout_coverage_pct"]) < COVERAGE_MIN)
    note = (
        f"Turnout is computed only over stations where both the registered and "
        f"the voters figure survived the read and the registered figure passed "
        f"its gate. This map is how much of each unit that is; the {below} "
        f"unit(s) below the {COVERAGE_MIN:.0f}% floor ruled on the bar are "
        f"withheld from the turnout map entirely.\n"
        f"The gaps are not random: the forms that fail are the low-resolution "
        f"scans, so a unit with poor coverage is also a unit whose surviving "
        f"stations may not represent it. Read the turnout map against this "
        f"one.\n{FOOT}")
    fig.text(0.012, 0.012, _wrap(note, 116), fontsize=6.8, color=INK_2,
             va="bottom")
    fig.tight_layout(rect=(0, 0.070, 1, 1))
    made = _save(fig, f"{figure_dir(FAMILY)}/coverage_{res['level']}", formats)
    plt.close(fig)
    return made


def scatter_figure(res, formats=None):
    """Turnout against Saied's share — the relationship that is not there."""
    rows = [r for r in res["rows"] if usable(r) and r.get("saied_share_pct")]
    x = np.array([float(r["turnout_pct"]) for r in rows])
    y = np.array([float(r["saied_share_pct"]) for r in rows])
    w = np.array([float(r["turnout_registered"]) for r in rows])
    r_p = float(np.corrcoef(x, y)[0, 1])
    nat = res["national"]

    fig, ax = plt.subplots(figsize=(7.6, 5.6))
    ax.set_facecolor(SURFACE)
    ax.scatter(x, y, s=np.clip(w / w.mean() * 14, 2, 220), alpha=0.42,
               linewidths=0, color=RAMP[4])
    b, a = np.polyfit(x, y, 1)
    xs = np.linspace(x.min(), x.max(), 50)
    ax.plot(xs, a + b * xs, color=HILITE, linewidth=1.6)
    ax.axvline(nat, color=INK_2, linewidth=1.0, linestyle="--")
    ax.annotate(f"national rate {nat:.1f}%", (nat, PCT_VMIN),
                textcoords="offset points", xytext=(5, 8), fontsize=8,
                color=INK_2)
    # Both axes are percentages, so both run the full 0-100 rather than being
    # fitted to the cloud -- the same rule the maps follow, and it is what makes
    # visible that turnout occupies a third of its range while Saied's share
    # occupies the top fifth of its.
    ax.set_xlim(PCT_VMIN, PCT_VMAX)
    ax.set_ylim(PCT_VMIN, PCT_VMAX)
    ax.set_xticks(range(0, 101, 10))
    ax.set_yticks(range(0, 101, 10))
    ax.set_xlabel("turnout (% of registered)", fontsize=9, color=INK_2)
    ax.set_ylabel("Saied's share of valid votes (%)", fontsize=9, color=INK_2)
    ax.set_title(f"Turnout against Saied's share — {res['level']} level",
                 fontsize=12, fontweight="bold", color=INK, loc="left")
    ax.grid(alpha=0.25, linewidth=0.5)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.tick_params(labelsize=8, colors=INK_2)
    note = (
        f"Pearson r = {r_p:+.3f} across {len(rows):,} {res['level']}s; the "
        f"fitted line rises {b:+.2f} points of Saied's share per point of "
        f"turnout. Points are sized by registered electorate, so the large "
        f"circles carry the votes.\n"
        f"The relationship most often assumed about this election is not in "
        f"this data. Across the {res['station_n']:,} stations on the same basis "
        f"r is {res['station_r']:+.3f}, against {r_p:+.3f} here — both near "
        f"zero, and the difference between them is a modifiable areal unit "
        f"effect rather than a finding: the same votes, aggregated two ways.\n"
        f"Units below {COVERAGE_MIN:.0f}% turnout coverage are excluded here as "
        f"on the maps.\n{UNCERTIFIED}\n{FOOT}")
    fig.text(0.010, 0.012, _wrap(note, 118), fontsize=6.8, color=INK_2,
             va="bottom")
    fig.tight_layout(rect=(0, 0.30, 1, 1))
    made = _save(fig, f"{figure_dir(FAMILY)}/turnout_vs_saied_{res['level']}",
                 formats)
    plt.close(fig)
    return made


# ---- coarser levels -------------------------------------------------------
# Governorate and region are summed from the delegation table on nested pcodes,
# the same way make_levels does it: adm2 is the first four characters of adm3
# and adm1 the first three. Neither level invents a source.
COARSE = [("governorate", "tun_admin2.geojson", "adm2_pcode", 4, 0.006),
          ("region", "tun_admin1.geojson", "adm1_pcode", 3, 0.008)]


def coarse_rows(deleg_rows, chars):
    """Turnout rolled up on the matched basis, never averaged from below."""
    agg = collections.defaultdict(lambda: collections.Counter())
    for r in deleg_rows:
        k = r["adm3_pcode"][:chars]
        agg[k]["reg"] += int(r["turnout_registered"] or 0)
        agg[k]["vot"] += int(r["turnout_voters"] or 0)
        agg[k]["st"] += int(r["turnout_stations"] or 0)
        agg[k]["n"] += int(r["n_stations"] or 0)
    out = {}
    for k, a in agg.items():
        out[k] = {
            "turnout_pct": f"{100.0 * a['vot'] / a['reg']:.4f}" if a["reg"] else "",
            "turnout_registered": a["reg"], "turnout_voters": a["vot"],
            "turnout_coverage_pct": f"{100.0 * a['st'] / a['n']:.4f}" if a["n"] else "",
        }
    return out


def coarse_figure(level, layer, pcode, chars, tol, deleg_rows, nat,
                  formats=None, scale="fixed"):
    vals_by = coarse_rows(deleg_rows, chars)
    feats = load_layer(layer)
    names = {f["properties"][pcode]: f["properties"].get(
        pcode.replace("_pcode", "_name"), "") for f in feats}
    have = {k: v for k, v in vals_by.items() if v["turnout_pct"]}
    vals = [float(v["turnout_pct"]) for v in have.values()]
    # 24 governorates and 6 regions leave turnout in a very narrow band, so
    # this is where the fixed 0-100 bar flattens hardest.
    fitted = scale == "fitted" and vals and max(vals) > min(vals)
    bar = (min(vals), max(vals)) if fitted else (PCT_VMIN, PCT_VMAX)
    buckets = collections.defaultdict(list)
    labelled = []
    for f in feats:
        code = f["properties"][pcode]
        path = feature_path(f["geometry"], tol)
        if path is None:
            continue
        v = have.get(code)
        if v is None:
            buckets[NO_DATA].append(path)
            continue
        buckets[pct_colour(float(v["turnout_pct"]), *bar)].append(path)
        labelled.append((names.get(code, code), float(v["turnout_pct"])))
    gov = _gov_paths(tol)
    fig, ax = plt.subplots(figsize=(7.9, 9.4))
    # At 24 and 6 units the note lists every unit and its rate: with the scale
    # fixed the map cannot separate them, so the numbers carry the detail.
    order = sorted(labelled, key=lambda t: -t[1])
    basis = (f" · scale fitted to this map "
             f"({100.0*(bar[1]-bar[0])/100.0:.0f}% of the full range)"
             if fitted else "")
    draw(ax, dict(buckets), gov, f"Turnout by {level}",
         f"summed from the delegation table on the matched basis · "
         f"national rate {nat:.2f}%{basis}", None, "turnout (% of registered)",
         len(have), 0, colourbar=bar,
         observed=None if fitted else ((min(vals), max(vals)) if vals else None),
         marker=(nat, "national rate"),
         ticks=fitted_ticks(*bar) if fitted else None,
         context=(PCT_VMIN, PCT_VMAX) if fitted else None)
    note = ((f"SCALE FITTED TO THIS MAP: the ramp spans {bar[0]:.1f}% to "
             f"{bar[1]:.1f}%, about {100.0/(bar[1]-bar[0]):.0f} times the "
             f"contrast of the fixed-scale version — aggregating to "
             f"{len(have)} units leaves turnout in a narrow band, so the fixed "
             f"one is nearly uniform. A shade here means nothing on any other "
             f"figure; maps/turnout/turnout_{level}.* is the comparable one.\n"
             if fitted else "")
            + "  ·  ".join(f"{n} {v:.1f}%" for n, v in order)
            + "\n"
            + f"Rolled up from the delegation table by summing the matched "
              f"numerator and denominator, not by averaging the level below: a "
              f"3,000-voter delegation must not weigh the same as a 60,000-voter "
              f"one. Range {min(vals):.1f}% to {max(vals):.1f}%.\n"
            + UNCERTIFIED + "\n" + FOOT)
    fig.text(0.012, 0.012, _wrap(note, 116), fontsize=6.8, color=INK_2,
             va="bottom")
    fig.tight_layout(rect=(0, 0.085, 1, 1))
    made = _save(fig, f"{figure_dir(FITTED_FAMILY if fitted else FAMILY)}/"
                 f"turnout_{level}", formats)
    plt.close(fig)
    return made


# ---- spatial clusters on turnout ------------------------------------------
def cluster_figure(res, tol, paths, gov_paths, formats=None):
    """Is turnout clustered beyond chance, and where?

    Same machinery as the `clusters/` family -- queen contiguity from shared
    ring vertices, conditional permutation, Benjamini-Hochberg across every
    unit -- applied to turnout instead of a candidate share. Only the units
    that pass the coverage floor take part: a unit withheld from the turnout
    map must not contribute a spatial lag either.
    """
    import spatial_stats as st_
    import spatial_weights as sw

    rows = {r[res["pcode"]]: r for r in res["rows"] if usable(r)}
    feats, keep_all = res["feats"], res["keep"]
    keep = [i for i in keep_all if feats[i]["properties"][res["pcode"]] in rows]
    adj_all = sw.queen_adjacency(feats)
    adj, _ = sw.subset(adj_all, keep)
    nm = [feats[i]["properties"].get(
        res["pcode"].replace("_pcode", "_name"), "") for i in keep]
    xy = sw.centroids_km(
        [float(feats[i]["properties"]["center_lat"]) for i in keep],
        [float(feats[i]["properties"]["center_lon"]) for i in keep])
    bridges = sw.bridge_components(adj, xy, nm)
    W = sw.row_standardised(adj)
    codes = [feats[i]["properties"][res["pcode"]] for i in keep]
    z = st_.standardise([float(rows[c]["turnout_pct"]) for c in codes])
    g = st_.global_moran(z, W, perms=9999, seed=11)
    lm = st_.local_moran(z, W, adj, perms=9999, seed=11, q=0.05)
    quad = [str(st_.QUADRANTS[v]) for v in lm["quadrant"]]
    counts = collections.Counter(quad)

    fill = {"HH": RAMP[6], "LL": RAMP[1], "HL": HILITE, "ns": NO_DATA}
    pos = {c: i for i, c in enumerate(codes)}
    buckets = collections.defaultdict(list)
    lh, withheld = [], []
    for i, code in enumerate(res["codes"]):
        p = paths[i]
        if p is None:
            continue
        j = pos.get(code)
        if j is None:
            withheld.append(p)
            continue
        q = quad[j]
        if q == "LH":
            lh.append(p)
            buckets[fill["LL"]].append(p)
        else:
            buckets[fill[q]].append(p)
    if withheld:
        buckets[NO_DATA] = buckets.get(NO_DATA, []) + withheld
    labels = [f"high turnout among high — HH ({counts['HH']})",
              f"low among low — LL ({counts['LL']})",
              f"high among low — HL ({counts['HL']})",
              f"not significant ({counts['ns']})"]
    fig, ax = plt.subplots(figsize=(7.8, 9.4))
    draw(ax, dict(buckets), gov_paths, "Turnout — spatial clusters",
         f"local Moran's I, {res['level']} level · Benjamini-Hochberg q = 0.05",
         list(range(len(labels) + 1)), "LISA class", len(codes), len(withheld),
         highlight=lh or None,
         hi_label=f"low among high — LH ({counts['LH']})",
         labels=labels, colours=[fill[k] for k in ("HH", "LL", "HL", "ns")],
         no_data_label="below the coverage floor")
    p = ("p < %.4g" % g["p_floor"] if g["p_sim"] <= g["p_floor"] + 1e-12
         else "p = %.4g" % g["p_sim"])
    note = (
        f"Global Moran's I = {g['I']:+.3f} ({p}, {g['perms']:,} permutations), "
        f"so turnout is clustered in space beyond chance — but less strongly "
        f"than vote choice: the candidates' shares run +0.556/+0.552/+0.375 at "
        f"delegation level and +0.599/+0.591/+0.399 at imada, against "
        f"{g['I']:+.3f} here, and the gap widens at the finer level. Whom people "
        f"voted for is more spatially organised than whether they voted at all. "
        f"The map localises that: a class is assigned only "
        f"where a unit's own neighbourhood beats {g['perms']:,} random ones, "
        f"after correction across all {len(codes):,} units "
        f"(threshold applied: p ≤ {lm['cut']:.2g}); "
        f"{int((lm['p'] <= 0.05).sum())} reach an uncorrected p ≤ 0.05.\n"
        f"{len(withheld)} unit(s) are excluded entirely for thin coverage, so "
        f"they contribute no value and no neighbourhood. "
        + (f"{len(bridges)} island group(s) are bridged to the mainland by "
           f"their shortest link.\n" if bridges else "\n")
        + UNCERTIFIED + "\n" + FOOT)
    fig.text(0.012, 0.012, _wrap(note, 116), fontsize=6.8, color=INK_2,
             va="bottom")
    fig.tight_layout(rect=(0, 0.082, 1, 1))
    made = _save(fig, f"{figure_dir(FAMILY)}/clusters_{res['level']}", formats)
    plt.close(fig)
    return made, g, lm, counts


# ---- zoomed sheets and per-extent detail -----------------------------------
# The extent list, the geometry and the context layer all come from
# `make_zooms`, which is where they were first solved. Duplicating them would
# let the two families drift into mapping different places under the same slug.
ZOOM_NOTE = (
    "Both panels use the fixed 0–100% scale, so a shade means the same thing "
    "on every sheet and against the national maps; each bar carries the rate "
    "or floor it is read against, and a bracket giving this extent's own "
    "range. The coverage panel is the same extent's evidence: pale is a unit "
    "whose turnout rests on few of its stations, and units under the floor "
    "carry no turnout at all.")

MICRO_TURNOUT_NOTE = (
    "One extent at full page size, on the same fixed 0–100% scale as every "
    "other figure here; the bracket on the bar and the subtitle both give this "
    "extent's own range.\nThis map previously classed on the extent's own "
    "quantiles, spending the whole ramp on local variation at the price of "
    "meaning nothing outside the map. With the scale fixed it no longer does, "
    "so what it adds over the turnout panel of zoom_turnout_* is size. The "
    "turnout family has no fitted per-extent set yet; maps/fitted/ carries the "
    "national and rollup turnout maps.")


def _turnout_panels(mine, rows, nat, edges, cov_edges):
    """Two panels: turnout on the fixed scale, and the evidence behind it."""
    def turnout_of(code):
        r = rows.get(code)
        return float(r["turnout_pct"]) if r and usable(r) else None

    def coverage_of(code):
        r = rows.get(code)
        if r is None or r.get("turnout_coverage_pct") in ("", None):
            return None
        return float(r["turnout_coverage_pct"])

    tvals = [v for v in (turnout_of(c) for c in mine) if v is not None]
    cvals = [v for v in (coverage_of(c) for c in mine) if v is not None]
    bar = (PCT_VMIN, PCT_VMAX)
    return [
        ("Turnout", "turnout (% of registered)",
         f"national rate {nat:.2f}% · fixed 0–100% scale",
         turnout_of, None, None, RAMP,
         (bar, (min(tvals), max(tvals)) if tvals else None,
          (nat, "national rate"))),
        ("Coverage behind it", "stations on the turnout basis (%)",
         f"units under {COVERAGE_MIN:.0f}% carry no turnout",
         coverage_of, None, None, RAMP,
         (bar, (min(cvals), max(cvals)) if cvals else None,
          (COVERAGE_MIN, "floor"))),
    ]


def _micro_turnout_panel(mine, rows, nat):
    """One panel for this extent alone, or None if too few units carry one."""
    vals = [float(rows[c]["turnout_pct"]) for c in mine
            if c in rows and usable(rows[c])]
    if len(vals) < len(RAMP):
        return None

    def value_of(code):
        r = rows.get(code)
        return float(r["turnout_pct"]) if r and usable(r) else None

    return [("Turnout", "turnout (% of registered)",
             f"{len(vals)} imadas here · {min(vals):.1f}–{max(vals):.1f}% "
             f"· national rate {nat:.2f}%",
             value_of, None, None, RAMP,
             ((PCT_VMIN, PCT_VMAX), (min(vals), max(vals)),
              (nat, "national rate")))]


def extent_sheets(nat, formats=None, only=None):
    import make_zooms as mz

    rows = {r["adm4_pcode"]: r for r in read("data/imada_margins.csv")}
    paths, boxes, member, gov_paths = mz.load_geometry()
    extents = mz.build_extents("all")

    # Nothing to precompute now that the scale is fixed: the panels no longer
    # need national breaks, only the national rate, which they already take.
    edges = None

    made = []
    for slug, title, level, codes, bases in extents:
        if only and only != slug:
            continue
        want = set(codes)
        mine = {c: p for c, p in paths.items() if member[level][c] in want}
        if not mine:
            continue
        view = mz.window(list(mine.values()))
        others = mz.neighbours_in_view(paths, boxes, mine, view)
        drawn = sum(1 for c in mine if c in rows and usable(rows[c]))
        # A governorate-scale extent gets the comparable sheet; the six regions
        # take the local basis only, exactly as the candidate families do.
        if "shares" in bases:
            made += mz.sheet(
                f"Turnout — {title}", mine, others, gov_paths, view,
                f"zoom_turnout_{slug}",
                _turnout_panels(mine, rows, nat, edges, COVER_EDGES),
                ZOOM_NOTE + "\n" + UNCERTIFIED,
                formats=formats, adaptive_chrome=True, family=FAMILY,
                foot=FOOT)
        panel = _micro_turnout_panel(mine, rows, nat)
        if panel is None:
            print(f"  {slug}: fewer than {len(RAMP)} imadas with turnout, "
                  f"no single-extent map")
        else:
            made += mz.sheet(
                f"Turnout — {title}", mine, others, gov_paths, view,
                f"micro_turnout_{slug}", panel,
                MICRO_TURNOUT_NOTE + "\n" + UNCERTIFIED,
                formats=formats or ("pdf", "png"), adaptive_chrome=True,
                panel_titles=False, family=FAMILY, foot=FOOT)
        print(f"  {slug:<16} {drawn:4d} imadas drawn of {len(mine)}")
    return made


# ---- kernel-smoothed surface and vote-weighted cartogram --------------------
def surface_figure(nat, formats=None):
    """Turnout as a smoothed field, on the same machinery as `surfaces/`.

    Weighted by the registered electorate rather than by votes cast: turnout is
    a rate over the electorate, so the electorate is what a place contributes.
    Otherwise identical to the candidate surfaces -- adaptive bandwidth at each
    sample's nearest-neighbour distance, kernels normalised per sample, and
    cells further than the support radius from any sample left blank.
    """
    import make_kde as mk
    from scipy.spatial import cKDTree

    rows = [r for r in read("data/imada_margins.csv")
            if r["lat"] and r["lon"] and usable(r)
            and int(r["turnout_registered"] or 0) > 0]
    from make_maps import albers as _albers
    px, py = _albers([float(r["lon"]) for r in rows],
                     [float(r["lat"]) for r in rows])
    P = np.column_stack([px, py]) * mk.EARTH_KM
    weight = np.array([float(r["turnout_registered"]) for r in rows])
    values = np.array([[float(r["turnout_pct"]) for r in rows]])

    outline = [p for p in (feature_path(f["geometry"], 0.01)
                           for f in load_layer("tun_admin0.geojson")) if p]
    gov = [p for p in (feature_path(f["geometry"], 0.008)
                       for f in load_layer("tun_admin2.geojson")) if p]
    h = mk.local_bandwidth(P)
    gx, gy, shape, inside = mk.build_grid(outline, mk.GRID_KM)
    num, den, sumsq, hbar = mk.smooth(P, h, weight, values, gx, gy)
    GXs, GYs = np.meshgrid(gx, gy)
    reach = cKDTree(P).query(np.column_stack([GXs.ravel(), GYs.ravel()]))[0]
    reach = reach.reshape(den.shape)
    supported = inside & (reach <= mk.SUPPORT_KM)
    field = mk.ratio(num[0], den)

    vals = field[supported]
    note = (
        f"Each of the {len(rows):,} imada centroids is a sample carrying its "
        f"own turnout and its registered electorate as weight, smoothed over "
        f"its own nearest-neighbour distance -- the same adaptive rule the "
        f"candidate surfaces use, cross-validated there. Contoured on the same "
        f"fixed 0-100% scale as the turnout choropleth, with the national rate "
        f"of {nat:.2f}% ruled across the bar, so surface and tiles read "
        f"against each other.\n"
        f"Cells further than {mk.SUPPORT_KM:.0f} km from any sample are left "
        f"blank rather than extrapolated. Imadas below the coverage floor "
        f"contribute no sample at all, so a thin part of the country is absent "
        f"here rather than smoothed over.\n{UNCERTIFIED}\n{FOOT}")
    made = mk.draw_field(
        field, supported, inside, gx, gy, None, RAMP,
        "Turnout, smoothed", f"vote-weighted kernel estimate · imada centroids",
        "turnout (% of registered)", gov, outline, _wrap(note, 112),
        "turnout_kde", f"no sample within {mk.SUPPORT_KM:.0f} km",
        family=FAMILY, colourbar=(PCT_VMIN, PCT_VMAX),
        observed=(float(vals.min()), float(vals.max())),
        marker=(nat, "national rate"))
    return made


def cartogram_figure(nat, formats=None):
    """Delegations as circles sized by electorate, coloured by turnout.

    The choropleths are equal-area, which lets the desert dominate: the ten
    largest delegations are 40.6% of the map. Here each circle's area is the
    registered electorate on the turnout basis, so ink tracks the people whose
    participation is being measured rather than the terrain.
    """
    import make_cartograms as mc
    from make_maps import albers as _albers

    rows = [r for r in read("data/delegation_margins.csv") if usable(r)]
    lon = [float(r["lon"]) for r in rows]
    lat = [float(r["lat"]) for r in rows]
    x, y = _albers(lon, lat)
    reg = np.array([float(r["turnout_registered"]) for r in rows])
    bbox_area = (max(x) - min(x)) * (max(y) - min(y))
    k = math.sqrt(mc.FILL * bbox_area / (math.pi * reg.sum()))
    r = k * np.sqrt(reg)
    px, py, disp = mc.dorling(x, y, r)

    vals = [float(q["turnout_pct"]) for q in rows]
    fig, ax = plt.subplots(figsize=(7.9, 9.4))
    ax.set_aspect("equal"); ax.set_axis_off(); ax.set_facecolor(SURFACE)
    gov = [p for p in (feature_path(f["geometry"], 0.012)
                       for f in load_layer("tun_admin2.geojson")) if p]
    from matplotlib.collections import PathCollection
    from matplotlib.patches import Circle
    ax.add_collection(PathCollection(gov, facecolors="none",
                                     edgecolors=GOV_LINE, linewidths=0.5,
                                     zorder=1))
    for cx, cy, cr, v in zip(px, py, r, vals):
        ax.add_patch(Circle((cx, cy), cr, facecolor=pct_colour(v),
                            edgecolor="#ffffff", linewidth=0.35, zorder=3))
    ax.autoscale_view()
    x0, x1 = ax.get_xlim()
    ax.set_xlim(x1 - 1.80 * (x1 - x0), x1)
    colour_bar(ax, PCT_VMIN, PCT_VMAX, "turnout (% of registered)", False,
               (min(vals), max(vals)) if vals else None,
               (nat, "national rate"))
    ax.text(0.01, 0.985, "Turnout, weighted by electorate",
            transform=ax.transAxes, fontsize=13, color=INK, va="top",
            fontweight="bold")
    ax.text(0.01, 0.945,
            f"Dorling cartogram · circle area is registered voters · "
            f"{len(rows)} delegations",
            transform=ax.transAxes, fontsize=9.5, color=INK_2, va="top")
    note = (
        f"Circle area is the registered electorate on the turnout basis, so "
        f"the ink is proportional to the people whose participation is being "
        f"measured -- unlike the choropleth, where the ten largest delegations "
        f"cover 40.6% of the map. Positions are approximate: circles are nudged "
        f"apart until none overlap, a median {100*np.median(disp):.1f}% of the "
        f"map diagonal from where they belong.\n"
        f"Colour is the same fixed 0-100% scale as the turnout choropleth, "
        f"with the national rate of {nat:.2f}% ruled across the bar. "
        f"Delegations below the coverage floor are "
        f"absent entirely rather than drawn at zero.\n{UNCERTIFIED}\n{FOOT}")
    fig.text(0.012, 0.012, _wrap(note, 116), fontsize=6.8, color=INK_2,
             va="bottom")
    fig.tight_layout(rect=(0, 0.082, 1, 1))
    made = _save(fig, f"{figure_dir(FAMILY)}/turnout_cartogram", formats)
    plt.close(fig)
    return made


# ---- driver ---------------------------------------------------------------
def analyse(level, layer, pcode, csv_path, name_prop, tol):
    feats = load_layer(layer)
    rows = read(csv_path)
    by = {r[pcode]: r for r in rows}
    keep = [i for i, f in enumerate(feats) if f["properties"][pcode] in by]
    nat, reg, vot = national_rate(rows)
    cov = [float(r["turnout_coverage_pct"]) for r in rows
           if r.get("turnout_coverage_pct") not in ("", None)]
    # The station-level correlation, computed rather than hardcoded: an earlier
    # draft carried a figure that had drifted once the coverage floor was added.
    srows = [r for r in read("data/station_margins.csv")
             if r.get("turnout_basis") == "1" and r.get("saied_share_pct")]
    sx = np.array([float(r["turnout_pct"]) for r in srows])
    sy = np.array([float(r["saied_share_pct"]) for r in srows])
    station_r = float(np.corrcoef(sx, sy)[0, 1])
    return {
        "station_r": station_r, "station_n": len(srows),
        "level": level, "pcode": pcode, "feats": feats, "keep": keep, "tol": tol,
        "codes": [feats[i]["properties"][pcode] for i in keep],
        "rows": rows, "national": nat, "registered": reg, "voters": vot,
        "coverage": cov,
        "drawn": sum(1 for r in rows if usable(r)),
        "withheld": sum(1 for r in rows
                        if r.get("turnout_pct") not in ("", None)
                        and not usable(r)),
        "no_turnout": sum(1 for r in rows if r.get("turnout_pct") in ("", None)),
    }


def report(res):
    print(f"\n=== {res['level']}: {len(res['rows']):,} units")
    print(f"    national turnout {res['national']:.2f}%  "
          f"(registered {res['registered']:,}, voters {res['voters']:,})")
    t = sorted(float(r["turnout_pct"]) for r in res["rows"] if usable(r))
    print(f"    drawn {res['drawn']:,}   withheld for coverage "
          f"{res['withheld']}   no turnout at all {res['no_turnout']}")
    print(f"    turnout range {t[0]:.1f}% – {t[-1]:.1f}%, median {st.median(t):.1f}%, "
          f"below national {sum(1 for x in t if x < res['national'])}, "
          f"above {sum(1 for x in t if x >= res['national'])}")
    c = sorted(res["coverage"])
    print(f"    coverage: min {c[0]:.0f}%  p10 {c[len(c)//10]:.0f}%  "
          f"median {st.median(c):.0f}%  at 100% {sum(1 for x in c if x == 100)}")
    print("    coverage ladder: " + "  ".join(
        f"<{thr}%={sum(1 for x in c if x < thr)}" for thr in (25, 40, 50, 60, 70)))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--level", choices=[l[0] for l in LEVELS])
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--formats", help="comma-separated, e.g. pdf,png")
    ap.add_argument("--basis",
                    choices=["national", "extents", "surface", "all"],
                    default="all",
                    help="national: the country-wide figures. extents: the "
                         "zoomed and per-extent sheets.")
    ap.add_argument("--only", help="one extent slug, e.g. grand_tunis")
    ap.add_argument("--scale", choices=["fixed", "fitted", "both"],
                    default="fixed",
                    help="fitted also writes the turnout choropleths with the "
                         "ramp spanning only the values each contains, into "
                         "maps/fitted/.")
    args = ap.parse_args()
    if not os.path.exists(ARCHIVE):
        sys.exit(f"missing {ARCHIVE}; run tools/fetch_boundaries.py")
    formats = tuple(args.formats.split(",")) if args.formats else None

    made, records = [], []
    for level, layer, pcode, csv_path, name_prop, tol in LEVELS:
        if args.level and level != args.level:
            continue
        res = analyse(level, layer, pcode, csv_path, name_prop, tol)
        report(res)
        records.append({
            "level": level, "national_turnout_pct": round(res["national"], 4),
            "registered": res["registered"], "voters": res["voters"],
            "units": len(res["rows"]), "drawn": res["drawn"],
            "withheld_for_coverage": res["withheld"],
            "coverage_floor_pct": COVERAGE_MIN,
            "coverage_median_pct": round(st.median(res["coverage"]), 4),
        })
        if args.report or args.basis not in ("national", "all"):
            continue
        paths = _paths(res["feats"], res["keep"], tol)
        gov = _gov_paths(tol)
        for sc in (("fixed", "fitted") if args.scale == "both"
                   else (args.scale,)):
            made += choropleth(res, "turnout", tol, paths, gov, formats,
                               scale=sc)
        # The electorate is a head count, not a percentage: it has no fixed
        # scale to depart from, so there is only one version of it.
        if args.scale in ("fixed", "both"):
            made += choropleth(res, "registered", tol, paths, gov, formats)
        made += coverage_figure(res, tol, paths, gov, formats)
        made += scatter_figure(res, formats)
        cmade, g, lm, counts = cluster_figure(res, tol, paths, gov, formats)
        made += cmade
        records[-1].update({
            "morans_i": round(g["I"], 6), "morans_p": g["p_sim"],
            "lisa_significant": int(lm["sig"].sum()),
            "lisa_classes": dict(counts),
        })
        print(f"    Moran's I {g['I']:+.4f} (p={g['p_sim']:.5f})  "
              f"LISA significant {int(lm['sig'].sum())}  {dict(counts)}")
        if level == "delegation":
            for cl, layer, pc, ch, ctol in COARSE:
                for sc in (("fixed", "fitted") if args.scale == "both"
                           else (args.scale,)):
                    made += coarse_figure(cl, layer, pc, ch, ctol,
                                          res["rows"], res["national"],
                                          formats, scale=sc)

    if not args.report and args.basis in ("surface", "all"):
        nat = national_rate(read("data/imada_margins.csv"))[0]
        made += surface_figure(nat, formats)
        made += cartogram_figure(
            national_rate(read("data/delegation_margins.csv"))[0], formats)

    if not args.report and args.basis in ("extents", "all"):
        nat = national_rate(read("data/imada_margins.csv"))[0]
        made += extent_sheets(nat, formats, args.only)

    if not args.report:
        os.makedirs(os.path.dirname(VERIFY), exist_ok=True)
        with open(VERIFY, "w", encoding="utf-8") as fh:
            for rec in records:
                fh.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
        for f in made:
            print(f"    {os.path.getsize(f):>9,}  {f}")
        print(f"{len(made)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
