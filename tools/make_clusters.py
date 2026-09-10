"""Spatial cluster maps: where the pattern beats chance, and where the regions are.

What this adds that no other family here does
---------------------------------------------
Every other figure in `maps/` shows *where* a value is. None of them attaches a
null model, and a choropleth of pure noise still looks patchy -- the eye finds
regions in anything. So "Saied is strong in the centre" has not been a finding
in this repo so far, only a description. These maps test it.

Global Moran's I is printed on every figure, because a local statistic is only
worth reading once the global one says there is structure to localise. There is,
overwhelmingly -- every pseudo p sits at the 1/10,000 floor:

    global Moran's I    delegation      imada
    Saied                 +0.556       +0.599
    Zammel                +0.552       +0.591
    Maghzaoui             +0.375       +0.399

`lisa_*` -- is this unit's neighbourhood unusual, and in which direction?
------------------------------------------------------------------------
Local Moran's I classes each unit by the sign of its own deviation and the sign
of its neighbours': `HH` is a unit above the mean among neighbours above it,
`LL` below among below, and the two mixed classes are spatial outliers.

`hotspot_*` -- the same test, drawn as a surface
------------------------------------------------
Getis-Ord Gi* includes the unit itself and has no outlier classes, which makes
it the more legible reading. But it is **not independent evidence**, and this is
worth stating because it is easy to present two figures as two confirmations:
under conditional permutation both statistics reduce to the same question --
is unit i's neighbourhood mean extreme against random neighbourhoods drawn from
the same values? -- because unit i's own value is held fixed in both and
therefore cancels out of the comparison.

Measured, not argued: on the same seed the two sets of p-values differ by at
most 0.001, one permutation's worth, and they select the same significant units
at every level and for every candidate. On a different seed they differ by 0.09,
which is ordinary Monte Carlo noise. So `hotspot_*` adds the continuous
z-surface and the hot/cold direction that the categorical LISA map throws away;
it does not add a second test.

`regions_*` -- what are the electoral regions, ignoring the administrative ones?
-------------------------------------------------------------------------------
Ward agglomeration on the three-candidate share vector under a contiguity
constraint, so every region is a connected piece of the country. This is the one
figure in the repo that draws a boundary the state did not draw.

The result is the headline: **six electoral regions explain more than three
times the variance the six official regions do, and more than all twenty-four
governorates.**

    variance explained (R^2)   delegation      imada
    6 official regions            0.209        0.157
    24 governorates               0.457        0.302
    6 electoral regions           0.670        0.482

Ward maximises this criterion by construction, so the clustering is *expected*
to win; the size of the gap is the informative part, not its sign. Six clusters
overtaking twenty-four governorates is not something the construction guarantees.

Three decisions worth stating
-----------------------------
**Permutation inference, not the analytical z.** The analytical variance of
Moran's I assumes normality; these shares are severely skewed (Saied's
delegation median 93.8% against a 59.7% floor), so that approximation is not
credible here.

**Benjamini-Hochberg, and it changes the answer.** The imada level runs 2,042
simultaneous tests, which at a nominal 0.05 expects about 102 false positives --
more units than any candidate's genuine cluster occupies here. Demonstrated
rather than asserted: on pure lattice noise this code returns exactly 20 of 400
units at raw p <= 0.05, the nominal 5%, and 0 after FDR. On the real data the
correction is just as sharp -- 445 imadas reach raw p <= 0.05 for Saied and 64
survive.

**10,000 permutations, because 1,000 is not enough here -- measured.** BH cannot
pass a unit whose p-value sits at the permutation floor unless enough units tie
there, and at m = 2,042 that needs about 41 of them. At 999 permutations
Zammel's imada LISA reported **zero** significant units and Maghzaoui's zero
too; at 9,999 they report 52 and 7. Those were false negatives manufactured
entirely by the p-value floor:

    imada, significant after FDR   Saied  Zammel  Maghzaoui
    999 permutations                  42       0          0
    9,999 permutations                64      52          7
    39,999 permutations               69      55          7

9,999 is where it converges -- quadrupling it again moves at most five units --
so that is what ships. The delegation level was already stable at 999, so the
imada level set the budget.

What the maps show
------------------
At delegation level the only significant cluster in the country is the Tunis
metropolitan core, and the three candidates' maps are nested rather than
independent: Saied's eight `LL` delegations -- Ariana Medina, Bab Bhar, Cite El
Khadra, El Menzah, Le Kram, Omrane, Rades, Soukra -- are a strict **subset** of
Zammel's nine `HH`, which adds Omrane Superieur. That is the arithmetic of a
91% result, where Saied's weakness is mechanically his rival's strength.

Maghzaoui's is a different cluster entirely, and a real one: five delegations in
the Kebili and Gafsa oases (Belkhir, Faouar, Kebili Nord, Kebili Sud, Souk El
Ahed) plus one spatial outlier, Guetar. The regionalisation finds the same thing
independently -- a 30-imada cluster averaging 6.4% for Maghzaoui against his
1.89% nationally -- and isolates Bou Abdellah, at 40.7%, on its own.

Islands and the graph
---------------------
Contiguity comes from `spatial_weights`, which derives it from shared ring
vertices and then bridges the disconnected island components. The order matters
and was got wrong once: subsetting to units that have a result *before* bridging
makes an island look like a stranded unit and drops it, which silently removed
Kerkennah from a national map. Subsetting comes first, bridging second, and then
nothing needs dropping -- 264 of 264 and 2,042 of 2,042 units are kept.

The units at a bridge endpoint are flagged in the published CSV, because their
"neighbourhood" is an imposed edge across water rather than an observed border.
"""

import argparse
import collections
import csv
import json
import os
import sys
import warnings

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import PathCollection
from matplotlib.patches import Patch, Rectangle
from matplotlib.transforms import Bbox
from scipy import sparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from make_maps import (ARCHIVE, GOV_LINE, HILITE, INK, INK_2, NO_DATA, RAMP,
                       SURFACE, class_of, draw, feature_path, figure_dir,
                       load_layer, read, save_figure)

