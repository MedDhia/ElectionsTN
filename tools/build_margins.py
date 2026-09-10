"""Candidate shares and margins per station, imada, delegation and governorate.

Every station in data/pv_presidential_2024.csv now carries an official INS
delegation code, via data/pv_delegation_map.csv. That code is also the join key
to real boundaries: in the OCHA/HDX COD-AB set, `adm3_pcode` is "TN" plus
`id_delegation`, and all 264 match both ways with nothing fuzzy in between.

Below the delegation, admin4 gives 2,084 imadas with Arabic names, which the PV
file also carries as `sector`. That join is by name, scoped inside the
delegation, and its rate and residue are reported rather than assumed.

Shares are of **valid votes**, so a share is scale-free and aggregating upward is
a plain sum of votes. Margin for a candidate is their share minus the strongest
rival's: positive for whoever leads the unit, negative for everyone else.

Vote sums aggregate over **certified** stations only, which is the convention
tools/reconcile_national.py already uses and which reproduces the published
national figures exactly. The distinction matters by one station: `10020210101`
in El Mida has three readable numbers (232 + 0 + 1 = 233) against a published
`valid` of 333, on a form with no recoverable grid. It is uncertified precisely
because that identity fails, so a digit in it is known to be wrong; summing it
would inject a bad reading into every level above it. Its own row keeps its
shares, flagged, so a reader can see it rather than wonder where it went.

Nothing here modifies data/pv_presidential_2024.csv.
"""

import argparse
import collections
import csv
import difflib
import io
import json
import math
import os
import re
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from arabic_latin import ar_norm

PV = "data/pv_presidential_2024.csv"
MAP = "data/pv_delegation_map.csv"
XW = "data/delegation_crosswalk.csv"
ARCHIVE = ".cache/boundaries/tun_admin_boundaries.geojson.zip"

STATION_OUT = "data/station_margins.csv"
IMADA_OUT = "data/imada_margins.csv"
DELEG_OUT = "data/delegation_margins.csv"
SUMMARY_OUT = "data/margin_summary.csv"
LOG = "data/verification/margins.jsonl"

PV_ROWS = 9448
CANDIDATES = ("saied", "zammel", "maghzaoui")

# Measured, not chosen for convenience. Scoped inside a delegation the imada
# name match reaches 99.1% at this floor. It is set here rather than lower
# because `صاحب الجبل الجوفية` and `صاحب الجبل القبلية` -- northern and southern
# Sahib El Jebel, two *different* imadas -- score 0.812 against each other, so
# any floor at 0.80 would silently merge them. Same failure the delegation-level
# compass lexicon exists to prevent.
IMADA_MIN = 0.85

# A second tier, for names the boundary file spells differently by one letter.
# Several admin4 names carry what look like transcription slips against the PV
# file -- `صانوش` for `زانوش`, `صقانص` for `صقانس`, `الفنة` for `القنة`,
# `جاتمة` for `خاتمة`, `طمزرط` for `تمزرط`, `فانض` for `فائض` -- which score
# around 0.80 and would otherwise be gaps.
#
# What makes them safe to accept is not the score but the *margin*: inside a
# delegation's handful of imadas each of these leads its runner-up by 0.20 to
# 0.45, so there is nothing else it could be. The case this must not admit is
# `صاحب الجبل الجوفية`, which scores 0.812 against `صاحب الجبل القبلية` --
# northern against southern -- and there the margin collapses to 0.025, because
# three Sahib El Jebel imadas exist and the name is genuinely ambiguous. The
# floor is set well above that and well below the typos.
IMADA_NEAR_MIN = 0.75
IMADA_NEAR_MARGIN = 0.15

AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def load_layer(name):
    with zipfile.ZipFile(ARCHIVE) as z, z.open(name) as fh:
        return json.load(io.TextIOWrapper(fh, encoding="utf-8"))["features"]


def read(path):
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def gi(row, col):
    v = (row.get(col) or "").strip()
    return int(v) if v.isdigit() else None


def imada_key(s):
    """Comparison key for an Arabic place name."""
    s = ar_norm(s or "").translate(AR_DIGITS)
    s = re.sub(r"\b0+(\d)", r"\1", s)      # `01جوان` == `1جوان`
    return re.sub(r"[\s\-_.]+", "", s)


