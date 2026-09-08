"""Bridge the PV datasets' Arabic delegation names to the INS Latin list.

The presidential PV dataset names every place in Arabic and carries no code but
`bureau_code`; `data/delegations_ins.csv` names the same delegations in French
with official INS codes. Nothing joined them, which is the open item recorded at
docs/DATASETS.md.

Three things make the join possible.

**`bureau_code` carries a delegation code after all.** Its first four digits are
ISIE's own (constituency, delegation) pair -- not INS codes, which is why
comparing them to `id_delegation` directly finds nothing. Over 9,448 stations
those four digits partition the delegations almost perfectly, so they serve as
an independent check on the folder-derived Arabic label, and they caught the one
place where that label is wrong.

**Qualifiers are translated, not transliterated.** `بنزرت الشمالية` is
`Bizerte Nord`. See tools/arabic_latin.py.

**Everything else matches on consonant skeletons.** Also arabic_latin.py.

Nothing here modifies `data/pv_presidential_2024.csv`.
"""

import argparse
import collections
import csv
import difflib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import re

from arabic_latin import (
    LAT_QUALIFIERS, QUALIFIERS, ar_norm, ar_skeleton, ar_words, lat_skeleton,
    lat_words, split_qualifier,
)

PV = "data/pv_presidential_2024.csv"
PC = "data/polling_centres_2022.csv"
INS = "data/delegations_ins.csv"
XW_OUT = "data/delegation_crosswalk.csv"
MAP_OUT = "data/pv_delegation_map.csv"
LOG = "data/verification/delegation_bridge.jsonl"

PV_ROWS = 9448

# The 24 governorates, paired by hand. This is the scope for every delegation
# match, so an error here would misdirect a whole governorate; it is checked in
# the audit by requiring all 24 on both sides to be used exactly once.
GOVERNORATES = {
    "أريانة": "Ariana", "بن عروس": "Ben Arous", "بنزرت": "Bizerte",
    "باجة": "Béja", "قابس": "Gabès", "قفصة": "Gafsa", "جندوبة": "Jendouba",
    "القيروان": "Kairouan", "القصرين": "Kasserine", "الكاف": "Kef",
    "قبلي": "Kébili", "المهدية": "Mahdia", "منوبة": "Mannouba",
    "مدنين": "Medenine", "المنستير": "Monastir", "نابل": "Nabeul",
    "صفاقس": "Sfax", "سيدي بوزيد": "Sidi Bouzid", "سليانة": "Siliana",
    "سوسة": "Sousse", "تطاوين": "Tataouine", "توزر": "Tozeur",
    "تونس": "Tunis", "زغوان": "Zaghouan",
}

# ISIE's folder tree nests two whole delegations inside a third. The raw path is
# `.../مدنين/جربة أجيم/بنقردان/...`, so every Ben Guerdane and Beni Khedech
# station is labelled `جربة أجيم` (Djerba Ajim), which is why that delegation
# carries 135 stations against Djerba Midoun's 55. ISIE's own bureau_code
# contradicts its own folder tree and separates them cleanly -- 2301, 2302 and
# 2303 -- and the `sector` column on those rows carries the real delegation
# name. Corrected by code, with the sector as corroboration.
ISIE_LABEL_FIX = {
    "2301": ("بنقردان", "sector column reads بنقردان on 69 of 70 rows"),
    "2302": ("بني خداش", "sector column reads بني خداش on all 40 rows"),
}

# Transliterations no skeleton can reach, decided individually. Keyed by
# (governorate, Arabic name).
DELEGATION_MANUAL = {
    ("Medenine", "جرجيس"): ("Zarzis", "ج renders as Z in the French form"),
    ("Tunis", "حلق الوادي"): (
        "La Goulette",
        "the French name is not a transliteration: حلق الوادي is 'throat of the "
        "river', La Goulette its French calque"),
}


def strip_governorate_suffix(label, gov_ar):
    """Drop a ` - <governorate>` disambiguator from a delegation label.

    `Ezzouhour` is a delegation of both Tunis and Kasserine, so ISIE writes
    `الزهور - تونس` and `الزهور - القصرين` to tell them apart. The suffix is not
    part of the name and drags the skeleton away from `Ezzouhour`.

    Deliberately narrow: it fires only when the trailing part is the row's own
    governorate. Two other dash-separated labels -- `الزاوية - القصيبة - الثريات`
    and `صيادة - لمطة - بوحجر` -- are genuinely multi-part place names that the
    INS list also hyphenates, and must survive untouched.
    """
    parts = [p.strip() for p in re.split(r"\s*[-–]\s*", label) if p.strip()]
    if len(parts) > 1 and ar_norm(parts[-1]) == ar_norm(gov_ar):
        return " - ".join(parts[:-1])
    return label