FAMILY = "clusters"

CANDIDATES = [("saied", "Kais Saied"), ("zammel", "Ayachi Zammel"),
              ("maghzaoui", "Zouhair Maghzaoui")]

# (name, layer, pcode column, csv, name property, simplify tolerance)
LEVELS = [
    ("delegation", "tun_admin3.geojson", "adm3_pcode",
     "data/delegation_margins.csv", "adm3_name", 0.004),
    ("imada", "tun_admin4.geojson", "adm4_pcode",
     "data/imada_margins.csv", "adm4_name", 0.002),
]

# Measured, not chosen: see the permutation ladder in the module docstring.
PERMS = 9999
Q = 0.05
SEED = 11

# Ward regionalisation. k = 6 is the whole point of the comparison -- it is the
# number of official regions, so the two partitions are matched on their one
# free parameter and only the criterion differs.
K_REGIONS = 6
K_LADDER = (2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 15, 24)

# LISA fills. Kept inside the documented palette: the two cluster classes take
# the ramp's extremes, so dark still reads as high, and both spatial-outlier
# classes take HILITE, whose established meaning in this repo is already "this
# unit is the anomaly". The rarer of the two outlier classes is drawn as a
# HILITE outline through draw()'s existing highlight hook rather than inventing
# an eighth hex.
LISA_FILL = {"HH": RAMP[6], "LL": RAMP[1], "HL": HILITE, "ns": NO_DATA}

# Gi* is classed on ABSOLUTE z bands, not quantiles -- the one family here that
# does. Two reasons. A z-score already carries its own units, so quantiles throw
# that away: on this data the top quantile class ran "1.4 - 19.5", putting a
# barely-above-average imada in the same bin as the strongest hot spot in the
# country and painting the whole south one shade. And absolute bands are
# comparable *between* candidates and *between* levels, which no per-candidate
# quantile scheme in this repo can be. The cut points are the conventional
# two-tailed 90 / 95 / 99% normal ones; the ramp is descriptive and the outline
# carries the FDR-corrected inference, which is stricter.
GI_EDGES = [-np.inf, -2.58, -1.96, -1.65, 1.65, 1.96, 2.58, np.inf]
GI_LABELS = ["cold, z < −2.58", "cold, −2.58 to −1.96", "cold, −1.96 to −1.65",
             "not notable, |z| < 1.65", "hot, 1.65 to 1.96",
             "hot, 1.96 to 2.58", "hot, z > 2.58"]

FOOT = ("Source: ISIE procès-verbaux, 9,419 certified stations · boundaries "
        "OCHA/HDX COD-AB (CC BY-IGO) · queen contiguity from shared boundary "
        "vertices")

VERIFY = "data/verification/clusters.jsonl"


def _save(fig, stem, formats=None):
    """save_figure, with `formats=None` meaning "the family default"."""
    return save_figure(fig, stem, formats) if formats else save_figure(fig, stem)


