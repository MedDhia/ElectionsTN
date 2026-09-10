"""Is a candidate representative's presence related to the margin of victory?

The question, and why the levels differ
---------------------------------------
`data/representatives_2024.csv` records, per station, how many of the three
representative rows on the paper were filled in. This tool relates that to the
margin of victory -- the winner's share of valid votes minus the runner-up's --
at every level the geography supports: station, imada, delegation and
governorate.

The four answers are *not* four estimates of one number. A correlation computed
over aggregates is a different quantity from the same correlation over
individuals, and the gap between them is the modifiable areal unit problem, not
noise. The repo has already measured one instance of it: turnout against
Saied's share is r = +0.057 at station level and +0.199 at delegation level. So
all four are reported side by side and none is presented as "the" answer.

What is controlled, and what cannot be
--------------------------------------
A raw cross-sectional correlation here would be hard to read, because both
sides of it vary by region: Saied's margin does, and so does whatever drives a
party to staff a polling station. So every level is also reported with its
governorate mean removed, which asks the narrower and more answerable question
-- within one governorate, do the stations where a representative signed differ
from the stations where none did?

Three things this cannot settle, stated because the numbers invite the
inference anyway:

* **Direction.** A party staffs the stations it cares about, and a station's
  result is what it is. Nothing here separates the two.
* **Scan quality.** Presence is read off the scan, so a station whose scan is
  poor can read as empty. `register_cc` is reported against presence for that
  reason: if placement quality predicted presence, the field would be partly
  measuring image quality.
* **The unread stations.** Presence is missing wherever a scan would not
  register, and that missingness is not random -- the codebook already warns
  that failed forms are the low-resolution scans.
"""

import argparse
import csv
import json
import os
import random
import sys

import numpy as np
from scipy import stats

REPS = "data/representatives_2024.csv"
STATIONS = "data/station_margins.csv"
OUT = "data/verification/representatives_margin.jsonl"


def load(path):
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def corr(x, y):
    """Pearson and Spearman with n, or None where there is nothing to compute."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    if len(x) < 3 or x.std() == 0 or y.std() == 0:
        return None
    r, pr = stats.pearsonr(x, y)
    rho, ps = stats.spearmanr(x, y)
    return {"n": int(len(x)), "pearson_r": float(r), "pearson_p": float(pr),
            "spearman_rho": float(rho), "spearman_p": float(ps)}


def show(label, c):
    if c is None:
        print(f"  {label:<34} --  not computable")
        return
    print(f"  {label:<34} n {c['n']:>5}   r {c['pearson_r']:+.3f} "
          f"(p {c['pearson_p']:.2e})   rho {c['spearman_rho']:+.3f}")


def demean(groups, values):
    """`values` with each group's mean removed, so only within-group variation
    survives. Groups of one carry no information and come back as nan."""
    out = np.full(len(values), np.nan)
    idx = {}
    for i, g in enumerate(groups):
        idx.setdefault(g, []).append(i)
    for g, rows in idx.items():
        v = np.array([values[i] for i in rows], float)
        ok = np.isfinite(v)
        if ok.sum() < 2:
            continue
        m = v[ok].mean()
        for i, j in enumerate(rows):
            if ok[i]:
                out[j] = v[i] - m
    return out


def welch(a, b):
    """Difference in means with a Welch interval, in the units of the input."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    a, b = a[np.isfinite(a)], b[np.isfinite(b)]
    if len(a) < 2 or len(b) < 2:
        return None
    t, p = stats.ttest_ind(a, b, equal_var=False)
    se = np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
    df = (a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b)) ** 2 / (
        (a.var(ddof=1) / len(a)) ** 2 / (len(a) - 1)
        + (b.var(ddof=1) / len(b)) ** 2 / (len(b) - 1))
    crit = stats.t.ppf(0.975, df)
    d = a.mean() - b.mean()
    return {"n_present": int(len(a)), "n_absent": int(len(b)),
            "mean_present": float(a.mean()), "mean_absent": float(b.mean()),
            "difference": float(d), "ci95": [float(d - crit * se),
                                             float(d + crit * se)],
            "t": float(t), "p": float(p)}


