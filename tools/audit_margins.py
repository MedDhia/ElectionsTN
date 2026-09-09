"""Standing check over the margin tables and the joined map data.

Reads only published files and exits non-zero on a violation, like the three
audits already in the repo. Two of its checks are worth naming.

**The national totals.** Summing the station table must reproduce the published
figures exactly. That single assertion exercises the whole chain -- reading,
certification basis, filtering, aggregation -- and is why it is here rather than
in a comment.

**Spatial coherence.** A name-based join can silently scramble which unit gets
which result, and no arithmetic check would notice: the totals still add up. What
does notice is geography. If the join were scrambled, values would be
uncorrelated with location, so the share of variance explained by the parent unit
would collapse to what a shuffled control gives. Measured: geography explains
44.7% at delegation level and 62.1% at imada level, against 8.6% and 12.3% for
shuffles of the same values. The floor here is set well below those and well
above the controls.
"""

import argparse
import collections
import csv
import json
import math
import os
import random
import statistics as st
import sys

STATION = "data/station_margins.csv"
DELEG = "data/delegation_margins.csv"
IMADA = "data/imada_margins.csv"
SUMMARY = "data/margin_summary.csv"
INS = "data/delegations_ins.csv"
GEO = ["data/maps/delegation_results.geojson", "data/maps/imada_results.geojson"]

PV_ROWS = 9448
DELEG_ROWS = 264
CANDIDATES = ("saied", "zammel", "maghzaoui")

# The published national figures, on the certified basis.
NATIONAL = {"saied": 2303043, "zammel": 176525, "maghzaoui": 47847}
NATIONAL_VALID = 2527415

# Well below what the real join achieves (0.447 / 0.621) and well above the
# shuffled controls (0.086 / 0.123).
COHERENCE_MIN = 0.25

METHODS = {"scoped", "scoped_near", "governorate_recovery",
           "governorate_recovery_near", "unmatched", ""}


