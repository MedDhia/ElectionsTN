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
            u[c] += int(r[f"rep_{c}"] or 0)
    return out


def write(path, units, keys, name_cols):
    fields = (list(keys) + list(name_cols)
              + ["n_stations", "n_read", "read_pct", "stations_with_any",
                 "any_pct", "any_lo_pct", "any_hi_pct", "representatives",
                 "reps_per_100_stations"]
              + [f"reps_{c}" for c in CANDIDATES]
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
                row[f"reps_{c}"] = u[c]
                row[f"stations_with_{c}_pct"] = (
                    round(100 * u[c] / n, 1) if n else "")
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
    print(f"\n{len(read)} stations read of {len(rows)}")
    print(f"  with at least one representative: {anyr} ({100*anyr/len(read):.1f}%)")
    print(f"  representatives recorded: {reps}")
    for c in CANDIDATES:
        n = sum(int(r[f"rep_{c}"] or 0) for r in read)
        print(f"    {c:10s} {n:5d} ({100*n/max(1,reps):.1f}% of representatives)")
    un = sum(int(r["unattributed"] or 0) for r in read)
    print(f"    unattributed rows: {un}")


if __name__ == "__main__":
    main()
