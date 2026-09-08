"""Standing coherence check over the published locality datasets.

Mirrors tools/audit_identities.py: it reads only the published CSVs -- never the
sources, never the build tool's internals -- and exits non-zero on a violation.
The point is that the coherence claim stays checkable after the fact, instead of
resting on one build having been run once.

    python3 tools/audit_locality_names.py [--verbose]
"""

import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from latin_names import DELEGATION_PREFIX, SOURCE_CANON, fold

DELEG = "data/delegations_ins.csv"
LOCAL = "data/hist_localities.csv"
HIST_XW = "data/hist_unit_crosswalk.csv"

DELEG_ROWS = 264
LOCAL_ROWS = 1276

HIST_COLS = ["caidat_1926", "caidat_1931", "controle_civil_1931", "delegation_1956"]

METHODS = {
    "name_and_centroid", "name_over_centroid", "centroid",
    "centroid_name_rejected", "hist_unit_delegation", "hist_unit_governorate",
    "name_only", "name_fuzzy", "unresolved",
}

XW_METHODS = {"exact", "exact_ambiguous", "manual", "fuzzy",
              "no_modern_equivalent", "unmatched"}

# `Ezzouhour` is a delegation of both Tunis (1162) and Kasserine (4253). A fold
# collision here is the territory, not a defect, so it is named rather than
# tolerated silently: any *other* collision is a real problem.
KNOWN_HOMONYMS = {"ezzouhour"}


def read(path):
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    for path in (DELEG, LOCAL, HIST_XW):
        if not os.path.exists(path):
            sys.exit(f"missing {path}; run tools/build_geo_crosswalk.py --write")

    delegs, locals_, xw = read(DELEG), read(LOCAL), read(HIST_XW)
    fail = []

    def check(ok, msg):
        if ok:
            if args.verbose:
                print(f"  ok    {msg}")
        else:
            fail.append(msg)
            print(f"  FAIL  {msg}")

    print("row counts")
    check(len(delegs) == DELEG_ROWS, f"delegations_ins.csv has {len(delegs)} rows, expected {DELEG_ROWS}")
    check(len(locals_) == LOCAL_ROWS, f"hist_localities.csv has {len(locals_)} rows, expected {LOCAL_ROWS}")

    print("whitespace")
    untrimmed = [(t, r_id, c) for t, rows, key in
                 (("delegations", delegs, "id"), ("localities", locals_, "id_2024"))
                 for r in rows for c, v in r.items()
                 if v is not None and v != v.strip()
                 for r_id in [r[key]]]
    check(not untrimmed, f"{len(untrimmed)} untrimmed cells, e.g. {untrimmed[:3]}")

    print("source labels")
    bad = sorted({r["sources_lat_lon"] for r in locals_
                  if r["sources_lat_lon"] and r["sources_lat_lon"] not in SOURCE_CANON.values()})
    check(not bad, f"sources_lat_lon outside the canonical set: {bad}")

    print("historical unit titles")
    pref = [(r["id_2024"], c, r[c]) for r in locals_ for c in HIST_COLS
            if r[c] and DELEGATION_PREFIX.match(r[c])]
    check(not pref, f"{len(pref)} cells still carry a 'Delegation de' title, e.g. {pref[:3]}")

    print("fold key is a key on the INS list")
    keys = {}
    for r in delegs:
        keys.setdefault(r["name_key"], []).append(r["delegation_name"])
    collide = {k: v for k, v in keys.items()
               if len({fold(x) for x in v}) == 1 and len(set(v)) > 1}
    check(not collide, f"distinct INS spellings colliding on one fold key: {collide}")
    homonyms = {k for k, v in keys.items() if len(v) > 1}
    check(homonyms <= KNOWN_HOMONYMS,
          f"undocumented delegation-name homonyms: {sorted(homonyms - KNOWN_HOMONYMS)}")

    print("name_key agrees with city_name")
    mismatched = [r["id_2024"] for r in locals_ if r["name_key"] != fold(r["city_name"])]
    check(not mismatched, f"{len(mismatched)} rows whose name_key does not fold from city_name, "
                          f"e.g. {mismatched[:5]}")

    print("referential integrity")
    valid_ids = {r["id_delegation"] for r in delegs}
    orphan = [r["id_2024"] for r in locals_
              if r["id_delegation"] and r["id_delegation"] not in valid_ids]
    check(not orphan, f"{len(orphan)} localities cite an id_delegation not in the INS list, "
                      f"e.g. {orphan[:5]}")
    xw_orphan = [r["historical_name"] for r in xw
                 if r["id_delegation"] and r["id_delegation"] not in valid_ids]
    check(not xw_orphan, f"{len(xw_orphan)} crosswalk rows cite an unknown id_delegation: {xw_orphan[:5]}")

    print("method vocabularies")
    bad_m = sorted({r["match_method"] for r in locals_} - METHODS)
    check(not bad_m, f"unknown match_method values: {bad_m}")
    bad_x = sorted({r["method"] for r in xw} - XW_METHODS)
    check(not bad_x, f"unknown crosswalk method values: {bad_x}")

    print("resolution carries its evidence")
    # A row resolved to a delegation must name it, and a row resolved by
    # coordinates must publish the distance that justified it -- otherwise the
    # assignment is an assertion with nothing behind it.
    silent = [r["id_2024"] for r in locals_
              if r["id_delegation"] and not r["delegation_name"]]
    check(not silent, f"{len(silent)} rows carry an id_delegation with no delegation_name")
    no_dist = [r["id_2024"] for r in locals_
               if r["match_method"] in ("centroid", "centroid_name_rejected")
               and not r["match_km"]]
    check(not no_dist, f"{len(no_dist)} centroid-resolved rows publish no match_km")
    unresolved_but_filled = [r["id_2024"] for r in locals_
                             if r["match_method"] == "unresolved" and r["id_delegation"]]
    check(not unresolved_but_filled,
          f"{len(unresolved_but_filled)} rows marked unresolved yet carry a delegation")

    print("governorate agrees with the delegation it names")
    gov_of = {r["id_delegation"]: r["governorate_name"] for r in delegs}
    wrong_gov = [r["id_2024"] for r in locals_ if r["id_delegation"]
                 and r["governorate_name"] != gov_of[r["id_delegation"]]]
    check(not wrong_gov, f"{len(wrong_gov)} rows whose governorate contradicts their delegation, "
                         f"e.g. {wrong_gov[:5]}")

    print("every historical unit name is accounted for")
    xw_keys = {r["name_key"] for r in xw}
    missing = sorted({fold(r[c]) for r in locals_ for c in HIST_COLS if r[c].strip()} - xw_keys)
    check(not missing, f"{len(missing)} historical unit names absent from the crosswalk: {missing[:5]}")
    undecided = [r["historical_name"] for r in xw if r["method"] == "unmatched"]
    check(not undecided, f"{len(undecided)} crosswalk rows left undecided: {undecided[:5]}")

    resolved = sum(1 for r in locals_ if r["match_method"] != "unresolved")
    print(f"\n{resolved}/{len(locals_)} localities resolved "
          f"({100 * resolved / len(locals_):.1f}%); "
          f"{len(xw)} historical unit names crosswalked")

    if fail:
        print(f"\n{len(fail)} check(s) failed")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
