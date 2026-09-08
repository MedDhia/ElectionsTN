"""Standing check over the Arabic-Latin delegation bridge.

Reads only the published files -- the crosswalk, the station map, the PV
dataset and the INS list -- and exits non-zero on a violation. Like
tools/audit_identities.py and tools/audit_locality_names.py, it exists so the
claim stays checkable after the fact rather than resting on one build.

The substantive invariant is the bijection: every one of the 264 official
delegations is claimed by exactly one ISIE unit, and no unit claims two. A
cross-script matcher fails by pairing two names that merely look alike, and
that failure always shows up here as a delegation claimed twice while another
goes unclaimed.
"""

import argparse
import collections
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from arabic_latin import ar_norm

PV = "data/pv_presidential_2024.csv"
INS = "data/delegations_ins.csv"
XW = "data/delegation_crosswalk.csv"
MAP = "data/pv_delegation_map.csv"

PV_ROWS = 9448
INS_ROWS = 264
UNITS = 279
METHODS = {"skeleton", "manual", "no_ins_counterpart"}


def read(p):
    with open(p, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    for p in (PV, INS, XW, MAP):
        if not os.path.exists(p):
            sys.exit(f"missing {p}; run tools/bridge_delegations.py --write")
    pv, ins, xw, smap = read(PV), read(INS), read(XW), read(MAP)

    fail = []

    def check(ok, msg):
        if ok:
            if args.verbose:
                print(f"  ok    {msg}")
        else:
            fail.append(msg)
            print(f"  FAIL  {msg}")

    print("row counts")
    check(len(pv) == PV_ROWS, f"{PV} has {len(pv)} rows, expected {PV_ROWS}")
    check(len(ins) == INS_ROWS, f"{INS} has {len(ins)} rows, expected {INS_ROWS}")
    check(len(xw) == UNITS, f"{XW} has {len(xw)} rows, expected {UNITS}")
    check(len(smap) == PV_ROWS, f"{MAP} has {len(smap)} rows, expected {PV_ROWS}")

    print("the bijection onto the official list")
    claims = collections.Counter(r["id_delegation"] for r in xw if r["id_delegation"])
    valid = {r["id_delegation"] for r in ins}
    twice = sorted(i for i, n in claims.items() if n > 1)
    check(not twice, f"delegations claimed by more than one ISIE unit: {twice}")
    unclaimed = sorted(valid - set(claims))
    check(not unclaimed, f"official delegations no ISIE unit claims: {unclaimed}")
    orphan = sorted(set(claims) - valid)
    check(not orphan, f"crosswalk cites id_delegation values not in the INS list: {orphan}")

    print("governorate scope")
    gov_of = {r["id_delegation"]: r["governorate_name"] for r in ins}
    crossed = [r["delegation_ar"] for r in xw if r["id_delegation"]
               and r["governorate_name"] != gov_of[r["id_delegation"]]]
    check(not crossed, f"{len(crossed)} units matched a delegation in another "
                       f"governorate: {crossed[:5]}")
    govs_xw = {r["governorate_name"] for r in xw}
    check(govs_xw == {r["governorate_name"] for r in ins},
          "the crosswalk's governorates do not match the INS list's")
    check(len({r["governorate_ar"] for r in xw}) == 24,
          f"{len({r['governorate_ar'] for r in xw})} distinct Arabic governorates, expected 24")

    print("methods and evidence")
    bad = sorted({r["match_method"] for r in xw} - METHODS)
    check(not bad, f"unknown match_method values: {bad}")
    silent = [r["delegation_ar"] for r in xw
              if r["id_delegation"] and not r["delegation_name"]]
    check(not silent, f"{len(silent)} units carry an id_delegation with no name")
    unmatched_filled = [r["delegation_ar"] for r in xw
                        if r["match_method"] == "no_ins_counterpart" and r["id_delegation"]]
    check(not unmatched_filled,
          f"{len(unmatched_filled)} units marked as having no counterpart yet carry one")

    print("the station map covers the dataset exactly")
    check({r["bureau_code"] for r in smap} == {r["bureau_code"] for r in pv},
          "the station map's bureau codes differ from the PV dataset's")
    check(len({r["bureau_code"] for r in smap}) == len(smap),
          "the station map repeats a bureau code")
    by_unit = {(r["governorate_name"], r["delegation_ar"]): r for r in xw}
    missing = [r["bureau_code"] for r in smap
               if (r["governorate_name"], r["delegation_ar"]) not in by_unit]
    check(not missing, f"{len(missing)} stations map to a unit absent from the "
                       f"crosswalk, e.g. {missing[:5]}")
    disagree = [r["bureau_code"] for r in smap
                if r["id_delegation"]
                != by_unit[(r["governorate_name"], r["delegation_ar"])]["id_delegation"]]
    check(not disagree, f"{len(disagree)} stations disagree with their unit's "
                        f"crosswalk row, e.g. {disagree[:5]}")

    print("station counts reconcile")
    counted = collections.Counter((r["governorate_name"], r["delegation_ar"])
                                  for r in smap)
    mism = [k for k, r in by_unit.items() if counted[k] != int(r["stations"])]
    check(not mism, f"{len(mism)} units whose station count disagrees with the map: {mism[:5]}")

    print("label changes are declared, classified, and only where they differ")
    CHANGES = {"", "misfiled_by_isie", "disambiguator_trimmed"}
    check(not sorted({r["label_change"] for r in smap} - CHANGES),
          f"unknown label_change values: "
          f"{sorted({r['label_change'] for r in smap} - CHANGES)}")
    wrong_flag = [r["bureau_code"] for r in smap
                  if (r["delegation_ar"] != r["delegation_ar_published"])
                  != bool(r["label_change"])]
    check(not wrong_flag, f"{len(wrong_flag)} stations whose label_change does not "
                          f"match the columns, e.g. {wrong_flag[:5]}")
    # A misfiling is asserted only where ISIE's own bureau_code contradicts its
    # folder tree, which is two delegations; trimming a disambiguator changes no
    # delegation, so it must never move a station between units.
    misfiled = {r["isie_code"] for r in smap if r["label_change"] == "misfiled_by_isie"}
    check(len(misfiled) == 2,
          f"misfiling asserted on {len(misfiled)} ISIE codes, expected exactly 2")
    bad_trim = [r["bureau_code"] for r in smap
                if r["label_change"] == "disambiguator_trimmed"
                and not r["delegation_ar_published"].startswith(r["delegation_ar"])]
    check(not bad_trim, f"{len(bad_trim)} trimmed labels are not a prefix of the "
                        f"published label, e.g. {bad_trim[:5]}")

    print("the Arabic side round-trips")
    pv_labels = {ar_norm(r["delegation"].strip()) for r in pv}
    map_labels = {ar_norm(r["delegation_ar_published"]) for r in smap}
    check(pv_labels == map_labels,
          "the map's published Arabic labels differ from the PV dataset's")

    matched = sum(1 for r in xw if r["id_delegation"])
    stations = sum(int(r["stations"]) for r in xw if r["id_delegation"])
    print(f"\n{matched}/{len(xw)} ISIE units resolved to all {len(ins)} official "
          f"delegations; {stations}/{len(pv)} stations "
          f"({100 * stations / len(pv):.1f}%) carry an official code")

    if fail:
        print(f"\n{len(fail)} check(s) failed")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