# ---- the analysis --------------------------------------------------------
def analyse(level, layer, pcode_col, csv_path, name_prop, perms=PERMS, q=Q):
    """Everything for one level: weights, Moran, LISA, Gi*, regionalisation."""
    import spatial_stats as st
    import spatial_weights as sw
    from sklearn.cluster import AgglomerativeClustering

    feats = load_layer(layer)
    names = [f["properties"][name_prop] for f in feats]
    adj_all = sw.queen_adjacency(feats)
    raw_degree = sw.degree_summary(adj_all)
    raw_components = [len(c) for c in sw.components(adj_all)]

    rows = {r[pcode_col]: r for r in read(csv_path)}
    keep = [i for i, f in enumerate(feats) if f["properties"][pcode_col] in rows]
    # Subset first, bridge second. The other order drops islands as "stranded".
    adj, pre_isolated = sw.subset(adj_all, keep)
    pre_components = [len(c) for c in sw.components(adj)]
    nm = [names[i] for i in keep]
    xy = sw.centroids_km(
        [float(feats[i]["properties"]["center_lat"]) for i in keep],
        [float(feats[i]["properties"]["center_lon"]) for i in keep])
    bridges = sw.bridge_components(adj, xy, nm)
    assert len(sw.components(adj)) == 1, "bridging left the graph disconnected"
    W = sw.row_standardised(adj)
    n = len(keep)

    codes = [feats[i]["properties"][pcode_col] for i in keep]
    valid = np.array([float(rows[c]["valid"]) for c in codes])
    out = {
        "level": level, "n": n, "n_layer": len(feats),
        "codes": codes, "names": nm, "keep": keep, "feats": feats,
        "rows": rows, "adj": adj, "W": W, "valid": valid,
        "raw_degree": raw_degree, "raw_components": raw_components,
        "pre_components": pre_components,
        "pre_isolated": [nm[i] for i in pre_isolated],
        "bridges": bridges,
        "bridged": sorted({i for b in bridges for i in b[:2]}),
        "degree": sw.degree_summary(adj),
        "perms": perms, "q": q, "cand": {},
    }

    for key, label in CANDIDATES:
        share = np.array([float(rows[c][f"{key}_share_pct"]) for c in codes])
        votes = np.array([float(rows[c][key]) for c in codes])
        z = st.standardise(share)
        g = st.global_moran(z, W, perms=perms, seed=SEED)
        zeb, s2, neg = st.eb_standardise(votes, valid)
        g_eb = st.global_moran(st.standardise(zeb), W, perms=perms, seed=SEED)
        lm = st.local_moran(z, W, adj, perms=perms, seed=SEED, q=q)
        lm_eb = st.local_moran(st.standardise(zeb), W, adj, perms=perms,
                               seed=SEED, q=q)
        go = st.getis_ord(share, adj, perms=perms, seed=SEED, q=q)
        # plain str, not a numpy string array: these become Counter keys and
        # JSON keys, and np.str_ serialises as "np.str_('ns')" in a repr
        quad = [str(st.QUADRANTS[v]) for v in lm["quadrant"]]
        out["cand"][key] = {
            "label": label, "share": share, "moran": g, "moran_eb": g_eb,
            "eb_s2": s2, "eb_negative": neg,
            "lisa": lm, "lisa_eb": lm_eb, "gi": go, "quad": quad,
            "raw_sig": int((lm["p"] <= 0.05).sum()),
            "counts": collections.Counter(quad),
            "eb_reclassified": int((lm["quadrant"] != lm_eb["quadrant"]).sum()),
        }

    # ---- regionalisation
    X = np.column_stack([out["cand"][k]["share"] for k, _ in CANDIDATES])
    # Standardised per candidate so Maghzaoui's 1.55-point spread is not simply
    # outvoted by Saied's 5.78; the three are near-linearly dependent (they sum
    # to ~100), so the effective dimensionality is two, not three.
    Xs = (X - X.mean(0)) / X.std(0)
    A = sparse.csr_matrix(
        ([1] * sum(len(a) for a in adj),
         ([i for i, a in enumerate(adj) for _ in a],
          [j for a in adj for j in sorted(a)])), shape=(n, n))
    gov = np.array([rows[c]["governorate_name"] for c in codes])
    reg = np.array([rows[c]["region_name"] for c in codes])

    def r2(labels):
        tot = ((Xs - Xs.mean(0)) ** 2).sum()
        bet = sum((labels == l).sum() *
                  ((Xs[labels == l].mean(0) - Xs.mean(0)) ** 2).sum()
                  for l in np.unique(labels))
        return float(bet / tot)

    ladder = []
    for k in K_LADDER:
        lab = AgglomerativeClustering(n_clusters=k, linkage="ward",
                                      connectivity=A).fit_predict(Xs)
        ladder.append((k, r2(lab)))
    lab = AgglomerativeClustering(n_clusters=K_REGIONS, linkage="ward",
                                  connectivity=A).fit_predict(Xs)
    # Relabel by mean Saied share, descending, so the cluster index is ordinal
    # and the ramp can carry it -- sklearn's own numbering is arbitrary. Index 0
    # is the *highest* Saied share and takes the palest step, which inverts this
    # repo's usual "darker is more" only because here the high-Saied class is
    # the 65%-of-the-vote background: shading it darkest would bury the four
    # distinctive regions under the homogeneous mass, which is the same mistake
    # the cartograms exist to correct.
    order = sorted(np.unique(lab), key=lambda l: -X[lab == l, 0].mean())
    remap = {old: new for new, old in enumerate(order)}
    lab = np.array([remap[v] for v in lab])
    out["regions"] = {
        "k": K_REGIONS, "labels": lab, "r2": r2(lab), "ladder": ladder,
        "r2_regions": r2(reg), "n_regions": len(set(reg)),
        "r2_gov": r2(gov), "n_gov": len(set(gov)),
        "gov": gov, "X": X,
        "profile": [{
            "cluster": int(l),
            "n": int((lab == l).sum()),
            "vote_pct": float(valid[lab == l].sum() / valid.sum() * 100),
            "saied": float(X[lab == l, 0].mean()),
            "zammel": float(X[lab == l, 1].mean()),
            "maghzaoui": float(X[lab == l, 2].mean()),
            "governorates": sorted(set(gov[lab == l])),
            "example": nm[int(np.flatnonzero(lab == l)[0])],
        } for l in range(K_REGIONS)],
        "single_governorate": int(sum(
            1 for l in range(K_REGIONS) if len(set(gov[lab == l])) == 1)),
    }
    return out



# The whole finding can be a handful of small urban units. At delegation level
# the significant cluster is eight delegations of inner Tunis, which occupy
# about 1% of the page -- the same problem the `zoom/` family exists to solve.
# So each figure carries an inset framed on *its own* significant units rather
# than on a hardcoded Greater Tunis box: Maghzaoui's cluster is in the Kebili
# oases, and a Tunis inset would frame empty desert for him.
# An inset only helps when the cluster is genuinely too small to see. Where it
# already covers a real share of the page, the inset duplicates the main map and
# its locator rectangle covers half the country -- strictly worse. The threshold
# is measured, and the two groups separate by an order of magnitude: the cases
# that need it cover 0.10%, 0.11% and 1.83% of the country's bounding box (Saied
# and Zammel at delegation level, Maghzaoui at imada), the cases that do not
# cover 12.1%, 21.6% and 31.4%. Anything at or under 5% gets an inset.
INSET_MAX_AREA_FRAC = 0.05
INSET_PAD = 0.45          # of the significant units' own extent, per side
INSET_MIN_FRAC = 0.05     # never zoom tighter than this much of the country
INSET_BOX = (0.015, 0.30, 0.315, 0.30)   # axes fraction: x, y, w, h


def _extent_of(paths):
    xs0, ys0, xs1, ys1 = [], [], [], []
    for p in paths:
        if p is None:
            continue
        bb = p.get_extents()
        xs0.append(bb.x0); ys0.append(bb.y0)
        xs1.append(bb.x1); ys1.append(bb.y1)
    if not xs0:
        return None
    return min(xs0), min(ys0), max(xs1), max(ys1)