def sector_readings(s, delegation_ar=""):
    """Every plausible reading of an ISIE sector name.

    A sector name may pair the imada with its delegation across a dash, and the
    order is not fixed: `العامرة - (سبالة أولاد عسكر)` puts the imada first and
    the delegation in brackets, while `منزل بوزيان - الخرشف` puts the delegation
    first. Assuming the first form collapsed all seven `منزل بوزيان - X` sectors
    onto one imada at a perfect score; offering both sides blindly then created
    the opposite error, because a delegation seat usually has an imada of the
    same name, so `X - (Deleg)` began matching `Deleg` instead of `X`.

    What settles it is the delegation, which is already known per station: the
    part that repeats the delegation name is the qualifier, and the other part is
    the place. Both parts are kept only when neither is the delegation, or when
    both are (`منزل بوزيان - منزل بوزيان` really is that imada).

    Brackets are stripped before splitting rather than parsed, because
    bidirectional text leaves them on the wrong side:
    `(علي البلهوان - (حي الخضراء` is really `علي البلهوان - (حي الخضراء)`.
    """
    s = re.sub(r"[()]", "", (s or "").strip())
    if " - " not in s:
        return [s]
    parts = [part.strip() for part in s.split(" - ") if part.strip()]
    dk = imada_key(delegation_ar)
    if dk:
        kept = [part for part in parts if imada_key(part) != dk]
        if kept:
            return kept + [s]
    return parts + [s]


def imada_score(sector, imada_name, delegation_ar=""):
    """Best similarity between any reading of a sector name and one imada.

    Beyond the readings above, two further allowances, each earned by a real
    case: containment, because a sector recorded as `خنيس` against an imada
    `خنيس الجنوبية` is the same place at a coarser grain; and word-order
    insensitivity, because Arabic compound names reorder (`أكتوبر 15` against
    `15أكتوبر`).
    """
    b = imada_key(imada_name)
    if not b:
        return 0.0
    bw = imada_key(" ".join(sorted(ar_norm(imada_name or "").split())))
    best = 0.0
    for reading in sector_readings(sector, delegation_ar):
        a = imada_key(reading)
        if not a:
            continue
        best = max(best, difflib.SequenceMatcher(None, a, b).ratio())
        if a in b or b in a:
            best = max(best, 0.90)
        aw = imada_key(" ".join(sorted(ar_norm(reading).split())))
        if aw and bw:
            best = max(best, difflib.SequenceMatcher(None, aw, bw).ratio())
    return best


