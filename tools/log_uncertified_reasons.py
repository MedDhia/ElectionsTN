"""Give the last four uncertified stations the reason the other 27 already have.

`docs/PV_OFFLINE_READING.md` says the stations without certified votes are "a
closed list, not a backlog: each is recorded in
`data/verification/unreadable_scans.jsonl` with a reason". That was true of 27 of
the 31. Four had no entry at all, so the claim was overstated by four rows —
which is exactly the kind of gap a closed list is supposed to make impossible.

Each of the four has a determinable reason, and they are not the same reason:

- **10020210101 — the form contradicts itself.** Its candidate table reads
  `0000` / `0008` / `0232` with the Arabic words صفر / واحد / مائتين واثنان
  وثلاثون beside them, so both channels put Saied at 232 and the table sums to
  233 at most. But the sheet's own `(ق)` reads 0333 and its `(ص)` reads 0333, and
  those are corroborated by `(س) 0346 = 333 + 4 + 9` and by a ballot account of
  `346 + 3 + 851 = 1200`. The papers and ballot blocks are certified and
  consistent; it is the candidate table that does not agree with the total the
  same form declares, by a hundred. No reading can certify that, and picking the
  total over the table would invent a candidate's votes.

- **11040610202 — the candidate table is off the page.** Recovered by
  `tools/fix_zero_rows.py` for its papers and ballot blocks, which are published;
  the scan simply does not contain the rows the votes identity needs.

- **23060210102 and 23061510302 — the scan is 568x416 and 552x392 pixels for the
  whole page.** At that size a four-digit field is a few pixels tall. This is the
  resolution floor, and it is the same floor `docs/PV_OFFLINE_READING.md` records
  for the other stations in that governorate.

Nothing is published here. This only writes down why four rows are empty, so the
list is closed in fact and not just in the sentence describing it.

Usage: python3 tools/log_uncertified_reasons.py [--write]
"""
import argparse, csv, json, os, sys

RESULTS = "data/pv_presidential_2024.csv"
LOG = "data/verification/unreadable_scans.jsonl"

REASONS = {
    "10020210101":
        "the form contradicts itself: the candidate table reads 0000/0008/0232 "
        "with the words صفر / واحد / مائتين واثنان وثلاثون, summing to 233 at "
        "most, while the same sheet's (ق) and (ص) both read 0333 — corroborated "
        "by (س) 0346 = 333+4+9 and by a ballot account of 346+3+851 = 1200. The "
        "papers and ballot blocks are certified; the candidate table is a "
        "hundred short of the total the form declares, and no reading can settle "
        "which the officers meant",
    "11040610202":
        "the candidate table is off the published page; the papers and ballot "
        "blocks were recovered by tools/fix_zero_rows.py and are published, but "
        "the scan does not contain the rows the votes identity needs",
    "23060210102":
        "the published scan is 568x416 for the whole page, so a four-digit field "
        "is a few pixels tall — the resolution floor, as for the other stations "
        "in مدنين",
    "23061510302":
        "the published scan is 552x392 for the whole page — the resolution floor, "
        "as for the other stations in مدنين",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    rows = {r["bureau_code"]: r for r in
            csv.DictReader(open(RESULTS, encoding="utf-8"))}
    existing, lines = set(), []
    if os.path.exists(LOG):
        for line in open(LOG, encoding="utf-8"):
            lines.append(line.rstrip("\n"))
            existing.add(json.loads(line)["bureau_code"])

    uncertified = {c for c, r in rows.items() if r["votes_certified"] != "1"}
    print(f"{len(uncertified)} stations without certified votes; "
          f"{len(uncertified & existing)} already have a logged reason")

    added = []
    for code, why in REASONS.items():
        if code not in rows:
            sys.exit(f"{code} is not in the dataset")
        if code not in uncertified:
            print(f"  {code}: now certified — no reason needed, skipped")
            continue
        if code in existing:
            print(f"  {code}: already logged, skipped")
            continue
        r = rows[code]
        added.append({"bureau_code": code, "note": why,
                      "papers_certified": r["papers_certified"],
                      "ballots_certified": r["ballots_certified"],
                      "reading": r["reading"], "status": r["status"]})
        print(f"  {code}: {why[:88]}...")

    missing = uncertified - existing - set(REASONS)
    if missing:
        sys.exit(f"still unlogged, and not covered here: {sorted(missing)}")
    print(f"\n{len(added)} reasons to add; every uncertified station would then "
          "have one")

    if not a.write:
        print("\ndry run, log untouched")
        return
    with open(LOG, "a", encoding="utf-8") as fh:
        for n in added:
            fh.write(json.dumps(n, ensure_ascii=False) + "\n")
    print(f"\n-> {LOG} (+{len(added)})")


if __name__ == "__main__":
    main()