def _cluster_inset(ax, paths, colour_of, gov_paths, focus, all_extent, label,
                   highlight=()):
    """Inset framed on `focus` (the significant paths).

    Returns the view rectangle so the caller can mark it on the main map, or
    None when there is nothing to magnify or the cluster is already large
    enough to read at national scale.
    """
    ext = _extent_of(focus)
    if ext is None:
        return None
    fx0, fy0, fx1, fy1 = all_extent
    area = ((ext[2] - ext[0]) * (ext[3] - ext[1])
            / ((fx1 - fx0) * (fy1 - fy0)))
    if area > INSET_MAX_AREA_FRAC:
        return None
    x0, y0, x1, y1 = ext
    px, py = (x1 - x0) * INSET_PAD, (y1 - y0) * INSET_PAD
    x0, x1, y0, y1 = x0 - px, x1 + px, y0 - py, y1 + py
    # Floor the zoom: a single significant unit would otherwise fill the inset
    # at a scale where no surrounding context is visible.
    minw, minh = (fx1 - fx0) * INSET_MIN_FRAC, (fy1 - fy0) * INSET_MIN_FRAC
    if x1 - x0 < minw:
        cx = (x0 + x1) / 2; x0, x1 = cx - minw / 2, cx + minw / 2
    if y1 - y0 < minh:
        cy = (y0 + y1) / 2; y0, y1 = cy - minh / 2, cy + minh / 2
    # match the inset's own aspect so circles are not stretched
    w, h = x1 - x0, y1 - y0
    box = list(INSET_BOX)
    want = (box[3] * 9.4) / (box[2] * 7.6)      # figure inches, h/w
    if h / w < want:
        need = w * want; cy = (y0 + y1) / 2
        y0, y1 = cy - need / 2, cy + need / 2
    else:
        need = h / want; cx = (x0 + x1) / 2
        x0, x1 = cx - need / 2, cx + need / 2

    iax = ax.inset_axes(box, transform=ax.transAxes)
    iax.set_aspect("equal")
    iax.set_facecolor(SURFACE)
    # Hiding the axes, not just the ticks: with only set_xticks([]) matplotlib
    # still drew the axis offset text, which showed up as a stray "2".
    iax.set_xticks([]); iax.set_yticks([])
    iax.xaxis.set_visible(False); iax.yaxis.set_visible(False)
    for sp in iax.spines.values():
        sp.set_edgecolor(GOV_LINE); sp.set_linewidth(0.8)
    view = Bbox.from_extents(x0, y0, x1, y1)
    buckets = collections.defaultdict(list)
    for i, p in enumerate(paths):
        # only what the window actually shows, so the inset carries its
        # surroundings rather than all 2,084 units
        if p is not None and p.get_extents().overlaps(view):
            buckets[colour_of(i)].append(p)
    for col, ps in buckets.items():
        iax.add_collection(PathCollection(ps, facecolors=col,
                                          edgecolors="#ffffff", linewidths=0.20,
                                          zorder=2))
    hl = [p for p in highlight if p is not None and p.get_extents().overlaps(view)]
    if hl:
        iax.add_collection(PathCollection(hl, facecolors="none",
                                          edgecolors=HILITE, linewidths=1.0,
                                          zorder=4))
    gp = [g for g in gov_paths if g.get_extents().overlaps(view)]
    if gp:
        iax.add_collection(PathCollection(gp, facecolors="none",
                                          edgecolors=GOV_LINE, linewidths=0.6,
                                          zorder=3))
    iax.set_xlim(x0, x1); iax.set_ylim(y0, y1)
    iax.set_title(label, fontsize=6.8, color=INK_2, loc="left", pad=2.5)
    return (x0, y0, x1, y1)


def _mark_inset(ax, rect):
    """Outline on the national map showing where the inset is looking."""
    if rect is None:
        return
    x0, y0, x1, y1 = rect
    ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, facecolor="none",
                           edgecolor=INK_2, linewidth=0.9, zorder=6))


# ---- figures -------------------------------------------------------------
def _paths(res, tol):
    feats, keep = res["feats"], res["keep"]
    return [feature_path(feats[i]["geometry"], tol) for i in keep]


def _gov_paths(tol):
    return [p for p in (feature_path(f["geometry"], tol * 2)
                        for f in load_layer("tun_admin2.geojson")) if p]


def _moran_line(g):
    p = ("p < %.4g" % g["p_floor"] if g["p_sim"] <= g["p_floor"] + 1e-12
         else "p = %.4g" % g["p_sim"])
    return (f"global Moran's I = {g['I']:+.3f} ({p}, {g['perms']:,} "
            f"permutations, pseudo z = {g['z_sim']:+.1f})")


LISA_ORDER = ["HH", "LL", "HL", "ns"]


def _lisa_colours(res, key, paths):
    """(paths_colors, lh_paths, labels, colours) for one candidate's LISA."""
    c = res["cand"][key]
    quad = c["quad"]
    buckets = {k: [] for k in LISA_ORDER}
    lh = []
    for i, qd in enumerate(quad):
        if paths[i] is None:
            continue
        if qd == "LH":
            lh.append(paths[i])
            buckets["LL"].append(paths[i])     # fill as low, outline as outlier
        else:
            buckets[qd].append(paths[i])
    n = c["counts"]
    labels = [
        f"high in a high neighbourhood — HH ({n['HH']})",
        f"low in a low neighbourhood — LL ({n['LL']})",
        f"high in a low neighbourhood — HL ({n['HL']})",
        f"not significant ({n['ns']})",
    ]
    pc = {LISA_FILL[k]: buckets[k] for k in LISA_ORDER}
    return pc, lh, labels, [LISA_FILL[k] for k in LISA_ORDER]


def lisa_figure(res, key, tol, paths, gov_paths, formats=None):
    c = res["cand"][key]
    pc, lh, labels, colours = _lisa_colours(res, key, paths)
    fig, ax = plt.subplots(figsize=(7.6, 9.4))
    sub = (f"local Moran's I, {res['level']} level · "
           f"Benjamini-Hochberg q = {res['q']}")
    draw(ax, pc, gov_paths, f"{c['label']} — spatial clusters",
         sub, list(range(len(labels) + 1)), "LISA class", res["n"], 0,
         highlight=lh or None,
         hi_label=f"low in a high neighbourhood — LH ({c['counts']['LH']})",
         labels=labels, colours=colours)
    sig_idx = np.flatnonzero(c["lisa"]["sig"])
    rect = _cluster_inset(
        ax, paths, lambda i: LISA_FILL.get(c["quad"][i], NO_DATA), gov_paths,
        [paths[i] for i in sig_idx], _extent_of(paths),
        f"the significant units, magnified ({len(sig_idx)})", highlight=lh)
    _mark_inset(ax, rect)
    note = (
        f"{_moran_line(c['moran'])}. The map localises that: a class is assigned "
        f"only where the unit's own neighbourhood is more extreme than "
        f"{res['perms']:,} random neighbourhoods drawn from the same values, "
        f"after Benjamini-Hochberg correction across all {res['n']:,} units "
        f"(threshold actually applied: p ≤ {c['lisa']['cut']:.2g}).\n"
        f"Uncorrected, {c['raw_sig']} units reach p ≤ 0.05 — which is what an "
        f"uncorrected LISA map would shade, and at {res['n']:,} tests about "
        f"{0.05 * res['n']:.0f} of those are expected by chance alone. "
        f"Empirical-Bayes standardising the rate, so a small unit's noisy share "
        f"is not read as geography, reclassifies "
        f"{c['eb_reclassified']} unit(s).\n" + FOOT)
    fig.text(0.012, 0.012, _wrap(note, 118), fontsize=6.8, color=INK_2,
             va="bottom")
    fig.tight_layout(rect=(0, 0.075, 1, 1))
    made = _save(fig, f"{figure_dir(FAMILY)}/lisa_{key}_{res['level']}", formats)
    plt.close(fig)
    return made


