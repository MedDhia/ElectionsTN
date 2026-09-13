"""Three diagnostic panels for the 2019 Saied model, in `maps/y2019`.

    model_saied_fit.{pdf,png,svg}

**Left: what the model predicted against what happened**, one point per
constituency. The 27 domestic points are leave-one-out predictions, so each was
made by a model refitted without that constituency, its variable selection
included. The six out-of-country points are colder still: predicted by a model
trained on the domestic 27 and stripped of every column those units lack --
geography, because they have no polygon, and the census, because it counts
residents of Tunisia.

**Middle: which block of predictors is doing the work.** The same
cross-validated error, refitted on one block at a time. A block that matters
moves its bar left of the mean-baseline rule. This is the panel carrying the
finding: the 2014 election results barely help, and the 2014 census does.

**Right: how stable the selection is.** Forward selection over 171 columns on 27
rows is the obvious thing to distrust, so the panel counts how many of the 27
folds chose each variable. A variable picked in nearly every fold is a finding;
one picked in six is the sample talking.

Arabic stays off the canvas -- matplotlib does no bidirectional reordering or
glyph shaping, so it would come out as reversed isolated letters -- which is why
unit names are romanised from the boundary layer's own Latin field.

Usage: python3 tools/make_model_figure.py
"""
import os, sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_maps import INK, INK_2, NO_DATA, RAMP, SURFACE, load_layer, save_figure
from make_2019_maps import fold
from model_saied_2019 import (BLOCKS, damerau, design, gov_of, loo, scores,
                              zoo)

OUT = "maps/y2019/model_saied_fit"
WINNER = "ols_forward3"

# The six out-of-country constituencies, romanised. Named rather than coded
# because each is a different kind of place and the left panel needs to say
# which is which.
ABROAD_LABEL = {
    "فرنسا 1": "France 1",
    "فرنسا 2": "France 2",
    "المانيا": "Germany",
    "ايطاليا": "Italy",
    "الدول العربيه وباقي دول العالم": "Arab states, rest of world",
    "القاره الامريكيه وبقيه الدول الاوروبيه": "Americas, rest of Europe",
}

# Census variable names are French field codes. Spelled out, they are the
# finding, so they are spelled out.
PRETTY = {
    "census_pct_occ_primaire": "employed with primary schooling only",
    "census_taux_chomage_diplomes_sup": "graduate unemployment rate",
    "census_pct_chom_neant": "unemployed with no schooling",
    "census_pct_mig_famille": "out-migrants leaving for family reasons",
    "census_pct_chom_primaire": "unemployed with primary schooling",
    "census_pct_marie": "married share of adults",
    "census_pct_celibataire": "never-married share of adults",
    "census_pct_taux_chomage": "unemployment rate",
    "census_pct_divorce": "divorced share of adults",
    "census_pct_primaire_educ": "primary schooling only, all ages",
    "census_pct_20_29": "aged 20 to 29",
    "census_pct_tv": "households with a television",
    "census_log_population": "log population",
}


def pretty(col):
    if col in PRETTY:
        return PRETTY[col]
    return col.replace("census_", "").replace("_", " ")


def latin_names():
    """{folded Arabic governorate: Latin name} from the boundary layer itself."""
    return {fold(f["properties"]["adm2_name1"]): f["properties"]["adm2_name"]
            for f in load_layer("tun_admin2.geojson")}


def romanise(unit, latin):
    if unit in ABROAD_LABEL:
        return ABROAD_LABEL[unit]
    gov = gov_of(unit)
    best = min((damerau(gov, k), k) for k in latin)[1]
    suffix = unit.strip()[-1]
    return f"{latin[best]} {suffix}" if suffix.isdigit() else latin[best]


