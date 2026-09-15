"""Dataset — the 2014 presidential runoff, per polling bureau.

Where this comes from
---------------------
ISIE published the 21 December 2014 runoff as one spreadsheet per delegation,
under `wp-content/uploads/filebases/pv-auto-bv-presidentielles-tour2/` --
*procès-verbal, automatique, bureau de vote*. The tree is gone from isie.tn
(every pre-2020 upload 404s) and survives in the Wayback Machine;
`tools/fetch_isie_filebases.py` recovers it into `.cache/isie2019/`.

This is the only tabulated tree in that archive. The other five hold scans of
handwritten forms, which would need the reading pipeline rather than a parse.

The path says `presidentielles-tour2` and carries no year. It is **2014**, not
2019, on three independent grounds: every one of the 269 workbooks names محمد
الباجي القايد السبسي and محمد المنصف المرزوقي, who contested the 2014 runoff
(2019 was Saied against Karoui); the workbooks carry their own print date of
22 December 2014, the day after the vote; and the totals reconcile to the 2014
declared result exactly, in the sense set out below.

What it gives the repo
----------------------
10,567 polling bureaux for 2014, against the 957 collection-centre rows
`data/presidential_2014_constituency.csv` holds. Bureau codes are 11 digits in
the same shape as `data/pv_presidential_2024.csv`.

The reconciliation, and why it is exact rather than approximate
---------------------------------------------------------------
The recovered tree gives 3,073,796 valid votes against the declared 3,110,042 --
36,246 short, 1.17%. That gap is not a residual: it is accounted for to the
vote, and the accounting is what certifies the parse.

`data/presidential_2014_constituency.csv` was decoded from ISIE's
constituency-level runoff PV in earlier, unrelated work, and it sums exactly to
the declared national result. Rolling this tree up to the same 33
constituencies, **31 of them agree with it to the single vote**. Two do not,
and each has a named cause:

* **فرنسا 1** (France 1, 36,252 votes) has no workbook in the tree at all. The
  CDX enumeration of the capture returned 270 files, among them
  `France2/France2.xlsx` and nothing named France 1; the 2014 diaspora
  constituencies were France 1 and France 2, so one of the two went unarchived
  in this snapshot. Whether another snapshot holds it is unchecked. This is the
  whole of the shortfall.
* **أريانة** (Ariana) comes out 6 votes *higher* here than in the constituency
  PV, all six on Essebsi, with Marzouki exact. This is not a parse error: each
  of the seven Ariana workbooks carries its own subtotal row, and all seven
  agree with the parse exactly. It is a disagreement between two ISIE
  publications, and the bureau sheets -- printed the day after the vote, a
  month before the constituency PV in the repo -- are the earlier of the two.
  It is published as found and logged, not adjusted.

36,252 - 6 = 36,246. Nothing is left over. `tools/audit_presidential_2014_bureau.py`
holds this as a standing invariant, so a reparse that drifted by a single vote
in any constituency would fail rather than pass within a tolerance.

Geography, and why the code beats the name
------------------------------------------
Each workbook sits at `<Governorate>/<Delegation>.xlsx` in ISIE's own ASCII
spelling, and those spellings differ from `data/delegations_ins.csv` far more
often than not -- `Feryena` for Feriana, `Zriba` for Ez-Zeriba, `Sejnene` for
Sedjnane. Folding the names matches only 165 of 264.

Inside 2014 the geography is better carried by the code itself: the first four
digits are constant within every delegation and unique across all 264, so
`code[:4]` is an exact delegation key. It is **not** the 2024 key, though --
ISIE renumbered between the two: only 203 of the 264 prefixes appear among the
2024 station codes at all, and 9 of the prefixes that do appear there map to
more than one delegation.
So the join to INS runs through names after all, in three passes scoped to the
governorate (which the path gives reliably: the 27 in-country labels collapse
onto the 24 INS governorates, with Tunis1/2, Nabeul1/2 and Sfax1/2 merging):

1. exact match on the space-stripped fold
2. best fuzzy match at ratio >= 0.80, taken highest-score-first
3. elimination, where one unmatched workbook faces one free INS slot

Every pass is bijective within its governorate: no INS delegation is claimed
twice. That constraint is what makes the fuzzy pass safe -- it is also what
resolves the only genuinely ambiguous case, `Gafsa/Moulares`, onto Oum El
Araies once the other ten Gafsa delegations have matched.

Out-of-country is aggregated, not per bureau
--------------------------------------------
Five workbooks cover the foreign constituencies (six existed; see France 1
above) and hold a single row each,
keyed by a two-digit constituency code rather than an 11-digit bureau. They are
published in the delegation file with `scope = etranger` and no INS code, and
excluded from the bureau file, which is in-country by construction.

Usage: python3 tools/build_presidential_2014_bureau.py [--write]
"""

