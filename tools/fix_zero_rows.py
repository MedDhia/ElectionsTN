"""Repair the stations the votes identity certified on a page of zeros.

`zammel + maghzaoui + saied == valid` is the identity that vouches for the
candidate total, and it has a solution the gate could not tell from a reading:
**zero**. A page with no candidate cells on it at all — the polling record
(محضر عملية الاقتراع) rather than the counting record (محضر عملية الفرز) — reads
as four empty fields, the reader emits 0 for each, and `0 + 0 + 0 == 0` closes
exactly. Ten stations were published that way, with every candidate on zero.

None of them is a station where nobody voted. Six hold no counting record in the
bundle at all: the only page the archive has for them is the polling record, so
their candidate votes are not recoverable and the rows are withdrawn. Three hold
a counting record the page chooser or the orientation pass had missed — one
scanned mirror-image, one landscape, one simply misread — and are restored here
from the scan, in full, identities closing. The tenth has a counting record whose
candidate table falls outside the scanned area: its papers and ballots blocks are
published and its votes are not.

The values below were read off the scans by eye. Every one is checked against the
form's own arithmetic before it is written, and the tool refuses to write a row
whose numbers do not close.

Usage: python3 tools/fix_zero_rows.py [--write]
"""
import argparse, csv, json, os, shutil, sys, tempfile

RESULTS = "data/pv_presidential_2024.csv"
UNREADABLE = "data/verification/unreadable_scans.jsonl"

# Stations restored from the scan. Keys are CSV columns; a block is published
# only when the identity over it closes, which is asserted below.
RESTORED = {
    "03020510204": dict(  # أريانة / المنيهلة — counting record present, read as zeros
        a_registered=980, b_delivered=900, c_signed=348, d_damaged=0, r_remaining=552,
        s_extracted=348, valid=328, blank=5, spoilt=15, w_voted=348, q_declared=328,
        zammel=7, maghzaoui=2, saied=319),
    "07050510101": dict(  # سليانة — the scan is mirror-image, so nothing registered
        a_registered=457, b_delivered=500, c_signed=118, d_damaged=0, r_remaining=382,
        s_extracted=118, valid=108, blank=7, spoilt=3, w_voted=118, q_declared=108,
        zammel=3, maghzaoui=1, saied=104),
    "04050210207": dict(  # منوبة — counting record sits on a later page of the bundle
        a_registered=1263, b_delivered=1200, c_signed=354, d_damaged=0, r_remaining=846,
        s_extracted=354, valid=341, blank=7, spoilt=6, w_voted=354, q_declared=341,
        zammel=7, maghzaoui=4, saied=330),
    "11040610202": dict(  # زغوان — landscape scan; the candidate table is off the page
        a_registered=878, b_delivered=800, c_signed=280, d_damaged=0, r_remaining=520,
        s_extracted=280, valid=268, blank=6, spoilt=6, w_voted=280),
}

# Stations whose bundle holds only the polling record. Nothing on the page is a
# candidate count, so the row is withdrawn rather than published as zeros.
WITHDRAWN = {
    "05011110101": "جندوبة",
    "07020210101": "سليانة",
    "07080610302": "سليانة",
    "12060410102": "القيروان",
    "16020410102": "توزر",
    "19050810302": "المهدية",
}

CAND = ("zammel", "maghzaoui", "saied")
VALUES = ("a_registered", "b_delivered", "c_signed", "d_damaged", "r_remaining",
          "s_extracted", "valid", "blank", "spoilt", "w_voted", "q_declared",
          "zammel", "maghzaoui", "saied")
DERIVED = ("candidate_sum", "turnout_pct", "saied_share_pct", "margin",
           "identities_ok", "cells_corrected", "logp_conceded",
           "fields_read", "fields_published", "fields_located",
           "split_corroborated", "valid_corroborated")


