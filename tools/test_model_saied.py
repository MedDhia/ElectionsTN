"""Checks on the joins and the estimator behind the 2019 Saied model.

Six things can silently corrupt that model, and each is checked here rather
than trusted:

1. **The constituency join.** Five files name the same 33 constituencies, and
   the 2019 report's text layer transposes letters in five of the names. The
   matcher has to land all 33 with no name claimed twice.
2. **The census governorate join.** The census writes MANNOUBA where the
   boundary layer writes Manubah, and MANNOUBA is equidistant from Jendouba.
   The one-to-one assignment has to resolve that, and only that.
3. **Aggregation order.** A governorate's share is its votes over its valid
   votes. Averaging two constituency shares instead is a different number, and
   the test pins the right one against arithmetic done independently.
4. **The delegation bridge.** All 264 delegations have to pair across the
   archive, INS and the census, one to one.
5. **The constituency split.** Tunis, Sfax and Nabeul vote in halves, recovered
   from the archive's own folder tree. The halves have to partition each
   governorate exactly, and the population each half sends per seat has to come
   out even -- seats were allocated on population, so a wrong split shows up
   there.
6. **Forward selection.** The fast implementation picks columns by partial
   correlation instead of refitting every candidate. Same answer or the speedup
   is a bug.

Usage: python3 tools/test_model_saied.py
"""
import collections
import csv
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_maps import load_layer
from make_2019_maps import fold, gov_of
from covariates import bridge, split_halves, validate
from model_saied_2019 import (Forward, PRES14, PRES19, align, census_governorates,
                              latin_fold, pres_counts, read, to_shares)

FAIL = []


