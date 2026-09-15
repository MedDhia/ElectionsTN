"""Standing check over the 2014 presidential runoff dataset.

Reads only the published files -- the bureau table, the delegation table and
the INS list -- and exits non-zero on a violation. Like the seven audits
beside it, it exists so the claim stays checkable after the fact rather than
resting on one build. It never opens `.cache/isie2019`, so it still runs after
the cache is gone, which it will be: the container is ephemeral and the source
tree is reachable only through the Wayback Machine.

Two invariants here are load-bearing rather than cosmetic.

The **bijection**: each of the 264 official delegations is claimed by exactly
one ISIE workbook and no workbook claims two. The crosswalk resolves 91 of 264
names by fuzzy match and 8 by elimination, and the way a fuzzy matcher fails is
always the same -- it pairs two names that merely look alike, leaving one
delegation claimed twice and another unclaimed. That shows up here and nowhere
else.

The **rollup**: the delegation table must reproduce by summing the bureau
table. The build derives both in one pass, so this catches a table that was
edited, truncated or regenerated against a different cache. It is also the
check that caught the defect this dataset shipped with at first: a duplicate
workbook resolved to a zero-byte download, which cost a whole delegation and
its 23 bureaux while reporting only an unreadable file.

Usage: python3 tools/audit_presidential_2014_bureau.py [--verbose]
"""

import argparse
import collections
import csv
import os
import sys

BUREAU = "data/presidential_2014_bureau.csv"
CONSTITUENCY = "data/presidential_2014_constituency.csv"
DELEG = "data/presidential_2014_delegation.csv"
INS = "data/delegations_ins.csv"

BUREAU_ROWS = 10567
DELEG_IN = 264
DELEG_OUT = 5
INS_ROWS = 264
SCOPES = {"tunisie", "etranger"}
# The declared 2014 runoff result, for the end-to-end reconciliation.
DECLARED_TOTAL = 3110042

# The workbook tree's 27 in-country and 5 foreign path labels against the 33
# Arabic constituency names the published PV table uses.
CONSTITUENCY_LABEL = {
    "Ariana": "أريانة", "Beja": "باجة", "BenArous": "بن عروس",
    "Bizerte": "بنزرت", "Gabes": "قابس", "Gafsa": "قفصة",
    "Jendouba": "جندوبة", "Kairouan": "القيروان", "Kasserine": "القصرين",
    "Kebili": "قبلي", "LeKef": "الكاف", "Mahdia": "المهدية",
    "Mannouba": "منوبة", "Medenine": "مدنين", "Monastir": "المنستير",
    "Nabeul1": "نابل 1", "Nabeul2": "نابل 2", "Sfax1": "صفاقس 1",
    "Sfax2": "صفاقس 2", "Sidi Bouzid": "سيدي بوزيد", "Siliana": "سليانة",
    "Sousse": "سوسة", "Tataouine": "تطاوين", "Tozeur": "توزر",
    "Tunis1": "تونس 1", "Tunis2": "تونس 2", "Zaghouan": "زغوان",
    "Allemagne": "ألمانيا", "Italie": "إيطاليا", "France2": "فرنسا 2",
    "Pays Arabes et Restes du Monde": "الدول العربية وباقي دول العالم",
    "Amérique et Reste d'Europe": "القارة الأمريكية وبقية الدول الأوروبية",
}
# The two constituencies that do not agree to the vote, and why. Both are
# argued in the builder's docstring; here they are pinned so that a reparse
# which drifted anywhere else -- or by a different amount in these two --
# fails rather than passing inside a tolerance.
ABSENT = {"فرنسا 1": 36252}          # no workbook survives in the Wayback tree
DISAGREE = {"أريانة": (6, 0)}        # ISIE's bureau sheets against its own PV