import argparse
import collections
import csv
import difflib
import glob
import json
import os
import re
import sys
import urllib.parse

import openpyxl

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import latin_names as LN

CACHE = ".cache/isie2019"
INS = "data/delegations_ins.csv"
OUT_BUREAU = "data/presidential_2014_bureau.csv"
OUT_DELEG = "data/presidential_2014_delegation.csv"
LOG = "data/verification/presidential_2014_bureau.jsonl"

CONSTITUENCY = "data/presidential_2014_constituency.csv"

# ISIE's workbook tree groups delegations under 27 in-country and 5 foreign
# path labels; `data/presidential_2014_constituency.csv` publishes the same
# runoff under the 33 Arabic constituency names. This is the mapping between
# them, and it is what makes the recovered tree checkable against a figure
# ISIE published independently of it.
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
# The one constituency with no workbook in the recovered tree.
MISSING_CONSTITUENCY = "فرنسا 1"

BUREAU = re.compile(r"^\d{11}$")
FOREIGN = re.compile(r"^\d{1,4}$")
FUZZY_MIN = 0.80
# The declared result, for the end-to-end check.
DECLARED = {"essebsi": 1731529, "marzouki": 1378513, "total": 3110042}


def squash(s):
    """The Latin fold with spaces removed: ISIE writes `BejaNord`, INS `Béja Nord`."""
    return LN.fold(s).replace(" ", "")


def workbooks():
    """(governorate label, delegation label) -> path, for each cached workbook.

    The recovery tool saved some workbooks twice, under two spellings of the
    same Wayback path (`Hassi El Frid` and `Hassi+El+Frid`, with and without
    the `Tunisie/` segment). The pairs are byte-identical except where one
    download was cut off, so the key keeps the **largest** file. Keeping the
    last in sort order instead -- as this did at first -- silently preferred a
    zero-byte `Hassi+El+Frid.xlsx` over its intact 18 KB twin, and cost the
    build a whole delegation and its 23 bureaux while reporting only an
    unreadable file.
    """
    out = {}
    for f in sorted(glob.glob(f"{CACHE}/*.xlsx")):
        parts = os.path.basename(f)[:-5].split("__")
        if len(parts) < 3:
            continue
        gov = urllib.parse.unquote(parts[-2]).replace("+", " ")
        deleg = urllib.parse.unquote(parts[-1]).replace("+", " ")
        key = (gov, deleg)
        if key in out and os.path.getsize(out[key]) >= os.path.getsize(f):
            continue
        out[key] = f
    return out


def read(path):
    """(candidate names, [(code, [votes], printed total)]) from one workbook."""
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb[wb.sheetnames[0]]
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    wb.close()
    head = tot_col = None
    for i, r in enumerate(rows):
        for j, c in enumerate(r):
            if isinstance(c, str) and "مجموع الأصوات" in c:
                head, tot_col = i, j
        if head is not None:
            break
    if head is None:
        return None, []
    cols = [(j, str(c).strip()) for j, c in enumerate(rows[head + 1])
            if c not in (None, "")]
    out = []
    for r in rows[head + 2:]:
        first = str(r[1]).strip() if len(r) > 1 and r[1] is not None else ""
        if "مجموع" in first:           # the sheet's own subtotal row
            continue
        if not (BUREAU.match(first) or FOREIGN.match(first)):
            continue
        try:
            votes = [int(str(r[j]).strip()) for j, _ in cols]
        except (TypeError, ValueError):
            continue
        try:
            printed = int(str(r[tot_col]).strip())
        except (TypeError, ValueError):
            printed = None
        centre = ""
        for c in r[2:8]:
            if isinstance(c, str) and c.strip():
                centre = " ".join(c.split())
                break
        out.append((first, centre, votes, printed))
    return [n for _, n in cols], out


