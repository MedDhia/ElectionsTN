"""Standing check over the turnout basis.

Reads only published files and exits non-zero on a violation, like the five
audits already in the repo. It exists because the turnout column has been wrong
twice, in two different ways, and neither showed up as an implausible national
figure -- only as absurd individual units.

The four checks that matter
---------------------------
**No station may publish an impossible turnout.** Forty once did, the worst at
13,133% -- three registered voters against 394 who voted. That is what happens
when the numerator is certified and the denominator is not: nothing on the form
contradicts a misread registered count, so only an explicit gate catches it.

**The numerator and denominator must come from the same stations.** Summing each
column over whatever happens to carry it made Houmt Souk report 1.1% turnout,
`registered` from 47 stations over `voters` from 3, against 17.3% on the matched
subset. 167 of 264 delegations were affected. So the aggregates are recomputed
here from the station table over `turnout_basis == 1` and must match to the
published digit.

**Coverage must be honest.** `turnout_coverage_pct` is what tells a reader that
Houmt Souk's figure rests on 5% of its stations, and it is what the maps use to
decide which units to withhold. If it drifted from the station counts the maps
would silently draw units they should not.

**The candidate columns must not have moved.** The turnout repair touched a
shared file, so the national vote totals are asserted here as a regression
guard: 2,303,043 / 176,525 / 47,847.
"""

import argparse
import collections
import csv
import os
import sys

STATION = "data/station_margins.csv"
DELEG = "data/delegation_margins.csv"
IMADA = "data/imada_margins.csv"
PV = "data/pv_presidential_2024.csv"

DELEG_ROWS, IMADA_ROWS, STATION_ROWS = 264, 2042, 9448
NATIONAL = {"saied": 2303043, "zammel": 176525, "maghzaoui": 47847}

# The national turnout on the matched, gated basis. Asserted to the tenth of a
# point: a change here means the basis moved, which is exactly what this audit
# exists to notice.
NATIONAL_TURNOUT = 30.38
TURNOUT_TOL = 0.05


def read(p):
    with open(p, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def num(r, c):
    v = r.get(c)
    return None if v in (None, "", "NA") else float(v)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    for p in (STATION, DELEG, IMADA, PV):
        if not os.path.exists(p):
            sys.exit(f"missing {p}; run tools/build_margins.py --write")

    stations, delegs, imadas = read(STATION), read(DELEG), read(IMADA)
    pv = {r["bureau_code"]: r for r in read(PV)}
    fail, passed = [], [0]

    def check(ok, msg):
        if ok:
            passed[0] += 1
        else:
            fail.append(msg)
            print(f"  FAIL  {msg}")

    check(len(stations) == STATION_ROWS,
          f"{STATION} has {len(stations)} rows, expected {STATION_ROWS}")
    check(len(delegs) == DELEG_ROWS,
          f"{DELEG} has {len(delegs)} rows, expected {DELEG_ROWS}")
    check(len(imadas) == IMADA_ROWS,
          f"{IMADA} has {len(imadas)} rows, expected {IMADA_ROWS}")

    # ---- station level
    impossible = []
    for r in stations:
        t = num(r, "turnout_pct")
        if t is not None and t > 100.0:
            impossible.append((r["bureau_code"], t))
    check(not impossible,
          f"{len(impossible)} station(s) publish turnout above 100%, worst "
          f"{max((t for _, t in impossible), default=0):,.1f}%")

    basis_wrong = []
    for r in stations:
        on = r.get("turnout_basis") == "1"
        has_t = num(r, "turnout_pct") is not None
        if on != has_t:
            basis_wrong.append(r["bureau_code"])
    check(not basis_wrong,
          f"{len(basis_wrong)} station(s) publish a turnout without being on "
          f"the turnout basis, or the reverse")

    gate_wrong = []
    for r in stations:
        if r.get("turnout_basis") != "1":
            continue
        reg, vot = num(r, "registered"), num(r, "voters")
        src = pv.get(r["bureau_code"], {})
        if reg is None or vot is None or reg <= 0 or vot > reg \
                or src.get("a_registered_ok") != "1":
            gate_wrong.append(r["bureau_code"])
    check(not gate_wrong,
          f"{len(gate_wrong)} station(s) are on the turnout basis without "
          f"passing the registered gate")

    # ---- aggregates recomputed from the stations
    for level, rows, key in (("delegation", delegs, "adm3_pcode"),
                             ("imada", imadas, "adm4_pcode")):
        agg = collections.defaultdict(lambda: collections.Counter())
        for r in stations:
            k = r.get(key)
            if not k:
                continue
            agg[k]["n"] += 1
            if r.get("turnout_basis") == "1":
                agg[k]["s"] += 1
                agg[k]["reg"] += int(float(r["registered"]))
                agg[k]["vot"] += int(float(r["voters"]))
        bad_sum, bad_cov, bad_pct, over = [], [], [], []
        for r in rows:
            a = agg.get(r[key])
            if a is None:
                continue
            if (int(r["turnout_registered"]) != a["reg"]
                    or int(r["turnout_voters"]) != a["vot"]
                    or int(r["turnout_stations"]) != a["s"]):
                bad_sum.append(r[key])
            cov = num(r, "turnout_coverage_pct")
            want = 100.0 * a["s"] / a["n"] if a["n"] else None
            if cov is None or want is None or abs(cov - want) > 1e-3:
                bad_cov.append(r[key])
            t = num(r, "turnout_pct")
            if a["reg"]:
                if t is None or abs(t - 100.0 * a["vot"] / a["reg"]) > 1e-3:
                    bad_pct.append(r[key])
                if t is not None and t > 100.0:
                    over.append((r[key], t))
            elif t is not None:
                bad_pct.append(r[key])
        check(not bad_sum,
              f"{level}: {len(bad_sum)} unit(s) do not sum their turnout "
              f"numerator and denominator over the same stations")
        check(not bad_cov,
              f"{level}: {len(bad_cov)} unit(s) publish a coverage that does "
              f"not match their station counts")
        check(not bad_pct,
              f"{level}: {len(bad_pct)} unit(s) publish a turnout that is not "
              f"their own voters over their own registered")
        check(not over,
              f"{level}: {len(over)} unit(s) publish turnout above 100%")

        tot_r = sum(int(r["turnout_registered"]) for r in rows)
        tot_v = sum(int(r["turnout_voters"]) for r in rows)
        rate = 100.0 * tot_v / tot_r if tot_r else 0.0
        check(abs(rate - NATIONAL_TURNOUT) <= TURNOUT_TOL,
              f"{level}: national turnout on the matched basis is {rate:.2f}%, "
              f"expected {NATIONAL_TURNOUT:.2f}% ± {TURNOUT_TOL}")
        if args.verbose:
            print(f"  {level}: national turnout {rate:.2f}% over "
                  f"{tot_r:,} registered")

    # ---- the repair must not have moved a single vote
    for c, want in NATIONAL.items():
        got = sum(int(r[c]) for r in delegs)
        check(got == want,
              f"national {c} is {got:,}, expected {want:,} — the turnout "
              f"repair moved a candidate column")

    print(f"{len(fail) + passed[0]} checks run")
    if fail:
        print(f"\n{len(fail)} check(s) failed")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
