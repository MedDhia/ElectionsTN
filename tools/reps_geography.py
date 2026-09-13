"""Aggregate the station-level representatives readings to mappable units.

Every rate here is over the stations that were actually **read**, never over all
stations in the unit. A station whose table was not located, or was located and
not yet read, is not a station where nobody came, and counting it in the
denominator would push every rate toward zero in exactly the places where the
scans are worst — which is a geographic pattern in its own right and would be
read as a finding about observers.

So each unit carries both numbers: `n_read` is the denominator, `n_stations` is
how many the unit has. A unit where those diverge is a unit whose figure rests on
a sample, and the maps grey out any unit thin enough that its rate is noise.

Usage: python3 tools/reps_geography.py [min_read]
"""
import csv, math, os, sys
from collections import defaultdict

SRC = "data/pv_representatives_2024.csv"
OUT_GOV = "data/representatives_by_governorate.csv"
OUT_DEL = "data/representatives_by_delegation.csv"
OUT_IMA = "data/representatives_by_imada.csv"

CANDIDATES = ("saied", "zammel", "maghzaoui")


def wilson(k, n, z=1.96):
    """Wilson interval: an exact-ish CI that stays inside [0,1] at small n.

    The normal interval is what a first pass reaches for and it is wrong here —
    a delegation with 6 stations read and 6 of them carrying a representative
    gets a zero-width interval from it, which is the one case where the reader
    most needs the width.
    """
    if not n:
        return None, None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def aggregate(rows, keys, name_cols):
    out = defaultdict(lambda: {"n_stations": 0, "n_read": 0, "any": 0,
                               "reps": 0, **{c: 0 for c in CANDIDATES},
                               **{c + "_st": 0 for c in CANDIDATES},
                               "unattributed": 0})
    for r in rows:
        k = tuple(r[c] for c in keys)
        if not all(k):
            continue
        u = out[k]
        u["n_stations"] += 1
        for c in name_cols:
            u[c] = r[c]
        if r["reading"] != "read":
            continue
        u["n_read"] += 1
        n = int(r["n_representatives"] or 0)
        u["reps"] += n
        u["any"] += 1 if n else 0
        u["unattributed"] += int(r["unattributed"] or 0)
        for c in CANDIDATES:
            k = int(r[f"rep_{c}"] or 0)
            u[c] += k                      # representative rows
            u[c + "_st"] += 1 if k else 0  # stations with at least one
    return out


def write(path, units, keys, name_cols):
    fields = (list(keys) + list(name_cols)
              + ["n_stations", "n_read", "read_pct", "stations_with_any",
                 "any_pct", "any_lo_pct", "any_hi_pct", "representatives",
                 "reps_per_100_stations"]
              + [f"reps_{c}" for c in CANDIDATES]
              + [f"stations_with_{c}" for c in CANDIDATES]
              + [f"stations_with_{c}_pct" for c in CANDIDATES]
              + ["unattributed"])
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fields)
        w.writeheader()
        for k, u in sorted(units.items()):
            n = u["n_read"]
            lo, hi = wilson(u["any"], n)
            row = dict(zip(keys, k))
            for c in name_cols:
                row[c] = u[c]
            row.update(
                n_stations=u["n_stations"], n_read=n,
                read_pct=round(100 * n / u["n_stations"], 1),
                stations_with_any=u["any"],
                any_pct=round(100 * u["any"] / n, 1) if n else "",
                any_lo_pct=round(100 * lo, 1) if n else "",
                any_hi_pct=round(100 * hi, 1) if n else "",
                representatives=u["reps"],
                reps_per_100_stations=round(100 * u["reps"] / n, 1) if n else "",
                unattributed=u["unattributed"])
            for c in CANDIDATES:
                # A station can record two representatives for the same
                # candidate, so the count of rows and the count of stations
                # are different quantities and the share must be built on the
                # second: a rate over stations that can exceed 100 is a bug
                # announcing itself, and this one did.
                row[f"reps_{c}"] = u[c]
                row[f"stations_with_{c}"] = u[c + "_st"]
                row[f"stations_with_{c}_pct"] = (
                    round(100 * u[c + "_st"] / n, 1) if n else "")
            w.writerow(row)
    print(f"{len(units)} units -> {path}")


def main():
    rows = list(csv.DictReader(open(SRC, encoding="utf-8")))
    write(OUT_GOV, aggregate(rows, ["governorate_name"], ["governorate_ar"]),
          ["governorate_name"], ["governorate_ar"])
    write(OUT_DEL, aggregate(rows, ["adm3_pcode"],
                             ["governorate_name", "delegation_name"]),
          ["adm3_pcode"], ["governorate_name", "delegation_name"])
    write(OUT_IMA, aggregate(rows, ["adm4_pcode"],
                             ["governorate_name", "delegation_name", "imada_name"]),
          ["adm4_pcode"], ["governorate_name", "delegation_name", "imada_name"])

    read = [r for r in rows if r["reading"] == "read"]
    reps = sum(int(r["n_representatives"] or 0) for r in read)
    anyr = sum(1 for r in read if int(r["n_representatives"] or 0))
    print(f"\n{len(read)} stations read of {len(rows)} ({100*len(read)/len(rows):.1f}%)")
    print(f"  with at least one representative: {anyr} ({100*anyr/len(read):.1f}% of read)")
    print(f"  representatives recorded: {reps}")
    for c in CANDIDATES:
        n = sum(int(r[f"rep_{c}"] or 0) for r in read)
        print(f"    {c:10s} {n:5d} ({100*n/max(1,reps):.1f}% of representatives)")
    un = sum(int(r["unattributed"] or 0) for r in read)
    print(f"    unattributed rows: {un}")
    post_stratified(rows, read)


def post_stratified(rows, read):
    """National figures weighted by governorate, and the raw ones beside them.

    The reading pass is not uniform across the country. It was ordered to keep
    coverage proportional, but it was interrupted at a point where the share
    read runs from about 11% to about 37% by governorate, so the raw mean over
    read stations is the mean of an unevenly drawn sample. Re-weighting each
    governorate to its true share of polling stations removes that, and printing
    both says how much it mattered — which on this sample is a few tenths of a
    point, so the imbalance is not doing the work.
    """
    tot, seen, hit, nrep = defaultdict(int), defaultdict(int), defaultdict(int), defaultdict(int)
    per_cand = {c: defaultdict(int) for c in CANDIDATES}
    for r in rows:
        g = r["governorate_name"] or r["governorate_ar"]
        tot[g] += 1
    for r in read:
        g = r["governorate_name"] or r["governorate_ar"]
        seen[g] += 1
        n = int(r["n_representatives"] or 0)
        hit[g] += 1 if n else 0
        nrep[g] += n
        for c in CANDIDATES:
            per_cand[c][g] += 1 if int(r[f"rep_{c}"] or 0) else 0
    N = sum(tot.values())
    covered = [g for g in tot if seen[g]]
    W = sum(tot[g] for g in covered)
    def wmean(num):
        return sum(tot[g] * num[g] / seen[g] for g in covered) / W
    print(f"\n  post-stratified by governorate ({len(covered)} of {len(tot)} covered,"
          f" {100*W/N:.0f}% of stations):")
    print(f"    stations with a representative: {100*wmean(hit):.1f}%"
          f"  (unweighted {100*sum(hit.values())/sum(seen.values()):.1f}%)")
    print(f"    representatives per 100 stations: {100*wmean(nrep):.1f}")
    for c in CANDIDATES:
        print(f"    stations with a {c} representative: {100*wmean(per_cand[c]):.1f}%")


if __name__ == "__main__":
    main()