class Log:
    def __init__(self, path):
        self.path, self.records = path, []

    def add(self, kind, **f):
        self.records.append(dict(kind=kind, **f))

    def counts(self):
        return dict(collections.Counter(r["kind"] for r in self.records))

    def write(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as fh:
            for r in self.records:
                fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")


def shares_and_margins(votes):
    """Shares of valid votes, and each candidate's margin over its best rival."""
    total = sum(votes.values())
    if total <= 0:
        return {}, {}, "", "", None
    share = {c: 100.0 * votes[c] / total for c in votes}
    margin = {}
    for c in votes:
        rival = max(v for k, v in share.items() if k != c)
        margin[c] = share[c] - rival
    order = sorted(share, key=lambda c: (-share[c], c))
    return share, margin, order[0], order[1], share[order[0]] - share[order[1]]


def percentiles(values, ps):
    """Linear-interpolated percentiles, so the summary needs no dependency."""
    if not values:
        return {p: None for p in ps}
    v = sorted(values)
    out = {}
    for p in ps:
        if len(v) == 1:
            out[p] = v[0]
            continue
        k = (len(v) - 1) * p / 100.0
        lo, hi = math.floor(k), math.ceil(k)
        out[p] = v[lo] if lo == hi else v[lo] + (v[hi] - v[lo]) * (k - lo)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(ARCHIVE):
        sys.exit(f"missing {ARCHIVE}; run tools/fetch_boundaries.py")
    pv, smap, xw = read(PV), read(MAP), read(XW)
    if len(pv) != PV_ROWS:
        sys.exit(f"refusing: {PV} has {len(pv)} rows, expected {PV_ROWS}")
    log = Log(LOG)

    a2 = {f["properties"]["adm2_pcode"]: f["properties"] for f in load_layer("tun_admin2.geojson")}
    a3 = {f["properties"]["adm3_pcode"]: f["properties"] for f in load_layer("tun_admin3.geojson")}
    a4 = [f["properties"] for f in load_layer("tun_admin4.geojson")]

    # The delegation join is by code and must stay exact.
    ins_pcodes = {"TN" + r["id_delegation"] for r in read("data/delegations_ins.csv")}
    if set(a3) != ins_pcodes:
        sys.exit(f"refusing: adm3_pcode set differs from INS codes "
                 f"({len(set(a3) ^ ins_pcodes)} symmetric difference)")

    by_bureau = {r["bureau_code"]: r for r in smap}
    imadas_by_deleg = collections.defaultdict(list)
    for p in a4:
        imadas_by_deleg[p["adm3_pcode"]].append(p)
    gov_ar_to_pcode = {ar_norm(p["adm2_name1"] or ""): code for code, p in a2.items()}

    # ---- imada resolution, scoped inside the delegation ---------------------
    pairs = {}
    for r in pv:
        m = by_bureau[r["bureau_code"]]
        pc = "TN" + m["id_delegation"] if m["id_delegation"] else ""
        k = (pc, r["sector"].strip(), r["governorate"].strip(), m["delegation_ar"])
        pairs[k] = pairs.get(k, 0) + 1

    resolved = {}
    for (pc, sector, gov_ar, deleg_ar), n in sorted(pairs.items()):
        cands = imadas_by_deleg.get(pc, [])
        method = "scoped"
        if not cands:
            # No delegation code: the 15 ISIE units with no INS counterpart.
            # Their imada names should still exist in admin4, and the imada's own
            # adm3_pcode then reveals the parent delegation -- so try the whole
            # governorate, and accept only an unambiguous winner.
            gpc = gov_ar_to_pcode.get(ar_norm(gov_ar))
            cands = [p for p in a4 if p["adm2_pcode"] == gpc] if gpc else []
            method = "governorate_recovery"
        if not cands:
            resolved[(pc, sector)] = (None, 0.0, 0.0, "no_candidates")
            continue
        ranked = sorted(((imada_score(sector, c["adm4_name1"] or "", deleg_ar), c)
                         for c in cands),
                        key=lambda t: (-t[0], t[1]["adm4_pcode"]))
        best, second = ranked[0], (ranked[1] if len(ranked) > 1 else (0.0, None))
        margin = best[0] - second[0]
        near = (best[0] >= IMADA_NEAR_MIN and margin >= IMADA_NEAR_MARGIN)
        accept = best[0] >= IMADA_MIN or near
        if accept and (method == "scoped" or margin > 0):
            how = method if best[0] >= IMADA_MIN else method + "_near"
            resolved[(pc, sector)] = (best[1], best[0], margin, how)
            if near and best[0] < IMADA_MIN:
                log.add("imada_near_match", sector=sector, delegation_pcode=pc,
                        matched=best[1]["adm4_name1"],
                        adm4_pcode=best[1]["adm4_pcode"],
                        score=round(best[0], 4), margin=round(margin, 4),
                        stations=n,
                        note="accepted below the main floor because it leads its "
                             "runner-up decisively inside the delegation; the two "
                             "names differ by about one character")
            method = how
            if method == "governorate_recovery":
                log.add("imada_governorate_recovery", sector=sector, governorate=gov_ar,
                        matched=best[1]["adm4_name1"], adm4_pcode=best[1]["adm4_pcode"],
                        recovered_delegation=best[1]["adm3_name"],
                        adm3_pcode=best[1]["adm3_pcode"], score=round(best[0], 4),
                        margin=round(margin, 4), stations=n,
                        note="station had no INS delegation; placed by matching its "
                             "imada name across the governorate")
        else:
            resolved[(pc, sector)] = (None, best[0], margin, method)
            log.add("imada_unmatched", sector=sector, delegation_pcode=pc,
                    governorate=gov_ar, stations=n, best_score=round(best[0], 4),
                    best_candidate=best[1]["adm4_name1"], method=method,
                    note=f"below the {IMADA_MIN} floor; left as a gap on the imada map")

    # An imada claimed by two different sectors is the failure signature a
    # cross-vocabulary match produces, so it is checked rather than hoped about.
    # Several ISIE sectors legitimately sit inside one imada -- ISIE splits a
    # large imada for polling (`الفريو 1`/`الفريو 2`, `الهيشرية 1`/`الهيشرية 2`).
    # That is expected, and aggregation sums them, so it is recorded rather than
    # treated as an error. What it also catches is the failure mode it was put
    # here for: a bad reading collapsing unrelated sectors onto one imada, which
    # is how the seven `منزل بوزيان - X` sectors were found.
    claims = collections.Counter(v[0]["adm4_pcode"] for v in resolved.values() if v[0])
    for pcode, n in claims.items():
        if n > 1:
            who = [k[1] for k, v in resolved.items() if v[0] and v[0]["adm4_pcode"] == pcode]
            log.add("imada_subdivided", adm4_pcode=pcode, sectors_mapped=n,
                    sectors=who,
                    note="ISIE polls this imada as several sectors; their votes "
                         "are summed into the one imada")

    # ---- station level ------------------------------------------------------
    stations = []
    for r in pv:
        m = by_bureau[r["bureau_code"]]
        pc = "TN" + m["id_delegation"] if m["id_delegation"] else ""
        im, score, imargin, method = resolved.get((pc, r["sector"].strip()),
                                                  (None, 0.0, 0.0, ""))
        votes = {c: gi(r, c) for c in CANDIDATES}
        complete = all(v is not None for v in votes.values())
        share, margin, winner, runner, mgap = ({}, {}, "", "", None)
        if complete:
            share, margin, winner, runner, mgap = shares_and_margins(votes)
        if complete and r["votes_certified"] != "1":
            log.add("complete_but_uncertified", bureau_code=r["bureau_code"],
                    votes={c: votes[c] for c in CANDIDATES},
                    candidate_sum=sum(votes.values()),
                    published_valid=r["valid"].strip(), status=r["status"],
                    note="three readable numbers that do not sum to the published "
                         "valid total, so a digit is wrong; the row keeps its "
                         "shares but is excluded from every vote sum")
        if not complete:
            log.add("station_incomplete", bureau_code=r["bureau_code"],
                    votes={c: votes[c] for c in CANDIDATES},
                    votes_certified=r["votes_certified"],
                    note="candidate triple incomplete; shares left blank and the "
                         "station excluded from vote sums, but still counted")
        reg, voted = gi(r, "a_registered"), gi(r, "w_voted")
        # Where the imada carries its own delegation (a recovery), prefer it.
        adm3 = im["adm3_pcode"] if im else pc
        d3 = a3.get(adm3)
        row = {
            "bureau_code": r["bureau_code"], "isie_code": m["isie_code"],
            "governorate_ar": r["governorate"].strip(),
            "delegation_ar": m["delegation_ar"],
            "sector_ar": r["sector"].strip(),
            "polling_centre_ar": r["polling_centre"].strip(),
            "governorate_name": d3["adm2_name"] if d3 else m["governorate_name"],
            "delegation_name": d3["adm3_name"] if d3 else m["delegation_name"],
            "region_name": d3["adm1_name"] if d3 else "",
            "id_delegation": adm3[2:] if adm3 else "",
            "adm3_pcode": adm3,
            "imada_name_ar": im["adm4_name1"] if im else "",
            "imada_name": im["adm4_name"] if im else "",
            "adm4_pcode": im["adm4_pcode"] if im else "",
            "imada_match_score": f"{score:.4f}" if im else "",
            "imada_match_method": method if im else "unmatched",
            "registered": reg if reg is not None else "",
            "voters": voted if voted is not None else "",
            "valid": gi(r, "valid") if gi(r, "valid") is not None else "",
            "blank": gi(r, "blank") if gi(r, "blank") is not None else "",
            "spoilt": gi(r, "spoilt") if gi(r, "spoilt") is not None else "",
            "votes_certified": r["votes_certified"],
            "complete": "1" if complete else "",
        }
        for c in CANDIDATES:
            row[c] = votes[c] if votes[c] is not None else ""
            row[f"{c}_share_pct"] = f"{share[c]:.4f}" if complete else ""
            row[f"{c}_margin_pp"] = f"{margin[c]:.4f}" if complete else ""
        row["candidate_sum"] = sum(votes.values()) if complete else ""
        row["winner"] = winner
        row["runner_up"] = runner
        row["margin_pp"] = f"{mgap:.4f}" if mgap is not None else ""
        # Turnout is a certified numerator over an UNCERTIFIED denominator.
        # `a_registered` appears in none of the form's identities -- it is the
        # one field read by classifier alone -- so the PV file's own
        # `a_registered_ok` is the only gate there is. Recomputing turnout from
        # the raw columns without it published a station at 13,133% (3
        # registered, 394 voters); `turnout_basis` records which stations may
        # be summed, so the aggregates cannot silently mix bases either.
        turnout_ok = (r.get("a_registered_ok") == "1" and reg and reg > 0
                      and voted is not None and voted <= reg)
        row["turnout_basis"] = "1" if turnout_ok else ""
        row["turnout_pct"] = f"{100.0 * voted / reg:.4f}" if turnout_ok else ""
        stations.append(row)

    # ---- aggregation -------------------------------------------------------
    def aggregate(rows, keyfn, extra):
        out = {}
        for r in rows:
            k = keyfn(r)
            if k is None:
                continue
            a = out.setdefault(k, {"n_stations": 0, "n_certified": 0,
                                   "registered": 0, "voters": 0, "valid": 0,
                                   "blank": 0, "spoilt": 0,
                                   "turnout_stations": 0,
                                   "turnout_registered": 0, "turnout_voters": 0,
                                   **{c: 0 for c in CANDIDATES}})
            a["n_stations"] += 1
            for f in ("registered", "voters", "valid", "blank", "spoilt"):
                if r[f] != "":
                    a[f] += int(r[f])
            # The turnout numerator and denominator are summed over the SAME
            # stations. Summing each column over whatever happens to carry it
            # is what made TN5256 report 1.1% turnout -- `registered` from 47
            # stations over `voters` from 3 -- against 17.3% on the matched
            # subset. 167 of 264 delegations were affected.
            if r["turnout_basis"] == "1":
                a["turnout_stations"] += 1
                a["turnout_registered"] += int(r["registered"])
                a["turnout_voters"] += int(r["voters"])
            # Certified is the aggregation basis; see the module docstring.
            if r["votes_certified"] == "1":
                a["n_certified"] += 1
                for c in CANDIDATES:
                    a[c] += int(r[c])
        rows_out = []
        for k, a in sorted(out.items()):
            votes = {c: a[c] for c in CANDIDATES}
            share, margin, winner, runner, mgap = shares_and_margins(votes)
            row = dict(extra(k, a))
            row.update({f: a[f] for f in ("n_stations", "n_certified", "registered",
                                          "voters", "valid", "blank", "spoilt",
                                          "turnout_stations",
                                          "turnout_registered",
                                          "turnout_voters")})
            for c in CANDIDATES:
                row[c] = votes[c]
                row[f"{c}_share_pct"] = f"{share.get(c, 0):.4f}" if share else ""
                row[f"{c}_margin_pp"] = f"{margin.get(c, 0):.4f}" if margin else ""
            row["candidate_sum"] = sum(votes.values())
            row["winner"], row["runner_up"] = winner, runner
            row["margin_pp"] = f"{mgap:.4f}" if mgap is not None else ""
            row["turnout_pct"] = (
                f"{100.0 * a['turnout_voters'] / a['turnout_registered']:.4f}"
                if a["turnout_registered"] else "")
            # How much of the unit the turnout figure actually rests on. A unit
            # whose stations mostly failed to read has a turnout computed from
            # a biased remnant, and missingness is not random -- 18.1% of
            # Medenine's stations against 8.1% of Nabeul's -- so this travels
            # with the figure rather than being left for the reader to guess.
            row["turnout_coverage_pct"] = (
                f"{100.0 * a['turnout_stations'] / a['n_stations']:.4f}"
                if a["n_stations"] else "")
            rows_out.append(row)
        return rows_out

    delegations = aggregate(
        stations, lambda r: r["adm3_pcode"] or None,
        lambda k, a: {"adm3_pcode": k, "id_delegation": k[2:],
                      "delegation_name": a3[k]["adm3_name"],
                      "delegation_name_ar": a3[k]["adm3_name1"],
                      "governorate_name": a3[k]["adm2_name"],
                      "governorate_name_ar": a3[k]["adm2_name1"],
                      "region_name": a3[k]["adm1_name"],
                      "lat": a3[k]["center_lat"], "lon": a3[k]["center_lon"],
                      "area_sqkm": a3[k]["area_sqkm"]})
    a4_by = {p["adm4_pcode"]: p for p in a4}
    imadas = aggregate(
        stations, lambda r: r["adm4_pcode"] or None,
        lambda k, a: {"adm4_pcode": k, "imada_name": a4_by[k]["adm4_name"],
                      "imada_name_ar": a4_by[k]["adm4_name1"],
                      "adm3_pcode": a4_by[k]["adm3_pcode"],
                      "delegation_name": a4_by[k]["adm3_name"],
                      "governorate_name": a4_by[k]["adm2_name"],
                      "region_name": a4_by[k]["adm1_name"],
                      "lat": a4_by[k]["center_lat"], "lon": a4_by[k]["center_lon"],
                      "area_sqkm": a4_by[k]["area_sqkm"]})

    # ---- report ------------------------------------------------------------
    nat = {c: sum(int(r[c]) for r in stations if r["votes_certified"] == "1")
           for c in CANDIDATES}
    tot = sum(nat.values())
    print(f"stations {len(stations)}  "
          f"complete {sum(1 for r in stations if r['complete']=='1')}  "
          f"certified {sum(1 for r in stations if r['votes_certified']=='1')} "
          f"(certified is the aggregation basis)")
    print(f"national: " + "  ".join(f"{c} {nat[c]:,} ({100*nat[c]/tot:.2f}%)" for c in CANDIDATES))
    print(f"          valid total {tot:,}")
    matched = sum(1 for r in stations if r["adm4_pcode"])
    print(f"\nimada resolution: {matched}/{len(stations)} stations "
          f"({100*matched/len(stations):.1f}%) into {len(imadas)} of 2,084 imadas")
    print(f"delegations covered: {len(delegations)}/264")
    nod = sum(1 for r in stations if not r["adm3_pcode"])
    print(f"stations with no delegation: {nod}")
    print(f"\nlog: {log.counts()}")

    if not args.write:
        print("\ndry run; pass --write to write the outputs")
        return

    # ---- summary (the distribution proper) ---------------------------------
    PS = [10, 25, 50, 75, 90]
    summary = []

    def describe(level, group_kind, group, rows, field):
        vals = [float(r[field]) for r in rows if r.get(field) not in ("", None)]
        if not vals:
            return
        mean = sum(vals) / len(vals)
        sd = (sum((v - mean) ** 2 for v in vals) / (len(vals) - 1)) ** 0.5 if len(vals) > 1 else 0.0
        q = percentiles(vals, PS)
        summary.append({
            "level": level, "group_kind": group_kind, "group": group,
            "metric": field, "n": len(vals),
            "mean": f"{mean:.4f}", "sd": f"{sd:.4f}",
            "min": f"{min(vals):.4f}",
            **{f"p{p}": f"{q[p]:.4f}" for p in PS},
            "max": f"{max(vals):.4f}",
        })

    metrics = [f"{c}_share_pct" for c in CANDIDATES] + ["margin_pp", "turnout_pct"]
    for level, rows in (("station", stations), ("imada", imadas), ("delegation", delegations)):
        for f in metrics:
            describe(level, "national", "Tunisia", rows, f)
        for gk, keyf in (("region", "region_name"), ("governorate", "governorate_name")):
            groups = collections.defaultdict(list)
            for r in rows:
                if r.get(keyf):
                    groups[r[keyf]].append(r)
            for g, rs in sorted(groups.items()):
                for f in metrics:
                    describe(level, gk, g, rs, f)

    def write_csv(path, rows, cols=None):
        cols = cols or list(rows[0].keys())
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols, lineterminator="\n")
            w.writeheader()
            for r in rows:
                w.writerow({c: r.get(c, "") for c in cols})
        os.replace(tmp, path)

    write_csv(STATION_OUT, stations)
    write_csv(DELEG_OUT, delegations)
    write_csv(IMADA_OUT, imadas)
    write_csv(SUMMARY_OUT, summary)
    log.write()
    print(f"\nwrote {STATION_OUT} ({len(stations)}), {DELEG_OUT} ({len(delegations)}), "
          f"{IMADA_OUT} ({len(imadas)}), {SUMMARY_OUT} ({len(summary)}), {LOG}")


if __name__ == "__main__":
    main()