def check(name, ok, detail=""):
    print(f"  {'ok  ' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAIL.append(name)


def canon():
    return sorted({fold(r["centre"]) for r in read(PRES14)})


def test_constituency_join():
    print("constituency join")
    keys = canon()
    check("2014 names are 33 distinct", len(keys) == 33, f"{len(keys)}")
    for path, col in ((PRES19, "constituency"),
                      ("data/legislative_2014_list_results.csv", "constituency"),
                      ("data/legislative_2019_list_results.csv", "constituency"),
                      ("data/presidential_2014_centre_turnout.csv", "centre"),
                      ("data/legislative_2014_constituency_results.csv",
                       "constituency")):
        names = {r[col] for r in read(path)}
        m = align(names, keys)
        onto = len(set(m.values())) == 33
        check(os.path.basename(path), onto and len(m) == len(names),
              f"{len(names)} names -> {len(set(m.values()))} constituencies")
    # the five the text layer damaged must still land, and land correctly
    damaged = {"املنستير": "المنستير", "املهديه": "المهديه", "مدنني": "مدنين",
               "املانيا": "المانيا"}
    m = align({r["constituency"] for r in read(PRES19)}, keys)
    hit = {k: v for k, v in m.items() if fold(k) in damaged}
    check("transposed names repair",
          all(v == fold(damaged[fold(k)]) for k, v in hit.items())
          and len(hit) == len(damaged), f"{len(hit)} of {len(damaged)}")


def test_census_join():
    print("census governorate join")
    layer = {f["properties"]["adm2_name"] for f in load_layer("tun_admin2.geojson")}
    import gzip
    import fetch_census
    with gzip.open(fetch_census.paths()["master"], "rt", encoding="utf-8") as fh:
        cen = {r["governorate"] for r in csv.DictReader(fh)}
    pair = census_governorates(cen, layer)
    check("bijection over 24 governorates",
          len(pair) == 24 and len(set(pair.values())) == 24, f"{len(pair)}")
    check("MANNOUBA resolves to Manubah, not Jendouba",
          pair.get("MANNOUBA") == "Manubah", str(pair.get("MANNOUBA")))
    check("JENDOUBA keeps Jendouba", pair.get("JENDOUBA") == "Jendouba")
    exact = [a for a, b in pair.items() if latin_fold(a) == latin_fold(b)]
    check("21 of 24 match with no repair at all", len(exact) == 21,
          f"{len(exact)} exact, repaired: "
          f"{sorted(a for a in pair if a not in exact)}")


def test_aggregation():
    print("aggregation to governorate")
    keys = canon()
    v, t = pres_counts(PRES19, keys, "constituency", "constituency_valid_votes")
    units = {c: gov_of(c) for c in keys}
    shares, names, valid = to_shares(v, t, units, top=0.0)
    saied = fold("قيس سعيد")

    # The same numbers, recomputed off the file with nothing from `to_shares`.
    # The name join is borrowed, because it is what the previous test covers;
    # what is independent here is the arithmetic and the order it happens in.
    m = align({r["constituency"] for r in read(PRES19)}, keys)
    raw = collections.Counter()
    den = {}
    for r in read(PRES19):
        g = gov_of(m[r["constituency"]])
        if g is None:
            continue
        if fold(r["candidate"]) == saied:
            raw[g] += float(r["votes"])
        den[(g, m[r["constituency"]])] = float(r["constituency_valid_votes"])
    tot = collections.Counter()
    for (g, _), d in den.items():
        tot[g] += d
    worst = max(abs(shares[g][saied] - raw[g] / tot[g]) for g in raw)
    check("24 governorates", len(shares) == 24, f"{len(shares)}")
    check("Saied's governorate share is votes over valid votes",
          worst < 1e-12, f"largest disagreement {worst:.2e}")

    # and a split governorate must land between its two halves, not outside them
    tunis = gov_of(fold("تونس 1"))
    v2, t2 = pres_counts(PRES19, keys, "constituency",
                         "constituency_valid_votes")
    per, _, _ = to_shares(v2, t2, {c: c for c in keys}, top=0.0)
    lo = min(per[fold("تونس 1")][saied], per[fold("تونس 2")][saied])
    hi = max(per[fold("تونس 1")][saied], per[fold("تونس 2")][saied])
    check("Tunis sits between Tunis 1 and Tunis 2",
          lo <= shares[tunis][saied] <= hi,
          f"{100 * lo:.2f} <= {100 * shares[tunis][saied]:.2f} <= {100 * hi:.2f}")


def test_bridge():
    print("delegation bridge and the constituency split")
    br = bridge()
    check("264 delegations bridged", len(br) == 264, f"{len(br)}")
    check("every delegation has a census row",
          all(d["census"] for d in br.values()))
    halves = collections.Counter(d["constituency"] for d in br.values()
                                 if d["constituency"] != d["governorate"])
    check("six halves over 53 delegations",
          len(halves) == 6 and sum(halves.values()) == 53,
          f"{len(halves)} halves, {sum(halves.values())} delegations")
    check("the halves partition their governorates 11+10, 8+8, 9+7",
          sorted(halves.values()) == [7, 8, 8, 9, 10, 11],
          str(sorted(halves.values())))
    # Kasserine has a delegation called الزهور and so does Tunis; the split must
    # not swallow the Kasserine one
    stray = [d for d in br.values()
             if d["constituency"] != d["governorate"]
             and fold("تونس") not in d["governorate"]
             and fold("صفاقس") not in d["governorate"]
             and fold("نابل") not in d["governorate"]]
    check("no delegation outside the three split governorates is filed in a half",
          not stray, f"{len(stray)} stray")
    check("population per seat is even across the halves and beats the swap",
          validate())


def test_forward_selection():
    print("forward selection")
    from sklearn.linear_model import LinearRegression
    rng = np.random.default_rng(11)
    X = rng.normal(size=(27, 40))
    y = 1.4 * X[:, 7] - 0.9 * X[:, 22] + 0.3 * rng.normal(size=27)

    def naive(k):
        chosen, rem = [], list(range(X.shape[1]))
        for _ in range(k):
            best, bj = np.inf, None
            for j in rem:
                cols = chosen + [j]
                r = LinearRegression().fit(X[:, cols], y)
                sse = float(np.sum((y - r.predict(X[:, cols])) ** 2))
                if sse < best:
                    best, bj = sse, j
            chosen.append(bj)
            rem.remove(bj)
        return chosen

    for k in (1, 2, 3):
        fast = Forward(k).fit(X, y).cols
        check(f"k={k} matches refitting every candidate", fast == naive(k),
              f"{fast}")
    check("it finds the two columns the target was built from",
          set(Forward(2).fit(X, y).cols) == {7, 22})


def main():
    for t in (test_constituency_join, test_census_join, test_aggregation,
              test_bridge, test_forward_selection):
        t()
    print()
    if FAIL:
        print(f"{len(FAIL)} failed: {FAIL}")
        raise SystemExit(1)
    print("all checks passed")


if __name__ == "__main__":
    main()
