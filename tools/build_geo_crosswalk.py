"""Ingest the INS delegation list and the historical locality file, make their
names coherent, and resolve every locality to a modern delegation.

Why this exists
---------------
The two source files share no join key. `id_2024` in the locality file looks
like a 2024 delegation code but is a row index running 1-1278 (only 28 of 1,276
values happen to equal an `id_delegation`); `id_geonames` is a local sequence,
not a GeoNames id; `id_census` keys the source census table. So a locality can
only be tied to its delegation by name or by coordinates -- which is why the
naming has to be coherent first.

What it does, and does not do
-----------------------------
Neither file's house style is rewritten to the other's. The locality file
hyphenates (`Menzel-Bourguiba`), the INS list uses spaces; both keep their own
spellings and gain a folded `name_key` that compares equal across them.

`city_name_sources` is never modified. It is a verbatim quotation from a census
or gazetteer -- 427 rows already differ from `city_name` precisely because the
author canonicalised one field and left the other as printed.

No row is ever deleted. Where two rows are one place spelled two ways, the
spelling is unified so both resolve together; the rows stay, because they are
distinct source observations (one `educ_*`, one `pop_tun_*`).

Every change and every judgement call is written to
data/verification/locality_names.jsonl.
"""

import argparse
import csv
import difflib
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from latin_names import (
    article_variant,
    canonical_source,
    fold,
    strip_delegation_prefix,
    vowel_skeleton,
)

DELEG_SRC = "data/sources/list_delegations_code_ins.csv"
LOCAL_SRC = "data/sources/db_hist_geonames_tunisia.csv"
DELEG_OUT = "data/delegations_ins.csv"
LOCAL_OUT = "data/hist_localities.csv"
HIST_XW_OUT = "data/hist_unit_crosswalk.csv"
LOG = "data/verification/locality_names.jsonl"

DELEG_ROWS = 264
LOCAL_ROWS = 1276

# Merges are gated on proximity as well as on the spelling relationship. The
# candidate generator (two co-located rows with different names) has known false
# positives: the six `(Commune de Tozeur)` rows and the ten
# `(Cercle de Ben-Gardane)` rows all carry a single parent-unit centroid -- that
# is what geo_precision 2 and 3 encode -- and are genuinely distinct localities.
MERGE_KM = 0.2
CANDIDATE_KM = 1.0

# A spelling absent from the INS list but this close to it still counts as
# official-vocabulary evidence. `Degache` and `Deguach` sit 0.86 km apart and are
# one place, but INS spells it `Degach`, so neither folds onto the official form;
# they score 0.92 and 0.86 against it. One place, spelled three ways across two
# files.
NEAR_INS_MIN = 0.85

# Only used for the 105 rows that carry no coordinates, where a name is the only
# evidence there is. Strict, because a village name fuzzy-matched against a
# delegation vocabulary is a coin flip below this.
FUZZY_MIN = 0.92

# An exact name match outranks the nearest centroid -- but only while the named
# delegation is somewhere near the locality, because Tunisian toponyms repeat.
# `El-Ksar` ("the castle") folds onto the Gafsa delegation `El Ksar` while
# sitting near Nebeur in Kef, 219 km away; kept on name alone it would have been
# filed in the wrong governorate. Measured over the 111 localities whose name is
# a delegation name, 110 sit within 19.0 km of that delegation's centroid (p50
# 0.4, p90 4.7, p95 7.4) and El-Ksar alone sits at 218.9. The bound is set at
# twice the observed legitimate maximum: it rejects the one coincidence and
# accepts every real match with room to spare.
NAME_TRUST_KM = 40.0

# The historical unit vocabulary is 70 distinct names, so every one was decided
# by hand rather than by threshold -- and it had to be. A 0.70 cutoff gets 13
# right and 7 badly wrong: `Hammama` (a tribal confederation of the Gafsa
# steppe) scores 0.80 against `Hammamet`, a Nabeul beach town; `Nefzaoua` (the
# Kebili oases) scores 0.77 against `Nefza`, a delegation at the opposite end of
# the country; `Djerid` and `Djerba` both score 0.71 against `Djerissa` in Kef.
# 0.85 is where this vocabulary happens to be clean -- all 12 matches above it
# are correct -- and everything below is listed explicitly below or left
# unmatched.
HIST_FUZZY_MIN = 0.85