def _nesting_note(res):
    """Whether Saied's low cluster and Zammel's high cluster are the same units.

    Computed rather than asserted: at delegation level Saied's eight are a
    strict subset of Zammel's nine, not an equal set, and an earlier draft of
    this caption claimed equality because the two counts happened to match at a
    lower permutation budget.
    """
    low = {i for i, q in enumerate(res["cand"]["saied"]["quad"]) if q == "LL"}
    high = {i for i, q in enumerate(res["cand"]["zammel"]["quad"]) if q == "HH"}
    if not low or not high:
        return ""
    if low == high:
        rel = f"are the same {len(low)} units"
    elif low < high:
        rel = (f"nest: Saied's {len(low)} are a strict subset of Zammel's "
               f"{len(high)}, which adds "
               + ", ".join(sorted(res["names"][i] for i in high - low)))
    elif high < low:
        rel = (f"nest: Zammel's {len(high)} are a strict subset of Saied's "
               f"{len(low)}")
    else:
        rel = (f"overlap in {len(low & high)} units of {len(low)} and "
               f"{len(high)}")
    return (f"Saied's low-among-low cluster and Zammel's high-among-high "
            f"cluster {rel} — the arithmetic of a 91% result, where Saied's "
            f"weakness is mechanically his rival's strength.\n")


def lisa_composite(res, tol, paths, gov_paths, formats=None):
    """Three panels: the point is that the candidates cluster in different places.

    Sized from the country's own aspect rather than a guessed figsize. Tunisia
    projects to height/width 2.14, so three panels side by side want a canvas
    of aspect 2.14/3 plus room for the chrome; a shorter one letterboxes each
    panel and spends most of the page on margin, which is what the first render
    did. Panel titles go above the axes, not inside them: with no legend there
    is no gutter to hold them and they printed across the map.
    """
    panel_aspect = 2.14
    w = 12.0
    map_h = w * panel_aspect / 3.0
    fig, axes = plt.subplots(1, 3, figsize=(w, map_h + 1.85))
    for ax, (key, _) in zip(axes, CANDIDATES):
        c = res["cand"][key]
        pc, lh, labels, colours = _lisa_colours(res, key, paths)
        draw(ax, pc, gov_paths, "", "", list(range(len(labels) + 1)), "",
             res["n"], 0, highlight=lh or None, compact=True, legend=False,
             units_note=False)
        ax.set_title(
            f"{c['label']}\nI = {c['moran']['I']:+.3f} · "
            f"{int(c['lisa']['sig'].sum())} of {res['n']:,} significant",
            fontsize=9.5, color=INK, pad=6, linespacing=1.5)
    handles = [Patch(facecolor=LISA_FILL[k], edgecolor="#ffffff", linewidth=0.4,
                     label=lab) for k, lab in zip(
                         LISA_ORDER,
                         ["high in a high neighbourhood (HH)",
                          "low in a low neighbourhood (LL)",
                          "high in a low neighbourhood (HL)",
                          "not significant"])]
    handles.append(Patch(facecolor="none", edgecolor=HILITE, linewidth=1.4,
                         label="low in a high neighbourhood (LH)"))
    fig.legend(handles=handles, loc="upper center", ncol=5, frameon=False,
               fontsize=8, bbox_to_anchor=(0.5, 0.925))
    fig.suptitle(f"Spatial clusters of each candidate's share — "
                 f"{res['level']} level", y=0.955, fontsize=13,
                 fontweight="bold", color=INK)
    note = (
        f"Local Moran's I against {res['perms']:,} conditional permutations, "
        f"Benjamini-Hochberg q = {res['q']} across all {res['n']:,} units. "
        f"Classes are per candidate, so the same shade in two panels means the "
        f"same relationship to that candidate's own mean, not the same share. "
        f"Clusters this small are specks at national scale by their nature — "
        f"the per-candidate figures magnify each of them.\n"
        + _nesting_note(res) + FOOT)
    fig.text(0.008, 0.012, _wrap(note, 168), fontsize=7.2, color=INK_2,
             va="bottom")
    fig.tight_layout(rect=(0, 0.075, 1, 0.885))
    made = _save(fig,
                       f"{figure_dir(FAMILY)}/lisa_composite_{res['level']}", formats)
    plt.close(fig)
    return made