def governorate_map(labels, ins_govs):
    """Each path label onto an INS governorate, or None for out-of-country."""
    out = {}
    for label in labels:
        k = squash(label)
        base = k.rstrip("12") if k and k[-1].isdigit() else k
        hits = [g for g in ins_govs if squash(g) == base]
        if not hits:
            hits = [g for g in ins_govs
                    if squash(g).endswith(base) or base.endswith(squash(g))]
        if not hits:
            near = difflib.get_close_matches(
                base, [squash(g) for g in ins_govs], n=1, cutoff=0.7)
            hits = [g for g in ins_govs if squash(g) == near[0]] if near else []
        out[label] = hits[0] if len(hits) == 1 else None
    return out


def crosswalk(pairs, ins, gmap):
    """(gov label, deleg label) -> (id_delegation, method), bijective per governorate."""
    by_gov = collections.defaultdict(list)
    for r in ins:
        by_gov[r["governorate_name"]].append(r)
    grouped = collections.defaultdict(list)
    for gov, deleg in pairs:
        g = gmap.get(gov)
        if g:
            grouped[g].append((gov, deleg))
    assigned, unresolved = {}, []
    for g, items in grouped.items():
        pool = {r["id_delegation"]: r for r in by_gov[g]}
        taken = set()
        for gov, deleg in items:
            hit = [i for i, r in pool.items()
                   if squash(r["delegation_name"]) == squash(deleg)
                   and i not in taken]
            if len(hit) == 1:
                assigned[(gov, deleg)] = (hit[0], "exact")
                taken.add(hit[0])
        rest = [p for p in items if p not in assigned]
        scored = []
        for gov, deleg in rest:
            for i, r in pool.items():
                if i in taken:
                    continue
                scored.append((difflib.SequenceMatcher(
                    None, squash(deleg), squash(r["delegation_name"])).ratio(),
                    gov, deleg, i))
        for score, gov, deleg, i in sorted(scored, key=lambda t: -t[0]):
            if (gov, deleg) in assigned or i in taken or score < FUZZY_MIN:
                continue
            assigned[(gov, deleg)] = (i, f"fuzzy:{score:.2f}")
            taken.add(i)
        rest = [p for p in items if p not in assigned]
        free = [i for i in pool if i not in taken]
        if len(rest) == 1 and len(free) == 1:
            assigned[rest[0]] = (free[0], "elimination")
        else:
            unresolved.extend((g, d, [pool[i]["delegation_name"] for i in free])
                              for _, d in rest)
    return assigned, unresolved