# Historical names whose modern counterpart exists but cannot be reached by
# spelling, because the place was renamed or the unit's title differs.
HIST_UNIT_MANUAL = {
    "souk el arba": ("delegation", "Jendouba", "renamed Jendouba after independence"),
    "souk el khemis": ("delegation", "Bou Salem", "renamed Bou Salem after independence"),
    "le kef": ("governorate", "Kef", "same name; the INS list drops the article"),
    "fahs": ("delegation", "El Fahs", "same name; the INS list carries the article"),
    "djemmal": ("delegation", "Jammel", "transliteration; INS spells it Jammel"),
    "sidi amor bou hadjela": ("delegation", "Bouhajla",
                              "historic name of the Bouhajla area, Kairouan"),
    "cercle militaire de tatahouine": ("governorate", "Tataouine",
                                       "colonial military circle over what is now Tataouine"),
    "tunis ville": ("governorate", "Tunis", "colonial subdivision of Tunis"),
    "tunis banlieue": ("governorate", "Tunis", "colonial subdivision of Tunis"),
    "djerba": ("governorate", "Medenine", "island, now three delegations of Medenine"),
    "djerid": ("governorate", "Tozeur", "oasis region, now Tozeur governorate"),
    "nefzaoua": ("governorate", "Kebili", "oasis region, now Kebili governorate"),
}

# Historical units with no modern namesake by design. Tribal caidats, colonial
# categories, and places since renamed. Reported, never forced onto a match.
# Names with no single modern counterpart at all. Tribal caidats covered
# populations rather than territories, and the colonial catch-all categories
# spanned several of today's governorates. Forcing these onto a match would be
# the one way to corrupt the file, so they are marked and left alone.
NO_MODERN_EQUIVALENT = {
    "aradh": "tribal caidat (Arad, Gabes region)",
    "djelass": "tribal caidat",
    "fraichiches": "tribal caidat (Kasserine steppe)",
    "hammama": "tribal confederation (Gafsa steppe); NOT Hammamet",
    "madjeur": "tribal caidat (Medjerda valley)",
    "ouerghemma": "tribal confederation spanning Medenine and Tataouine",
    "oulad aoun": "tribal caidat",
    "oulad ayar": "tribal caidat",
    "territoires du sud": "colonial military territory spanning several governorates",
    "medenine ben gardane zarzis": "one cell naming three units; not a single unit",
}

HIST_COLS = ["caidat_1926", "caidat_1931", "controle_civil_1931", "delegation_1956"]


def km(lat1, lon1, lat2, lon2):
    """Equirectangular distance. Adequate at these scales and dependency-free."""
    return 111.0 * math.hypot(lat1 - lat2, (lon1 - lon2) * math.cos(math.radians(lat1)))


def as_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def read_semicolon(path):
    with open(path, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh, delimiter=";"))
    return rows