def check(code, v):
    """Assert the identities that decide which blocks may be published."""
    votes = all(k in v for k in CAND)
    if votes and sum(v[k] for k in CAND) != v["valid"]:
        sys.exit(f"{code}: candidates sum to {sum(v[k] for k in CAND)}, "
                 f"valid {v['valid']} — refusing to write")
    if v["s_extracted"] != v["valid"] + v["blank"] + v["spoilt"]:
        sys.exit(f"{code}: {v['s_extracted']} extracted != "
                 f"{v['valid']}+{v['blank']}+{v['spoilt']} — refusing to write")
    if v["s_extracted"] + v["d_damaged"] + v["r_remaining"] != v["b_delivered"]:
        sys.exit(f"{code}: ballots do not account to {v['b_delivered']} delivered "
                 "— refusing to write")
    return votes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    rows = list(csv.DictReader(open(RESULTS, encoding="utf-8")))
    fields = list(rows[0].keys())
    by = {r["bureau_code"]: r for r in rows}

    degenerate = [r["bureau_code"] for r in rows
                  if r["votes_certified"] == "1" and r["candidate_sum"] == "0"
                  and all(r[c] == "0" for c in CAND)]
    print(f"{len(degenerate)} certified rows whose candidates all read zero")
    unknown = set(degenerate) - set(RESTORED) - set(WITHDRAWN)
    if unknown:
        sys.exit("not accounted for by this tool: " + ", ".join(sorted(unknown)))

    for code, v in RESTORED.items():
        votes = check(code, v)
        r = by[code]
        for k in VALUES:
            r[k] = str(v[k]) if k in v else ""
        r["candidate_sum"] = str(sum(v[k] for k in CAND)) if votes else ""
        r["turnout_pct"] = str(round(100 * v["w_voted"] / v["a_registered"], 2))
        r["saied_share_pct"] = (str(round(100 * v["saied"] / v["valid"], 2))
                                if votes else "")
        r["a_registered_ok"] = "1"
        r["votes_certified"] = "1" if votes else "0"
        r["papers_certified"] = "1"
        r["ballots_certified"] = "1"
        r["reading"] = "vision"
        r["status"] = "read_by_eye"
        for k in ("identities_ok", "cells_corrected", "logp_conceded", "margin",
                  "fields_read", "fields_published", "fields_located",
                  "split_corroborated", "valid_corroborated"):
            r[k] = ""
        print(f"  restored {code}: "
              + (f"{v['zammel']}/{v['maghzaoui']}/{v['saied']} of {v['valid']}"
                 if votes else "papers and ballots only, no candidate table on the scan"))

    notes = []
    for code, gov in WITHDRAWN.items():
        r = by[code]
        for k in VALUES + DERIVED:
            r[k] = ""
        r["a_registered_ok"] = "0"
        for k in ("votes_certified", "papers_certified", "ballots_certified"):
            r[k] = "0"
        r["reading"], r["status"] = "none", "unverified"
        notes.append({"bureau_code": code, "governorate": gov,
                      "reason": "no_counting_record",
                      "note": "the bundle holds only the polling record "
                              "(محضر عملية الاقتراع); no page carries the candidate "
                              "counts. The row had been certified on a reading of "
                              "zeros, which the votes identity satisfies trivially."})
        print(f"  withdrew {code}: no counting record in the bundle")

    if not a.write:
        print("\ndry run, dataset untouched")
        return

    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(RESULTS) or ".")
    with os.fdopen(fd, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    shutil.move(tmp, RESULTS)

    have = set()
    if os.path.exists(UNREADABLE):
        have = {json.loads(l)["bureau_code"] for l in open(UNREADABLE, encoding="utf-8")}
    with open(UNREADABLE, "a", encoding="utf-8") as fh:
        for n in notes:
            if n["bureau_code"] not in have:
                fh.write(json.dumps(n, ensure_ascii=False) + "\n")
    print(f"\n-> {RESULTS}\n-> {UNREADABLE}")


if __name__ == "__main__":
    main()