MATCH_MIN = 0.62          # set from the measured score distribution
MARGIN_MIN = 0.02         # a match must beat the runner-up by this much

# A match is corroborated when the French name of one of that delegation's own
# polling centres contains its Latin delegation name. This is an independent
# channel: `polling_centres_2022.csv` pairs Arabic `delegation` with French
# `centre_name_fr` row by row, and was built from a different source (ISIE's
# USSD directory) by a different pipeline. It can confirm but not refute --
# centres are often named after a school or a locality rather than the
# delegation -- so an uncorroborated match is not evidence of a wrong one.
CORROBORATE_MIN = 0.80


def corroboration(deleg_ar, deleg_lat, centre_names):
    """Best skeleton similarity between the Latin name and this delegation's
    French centre names, over windows of up to four consecutive words."""
    if not centre_names or not deleg_lat:
        return None
    skels = set()
    for n in centre_names:
        ws = lat_words(n)
        for i in range(len(ws)):
            for j in range(i + 1, min(i + 5, len(ws)) + 1):
                k = lat_skeleton(ws[i:j])
                if len(k) >= 2:
                    skels.add(k)
    stem, _ = split_qualifier(lat_words(deleg_lat), LAT_QUALIFIERS, False)
    target = lat_skeleton(stem)
    if not target or not skels:
        return None
    return max(difflib.SequenceMatcher(None, target, t).ratio() for t in skels)


def read(path):
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