def read(p):
    with open(p, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def num(s):
    return int(s) if s not in (None, "") else None


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    for p in (BUREAU, DELEG, INS, CONSTITUENCY):
        if not os.path.exists(p):
            sys.exit(f"missing {p}; run tools/build_presidential_2014_bureau.py --write")
    bur, dg, ins = read(BUREAU), read(DELEG), read(INS)

    fail = []

    def check(ok, msg):
        if ok:
            if args.verbose:
                print(f"  ok    {msg}")
        else:
            fail.append(msg)
            print(f"  FAIL  {msg}")

    print("the tables are the size they claim")
    check(len(bur) == BUREAU_ROWS,
          f"{len(bur)} bureau rows, expected {BUREAU_ROWS}")
    check(len(ins) == INS_ROWS, f"{len(ins)} INS rows, expected {INS_ROWS}")
    scopes = collections.Counter(r["scope"] for r in dg)
    check(not set(scopes) - SCOPES,
          f"unknown scope values: {sorted(set(scopes) - SCOPES)}")
    check(scopes["tunisie"] == DELEG_IN,
          f"{scopes['tunisie']} in-country delegations, expected {DELEG_IN}")
    check(scopes["etranger"] == DELEG_OUT,
          f"{scopes['etranger']} constituencies abroad, expected {DELEG_OUT}")

    print("bureau codes are unique 11-digit keys and the prefix is a delegation key")
    codes = [r["bureau_code"] for r in bur]
    dup = [c for c, n in collections.Counter(codes).items() if n > 1]
    check(not dup, f"{len(dup)} bureau codes appear twice, e.g. {dup[:5]}")
    bad = [c for c in codes if len(c) != 11 or not c.isdigit()]
    check(not bad, f"{len(bad)} bureau codes are not 11 digits, e.g. {bad[:5]}")
    off = [r["bureau_code"] for r in bur
           if r["delegation_key_2014"] != r["bureau_code"][:4]]
    check(not off, f"{len(off)} rows whose delegation_key_2014 is not the code's "
                   f"first four digits, e.g. {off[:5]}")
    # The claim that makes the key a key: within 2014 a prefix never spans two
    # delegations. (It does not survive into 2024, which is why the INS join
    # runs through names -- see the builder's docstring.)
    spread = collections.defaultdict(set)
    for r in bur:
        spread[r["delegation_key_2014"]].add(r["id_delegation"])
    split = {k: sorted(v) for k, v in spread.items() if len(v) > 1}
    check(not split, f"{len(split)} code prefixes span more than one delegation: "
                     f"{list(split.items())[:3]}")
    check(len(spread) == DELEG_IN,
          f"{len(spread)} distinct code prefixes, expected {DELEG_IN}")

    print("the vote arithmetic closes on every row of both tables")
    for name, rows in (("bureau", bur), ("delegation", dg)):
        bad_sum, bad_share, bad_margin, out_of_range = [], [], [], []
        for r in rows:
            key = r.get("bureau_code") or f"{r['governorate_isie']}/{r['delegation_isie']}"
            e, m, v = num(r["essebsi"]), num(r["marzouki"]), num(r["valid_votes"])
            if None in (e, m, v) or e < 0 or m < 0:
                bad_sum.append(key)
                continue
            if e + m != v:
                bad_sum.append(key)
                continue
            if not v:
                continue
            if abs(float(r["essebsi_share_pct"]) - round(100.0 * e / v, 2)) > 1e-9:
                bad_share.append(key)
            if abs(float(r["margin_pp"]) - round(100.0 * (e - m) / v, 2)) > 1e-9:
                bad_margin.append(key)
            if not 0 <= float(r["essebsi_share_pct"]) <= 100:
                out_of_range.append(key)
            if not -100 <= float(r["margin_pp"]) <= 100:
                out_of_range.append(key)
        check(not bad_sum, f"{len(bad_sum)} {name} rows where essebsi + marzouki != "
                           f"valid_votes, e.g. {bad_sum[:5]}")
        check(not bad_share, f"{len(bad_share)} {name} rows whose essebsi_share_pct "
                             f"does not reproduce, e.g. {bad_share[:5]}")
        check(not bad_margin, f"{len(bad_margin)} {name} rows whose margin_pp does "
                              f"not reproduce, e.g. {bad_margin[:5]}")
        check(not out_of_range, f"{len(out_of_range)} {name} rows with a share or "
                                f"margin out of range, e.g. {out_of_range[:5]}")

    print("the INS join is a bijection onto all 264 official delegations")
    by_id = {r["id_delegation"]: r for r in ins}
    inc = [r for r in dg if r["scope"] == "tunisie"]
    claimed = collections.Counter(r["id_delegation"] for r in inc)
    twice = [i for i, n in claimed.items() if n > 1]
    check(not twice, f"{len(twice)} delegations claimed by two workbooks: {twice[:5]}")
    unclaimed = sorted(set(by_id) - set(claimed))
    check(not unclaimed, f"{len(unclaimed)} official delegations unclaimed: "
                         f"{[by_id[i]['delegation_name'] for i in unclaimed[:5]]}")
    stray = sorted(set(claimed) - set(by_id))
    check(not stray, f"{len(stray)} id_delegation values absent from {INS}: {stray[:5]}")
    abroad = [r["delegation_isie"] for r in dg
              if r["scope"] == "etranger" and r["id_delegation"]]
    check(not abroad, f"{len(abroad)} out-of-country rows carry an INS code: {abroad}")

    print("the geography columns agree with the INS list, on both tables")
    for name, rows in (("bureau", bur), ("delegation", inc)):
        wrong = []
        for r in rows:
            rec = by_id.get(r["id_delegation"])
            if not rec or any(r[k] != rec[k] for k in
                              ("governorate_name", "delegation_name", "region_name")):
                wrong.append(r.get("bureau_code") or r["delegation_isie"])
        check(not wrong, f"{len(wrong)} {name} rows whose geography disagrees with "
                         f"{INS}, e.g. {wrong[:5]}")

    print("match_method is from the fixed vocabulary")
    def method_ok(s):
        if s in ("exact", "elimination"):
            return True
        if s.startswith("fuzzy:"):
            try:
                return 0.80 <= float(s[6:]) <= 1.0
            except ValueError:
                return False
        return False
    badm = sorted({r["match_method"] for r in inc if not method_ok(r["match_method"])})
    check(not badm, f"unknown match_method values: {badm[:5]}")
    check(not [r for r in dg if r["scope"] == "etranger" and r["match_method"]],
          "an out-of-country row carries a match_method")

    print("the delegation table reproduces by rolling up the bureau table")
    roll = collections.defaultdict(lambda: [0, 0, 0])
    for r in bur:
        a = roll[r["id_delegation"]]
        a[0] += int(r["essebsi"])
        a[1] += int(r["marzouki"])
        a[2] += 1
    mism = []
    for r in inc:
        a = roll.get(r["id_delegation"])
        if not a or [int(r["essebsi"]), int(r["marzouki"]), int(r["n_bureaux"])] != a:
            mism.append(f"{r['delegation_isie']} {a} vs "
                        f"[{r['essebsi']}, {r['marzouki']}, {r['n_bureaux']}]")
    check(not mism, f"{len(mism)} delegations whose rollup disagrees: {mism[:3]}")
    check(sum(int(r["n_bureaux"]) for r in inc) == len(bur),
          f"n_bureaux sums to {sum(int(r['n_bureaux']) for r in inc)}, "
          f"expected {len(bur)}")
    check(not [r for r in inc if int(r["n_bureaux"]) < 1],
          "an in-country delegation publishes no bureaux")
    check(not [r for r in dg if r["scope"] == "etranger" and int(r["n_bureaux"])],
          "an out-of-country row claims bureaux, which are in-country by construction")

    print("every constituency agrees to the vote with the published runoff PV")
    # The load-bearing end-to-end check. The reference was decoded from ISIE's
    # constituency-level PV in separate work and sums exactly to the declared
    # national result, so the two publications are independent. 31 of 33
    # constituencies must match to the single vote, and the other two must
    # differ by exactly the amounts argued in the builder's docstring.
    ref = collections.defaultdict(lambda: [0, 0])
    for r in read(CONSTITUENCY):
        if r["round"] == "r2":
            ref[r["centre"]][0 if "السبسي" in r["candidate"] else 1] = int(r["votes"])
    check(sum(sum(v) for v in ref.values()) == DECLARED_TOTAL,
          f"{CONSTITUENCY} no longer sums to the declared {DECLARED_TOTAL:,}, "
          f"so it cannot serve as the reference")
    labels = {r["governorate_isie"] for r in dg}
    check(not labels - set(CONSTITUENCY_LABEL),
          f"workbook labels with no constituency: {sorted(labels - set(CONSTITUENCY_LABEL))}")
    got = collections.defaultdict(lambda: [0, 0])
    for r in dg:
        ar = CONSTITUENCY_LABEL.get(r["governorate_isie"])
        if ar:
            got[ar][0] += int(r["essebsi"])
            got[ar][1] += int(r["marzouki"])
    check(sorted(set(ref) - set(got)) == sorted(ABSENT),
          f"the constituencies missing from the dataset are "
          f"{sorted(set(ref) - set(got))}, expected {sorted(ABSENT)}")
    for ar, votes in ABSENT.items():
        check(sum(ref.get(ar, [0, 0])) == votes,
              f"{ar} is published at {sum(ref.get(ar, [0, 0])):,} votes, "
              f"expected the {votes:,} the shortfall is accounted for by")
    off = {ar: (got[ar][0] - ref[ar][0], got[ar][1] - ref[ar][1])
           for ar in got if got[ar] != ref[ar]}
    check(off == DISAGREE,
          f"constituencies disagreeing with the published PV: {off}, "
          f"expected exactly {DISAGREE}")
    # Which makes the shortfall arithmetic, not an allowance.
    e = sum(int(r["essebsi"]) for r in dg)
    m = sum(int(r["marzouki"]) for r in dg)
    left = (DECLARED_TOTAL - e - m - sum(ABSENT.values())
            + sum(a + b for a, b in DISAGREE.values()))
    check(left == 0,
          f"{left:,} votes of the shortfall are unaccounted for; it should be "
          f"exactly France 1 less the Ariana overcount")

    print(f"\n{len(bur):,} bureaux in {DELEG_IN} delegations, {e + m:,} valid "
          f"votes; Essebsi {100.0 * e / (e + m):.2f}%; "
          f"{len(got) - len(off)} of {len(ref)} constituencies exact to the vote, "
          f"{len(ABSENT)} absent from the archive, {len(off)} disagreeing")

    if fail:
        print(f"\n{len(fail)} check(s) failed")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