def read(p):
    with open(p, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def coherence(rows, value_col, group_col, seed=7):
    """Share of variance in `value_col` explained by `group_col`, and the same
    statistic after shuffling values across units."""
    rows = [r for r in rows if r.get(value_col) and r.get(group_col)]
    if len(rows) < 20:
        return None, None
    vals = [float(r[value_col]) for r in rows]
    overall = st.pstdev(vals)
    if overall == 0:
        return None, None

    def within(values):
        g = collections.defaultdict(list)
        for r, v in zip(rows, values):
            g[r[group_col]].append(v)
        num = sum(sum((v - st.fmean(vs)) ** 2 for v in vs)
                  for vs in g.values() if len(vs) > 1)
        den = sum(len(vs) for vs in g.values() if len(vs) > 1)
        return math.sqrt(num / den) if den else None

    w = within(vals)
    shuffled = vals[:]
    random.Random(seed).shuffle(shuffled)
    ws = within(shuffled)
    if w is None or ws is None:
        return None, None
    return 1 - (w / overall) ** 2, 1 - (ws / overall) ** 2


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    for p in (STATION, DELEG, IMADA, SUMMARY, INS, *GEO):
        if not os.path.exists(p):
            sys.exit(f"missing {p}; run tools/build_margins.py --write "
                     f"and tools/make_maps.py")
    stations, delegs, imadas = read(STATION), read(DELEG), read(IMADA)
    fail = []
    passed = [0]

    # Messages state the failure condition, so echoing them on success would
    # read backwards -- "ok: the join may be scrambled". Successes are therefore
    # counted, not echoed, and only failures print their message.
    def check(ok, msg):
        if ok:
            passed[0] += 1
        else:
            fail.append(msg)
            print(f"  FAIL  {msg}")

    def section(name):
        if args.verbose and passed[0]:
            print(f"        {passed[0]} passed")
        print(name)

    section("row counts")
    check(len(stations) == PV_ROWS, f"{STATION} has {len(stations)}, expected {PV_ROWS}")
    check(len(delegs) == DELEG_ROWS, f"{DELEG} has {len(delegs)}, expected {DELEG_ROWS}")
    check(len({r["bureau_code"] for r in stations}) == len(stations),
          "a bureau_code repeats in the station table")

    section("the national totals reproduce the published figures")
    nat = {c: sum(int(r[c]) for r in stations if r["votes_certified"] == "1")
           for c in CANDIDATES}
    for c in CANDIDATES:
        check(nat[c] == NATIONAL[c],
              f"{c} sums to {nat[c]:,}, published {NATIONAL[c]:,}")
    check(sum(nat.values()) == NATIONAL_VALID,
          f"valid sums to {sum(nat.values()):,}, published {NATIONAL_VALID:,}")

    section("levels agree with each other")
    for label, rows, col in (("delegation", delegs, "adm3_pcode"),
                             ("imada", imadas, "adm4_pcode")):
        for c in CANDIDATES:
            agg = sum(int(r[c]) for r in rows)
            direct = sum(int(r[c]) for r in stations
                         if r["votes_certified"] == "1" and r[col])
            check(agg == direct,
                  f"{label} {c} sums to {agg:,} but its stations give {direct:,}")
        st_n = sum(1 for r in stations if r[col])
        agg_n = sum(int(r["n_stations"]) for r in rows)
        check(st_n == agg_n,
              f"{label} station counts disagree: {agg_n} aggregated, {st_n} in the "
              f"station table")

    section("shares and margins are internally consistent")
    bad_range = [r["bureau_code"] for r in stations for c in CANDIDATES
                 if r[f"{c}_share_pct"] and not 0 <= float(r[f"{c}_share_pct"]) <= 100]
    check(not bad_range, f"{len(bad_range)} shares outside [0,100], e.g. {bad_range[:3]}")
    bad_sum = [r["bureau_code"] for r in stations
               if r["saied_share_pct"]
               and abs(sum(float(r[f"{c}_share_pct"]) for c in CANDIDATES) - 100) > 0.01]
    check(not bad_sum, f"{len(bad_sum)} rows whose three shares do not sum to 100, "
                       f"e.g. {bad_sum[:3]}")
    bad_margin = []
    for r in stations + delegs + imadas:
        if not r.get("margin_pp") or not r.get("winner"):
            continue
        shares = sorted((float(r[f"{c}_share_pct"]) for c in CANDIDATES
                         if r.get(f"{c}_share_pct")), reverse=True)
        if len(shares) == 3 and abs((shares[0] - shares[1]) - float(r["margin_pp"])) > 0.01:
            bad_margin.append(r.get("bureau_code") or r.get("adm3_pcode") or r.get("adm4_pcode"))
    check(not bad_margin, f"{len(bad_margin)} rows where margin_pp is not the "
                          f"winner's lead, e.g. {bad_margin[:3]}")
    bad_winner = [r.get("bureau_code") or r.get("adm4_pcode")
                  for r in stations + delegs + imadas
                  if r.get("winner") and r.get(f"{r['winner']}_share_pct")
                  and any(float(r[f"{c}_share_pct"]) > float(r[f"{r['winner']}_share_pct"]) + 1e-9
                          for c in CANDIDATES if r.get(f"{c}_share_pct"))]
    check(not bad_winner, f"{len(bad_winner)} rows whose winner is not the top share")

    section("the delegation join is still exact, by code")
    ins_pcodes = {"TN" + r["id_delegation"] for r in read(INS)}
    check({r["adm3_pcode"] for r in delegs} == ins_pcodes,
          "the delegation table's pcodes differ from the INS codes")
    orphan = [r["adm4_pcode"] for r in imadas if r["adm3_pcode"] not in ins_pcodes]
    check(not orphan, f"{len(orphan)} imadas cite an unknown parent delegation")

    section("methods and coverage")
    bad_m = sorted({r["imada_match_method"] for r in stations} - METHODS)
    check(not bad_m, f"unknown imada_match_method values: {bad_m}")
    nod = [r["bureau_code"] for r in stations if not r["adm3_pcode"]]
    check(not nod, f"{len(nod)} stations carry no delegation, e.g. {nod[:3]}")

    section("spatial coherence beats a shuffled control")
    for label, rows, val, grp in (
            ("delegation", delegs, "saied_share_pct", "governorate_name"),
            ("imada", imadas, "saied_share_pct", "delegation_name")):
        got, shuf = coherence(rows, val, grp)
        check(got is not None, f"{label}: coherence not computable")
        if got is None:
            continue
        check(got >= COHERENCE_MIN,
              f"{label}: geography explains only {got:.1%} of variance "
              f"(floor {COHERENCE_MIN:.0%}) — the join may be scrambled")
        check(got > shuf * 2,
              f"{label}: {got:.1%} explained is not clearly above the shuffled "
              f"control {shuf:.1%}")
        if args.verbose:
            print(f"        {label}: geography explains {got:.1%} of variance, "
                  f"shuffled control {shuf:.1%}")

    section("the joined GeoJSON matches the tables")
    for path, col, table in ((GEO[0], "adm3_pcode", delegs), (GEO[1], "adm4_pcode", imadas)):
        gj = json.load(open(path, encoding="utf-8"))
        codes = {f["properties"][col] for f in gj["features"]}
        check(len(gj["features"]) == len(codes),
              f"{path} repeats a {col}")
        missing = {r[col] for r in table} - codes
        check(not missing, f"{path} is missing {len(missing)} units that the table has")
        joined = sum(1 for f in gj["features"] if f["properties"].get("saied_share_pct"))
        check(joined == len(table),
              f"{path} carries results on {joined} features, table has {len(table)}")

    if args.verbose and passed[0]:
        print(f"        {passed[0]} passed")
    print(f"\n{len(stations):,} stations · {len(delegs)} delegations · "
          f"{len(imadas):,} imadas · national valid {sum(nat.values()):,}")
    print(f"{len(fail) + passed[0]} checks run")
    if fail:
        print(f"\n{len(fail)} check(s) failed")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
