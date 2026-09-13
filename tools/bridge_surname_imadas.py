"""Resolve every imada in the 2024 voter registry to an admin4 boundary.

Why this exists
---------------
`data/voter_surnames_2024/surnames_by_imada.csv.gz` names its geography the way
the registry PDFs print it: a governorate, an *electoral constituency* and an
imada, all in Arabic and none of them carrying a code. The boundaries the maps
are drawn on (OCHA COD-AB admin4, 2,084 imadas) carry `adm4_pcode` and their own
Arabic spelling. Nothing joins the two but the names, so they are matched here,
once, and the result is written out as a crosswalk the map tool reads.

Scope, and why it is the governorate rather than the delegation
---------------------------------------------------------------
`tools/build_margins.py` matches imadas *inside a delegation*, which is the
tightest scope available there because every PV row already knows its delegation.
The registry does not: its `constituency` is the electoral constituency, and for
13 of Tunis's delegations that is a pair joined by a dash -- `التحرير - باردو`
is two delegations, not one. So the scope here is the governorate, and the
constituency is used as a *preference* rather than a filter: candidates sitting
in a delegation the constituency names are ranked first, and the wider
governorate is fallen back on only when that set offers nothing above the floor.

The floors are `build_margins`' own, for the same reason they were set there:
0.85 keeps `صاحب الجبل الجوفية` and `صاحب الجبل القبلية` -- northern and southern
Sahib El Jebel, two different imadas that score 0.812 against each other --
apart. The near-match tier at 0.75 admits a one-letter difference only where it
leads its runner-up by 0.15, which no genuinely ambiguous pair does.

What is written
---------------
`data/surname_imada_crosswalk.csv`, one row per registry imada, with the pcode,
the score, the method, and the registry's own voter total so a later reader can
see what each matched row carries. Every judgement call, every near match and
every gap goes to `data/verification/surname_imada_bridge.jsonl`.

Diaspora rows are not matched and not written: the ten consular constituencies
have no admin4 geometry, by construction. They are counted in the summary so the
gap is stated rather than silent.

Usage: python3 tools/bridge_surname_imadas.py
"""

import collections
import csv
import gzip
import io
import json
import os
import re
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from build_margins import (ARCHIVE, IMADA_MIN, IMADA_NEAR_MARGIN,
                           IMADA_NEAR_MIN, imada_key, imada_score)

IMADA_GZ = "data/voter_surnames_2024/surnames_by_imada.csv.gz"
OUT = "data/surname_imada_crosswalk.csv"
LOG = "data/verification/surname_imada_bridge.jsonl"

# A constituency may name two delegations across a dash; this is the score a
# part has to reach against `adm3_name1` for its delegation to be preferred.
DELEG_MIN = 0.85

# Two places where the registry and the boundary file use different Arabic words
# for the same thing. Each is applied as an *extra reading* of the registry name,
# never as a rewrite: the raw name is still scored, the alias only adds a second
# chance, and a match won on one is logged as `alias` so it can be audited.
#
# `جوفية` is the Tunisian dialectal "northern" and pairs with `قبلية`
# "southern"; the boundary file writes the standard `شمالية`. Nabeul's
# `صاحب الجبل الجوفية` has no counterpart under that spelling, and under the
# alias it lands on `صاحب الجبل الشمالية` at 1.00 while `صاحب الجبل القبلية` --
# the southern one, the unit this must not pick -- stays at 0.81.
#
# `غرة` is "the first of" before a month name, which the boundary file writes as
# the digit: `غرة جوان` is `01جوان`. Both governorates that use it, Tunis and
# Tozeur, hold exactly one such unit.
ALIASES = ((re.compile(r"جوفية"), "شمالية"),
           (re.compile(r"جوفي\b"), "شمالي"),
           (re.compile(r"^غرة\s+"), "1"))


def load_layer(name):
    with zipfile.ZipFile(ARCHIVE) as z, z.open(name) as fh:
        return json.load(io.TextIOWrapper(fh, encoding="utf-8"))["features"]