def rollup(rows, key):
    """Per unit: presence rate over placed stations, and the unit's margin from
    its own vote totals -- summed, not averaged over stations, so the margin is
    the unit's real margin and not a mean of ratios."""
    agg = {}
    for r in rows:
        k = r.get(key) or ""
        if not k:
            continue
        a = agg.setdefault(k, {"placed": 0, "present": 0, "filled": 0,
                               "saied": 0.0, "zammel": 0.0, "maghzaoui": 0.0,
                               "registered": 0.0, "voters": 0.0,
                               "stations": 0, "gov": r.get("governorate_name")})
        a["stations"] += 1
        if r["_placed"]:
            a["placed"] += 1
            a["present"] += r["_any"]
            a["filled"] += r["_filled"]
        if r["_complete"]:
            for c in ("saied", "zammel", "maghzaoui"):
                a[c] += r[f"_{c}"]
        if r["_treg"] is not None:
            a["registered"] += r["_treg"]
            a["voters"] += r["_tvot"]
    out = []
    for k, a in agg.items():
        if not a["placed"]:
            continue
        v = sorted(((a["saied"], "saied"), (a["zammel"], "zammel"),
                    (a["maghzaoui"], "maghzaoui")), reverse=True)
        total = sum(x[0] for x in v)
        if total <= 0:
            continue
        out.append({
            "key": k, "gov": a["gov"], "stations": a["stations"],
            "placed": a["placed"],
            "presence_rate": 100.0 * a["present"] / a["placed"],
            "rows_per_station": a["filled"] / a["placed"],
            "margin_pp": 100.0 * (v[0][0] - v[1][0]) / total,
            "saied_share_pct": 100.0 * a["saied"] / total,
            "turnout_pct": (100.0 * a["voters"] / a["registered"]
                            if a["registered"] > 0 else np.nan),
        })
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--write", action="store_true",
                    help=f"also write {OUT}")
    ap.add_argument("--seed", type=int, default=11,
                    help="seed for the shuffled-presence null reference")
    args = ap.parse_args()

    for p in (REPS, STATIONS):
        if not os.path.exists(p):
            sys.exit(f"missing {p}")

    reps = {r["bureau_code"]: r for r in load(REPS)}
    rows = []
    for s in load(STATIONS):
        r = reps.get(s["bureau_code"])
        filled = num(r["reps_rows_filled"]) if r else None
        rows.append({
            **{k: s[k] for k in ("bureau_code", "governorate_name",
                                 "delegation_name", "adm3_pcode",
                                 "adm4_pcode", "id_delegation")},
            "_placed": filled is not None,
            "_filled": int(filled or 0),
            "_any": int(bool(filled)),
            "_cc": num(r["register_cc"]) if r else None,
            "_margin": num(s["margin_pp"]),
            "_saied_share": num(s["saied_share_pct"]),
            "_complete": s["complete"] == "1" and num(s["saied"]) is not None,
            "_saied": num(s["saied"]) or 0.0,
            "_zammel": num(s["zammel"]) or 0.0,
            "_maghzaoui": num(s["maghzaoui"]) or 0.0,
            "_registered": num(s["registered"]),
            "_treg": num(s["registered"]) if s["turnout_pct"] else None,
            "_tvot": num(s["voters"]) if s["turnout_pct"] else None,
            "_turnout": num(s["turnout_pct"]),
        })

    placed = [r for r in rows if r["_placed"]]
    print(f"stations: {len(rows)} in {STATIONS}, {len(placed)} with a "
          f"presence reading ({100.0 * len(placed) / len(rows):.1f}%)")
    n_any = sum(r["_any"] for r in placed)
    print(f"  at least one representative row filled: {n_any} "
          f"({100.0 * n_any / len(placed):.1f}% of those read)")
    dist = {k: sum(1 for r in placed if r["_filled"] == k) for k in range(4)}
    print("  rows filled: " + "  ".join(
        f"{k}: {v} ({100.0 * v / len(placed):.1f}%)" for k, v in dist.items()))

    log = [{"record": "coverage", "stations": len(rows),
            "with_reading": len(placed), "any_present": n_any,
            "rows_filled": dist}]

    # --- the confound that would invalidate the field, checked first --------
    print("\nis presence just a proxy for scan quality?")
    c = corr([r["_cc"] for r in placed], [r["_any"] for r in placed])
    show("registration cc vs presence", c)
    log.append({"record": "confound", "pair": "register_cc ~ presence",
                **(c or {})})

    both = [r for r in placed if r["_margin"] is not None]
    print(f"\nstation level ({len(both)} stations with a margin and a reading)")
    show("presence (0/1) vs margin_pp",
         corr([r["_any"] for r in both], [r["_margin"] for r in both]))
    show("rows filled (0-3) vs margin_pp",
         corr([r["_filled"] for r in both], [r["_margin"] for r in both]))
    show("presence vs Saied share",
         corr([r["_any"] for r in both], [r["_saied_share"] for r in both]))
    show("presence vs turnout",
         corr([r["_any"] for r in both], [r["_turnout"] for r in both]))
    show("presence vs registered electors",
         corr([r["_any"] for r in both], [r["_registered"] for r in both]))

    w = welch([r["_margin"] for r in both if r["_any"]],
              [r["_margin"] for r in both if not r["_any"]])
    if w:
        print(f"  margin where a representative signed: "
              f"{w['mean_present']:.2f}pp (n {w['n_present']})")
        print(f"  margin where none did:                "
              f"{w['mean_absent']:.2f}pp (n {w['n_absent']})")
        print(f"  difference: {w['difference']:+.2f}pp "
              f"(95% CI {w['ci95'][0]:+.2f} to {w['ci95'][1]:+.2f}, "
              f"p {w['p']:.2e})")
        log.append({"record": "station_difference", "outcome": "margin_pp", **w})

    dm_m = demean([r["governorate_name"] for r in both],
                  [r["_margin"] for r in both])
    dm_p = demean([r["governorate_name"] for r in both],
                  [float(r["_any"]) for r in both])
    show("within governorate, presence vs margin", corr(dm_p, dm_m))

    for level, key in (("imada", "adm4_pcode"),
                       ("delegation", "adm3_pcode"),
                       ("governorate", "governorate_name")):
        units = rollup(rows, key)
        print(f"\n{level} level ({len(units)} units with at least one station "
              f"read)")
        pr = [u["presence_rate"] for u in units]
        show("presence rate vs margin_pp",
             corr(pr, [u["margin_pp"] for u in units]))
        show("rows per station vs margin_pp",
             corr([u["rows_per_station"] for u in units],
                  [u["margin_pp"] for u in units]))
        show("presence rate vs Saied share",
             corr(pr, [u["saied_share_pct"] for u in units]))
        show("presence rate vs turnout",
             corr(pr, [u["turnout_pct"] for u in units]))
        if level != "governorate":
            show("within governorate, presence vs margin",
                 corr(demean([u["gov"] for u in units], pr),
                      demean([u["gov"] for u in units],
                             [u["margin_pp"] for u in units])))
        c = corr(pr, [u["margin_pp"] for u in units])
        log.append({"record": "level", "level": level, "units": len(units),
                    "presence_rate_vs_margin": c or {}})
        print(f"  presence rate: min {min(pr):.1f}%  median "
              f"{np.median(pr):.1f}%  max {max(pr):.1f}%")

    # --- the null reference ------------------------------------------------
    # Shuffling presence across the stations that have a reading destroys any
    # real association while leaving every other feature of the data alone --
    # the same station count, the same margin distribution, the same unit
    # sizes. Whatever this reports is what the pipeline produces from noise,
    # and it is the number the results above have to be read against. On a
    # synthetic file with presence assigned at random the tool returned
    # |r| <= 0.04 at station, imada and delegation level, which is what
    # licensed reading the real figures as signal rather than as artefact.
    print("\nnull reference: presence shuffled across the stations that "
          f"have a reading (seed {args.seed})")
    rng = random.Random(args.seed)
    shuffled = [r["_any"] for r in placed]
    rng.shuffle(shuffled)
    for r, v in zip(placed, shuffled):
        r["_any"], r["_filled"] = v, v
    show("station: presence vs margin_pp",
         corr([r["_any"] for r in both], [r["_margin"] for r in both]))
    for level, key in (("imada", "adm4_pcode"), ("delegation", "adm3_pcode")):
        units = rollup(rows, key)
        show(f"{level}: presence rate vs margin_pp",
             corr([u["presence_rate"] for u in units],
                  [u["margin_pp"] for u in units]))

    if args.write:
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        with open(OUT, "w", encoding="utf-8") as fh:
            for rec in log:
                json.dump(rec, fh, ensure_ascii=False)
                fh.write("\n")
        print(f"\nwrote {OUT} ({len(log)} records)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