class Log:
    def __init__(self, path):
        self.path, self.records = path, []

    def add(self, kind, **f):
        self.records.append(dict(kind=kind, **f))

    def counts(self):
        c = collections.Counter(r["kind"] for r in self.records)
        return dict(c)

    def write(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as fh:
            for r in self.records:
                fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")


def score(ar_name, lat_name):
    """Similarity of two names across scripts, or None if qualifiers disagree.

    A qualifier mismatch is fatal rather than merely costly: `Bizerte Nord` and
    `Bizerte Sud` differ by one translated word, and a matcher that trades that
    off against stem similarity will pick whichever of the pair happens to sort
    first. Two readings of the Arabic are tried, because الجديدة is `Nouvelle`
    in `المدينة الجديدة` but transliterates to `Djedeida` on its own.
    """
    lat_stem, lat_q = split_qualifier(lat_words(lat_name), LAT_QUALIFIERS, False)
    lat_skel = lat_skeleton(lat_stem)
    aw = ar_words(ar_name)
    best = None
    for use_lexicon in (True, False):
        if use_lexicon:
            ar_stem, ar_q = split_qualifier(aw, QUALIFIERS, True)
        else:
            ar_stem, ar_q = aw, set()
        if lat_q:
            if not (ar_q & lat_q):
                continue
        elif ar_q:
            continue
        a, b = ar_skeleton(ar_stem), lat_skel
        if not a and not b:
            s = 1.0
        elif not a or not b:
            s = 0.0
        else:
            s = difflib.SequenceMatcher(None, a, b).ratio()
        if best is None or s > best:
            best = s
    return best


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--review", action="store_true",
                    help="print every unit with its best and runner-up match")
    args = ap.parse_args()

    pv, ins = read(PV), read(INS)
    centres = collections.defaultdict(set)
    if os.path.exists(PC):
        for r in read(PC):
            d, f = ar_norm(r["delegation"].strip()), r["centre_name_fr"].strip()
            if d and f:
                centres[d].add(f)
    if len(pv) != PV_ROWS:
        sys.exit(f"refusing: {PV} has {len(pv)} rows, expected {PV_ROWS}")
    log = Log(LOG)

    gov_ar = {r["governorate"].strip() for r in pv}
    unknown = gov_ar - set(GOVERNORATES)
    if unknown:
        sys.exit(f"refusing: unmapped governorates {unknown}")

    # --- units, and the label corrections the codes justify -----------------
    for r in pv:
        r["_code"] = r["bureau_code"][:4]
        fix = ISIE_LABEL_FIX.get(r["_code"])
        published = r["delegation"].strip()
        if fix:
            r["_deleg"], r["_change"] = fix[0], "misfiled_by_isie"
        else:
            trimmed = strip_governorate_suffix(published, r["governorate"].strip())
            r["_deleg"] = trimmed
            r["_change"] = "disambiguator_trimmed" if trimmed != published else ""
        r["_gov"] = GOVERNORATES[r["governorate"].strip()]

    for code, (name, why) in ISIE_LABEL_FIX.items():
        n = sum(1 for r in pv if r["_code"] == code)
        log.add("isie_label_fix", isie_code=code, corrected_to=name, stations=n,
                evidence=why,
                note="ISIE's folder tree nested this delegation inside another; "
                     "its own bureau_code keeps them separate")

    units = collections.defaultdict(list)
    for r in pv:
        units[(r["_gov"], r["_deleg"])].append(r)

    # A unit's code is the majority prefix; anything else is a code typo, and
    # the label is trusted over the code for those rows.
    unit_code = {}
    for key, rows in units.items():
        counts = collections.Counter(r["_code"] for r in rows)
        code, n = counts.most_common(1)[0]
        unit_code[key] = code
        for other, m in counts.items():
            if other != code:
                log.add("bureau_code_typo", governorate=key[0], delegation=key[1],
                        majority_code=code, majority_stations=n,
                        odd_code=other, odd_stations=m,
                        bureau_codes=[r["bureau_code"] for r in rows
                                      if r["_code"] == other],
                        note="one or two stations carry a delegation code that "
                             "disagrees with the rest of their delegation; the "
                             "label is trusted and the station is not moved")

    # --- match each unit against the INS list, scoped by governorate --------
    by_gov = collections.defaultdict(list)
    for r in ins:
        by_gov[r["governorate_name"]].append(r)

    results, review = {}, []
    for (gov, deleg), rows in sorted(units.items()):
        manual = DELEGATION_MANUAL.get((gov, deleg))
        cands = by_gov[gov]
        scored = []
        for c in cands:
            s = score(deleg, c["delegation_name"])
            if s is not None:
                scored.append((s, c))
        scored.sort(key=lambda t: (-t[0], t[1]["delegation_name"]))
        best = scored[0] if scored else (0.0, None)
        second = scored[1] if len(scored) > 1 else (0.0, None)
        margin = best[0] - second[0]

        if manual:
            hit = next(c for c in cands if c["delegation_name"] == manual[0])
            results[(gov, deleg)] = (hit, "manual", 1.0, None)
            log.add("manual_match", governorate=gov, delegation_ar=deleg,
                    matched=manual[0], reason=manual[1])
        elif best[1] is not None and best[0] >= MATCH_MIN and margin >= MARGIN_MIN:
            results[(gov, deleg)] = (best[1], "skeleton", best[0], margin)
        else:
            results[(gov, deleg)] = (None, "no_ins_counterpart", best[0], margin)
        review.append((best[0], margin, gov, deleg, len(rows),
                       best[1]["delegation_name"] if best[1] else "",
                       second[1]["delegation_name"] if second[1] else ""))

    if args.review:
        review.sort()
        print(f"{'score':>6} {'margin':>7} {'gov':13} {'arabic':24} {'st':>4}  "
              f"{'best':22} runner-up")
        for s, m, g, d, n, b, sec in review:
            print(f"{s:6.3f} {m:+7.3f} {g:13} {d:24} {n:4d}  {b:22} {sec}")

    # --- reconcile both directions ------------------------------------------
    matched_ins = collections.Counter()
    for hit, method, _s, _m in results.values():
        if hit is not None:
            matched_ins[hit["id_delegation"]] += 1

    unmatched_pv = [k for k, v in results.items() if v[0] is None]
    unmatched_ins = [r for r in ins if matched_ins[r["id_delegation"]] == 0]
    contested = [(i, n) for i, n in matched_ins.items() if n > 1]

    for gov, deleg in sorted(unmatched_pv):
        log.add("no_ins_counterpart", governorate=gov, delegation_ar=deleg,
                stations=len(units[(gov, deleg)]),
                isie_code=unit_code[(gov, deleg)],
                note="named in ISIE's tree with no delegation of that name in "
                     "the 2024 INS list; left unmatched rather than forced onto "
                     "a neighbour")
    for r in unmatched_ins:
        log.add("ins_unmatched", governorate=r["governorate_name"],
                delegation_name=r["delegation_name"],
                id_delegation=r["id_delegation"],
                note="official delegation with no ISIE unit matched to it")
    for i, n in contested:
        nm = next(r["delegation_name"] for r in ins if r["id_delegation"] == i)
        log.add("ins_contested", id_delegation=i, delegation_name=nm, claimed_by=n,
                note="more than one ISIE unit matched this delegation")

    corrob = {}
    for (gov, deleg), (hit, _m, _s, _mg) in results.items():
        c = corroboration(deleg, hit["delegation_name"] if hit else "",
                          centres.get(ar_norm(deleg)))
        corrob[(gov, deleg)] = c
        if hit is not None and c is not None and c < CORROBORATE_MIN:
            log.add("uncorroborated", governorate=gov, delegation_ar=deleg,
                    delegation_name=hit["delegation_name"],
                    best_centre_similarity=round(c, 4),
                    note="no French centre name in this delegation echoes its "
                         "Latin name; the channel confirms but cannot refute, "
                         "since centres are named after schools and localities")

    print(f"ISIE delegation units: {len(units)}   INS delegations: {len(ins)}")
    methods = collections.Counter(v[1] for v in results.values())
    for k, v in methods.most_common():
        print(f"  {k:22} {v}")
    print(f"INS delegations matched: {sum(1 for r in ins if matched_ins[r['id_delegation']])}"
          f"/{len(ins)}")
    print(f"INS delegations claimed twice: {len(contested)}")
    stations_unmatched = sum(len(units[k]) for k in unmatched_pv)
    print(f"stations in unmatched units: {stations_unmatched}/{len(pv)} "
          f"({100 * stations_unmatched / len(pv):.1f}%)")
    ok = sum(1 for k, v in corrob.items()
             if results[k][0] is not None and v is not None and v >= CORROBORATE_MIN)
    nodata = sum(1 for k, v in corrob.items() if results[k][0] is not None and v is None)
    weak = sum(1 for k, v in corrob.items()
               if results[k][0] is not None and v is not None and v < CORROBORATE_MIN)
    print(f"corroborated by an independent French centre name: {ok}"
          f"  (no centre data {nodata}, uncorroborated {weak})")
    print("\nlog:", log.counts())

    if not args.write:
        print("\ndry run; pass --write to write the outputs")
        return

    xw = []
    for (gov, deleg), (hit, method, s, m) in sorted(results.items()):
        xw.append({
            "isie_code": unit_code[(gov, deleg)],
            "governorate_ar": next(a for a, l in GOVERNORATES.items() if l == gov),
            "delegation_ar": deleg,
            "governorate_name": gov,
            "delegation_name": hit["delegation_name"] if hit else "",
            "id_delegation": hit["id_delegation"] if hit else "",
            "id_delegation_salb_un": hit["id_delegation_salb_un"] if hit else "",
            "region_name": hit["region_name"] if hit else "",
            "lat": hit["lat"] if hit else "",
            "lon": hit["lon"] if hit else "",
            "stations": len(units[(gov, deleg)]),
            "match_method": method,
            "match_score": f"{s:.4f}",
            "match_margin": "" if m is None else f"{m:.4f}",
            "corroboration": ("" if corrob[(gov, deleg)] is None
                              else f"{corrob[(gov, deleg)]:.4f}"),
        })
    write_csv(XW_OUT, xw, list(xw[0].keys()))

    idx = {(r["governorate_name"], r["delegation_ar"]): r for r in xw}
    smap = []
    for r in pv:
        x = idx[(r["_gov"], r["_deleg"])]
        smap.append({
            "bureau_code": r["bureau_code"],
            "isie_code": r["_code"],
            "governorate_ar": r["governorate"].strip(),
            "delegation_ar_published": r["delegation"].strip(),
            "delegation_ar": r["_deleg"],
            "governorate_name": x["governorate_name"],
            "delegation_name": x["delegation_name"],
            "id_delegation": x["id_delegation"],
            # Two different things, kept apart: ISIE filed these stations under
            # the wrong delegation, against its own bureau_code, or ISIE was
            # right and only a ` - <governorate>` disambiguator was trimmed.
            "label_change": r["_change"],
        })
    write_csv(MAP_OUT, smap, list(smap[0].keys()))
    log.write()
    print(f"\nwrote {XW_OUT} ({len(xw)}), {MAP_OUT} ({len(smap)}), {LOG}")


def write_csv(path, rows, cols):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})
    os.replace(tmp, path)


if __name__ == "__main__":
    main()