def hotspot_figure(res, key, tol, paths, gov_paths, formats=None):
    """Gi* z on the sequential ramp; FDR significance as a HILITE outline.

    Fill and inference are deliberately separated. The z-score is continuous and
    every unit has one, so it belongs on a ramp; significance is a yes/no about
    2,000 simultaneous tests, so it belongs on an outline. Shading only the
    significant units would throw away the surface, and shading all of them
    without marking significance would overclaim.

    The outline is the same set of units the LISA figure classifies, for the
    reason in the module docstring -- the two statistics share a null. That is
    asserted in `tools/audit_clusters.py` rather than left as a coincidence.
    """
    c = res["cand"][key]
    z = c["gi"]["z"]
    edges = GI_EDGES
    counts = [0] * len(GI_LABELS)
    buckets = collections.defaultdict(list)
    for i, p in enumerate(paths):
        k = class_of(z[i], edges)
        counts[k] += 1
        if p is not None:
            buckets[RAMP[k]].append(p)
    sig = [paths[i] for i in np.flatnonzero(c["gi"]["sig"]) if paths[i] is not None]
    fig, ax = plt.subplots(figsize=(7.6, 9.4))
    draw(ax, dict(buckets), gov_paths, f"{c['label']} — hot and cold spots",
         f"Getis-Ord Gi* z-score, {res['level']} level", edges,
         "Gi* z-score", res["n"], 0,
         labels=[f"{lab} ({n})" for lab, n in zip(GI_LABELS, counts)],
         highlight=sig or None,
         hi_label=f"significant after FDR ({int(c['gi']['sig'].sum())})")
    sig_idx = np.flatnonzero(c["gi"]["sig"])
    rect = _cluster_inset(
        ax, paths, lambda i: RAMP[class_of(z[i], edges)], gov_paths,
        [paths[i] for i in sig_idx], _extent_of(paths),
        f"the significant units, magnified ({len(sig_idx)})")
    _mark_inset(ax, rect)
    hot, cold = int(c["gi"]["hot"].sum()), int(c["gi"]["cold"].sum())
    note = (
        f"Gi* includes the unit itself, so it measures whether the local total "
        f"is unusual rather than how the unit relates to its neighbours: it has "
        f"no outlier classes and is the more legible of the two cluster "
        f"statistics — but not a second one: under conditional permutation it "
        f"selects the same units as the LISA map beside it, because both hold "
        f"the unit's own value fixed and so test the same neighbourhood. What "
        f"it adds is the continuous surface the quadrant map discards. "
        f"Positive is a hot spot, negative a cold spot; the ramp "
        f"carries the z-score in fixed bands rather than quantiles, so a shade "
        f"means the same thing on every one of these maps; the observed range "
        f"here is {z.min():+.1f} to {z.max():+.1f}. The outline marks the "
        f"{int(c['gi']['sig'].sum())} units that survive Benjamini-Hochberg at "
        f"q = {res['q']} — {hot} hot, {cold} cold.\n"
        f"{_moran_line(c['moran'])}.\n" + FOOT)
    fig.text(0.012, 0.012, _wrap(note, 118), fontsize=6.8, color=INK_2,
             va="bottom")
    fig.tight_layout(rect=(0, 0.068, 1, 1))
    made = _save(fig, f"{figure_dir(FAMILY)}/hotspot_{key}_{res['level']}", formats)
    plt.close(fig)
    return made


def regions_figure(res, tol, paths, gov_paths, formats=None):
    import make_levels
    r = res["regions"]
    lab = r["labels"]
    colours = make_levels.ramp_of(r["k"])
    buckets = collections.defaultdict(list)
    for i, p in enumerate(paths):
        if p is not None:
            buckets[colours[lab[i]]].append(p)
    labels = [f"{p['saied']:.1f} / {p['zammel']:.1f} / {p['maghzaoui']:.1f}"
              f"  · {p['n']} unit{'' if p['n'] == 1 else 's'}, "
              f"{p['vote_pct']:.1f}% of votes"
              for p in r["profile"]]
    fig, ax = plt.subplots(figsize=(7.9, 9.4))
    draw(ax, dict(buckets), gov_paths,
         f"Electoral regions — {r['k']} contiguous clusters",
         f"Ward clustering on the three shares, {res['level']} level",
         list(range(r["k"] + 1)),
         "mean Saied / Zammel / Maghzaoui share (%)", res["n"], 0,
         labels=labels, colours=colours)
    singles = [p for p in r["profile"] if p["n"] == 1]
    note = (
        f"Each region is contiguous by construction — Ward agglomeration under "
        f"the same queen-contiguity constraint used for the statistics above — "
        f"and is built only from how the three candidates polled, with no "
        f"reference to any administrative boundary. Shaded by mean Saied share, "
        f"palest at the top: the 94%-Saied mass that covers two thirds of the "
        f"vote is deliberately the background, so the distinctive regions carry "
        f"the ink rather than the homogeneous majority. Every legend row prints "
        f"its own three means, so no shade has to be guessed at.\n"
        f"These {r['k']} regions explain R² = {r['r2']:.3f} of the variance in "
        f"the three-share vector, against {r['r2_regions']:.3f} for the "
        f"{r['n_regions']} official regions and {r['r2_gov']:.3f} for all "
        f"{r['n_gov']} governorates. Six electoral regions therefore beat "
        f"twenty-four administrative ones, which is the finding: this vote does "
        f"not respect the state's geography. Only "
        f"{r['single_governorate']} of the {r['k']} "
        f"{'stays' if r['single_governorate'] == 1 else 'stay'} inside one "
        f"governorate; the rest cut across the administrative grid.\n")
    if singles:
        note += (
            "Ward isolates genuine extremes rather than splitting the country "
            "evenly, so a one-unit region is a real outlier and not a failure: "
            + ", ".join(f"{p['example']} at "
                        f"{p['saied']:.0f}/{p['zammel']:.0f}/{p['maghzaoui']:.0f}"
                        for p in singles) + ".\n")
    note += FOOT
    fig.text(0.012, 0.012, _wrap(note, 118), fontsize=6.8, color=INK_2,
             va="bottom")
    fig.tight_layout(rect=(0, 0.085, 1, 1))
    made = _save(fig, f"{figure_dir(FAMILY)}/regions_{res['level']}", formats)
    plt.close(fig)
    return made