def registry_imadas():
    """The distinct (governorate, constituency, imada) of the domestic registry.

    Read straight off the imada table rather than the manifest, because the
    manifest's header fields are what the PDF printed and the table's are what
    the aggregation actually keyed on -- and the map is drawn from the table.
    """
    totals, order = {}, []
    with gzip.open(IMADA_GZ, "rt", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["is_diaspora"] == "1":
                continue
            key = (row["governorate"], row["constituency"], row["imada"])
            if key not in totals:
                totals[key] = int(row["imada_total_voters"])
                order.append(key)
    return order, totals


def constituency_parts(s):
    return [p.strip() for p in (s or "").split(" - ") if p.strip()]


def readings(imada_ar):
    """The registry name, plus any aliased rewriting of it.

    The raw name always comes first, so a name that matches as printed is never
    decided by an alias.
    """
    out = [imada_ar]
    for pattern, repl in ALIASES:
        alt = pattern.sub(repl, imada_ar)
        if alt != imada_ar and alt not in out:
            out.append(alt)
    return out


def best_score(imada_ar, adm4_name):
    """The best score any reading of the registry name reaches, and which one."""
    scored = [(imada_score(r, adm4_name or ""), r) for r in readings(imada_ar)]
    return max(scored, key=lambda t: t[0])


def main():
    feats = load_layer("tun_admin4.geojson")
    by_gov = collections.defaultdict(list)
    for f in feats:
        p = f["properties"]
        by_gov[imada_key(p["adm2_name1"])].append(p)

    keys, totals = registry_imadas()
    log, rows = [], []
    claimed = collections.defaultdict(list)
    matched = near = alias = gov_scope = 0

    for gov_ar, cons_ar, imada_ar in keys:
        cands = by_gov.get(imada_key(gov_ar), [])
        if not cands:
            log.append({"kind": "governorate_unmatched", "governorate": gov_ar,
                        "imada": imada_ar,
                        "note": "no admin4 unit under this governorate name"})
            continue

        # Candidates whose delegation is one the constituency names come first.
        parts = constituency_parts(cons_ar)
        preferred = [c for c in cands
                     if any(imada_score(part, c["adm3_name1"] or "") >= DELEG_MIN
                            for part in parts)]

        best = None
        for pool, scope in ((preferred, "constituency"), (cands, "governorate")):
            if not pool:
                continue
            ranked = sorted(((best_score(imada_ar, c["adm4_name1"]), c)
                             for c in pool), key=lambda t: -t[0][0])
            (score, reading), cand = ranked[0]
            runner = ranked[1][0][0] if len(ranked) > 1 else 0.0
            aliased = reading != imada_ar
            if score >= IMADA_MIN:
                best = (score, cand, scope, "alias" if aliased else "scoped")
                if aliased:
                    log.append({"kind": "imada_alias_match", "governorate": gov_ar,
                                "constituency": cons_ar, "imada": imada_ar,
                                "read_as": reading, "matched": cand["adm4_name1"],
                                "adm4_pcode": cand["adm4_pcode"],
                                "score": round(score, 4),
                                "runner_up": round(runner, 4), "scope": scope,
                                "note": "matched on an aliased reading of the "
                                        "registry name, not the name as printed"})
                break
            if score >= IMADA_NEAR_MIN and score - runner >= IMADA_NEAR_MARGIN:
                best = (score, cand, scope, "alias" if aliased else "near")
                log.append({"kind": "imada_near_match", "governorate": gov_ar,
                            "constituency": cons_ar, "imada": imada_ar,
                            "matched": cand["adm4_name1"],
                            "adm4_pcode": cand["adm4_pcode"],
                            "read_as": reading,
                            "score": round(score, 4),
                            "runner_up": round(runner, 4), "scope": scope,
                            "note": "below the 0.85 floor but leading its "
                                    "runner-up by more than 0.15"})
                break

        if best is None:
            ranked = sorted(((best_score(imada_ar, c["adm4_name1"]), c)
                             for c in cands), key=lambda t: -t[0][0])
            log.append({"kind": "imada_unmatched", "governorate": gov_ar,
                        "constituency": cons_ar, "imada": imada_ar,
                        "voters": totals[(gov_ar, cons_ar, imada_ar)],
                        "best_candidate": ranked[0][1]["adm4_name1"],
                        "best_score": round(ranked[0][0][0], 4),
                        "note": "left out of the crosswalk; its voters are "
                                "absent from the dot maps"})
            continue

        score, cand, scope, method = best
        matched += 1
        near += method == "near"
        alias += method == "alias"
        gov_scope += scope == "governorate"
        claimed[cand["adm4_pcode"]].append(imada_ar)
        rows.append({
            "governorate_ar": gov_ar,
            "constituency_ar": cons_ar,
            "imada_ar": imada_ar,
            "adm4_pcode": cand["adm4_pcode"],
            "adm4_name_ar": cand["adm4_name1"] or "",
            "adm4_name": cand["adm4_name"] or "",
            "adm3_pcode": cand["adm3_pcode"],
            "delegation_name": cand["adm3_name"] or "",
            "governorate_name": cand["adm2_name"] or "",
            "lat": f"{cand['center_lat']:.8f}",
            "lon": f"{cand['center_lon']:.8f}",
            "area_sqkm": f"{cand['area_sqkm']:.6f}",
            "registry_voters": totals[(gov_ar, cons_ar, imada_ar)],
            "match_score": f"{score:.4f}",
            "match_method": method,
            "match_scope": scope,
        })

    # Two registry imadas on one boundary unit is the failure signature worth
    # printing: it is legitimate where the registry splits a large imada into
    # numbered books, and a mistake where two unrelated names collapse.
    for pcode, names in sorted(claimed.items()):
        if len(names) > 1:
            log.append({"kind": "adm4_claimed_twice", "adm4_pcode": pcode,
                        "registry_imadas": names,
                        "note": "their voters are summed onto the one boundary unit"})

    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "w", encoding="utf-8") as fh:
        for r in log:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    with open(OUT, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    mapped_voters = sum(r["registry_voters"] for r in rows)
    all_voters = sum(totals.values())
    print(f"registry imadas (domestic): {len(keys)}")
    print(f"  matched   {matched} ({100*matched/len(keys):.2f}%)"
          f"  -- {near} on the near-match tier, {alias} on an alias, "
          f"{gov_scope} on governorate scope")
    print(f"  unmatched {len(keys) - matched}")
    print(f"  boundary units reached: {len(claimed)} of {len(feats)}")
    print(f"  voters carried: {mapped_voters:,} of {all_voters:,} "
          f"({100*mapped_voters/all_voters:.2f}%)")
    print(f"wrote {OUT} ({len(rows)}), {LOG} ({len(log)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