def main():
    names, X, y, cols, w, dom, _ = design("forecast", "constituency")
    keep = ~np.isnan(X[dom]).any(axis=0)
    Xd, yd, wd = X[dom][:, keep], y[dom], w[dom]
    kept = [c for c, k in zip(cols, keep) if k]
    link = (lambda v: v, lambda v: v)

    win = dict(zoo(Xd.shape[1]))[WINNER]
    pred = loo(win, Xd, yd, link)
    s = scores(yd, pred, wd)
    base = scores(yd, loo(dict(zoo(1))["mean"], Xd, yd, link), wd)

    finite = ~np.isnan(X[~dom][:, keep]).any(axis=0)
    elec = [i for i, c in enumerate(kept) if finite[i]
            and not c.startswith(("lat", "lon", "log_area", "region_"))]
    Xe = X[:, keep][:, elec]
    ab = dict(zoo(len(elec)))[WINNER]().fit(Xe[dom], y[dom]).predict(Xe[~dom])
    s_ab = scores(y[~dom], ab, w[~dom])

    present = {b: [i for i, c in enumerate(kept) if f(c)]
               for b, f in BLOCKS.items()}
    present = {b: idx for b, idx in present.items() if idx}
    bars = [("everything", len(kept), s["rmse_pp"])]
    for b, idx in present.items():
        bars.append((b.replace("_", " "), len(idx),
                     scores(yd, loo(dict(zoo(len(idx)))[WINNER], Xd[:, idx],
                                    yd, link), wd)["rmse_pp"]))
    bars.sort(key=lambda t: t[2])

    # selection stability: what each of the 27 refits actually chose
    counts = {}
    for i in range(len(yd)):
        m = np.arange(len(yd)) != i
        for j in win().fit(Xd[m], yd[m]).cols:
            counts[kept[j]] = counts.get(kept[j], 0) + 1
    picked = sorted(counts.items(), key=lambda t: t[1])[-9:]
    chosen = [kept[j] for j in win().fit(Xd, yd).cols]

    latin = latin_names()
    fig, (axl, axm, axr) = plt.subplots(
        1, 3, figsize=(18.2, 6.4), facecolor=SURFACE,
        gridspec_kw={"width_ratios": [1.22, 1.0, 1.06], "wspace": 0.52})

    # ---- left: predicted against actual
    axl.set_facecolor(SURFACE)
    lo, hi = 2.0, 32.5
    axl.plot([lo, hi], [lo, hi], color=INK_2, lw=0.9, ls=(0, (4, 3)), zorder=1)
    axl.axhline(100 * yd.mean(), color=NO_DATA, lw=8, zorder=0)
    axl.scatter(100 * yd, 100 * pred, s=42, facecolor=RAMP[4],
                edgecolor="#ffffff", linewidth=0.7, zorder=3,
                label=f"27 domestic, leave-one-out (RMSE {s['rmse_pp']:.2f}p)")
    axl.scatter(100 * y[~dom], 100 * ab, s=52, facecolor="none",
                edgecolor=RAMP[6], linewidth=1.3, zorder=3,
                label=f"6 abroad, cold transfer (RMSE {s_ab['rmse_pp']:.2f}p)")
    # Labels alternate above and below: 33 names in a cloud this tight collide
    # however they are placed, and alternating keeps a pair legible.
    for k, (t, p, n) in enumerate(zip(yd, pred, np.array(names)[dom])):
        axl.annotate(romanise(n, latin), (100 * t, 100 * p),
                     textcoords="offset points",
                     xytext=(5.0, 2.6 if k % 2 == 0 else -7.4),
                     fontsize=6.0, color=INK_2, zorder=4)
    for t, p, n in zip(y[~dom], ab, np.array(names)[~dom]):
        axl.annotate(romanise(n, latin), (100 * t, 100 * p),
                     textcoords="offset points", xytext=(5.0, 2.6),
                     fontsize=6.0, color=RAMP[6], zorder=4)
    axl.set_xlim(lo, hi)
    axl.set_ylim(lo, hi)
    axl.set_xlabel("Saied's actual share of valid votes, %", fontsize=8.5)
    axl.set_ylabel("predicted share, %", fontsize=8.5)
    axl.set_title("Predicted against actual", fontsize=10.5, loc="left",
                  color=INK)
    axl.tick_params(labelsize=7.5, colors=INK_2)
    axl.legend(loc="upper left", fontsize=7.2, frameon=False)
    axl.annotate("the grey band is the national mean: a model with nothing to "
                 "say sits on it, not on the diagonal",
                 (0.5, -0.115), xycoords="axes fraction", ha="center",
                 fontsize=7.0, color=INK_2)
    for sp in axl.spines.values():
        sp.set_color(NO_DATA)

    # ---- middle: error by block of predictors
    axm.set_facecolor(SURFACE)
    ypos = np.arange(len(bars))[::-1]
    axm.barh(ypos, [b[2] for b in bars], height=0.62, color=RAMP[2],
             edgecolor="#ffffff", linewidth=0.6, zorder=2)
    axm.axvline(base["rmse_pp"], color="#e34948", lw=1.4, zorder=3)
    axm.annotate(f"predicting the mean, {base['rmse_pp']:.2f} points",
                 (base["rmse_pp"], len(bars) - 0.42),
                 textcoords="offset points", xytext=(-6, 0), fontsize=7.4,
                 color="#e34948", ha="right", va="center")
    for yy, (tag, ncol, v) in zip(ypos, bars):
        axm.annotate(f"{v:.2f}p", (v, yy), textcoords="offset points",
                     xytext=(4, 0), va="center", fontsize=7.2, color=INK_2)
    axm.set_yticks(ypos)
    axm.set_yticklabels([f"{t}  ({n})" for t, n, _ in bars], fontsize=8)
    axm.set_xlim(0, max(base["rmse_pp"], max(b[2] for b in bars)) * 1.16)
    axm.set_ylim(-0.7, len(bars) - 0.02)
    axm.set_xlabel("leave-one-out RMSE, percentage points  (lower is better)",
                   fontsize=8.5)
    axm.set_title("Which predictors do the work", fontsize=10.5, loc="left",
                  color=INK)
    axm.tick_params(labelsize=7.5, colors=INK_2)
    for sp in axm.spines.values():
        sp.set_color(NO_DATA)

    # ---- right: how often each variable survives a refit
    axr.set_facecolor(SURFACE)
    ypos = np.arange(len(picked))
    axr.barh(ypos, [c for _, c in picked], height=0.62,
             color=[RAMP[4] if v in chosen else RAMP[1] for v, _ in picked],
             edgecolor="#ffffff", linewidth=0.6, zorder=2)
    for yy, (v, c) in zip(ypos, picked):
        axr.annotate(f"{c}/{len(yd)}", (c, yy), textcoords="offset points",
                     xytext=(4, 0), va="center", fontsize=7.2, color=INK_2)
    axr.set_yticks(ypos)
    axr.set_yticklabels([pretty(v) for v, _ in picked], fontsize=8)
    axr.set_xlim(0, len(yd) * 1.16)
    axr.set_xlabel("folds out of 27 that chose this variable", fontsize=8.5)
    axr.set_title("How stable the selection is", fontsize=10.5, loc="left",
                  color=INK)
    axr.tick_params(labelsize=7.5, colors=INK_2)
    axr.annotate("dark bars are the three the full-sample fit keeps",
                 (0.5, -0.115), xycoords="axes fraction", ha="center",
                 fontsize=7.0, color=INK_2)
    for sp in axr.spines.values():
        sp.set_color(NO_DATA)

    fig.suptitle("Kais Saied's first-round share, 15 September 2019: "
                 "what a model can and cannot recover",
                 fontsize=12.5, x=0.045, ha="left", color=INK, y=1.005)
    fig.text(0.045, -0.045,
             "Forward-selected OLS, three variables, the selection redone "
             "inside every fold. Candidate predictors: the 2014 presidential "
             "and legislative results by constituency, 2014 participation, "
             "geography,\nand the 2014 census aggregated from delegation to "
             "governorate. Every number is out of sample. Sources: ISIE 2019 "
             "retrospective report annex 7, JORT 2014, INS RGPH 2014 via "
             "MedDhia/rgph2014tn, OCHA/HDX COD-AB boundaries.\n"
             "Built by tools/make_model_figure.py; the evaluation, including "
             "the permutation test behind these numbers, is "
             "tools/model_saied_2019.py.",
             fontsize=6.6, color=INK_2, ha="left", va="top")

    made = save_figure(fig, OUT)
    plt.close(fig)
    print(f"domestic LOO RMSE {s['rmse_pp']:.2f}p (baseline "
          f"{base['rmse_pp']:.2f}p), abroad {s_ab['rmse_pp']:.2f}p")
    print("full-sample selection: " + ", ".join(pretty(c) for c in chosen))
    for p in made:
        print("  wrote", p)


if __name__ == "__main__":
    main()