def ladder_figure(res, formats=None):
    """R^2 against k, with the administrative partitions as reference lines.

    Not a map, because the finding is not spatial: it is that the official
    geography sits far below what a contiguity-constrained clustering of the
    same units achieves at the same k, and that the gap is wide enough that six
    electoral regions overtake twenty-four governorates.
    """
    r = res["regions"]
    ks = [k for k, _ in r["ladder"]]
    r2 = [v for _, v in r["ladder"]]
    fig, ax = plt.subplots(figsize=(7.4, 4.9))
    ax.set_facecolor(SURFACE)
    ax.plot(ks, r2, "-o", color=RAMP[5], markersize=4.5, linewidth=1.6,
            label="electoral regions (Ward, contiguity-constrained)")
    ax.axhline(r["r2_regions"], color=HILITE, linewidth=1.3, linestyle="--")
    ax.axhline(r["r2_gov"], color=INK_2, linewidth=1.3, linestyle=":")
    ax.annotate(f"the {r['n_regions']} official regions: R² = {r['r2_regions']:.3f}",
                (ks[-1], r["r2_regions"]), textcoords="offset points",
                xytext=(-4, 6), ha="right", fontsize=8, color=HILITE)
    ax.annotate(f"all {r['n_gov']} governorates: R² = {r['r2_gov']:.3f}",
                (ks[-1], r["r2_gov"]), textcoords="offset points",
                xytext=(-4, 6), ha="right", fontsize=8, color=INK_2)
    kk = r["k"]
    ax.plot([kk], [r["r2"]], "o", markersize=10, markerfacecolor="none",
            markeredgecolor=HILITE, markeredgewidth=1.6)
    ax.annotate(f"k = {kk}: R² = {r['r2']:.3f}", (kk, r["r2"]),
                textcoords="offset points", xytext=(8, -10), fontsize=8.5,
                color=INK)
    ax.set_xlabel("number of regions (k)", fontsize=9, color=INK_2)
    ax.set_ylabel("share of variance in the three shares explained (R²)",
                  fontsize=9, color=INK_2)
    ax.set_title(f"Electoral regions against administrative ones — "
                 f"{res['level']} level", fontsize=12, fontweight="bold",
                 color=INK, loc="left")
    ax.set_ylim(0, 1)
    ax.grid(alpha=0.25, linewidth=0.5)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.tick_params(labelsize=8, colors=INK_2)
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    note = (
        f"Ward agglomeration on the three standardised shares of {res['n']:,} "
        f"{res['level']}s, constrained so every region is contiguous. The "
        f"administrative lines are the same statistic computed on the official "
        f"partitions of the same units, so the comparison is like for like: at "
        f"k = {r['n_regions']} the clustering explains "
        f"{r['r2'] / r['r2_regions']:.1f}× what the official regions do, and it "
        f"passes all {r['n_gov']} governorates at "
        f"k = {next(k for k, v in r['ladder'] if v > r['r2_gov'])}.\n"
        f"Ward maximises this criterion by construction, so the clustering is "
        f"expected to win; the size of the gap is the informative part, not its "
        f"sign.\n" + FOOT)
    fig.text(0.012, 0.012, _wrap(note, 118), fontsize=6.8, color=INK_2,
             va="bottom")
    fig.tight_layout(rect=(0, 0.20, 1, 1))
    made = _save(fig,
                       f"{figure_dir(FAMILY)}/region_ladder_{res['level']}", formats)
    plt.close(fig)
    return made


def _wrap(text, cols):
    """Wrap each line to `cols`, before the figure is sized.

    `bbox_inches="tight"` expands the canvas around any text that overflows it,
    so an unwrapped footnote sizes every figure to its own longest line and the
    family stops being comparable. That has bitten twice in this repo.
    """
    import textwrap
    return "\n".join(textwrap.fill(line, cols) if line else ""
                     for line in text.split("\n"))


# ---- outputs -------------------------------------------------------------
CSV_COLUMNS = ["pcode", "name", "governorate_name", "region_name", "n_neighbours",
               "island_bridged", "region_cluster", "region_saied_mean",
               "region_zammel_mean", "region_maghzaoui_mean"]


def write_csv(res, pcode_col):
    rows, r = res["rows"], res["regions"]
    prof = {p["cluster"]: p for p in r["profile"]}
    path = f"data/{res['level']}_clusters.csv"
    cols = list(CSV_COLUMNS)
    for key, _ in CANDIDATES:
        cols += [f"{key}_lisa_class", f"{key}_lisa_i", f"{key}_lisa_p",
                 f"{key}_lisa_sig", f"{key}_gi_z", f"{key}_gi_p",
                 f"{key}_gi_sig"]
    bridged = set(res["bridged"])
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        for i, code in enumerate(res["codes"]):
            src = rows[code]
            rec = {
                "pcode": code, "name": res["names"][i],
                "governorate_name": src["governorate_name"],
                "region_name": src["region_name"],
                "n_neighbours": len(res["adj"][i]),
                "island_bridged": int(i in bridged),
                "region_cluster": int(r["labels"][i]),
                "region_saied_mean": f"{prof[int(r['labels'][i])]['saied']:.4f}",
                "region_zammel_mean": f"{prof[int(r['labels'][i])]['zammel']:.4f}",
                "region_maghzaoui_mean":
                    f"{prof[int(r['labels'][i])]['maghzaoui']:.4f}",
            }
            for key, _ in CANDIDATES:
                c = res["cand"][key]
                rec[f"{key}_lisa_class"] = c["quad"][i]
                rec[f"{key}_lisa_i"] = f"{c['lisa']['I'][i]:.6f}"
                rec[f"{key}_lisa_p"] = f"{c['lisa']['p'][i]:.6f}"
                rec[f"{key}_lisa_sig"] = int(c["lisa"]["sig"][i])
                rec[f"{key}_gi_z"] = f"{c['gi']['z'][i]:.6f}"
                rec[f"{key}_gi_p"] = f"{c['gi']['p'][i]:.6f}"
                rec[f"{key}_gi_sig"] = int(c["gi"]["sig"][i])
            w.writerow(rec)
    return path