class Log:
    def __init__(self, path):
        self.path = path
        self.records = []

    def add(self, kind, **fields):
        self.records.append(dict(kind=kind, **fields))

    def counts(self):
        out = {}
        for r in self.records:
            out[r["kind"]] = out.get(r["kind"], 0) + 1
        return out

    def write(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as fh:
            for r in self.records:
                fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")


def hygiene(delegs, locals_, log):
    """Trim every cell, canonicalise the source labels, drop the 1956 title."""
    for rows, table, key in ((delegs, "delegations", "id"), (locals_, "localities", "id_2024")):
        for r in rows:
            for col, val in list(r.items()):
                if val is None:
                    continue
                trimmed = val.strip()
                if trimmed != val:
                    log.add("trim", table=table, row=r[key], column=col,
                            before=val, after=trimmed)
                    r[col] = trimmed

    for r in locals_:
        before = r["sources_lat_lon"]
        after = canonical_source(before)
        if after != before:
            log.add("source_label", table="localities", row=r["id_2024"],
                    column="sources_lat_lon", before=before, after=after)
            r["sources_lat_lon"] = after

        before = r["delegation_1956"]
        after = strip_delegation_prefix(before)
        if after != before:
            log.add("strip_prefix", table="localities", row=r["id_2024"],
                    column="delegation_1956", before=before, after=after)
            r["delegation_1956"] = after

    # One cell names three units at once; it cannot be a single value. Recorded
    # once with the rows it affects rather than once per row.
    composite = {}
    for r in locals_:
        v = r["controle_civil_1931"]
        if "," in v:
            composite.setdefault(v, []).append(r["id_2024"])
    for v, rows in sorted(composite.items()):
        log.add("composite_cell", table="localities", column="controle_civil_1931",
                value=v, rows=rows, row_count=len(rows),
                note="names several units in one cell; left as-is for the author to split")


# Source rows that are residual categories rather than places. `city_name` is
# rightly empty for these, so they are not counted as missing names.
# Source rows that are residual categories rather than places. `city_name` is
# rightly empty for these, so they are not counted as missing names.
RESIDUAL_MARKERS = (
    "non erige", "non denomme", "non denome", "centres non", "territoires non",
    "proprietes isolees", "autres centres", "route de", "controle de",
    "region de", "ville europeenne",
)


def is_residual(src):
    """True when a source cell is a category or a list, not one place name."""
    f = fold(src)
    if any(m in f for m in RESIDUAL_MARKERS):
        return True
    # `Sidi-Ahmed-Salah, Ain-Kerma, Oued-Souane, ...` and
    # `Cebala-du-Mornag, Sidi Saad et Chela` name several places at once.
    return src.count(",") >= 2 or ("," in src and " et " in f)


def classify_missing(locals_, log):
    """Classify the empty `city_name` rows, and fill the ones that are real.

    Two different things share an empty cell. Rows 1201-1278 were appended with
    only `city_name_sources` filled, and there the source name is already the
    current name (`Bizerte-Sud`, `Ghar-El-Melah`, `Remada`) -- leaving those
    nameless would leave 50-odd localities unresolvable by name for no reason.
    The rest are residual source categories (`Territoires non eriges en
    communes`, `Centres non denommes en 1921`) where an empty `city_name` is
    the correct value and inventing one would be a fabrication.

    Every fill is logged, because copying the source name into the author's
    canonical column is a judgement about their data, not a mechanical fix.
    """
    residual = filled = 0
    for r in locals_:
        if r["city_name"].strip():
            continue
        src = r["city_name_sources"].strip()
        if not src or is_residual(src):
            log.add("empty_city_name", row=r["id_2024"], city_name_sources=src,
                    verdict="residual_category",
                    note="source cell is a category or a list of places; "
                         "city_name left empty")
            residual += 1
        else:
            log.add("city_name_filled", row=r["id_2024"], before="", after=src,
                    note="row carried only the source name, and that name is "
                         "already the current one")
            r["city_name"] = src
            filled += 1
    return residual, filled


def merge_spellings(locals_, ins_keys, log):
    """Unify `city_name` where two rows are one place spelled two ways.

    Two classes, both conservative:

    `fold_identical` -- the names already fold to the same key (`Chaal`/`Chaâl`),
    so they differ only in accent or hyphenation. No distance test is needed:
    they are the same name.

    `coordinate_confirmed` -- the names fold differently but the rows sit within
    MERGE_KM and the spellings stand in a recognised relationship: one is the
    other plus a leading article, or they share a consonant skeleton. Anything
    else, including a pair that differs by an added qualifier
    (`Tabarka`/`Ile de Tabarka`), is reported and left alone.
    """
    by_key = {}
    for r in locals_:
        v = r["city_name"].strip()
        if v:
            by_key.setdefault(fold(v), []).append(r)

    freq = {}
    for r in locals_:
        v = r["city_name"].strip()
        if v:
            freq[v] = freq.get(v, 0) + 1

    ins_vocab = sorted(ins_keys)

    def ins_closeness(name):
        """How close a spelling is to the official delegation vocabulary."""
        m = difflib.get_close_matches(fold(name), ins_vocab, n=1, cutoff=0.0)
        return difflib.SequenceMatcher(None, fold(name), m[0]).ratio() if m else 0.0

    def preferred(spellings):
        """Pick the spelling to keep, and say which rule chose it."""
        matching = sorted(s for s in spellings if fold(s) in ins_keys)
        if matching:
            return matching[0], "matches the INS delegation list"
        scored = sorted(spellings,
                        key=lambda s: (-ins_closeness(s), -freq.get(s, 0), -len(s), s))
        if ins_closeness(scored[0]) >= NEAR_INS_MIN:
            return scored[0], "closest spelling to the INS delegation list"
        best = sorted(spellings, key=lambda s: (-freq.get(s, 0), -len(s), s))[0]
        return best, "most frequent spelling in the file (ties by length)"

    merges = 0
    unrelated = 0

    # Class 1: same fold key, different raw spelling.
    for key, rows in by_key.items():
        spellings = {r["city_name"].strip() for r in rows}
        if len(spellings) < 2:
            continue
        keep, rule = preferred(spellings)
        for r in rows:
            was = r["city_name"].strip()
            if was != keep:
                log.add("merge_spelling", klass="fold_identical", row=r["id_2024"],
                        before=was, after=keep, rule=rule,
                        id_census=r["id_census"], distance_km=None,
                        note="one toponym rendered two ways (accent or "
                             "hyphenation only); this normalises the spelling "
                             "and asserts nothing about whether the rows are "
                             "the same place -- two places can share a name, "
                             "and Chaal and Ouled Sidi-Tlil each do")
                r["city_name"] = keep
                merges += 1

    # Class 2: different fold keys, co-located.
    pts = [r for r in locals_ if r["city_name"].strip()
           and as_float(r["lat"]) is not None and as_float(r["lon"]) is not None]
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            a, b = pts[i], pts[j]
            na, nb = a["city_name"].strip(), b["city_name"].strip()
            fa, fb = fold(na), fold(nb)
            if fa == fb:
                continue
            d = km(as_float(a["lat"]), as_float(a["lon"]),
                   as_float(b["lat"]), as_float(b["lon"]))
            if d >= CANDIDATE_KM:
                continue
            article = article_variant(fa, fb)
            skeleton = vowel_skeleton(na) == vowel_skeleton(nb)
            related = article or skeleton
            # Proximity under MERGE_KM is the ordinary evidence. An exact match
            # to the official delegation vocabulary is independent evidence of
            # the correct spelling, and earns the wider radius: `Maareth` sits
            # 0.37 km from `Mareth`, which is a delegation of Gabes.
            official = (fa in ins_keys or fb in ins_keys
                        or max(ins_closeness(na), ins_closeness(nb)) >= NEAR_INS_MIN)
            if related and (d <= MERGE_KM or official):
                keep, rule = preferred({na, nb})
                reason = "leading article only" if article else "vowel variation only"
                for r in (a, b):
                    was = r["city_name"].strip()
                    if was != keep:
                        log.add("merge_spelling", klass="coordinate_confirmed",
                                row=r["id_2024"], before=was, after=keep,
                                rule=rule, reason=reason,
                                distance_km=round(d, 3),
                                id_census=r["id_census"],
                                paired_with=(b if r is a else a)["id_2024"],
                                paired_id_census=(b if r is a else a)["id_census"])
                        r["city_name"] = keep
                        merges += 1
            elif related:
                log.add("variant_candidate_rejected", row_a=a["id_2024"],
                        row_b=b["id_2024"], name_a=na, name_b=nb,
                        distance_km=round(d, 3),
                        article_variant=article, vowel_variant=skeleton,
                        note="looks like a spelling variant but is too far apart "
                             "and neither spelling is in the INS list")
            else:
                unrelated += 1
    if unrelated:
        # The candidate generator is proximity alone, and most co-located pairs
        # are genuinely distinct localities sharing a parent-unit centroid --
        # the six `(Commune de Tozeur)` rows, the ten `(Cercle de Ben-Gardane)`
        # rows. Counted rather than listed, so the log stays readable.
        log.add("colocated_distinct_pairs", count=unrelated,
                radius_km=CANDIDATE_KM,
                note="co-located rows with unrelated names; not variants. Mostly "
                     "localities carrying a shared parent-unit centroid, which is "
                     "what geo_precision 2 and 3 encode")
    return merges


def report_duplicate_rows(locals_, log):
    """Rows that may be one locality recorded twice. Reported, never deleted."""
    by_name = {}
    for r in locals_:
        v = r["city_name"].strip()
        if v:
            by_name.setdefault(fold(v), []).append(r)
    n = 0
    for key, rows in by_name.items():
        if len(rows) < 2:
            continue
        for i in range(len(rows)):
            for j in range(i + 1, len(rows)):
                a, b = rows[i], rows[j]
                la, lo = as_float(a["lat"]), as_float(a["lon"])
                lb, lob = as_float(b["lat"]), as_float(b["lon"])
                d = None if None in (la, lo, lb, lob) else km(la, lo, lb, lob)
                if d is not None and d >= 5.0:
                    continue  # same name, far apart: different places
                units_a = tuple(a[c] for c in HIST_COLS)
                units_b = tuple(b[c] for c in HIST_COLS)
                # A shared name is not a shared place. Coordinates settle it
                # where both rows have them; otherwise the historical units do,
                # because a locality recorded twice sits in the same caidat
                # while two namesakes generally do not.
                if d is not None:
                    verdict = "same_place_two_sources" if d < 1.0 else "distinct_places_same_name"
                    basis = "coordinates"
                elif any(x and y and x != y for x, y in zip(units_a, units_b)):
                    verdict, basis = "distinct_places_same_name", "differing historical units"
                else:
                    verdict, basis = "same_place_two_sources", "no coordinates; historical units agree"
                log.add("duplicate_row_candidate", name=a["city_name"].strip(),
                        row_a=a["id_2024"], row_b=b["id_2024"],
                        id_census_a=a["id_census"], id_census_b=b["id_census"],
                        source_a=a["city_name_sources"], source_b=b["city_name_sources"],
                        distance_km=None if d is None else round(d, 3),
                        units_a=list(units_a), units_b=list(units_b),
                        verdict=verdict, basis=basis,
                        note="two rows share a name. Reported, never merged: a "
                             "row is a source observation, so deleting one "
                             "would lose a census record")
                n += 1
    return n


def build_hist_unit_crosswalk(locals_, delegs, log):
    """Map every distinct historical unit name to a modern unit, or to nothing.

    Four columns name units that no longer exist: caidats of 1926 and 1931,
    contoles civils of 1931, and the delegations of 1956. Between them they use
    70 distinct names over 2,612 cells -- small enough that each one is decided
    explicitly, which matters because the wrong ones are wrong by hundreds of
    kilometres rather than by a letter.

    Resolution order: exact fold match, then the hand-written table, then fuzzy
    match above HIST_FUZZY_MIN, then unmatched.
    """
    gov = {}
    for r in delegs:
        gov.setdefault(fold(r["governorate_name"]), r["governorate_name"])
    dele = {}
    for r in delegs:
        dele.setdefault(fold(r["delegation_name"]), []).append(r)
    vocab = sorted(set(gov) | set(dele))

    seen = {}
    for r in locals_:
        for col in HIST_COLS:
            v = r[col].strip()
            if v:
                e = seen.setdefault(v, {"cells": 0, "columns": set()})
                e["cells"] += 1
                e["columns"].add(col)

    rows = []
    for name in sorted(seen):
        key = fold(name)
        level = modern = note = method = ""
        score = None

        if key in gov:
            level, modern, method, score = "governorate", gov[key], "exact", 1.0
        elif key in dele and len(dele[key]) == 1:
            level, modern, method, score = "delegation", dele[key][0]["delegation_name"], "exact", 1.0
        elif key in dele:
            level, modern, method, score = "delegation", dele[key][0]["delegation_name"], "exact_ambiguous", 1.0
            note = "name is a delegation in more than one governorate"
        elif key in HIST_UNIT_MANUAL:
            level, modern, note = HIST_UNIT_MANUAL[key]
            method, score = "manual", 1.0
        elif key in NO_MODERN_EQUIVALENT:
            method, note = "no_modern_equivalent", NO_MODERN_EQUIVALENT[key]
        else:
            best = difflib.get_close_matches(key, vocab, n=1, cutoff=HIST_FUZZY_MIN)
            if best:
                score = round(difflib.SequenceMatcher(None, key, best[0]).ratio(), 4)
                if best[0] in gov:
                    level, modern = "governorate", gov[best[0]]
                else:
                    level, modern = "delegation", dele[best[0]][0]["delegation_name"]
                method, note = "fuzzy", "transliteration variant"
            else:
                method = "unmatched"
                note = "no modern counterpart found and none asserted by hand"
                log.add("historical_unit_unmatched", value=name,
                        columns=sorted(seen[name]["columns"]),
                        cells=seen[name]["cells"], note=note)

        gov_of = ""
        id_del = ""
        if level == "delegation" and modern:
            hit = dele[fold(modern)][0]
            gov_of, id_del = hit["governorate_name"], hit["id_delegation"]
        elif level == "governorate":
            gov_of = modern

        rows.append({
            "historical_name": name,
            "name_key": key,
            "columns": " ".join(sorted(seen[name]["columns"])),
            "cells": seen[name]["cells"],
            "modern_level": level,
            "modern_name": modern,
            "governorate_name": gov_of,
            "id_delegation": id_del,
            "method": method,
            "score": "" if score is None else f"{score:.4f}",
            "note": note,
        })
        log.add("historical_unit", value=name, method=method, modern_level=level,
                modern_name=modern, score=score, cells=seen[name]["cells"],
                note=note)
    return rows


def hist_unit_index(crosswalk):
    """Fold key -> the crosswalk row, for the resolver's fallback."""
    return {r["name_key"]: r for r in crosswalk if r["modern_name"]}


def resolve(locals_, delegs, hist_idx, log):
    """Tie each locality to a modern delegation, recording the evidence.

    An exact fold-key match to an official delegation name outranks the nearest
    centroid, because the centroid is only a point: a locality near a boundary
    is routinely closer to a neighbour's centroid than to its own. Where the two
    disagree, the disagreement is logged with both distances rather than
    silently resolved.
    """
    by_key = {}
    for r in delegs:
        by_key.setdefault(fold(r["delegation_name"]), []).append(r)
    vocab = sorted(by_key)
    centroids = [(r, as_float(r["lat"]), as_float(r["lon"])) for r in delegs]

    def nearest(la, lo):
        ranked = sorted(((km(la, lo, a, b), r) for r, a, b in centroids),
                        key=lambda t: t[0])
        return ranked[0], ranked[1]

    stats = {}
    for r in locals_:
        name = r["city_name"].strip()
        key = fold(name) if name else ""
        r["name_key"] = key
        la, lo = as_float(r["lat"]), as_float(r["lon"])

        hit = by_key.get(key, [])
        ambiguous = len(hit) > 1
        if ambiguous:
            log.add("name_ambiguous", row=r["id_2024"], name=name,
                    candidates=[d["id_delegation"] for d in hit],
                    note="name is a delegation name in more than one governorate; "
                         "resolved by coordinates instead")

        chosen = None
        method = "unresolved"
        score = None
        match_km = None
        margin = None

        if la is not None and lo is not None:
            (d1, near1), (d2, _near2) = nearest(la, lo)
            match_km, margin = round(d1, 3), round(d2 - d1, 3)
            if len(hit) == 1:
                named = hit[0]
                named_km = km(la, lo, as_float(named["lat"]), as_float(named["lon"]))
                if named_km > NAME_TRUST_KM:
                    # The name matches a delegation on the other side of the
                    # country. That is a repeated toponym, not this locality.
                    log.add("name_coincidence", row=r["id_2024"], name=name,
                            name_match=named["delegation_name"],
                            name_match_governorate=named["governorate_name"],
                            name_match_km=round(named_km, 3),
                            resolved_as=near1["delegation_name"],
                            centroid_km=round(d1, 3),
                            note="name matches a delegation too far away to be "
                                 "this place; resolved by coordinates instead")
                    r["id_delegation"] = near1["id_delegation"]
                    r["delegation_name"] = near1["delegation_name"]
                    r["governorate_name"] = near1["governorate_name"]
                    r["region_name"] = near1["region_name"]
                    r["match_method"] = "centroid_name_rejected"
                    r["match_score"] = ""
                    r["match_km"] = f"{d1:.3f}"
                    r["match_margin_km"] = f"{d2 - d1:.3f}"
                    stats["centroid_name_rejected"] = stats.get("centroid_name_rejected", 0) + 1
                    continue
                chosen, method, score = named, "name_and_centroid", 1.0
                if named["id_delegation"] != near1["id_delegation"]:
                    method = "name_over_centroid"
                    log.add("name_centroid_conflict", row=r["id_2024"], name=name,
                            name_match=named["delegation_name"],
                            name_match_km=round(named_km, 3),
                            centroid_match=near1["delegation_name"],
                            centroid_km=round(d1, 3),
                            margin_km=round(d2 - d1, 3),
                            resolved_as=named["delegation_name"],
                            note="exact name match kept; nearest centroid is a "
                                 "neighbouring delegation")
                match_km = round(named_km, 3)
            else:
                chosen, method, score = near1, "centroid", None
        else:
            # No coordinates: 105 rows. The name is the first resort, and the
            # historical unit the row sits in is the second -- a contole civil
            # or caidat that maps to a modern unit places the locality inside
            # it even when the locality's own name resolves to nothing.
            if len(hit) == 1:
                chosen, method, score = hit[0], "name_only", 1.0
            elif key:
                best = difflib.get_close_matches(key, vocab, n=1, cutoff=FUZZY_MIN)
                if best:
                    cand = by_key[best[0]]
                    if len(cand) == 1:
                        chosen = cand[0]
                        method = "name_fuzzy"
                        score = round(difflib.SequenceMatcher(None, key, best[0]).ratio(), 4)
                        log.add("name_fuzzy", row=r["id_2024"], name=name,
                                matched=chosen["delegation_name"], score=score,
                                note="no coordinates; name is the only evidence")

            if chosen is None:
                # Prefer the narrowest era that resolves: a 1956 delegation is a
                # tighter statement than a 1931 contole civil, which is tighter
                # than a caidat.
                for col in ("delegation_1956", "controle_civil_1931",
                            "caidat_1931", "caidat_1926"):
                    cw = hist_idx.get(fold(r[col]))
                    if not cw:
                        continue
                    if cw["modern_level"] == "delegation":
                        chosen = by_key[fold(cw["modern_name"])][0]
                        method = "hist_unit_delegation"
                    else:
                        # Governorate only. There is no single delegation to
                        # name, so id_delegation stays empty and the row still
                        # carries a governorate.
                        r["_gov_only"] = cw
                        method = "hist_unit_governorate"
                    log.add("hist_unit_fallback", row=r["id_2024"], name=name,
                            column=col, historical_unit=r[col],
                            modern_level=cw["modern_level"],
                            modern_name=cw["modern_name"], method=method,
                            note="no coordinates and no name match; placed by the "
                                 "historical unit the row records")
                    break

        gov_only = r.pop("_gov_only", None)
        if chosen:
            r["id_delegation"] = chosen["id_delegation"]
            r["delegation_name"] = chosen["delegation_name"]
            r["governorate_name"] = chosen["governorate_name"]
            r["region_name"] = chosen["region_name"]
        elif gov_only:
            r["id_delegation"] = ""
            r["delegation_name"] = ""
            r["governorate_name"] = gov_only["governorate_name"]
            r["region_name"] = next(
                (d["region_name"] for d in delegs
                 if d["governorate_name"] == gov_only["governorate_name"]), "")
        else:
            r["id_delegation"] = r["delegation_name"] = ""
            r["governorate_name"] = r["region_name"] = ""
        r["match_method"] = method
        r["match_score"] = "" if score is None else f"{score:.4f}"
        r["match_km"] = "" if match_km is None else f"{match_km:.3f}"
        r["match_margin_km"] = "" if margin is None else f"{margin:.3f}"
        stats[method] = stats.get(method, 0) + 1
    return stats


def write_csv(path, rows, columns):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=columns, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in columns})
    os.replace(tmp, path)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--delegations", default=DELEG_SRC)
    ap.add_argument("--localities", default=LOCAL_SRC)
    ap.add_argument("--write", action="store_true",
                    help="write the outputs; without it, report only")
    args = ap.parse_args()

    delegs = read_semicolon(args.delegations)
    locals_ = read_semicolon(args.localities)
    if len(delegs) != DELEG_ROWS or len(locals_) != LOCAL_ROWS:
        sys.exit(f"refusing: expected {DELEG_ROWS}/{LOCAL_ROWS} rows, "
                 f"got {len(delegs)}/{len(locals_)}")

    sources_before = [r["city_name_sources"] for r in locals_]
    log = Log(LOG)

    hygiene(delegs, locals_, log)
    for r in delegs:
        r["name_key"] = fold(r["delegation_name"])

    ins_keys = {r["name_key"] for r in delegs}
    residual, filled = classify_missing(locals_, log)
    merges = merge_spellings(locals_, ins_keys, log)
    dups = report_duplicate_rows(locals_, log)
    crosswalk = build_hist_unit_crosswalk(locals_, delegs, log)
    stats = resolve(locals_, delegs, hist_unit_index(crosswalk), log)

    # city_name_sources is a quotation and must survive byte-identical.
    for before, r in zip(sources_before, locals_):
        if before.strip() != r["city_name_sources"]:
            sys.exit(f"refusing: city_name_sources changed on row {r['id_2024']}")

    deleg_cols = list(read_semicolon(args.delegations)[0].keys()) + ["name_key"]
    local_cols = list(read_semicolon(args.localities)[0].keys()) + [
        "name_key", "id_delegation", "delegation_name", "governorate_name",
        "region_name", "match_method", "match_score", "match_km", "match_margin_km",
    ]

    print(f"delegations {len(delegs)}   localities {len(locals_)}")
    print(f"spelling merges applied: {merges}")
    print(f"empty city_name: {residual} left empty as residual categories, "
          f"{filled} filled from the source name")
    print(f"duplicate-row candidates reported: {dups}")
    print(f"historical unit names crosswalked: {len(crosswalk)}")
    print("\nresolution by method:")
    for k, v in sorted(stats.items(), key=lambda t: -t[1]):
        print(f"  {k:22s} {v:5d}  ({100*v/len(locals_):.1f}%)")
    print("\nlog records by kind:")
    for k, v in sorted(log.counts().items(), key=lambda t: -t[1]):
        print(f"  {k:30s} {v}")

    cen = sorted(float(r["match_km"]) for r in locals_
                 if r["match_method"] == "centroid" and r["match_km"])
    if cen:
        def pct(p):
            return cen[min(len(cen) - 1, int(len(cen) * p / 100))]
        print(f"\ncentroid-resolved distance km: p50 {pct(50):.1f}  p90 {pct(90):.1f}  "
              f"p99 {pct(99):.1f}  max {cen[-1]:.1f}  (n={len(cen)})")

    xw_methods = {}
    for r in crosswalk:
        xw_methods[r["method"]] = xw_methods.get(r["method"], 0) + 1
    print("\nhistorical unit crosswalk by method:")
    for k, v in sorted(xw_methods.items(), key=lambda t: -t[1]):
        print(f"  {k:22s} {v:5d}")

    if args.write:
        write_csv(DELEG_OUT, delegs, deleg_cols)
        write_csv(LOCAL_OUT, locals_, local_cols)
        write_csv(HIST_XW_OUT, crosswalk, [
            "historical_name", "name_key", "columns", "cells", "modern_level",
            "modern_name", "governorate_name", "id_delegation", "method",
            "score", "note"])
        log.write()
        print(f"\nwrote {DELEG_OUT}, {LOCAL_OUT}, {HIST_XW_OUT}, {LOG}")
    else:
        print("\ndry run; pass --write to write the outputs")


if __name__ == "__main__":
    main()