def reference():
    """(essebsi, marzouki) per Arabic constituency, from the published PV table.

    `data/presidential_2014_constituency.csv` was decoded from ISIE's own
    constituency-level runoff PV in earlier work, and it sums exactly to the
    declared national result. That makes it an independent check on this tree:
    the two were published separately, from different documents, and neither
    was derived from the other.
    """
    out = collections.defaultdict(lambda: [0, 0])
    with open(CONSTITUENCY, encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            if r["round"] != "r2":
                continue
            i = 0 if "السبسي" in r["candidate"] else 1
            out[r["centre"]][i] = int(r["votes"])
    return out


def reconcile(deleg_rows):
    """Per-constituency recovered-minus-published, keyed by Arabic name."""
    ref = reference()
    got = collections.defaultdict(lambda: [0, 0])
    for r in deleg_rows:
        ar = CONSTITUENCY_LABEL[r["governorate_isie"]]
        got[ar][0] += r["essebsi"]
        got[ar][1] += r["marzouki"]
    out = []
    for ar in sorted(ref):
        g, p = got.get(ar, [0, 0]), ref[ar]
        out.append({"constituency": ar,
                    "recovered": g, "published": p,
                    "delta_essebsi": g[0] - p[0],
                    "delta_marzouki": g[1] - p[1],
                    "in_tree": ar in got})
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--write", action="store_true", help="write the datasets")
    args = ap.parse_args()

    ins = list(csv.DictReader(open(INS, encoding="utf-8")))
    ins_govs = sorted({r["governorate_name"] for r in ins})
    by_id = {r["id_delegation"]: r for r in ins}

    books = workbooks()
    gmap = governorate_map({g for g, _ in books}, ins_govs)
    assigned, unresolved = crosswalk(list(books), ins, gmap)
    for g, d, free in unresolved:
        print(f"  UNRESOLVED {g}: {d}  free: {free}")

    bureau_rows, deleg_rows = [], []
    names_seen = collections.Counter()
    unreadable, printed_mismatch, duplicate_codes = [], 0, []
    seen_codes = {}

    for (gov, deleg), path in sorted(books.items()):
        try:
            names, rows = read(path)
        except Exception as exc:                       # noqa: BLE001
            unreadable.append({"governorate": gov, "delegation": deleg,
                               "file": os.path.basename(path),
                               "error": type(exc).__name__})
            continue
        if not rows:
            unreadable.append({"governorate": gov, "delegation": deleg,
                               "file": os.path.basename(path),
                               "error": "no data rows"})
            continue
        names_seen[tuple(names)] += 1
        ins_id, method = assigned.get((gov, deleg), ("", ""))
        rec = by_id.get(ins_id)
        scope = "tunisie" if gmap.get(gov) else "etranger"
        agg = [0, 0]
        n_bureau = 0
        for code, centre, votes, printed in rows:
            if printed is not None and printed != sum(votes):
                printed_mismatch += 1
            agg[0] += votes[0]
            agg[1] += votes[1]
            if scope == "etranger":
                continue
            if code in seen_codes:
                duplicate_codes.append({"bureau_code": code,
                                        "first": "/".join(seen_codes[code]),
                                        "again": f"{gov}/{deleg}"})
                continue
            seen_codes[code] = (gov, deleg)
            n_bureau += 1
            bureau_rows.append({
                "bureau_code": code,
                "delegation_key_2014": code[:4],
                "governorate_isie": gov,
                "delegation_isie": deleg,
                "governorate_name": rec["governorate_name"] if rec else "",
                "delegation_name": rec["delegation_name"] if rec else "",
                "id_delegation": ins_id,
                "region_name": rec["region_name"] if rec else "",
                "polling_centre": centre,
                "essebsi": votes[0],
                "marzouki": votes[1],
                "valid_votes": sum(votes),
                "essebsi_share_pct": round(100.0 * votes[0] / sum(votes), 2) if sum(votes) else "",
                "margin_pp": round(100.0 * (votes[0] - votes[1]) / sum(votes), 2) if sum(votes) else "",
            })
        total = agg[0] + agg[1]
        deleg_rows.append({
            "scope": scope,
            "governorate_isie": gov,
            "delegation_isie": deleg,
            "governorate_name": rec["governorate_name"] if rec else "",
            "delegation_name": rec["delegation_name"] if rec else "",
            "id_delegation": ins_id,
            "region_name": rec["region_name"] if rec else "",
            "match_method": method,
            "n_bureaux": n_bureau,
            "essebsi": agg[0],
            "marzouki": agg[1],
            "valid_votes": total,
            "essebsi_share_pct": round(100.0 * agg[0] / total, 2) if total else "",
            "margin_pp": round(100.0 * (agg[0] - agg[1]) / total, 2) if total else "",
        })

    # The two structural claims, measured rather than asserted.
    claimed = collections.Counter(i for i, _ in assigned.values())
    bijective = not [i for i, n in claimed.items() if n > 1]
    prefixes = collections.defaultdict(set)
    for r in bureau_rows:
        prefixes[r["delegation_key_2014"]].add(r["delegation_isie"])
    split_prefixes = {k: sorted(v) for k, v in prefixes.items() if len(v) > 1}

    e = sum(r["essebsi"] for r in deleg_rows)
    m = sum(r["marzouki"] for r in deleg_rows)
    s = e + m
    print(f"{len(books)} workbooks, {len(unreadable)} unreadable")
    print(f"  bureaux (in-country): {len(bureau_rows):,}")
    print(f"  delegations: {sum(1 for r in deleg_rows if r['scope']=='tunisie')}"
          f" in-country + {sum(1 for r in deleg_rows if r['scope']=='etranger')} abroad")
    print(f"  candidate columns identical across workbooks: "
          f"{names_seen.most_common(1)[0][1]} of {sum(names_seen.values())}")
    print(f"  rows where the printed total disagrees with the sum: {printed_mismatch}")
    print(f"  bureau codes claimed by two delegations: {len(duplicate_codes)}")
    print(f"  crosswalk bijective within every governorate: {bijective}")
    print(f"  code[:4] as a delegation key: {len(prefixes)} prefixes, "
          f"{len(split_prefixes)} spanning more than one delegation")
    print(f"  Essebsi  {e:>9,}  {100.0*e/s:6.2f}%   (declared {DECLARED['essebsi']:,}  55.68%)")
    print(f"  Marzouki {m:>9,}  {100.0*m/s:6.2f}%   (declared {DECLARED['marzouki']:,}  44.32%)")
    print(f"  total    {s:>9,}            (declared {DECLARED['total']:,})")
    print(f"  shortfall {DECLARED['total']-s:,} ({100.0*(DECLARED['total']-s)/DECLARED['total']:.2f}%)")

    rec = reconcile(deleg_rows)
    absent = [r for r in rec if not r["in_tree"]]
    off = [r for r in rec if r["in_tree"]
           and (r["delta_essebsi"] or r["delta_marzouki"])]
    exact = sum(1 for r in rec if r["in_tree"]) - len(off)
    print(f"\n  against the published constituency PV ({len(rec)} constituencies):")
    print(f"    exact to the vote: {exact}")
    for r in absent:
        print(f"    no workbook in the tree: {r['constituency']} "
              f"({sum(r['published']):,} votes)")
    for r in off:
        print(f"    disagrees: {r['constituency']} essebsi {r['delta_essebsi']:+,} "
              f"marzouki {r['delta_marzouki']:+,}")
    unexplained = (DECLARED["total"] - s
                   - sum(sum(r["published"]) for r in absent)
                   + sum(r["delta_essebsi"] + r["delta_marzouki"] for r in off))
    print(f"    shortfall left unexplained: {unexplained:,}")
    for u in unreadable:
        print(f"  unreadable: {u['governorate']}/{u['delegation']} ({u['error']})")

    if not args.write:
        return 0

    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(OUT_BUREAU, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(bureau_rows[0]))
        w.writeheader()
        w.writerows(sorted(bureau_rows, key=lambda r: r["bureau_code"]))
    with open(OUT_DELEG, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(deleg_rows[0]))
        w.writeheader()
        w.writerows(sorted(deleg_rows, key=lambda r: (r["scope"], r["id_delegation"] or "zz",
                                                      r["delegation_isie"])))
    with open(LOG, "w", encoding="utf-8") as fh:
        recs = [
            {"record": "source",
             "tree": "pv-auto-bv-presidentielles-tour2",
             "via": "wayback, see tools/fetch_isie_filebases.py",
             "election": "presidential runoff, 21 December 2014",
             "evidence": ["all workbooks name Essebsi and Marzouki",
                          "workbooks carry a print date of 2014-12-22",
                          "totals reconcile to the declared result within 1.2%"]},
            {"record": "coverage", "workbooks": len(books),
             "unreadable": unreadable,
             "bureaux": len(bureau_rows),
             "delegations_in_country": sum(1 for r in deleg_rows if r["scope"] == "tunisie"),
             "constituencies_abroad": sum(1 for r in deleg_rows if r["scope"] == "etranger")},
            {"record": "reconciliation", "essebsi": e, "marzouki": m, "total": s,
             "declared": DECLARED,
             "share_essebsi": round(100.0 * e / s, 2),
             "share_marzouki": round(100.0 * m / s, 2),
             "shortfall": DECLARED["total"] - s,
             "printed_total_mismatches": printed_mismatch},
            {"record": "reconciliation_by_constituency",
             "against": CONSTITUENCY,
             "constituencies": len(rec),
             "exact_to_the_vote": exact,
             "absent_from_tree": [{"constituency": r["constituency"],
                                   "published": sum(r["published"])}
                                  for r in absent],
             "disagreements": [{"constituency": r["constituency"],
                                "delta_essebsi": r["delta_essebsi"],
                                "delta_marzouki": r["delta_marzouki"]}
                               for r in off],
             "shortfall_unexplained": unexplained},
            {"record": "crosswalk",
             "passes": dict(collections.Counter(
                 v[1].split(":")[0] for v in assigned.values())),
             "fuzzy_min": FUZZY_MIN,
             "bijective_within_governorate": bijective,
             "delegation_key_2014": {"prefixes": len(prefixes),
                                     "spanning_more_than_one": split_prefixes},
             "duplicate_bureau_codes": duplicate_codes},
        ]
        for r in sorted(deleg_rows, key=lambda r: r["delegation_isie"]):
            if r["match_method"] and not r["match_method"].startswith("exact"):
                recs.append({"record": "match", "isie": f"{r['governorate_isie']}/{r['delegation_isie']}",
                             "ins": r["delegation_name"], "id_delegation": r["id_delegation"],
                             "method": r["match_method"]})
        for rec in recs:
            json.dump(rec, fh, ensure_ascii=False)
            fh.write("\n")
    print(f"\nwrote {OUT_BUREAU}, {OUT_DELEG}, {LOG}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