def verification_records(res):
    recs = [{
        "level": res["level"], "kind": "weights",
        "units_in_layer": res["n_layer"], "units_analysed": res["n"],
        "queen_degree_min_median_mean_max_isolated": list(res["raw_degree"]),
        "components_before_subset": res["raw_components"],
        "components_after_subset": res["pre_components"],
        "isolated_after_subset": res["pre_isolated"],
        "bridges": [{"from": a, "to": b, "km": km} for _, _, a, b, km in res["bridges"]],
        "degree_final": list(res["degree"]),
    }]
    for key, _ in CANDIDATES:
        c = res["cand"][key]
        recs.append({
            "level": res["level"], "kind": "autocorrelation", "candidate": key,
            "morans_i": round(c["moran"]["I"], 6),
            "morans_p": c["moran"]["p_sim"],
            "morans_z_sim": round(c["moran"]["z_sim"], 4),
            "morans_i_eb": round(c["moran_eb"]["I"], 6),
            "eb_between_variance": c["eb_s2"],
            "eb_variance_clamped": c["eb_negative"],
            "permutations": c["moran"]["perms"],
            "lisa_raw_p05": c["raw_sig"],
            "lisa_fdr_significant": int(c["lisa"]["sig"].sum()),
            "lisa_fdr_cutoff": c["lisa"]["cut"],
            "lisa_classes": dict(c["counts"]),
            "lisa_eb_reclassified": c["eb_reclassified"],
            "gi_significant": int(c["gi"]["sig"].sum()),
            "gi_hot": int(c["gi"]["hot"].sum()),
            "gi_cold": int(c["gi"]["cold"].sum()),
            "gi_z_min": round(float(c["gi"]["z"].min()), 4),
            "gi_z_max": round(float(c["gi"]["z"].max()), 4),
        })
    r = res["regions"]
    recs.append({
        "level": res["level"], "kind": "regionalisation", "k": r["k"],
        "r2": round(r["r2"], 6),
        "r2_official_regions": round(r["r2_regions"], 6),
        "n_official_regions": r["n_regions"],
        "r2_governorates": round(r["r2_gov"], 6),
        "n_governorates": r["n_gov"],
        "ladder": [{"k": k, "r2": round(v, 6)} for k, v in r["ladder"]],
        "single_governorate_regions": r["single_governorate"],
        "profile": r["profile"],
    })
    return recs


def report(res):
    print(f"\n=== {res['level']}: {res['n']:,} of {res['n_layer']:,} units")
    print(f"    queen degree (min/median/mean/max/isolated): {res['raw_degree']}")
    print(f"    components before subset {res['raw_components']}, "
          f"after subset {res['pre_components']}, after bridging 1")
    for _, _, a, b, km in res["bridges"]:
        print(f"      bridged {a} -> {b} ({km} km)")
    for key, label in CANDIDATES:
        c = res["cand"][key]
        print(f"    {label:18s} I={c['moran']['I']:+.4f} "
              f"(p={c['moran']['p_sim']:.5f}, z={c['moran']['z_sim']:+.1f})  "
              f"EB I={c['moran_eb']['I']:+.4f}")
        print(f"      LISA raw p≤.05 {c['raw_sig']:5d} -> FDR "
              f"{int(c['lisa']['sig'].sum()):5d} (cut {c['lisa']['cut']:.2e})  "
              f"{dict(c['counts'])}  EB reclassified {c['eb_reclassified']}")
        print(f"      Gi*  significant {int(c['gi']['sig'].sum()):5d} "
              f"(hot {int(c['gi']['hot'].sum())}, cold {int(c['gi']['cold'].sum())})"
              f"  z {c['gi']['z'].min():+.2f}..{c['gi']['z'].max():+.2f}")
    r = res["regions"]
    print(f"    regionalisation k={r['k']}: R²={r['r2']:.4f}  vs "
          f"{r['n_regions']} official regions {r['r2_regions']:.4f}  vs "
          f"{r['n_gov']} governorates {r['r2_gov']:.4f}")
    print("      ladder: " + "  ".join(f"k{k}={v:.3f}" for k, v in r["ladder"]))
    for p in r["profile"]:
        print(f"      c{p['cluster']}: n={p['n']:5d} votes={p['vote_pct']:5.1f}%  "
              f"S/Z/M={p['saied']:5.1f}/{p['zammel']:4.1f}/{p['maghzaoui']:4.1f}  "
              f"{len(p['governorates'])} governorate(s), e.g. {p['example']}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--level", choices=[l[0] for l in LEVELS],
                    help="only this level")
    ap.add_argument("--basis", choices=["lisa", "hotspot", "regions"],
                    help="only this basis")
    ap.add_argument("--perms", type=int, default=PERMS,
                    help=f"permutations per test (default {PERMS})")
    ap.add_argument("--report", action="store_true",
                    help="print the statistics and write no figures")
    ap.add_argument("--formats", help="comma-separated, e.g. pdf,png")
    args = ap.parse_args()
    if not os.path.exists(ARCHIVE):
        sys.exit(f"missing {ARCHIVE}; run tools/fetch_boundaries.py")
    warnings.filterwarnings("ignore", category=UserWarning)
    formats = tuple(args.formats.split(",")) if args.formats else None

    made, records = [], []
    for level, layer, pcode, csv_path, name_prop, tol in LEVELS:
        if args.level and level != args.level:
            continue
        res = analyse(level, layer, pcode, csv_path, name_prop, perms=args.perms)
        report(res)
        records += verification_records(res)
        if args.report:
            continue
        out = write_csv(res, pcode)
        print(f"    wrote {out}")
        paths = _paths(res, tol)
        gov_paths = _gov_paths(tol)
        if args.basis in (None, "lisa"):
            for key, _ in CANDIDATES:
                made += lisa_figure(res, key, tol, paths, gov_paths, formats)
            made += lisa_composite(res, tol, paths, gov_paths, formats)
        if args.basis in (None, "hotspot"):
            for key, _ in CANDIDATES:
                made += hotspot_figure(res, key, tol, paths, gov_paths, formats)
        if args.basis in (None, "regions"):
            made += regions_figure(res, tol, paths, gov_paths, formats)
            made += ladder_figure(res, formats)

    if not args.report:
        os.makedirs(os.path.dirname(VERIFY), exist_ok=True)
        with open(VERIFY, "w", encoding="utf-8") as fh:
            for rec in records:
                fh.write(json.dumps(rec, ensure_ascii=False, sort_keys=True,
                                    default=float) + "\n")
        print(f"\nwrote {VERIFY} ({len(records)} records)")
        for f in made:
            print(f"    {os.path.getsize(f):>9,}  {f}")
        print(f"{len(made)} files")


if __name__ == "__main__":
    main()
