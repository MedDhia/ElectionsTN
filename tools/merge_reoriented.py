"""Publish the blocks that became readable once the scans were turned upright.

`tools/fix_orientation.py` repaired 81 cached scans stored sideways. Twelve of
them were rows with no ballot account at all — a gap this project had written
down as a scan-quality floor. It was not a scan-quality floor. Eleven of the
twelve read cleanly the moment the page was the right way up, and two more of
the 81 turn out to have a readable papers block.

Every reading here is checked twice before it is written: the papers cells
against the form's `(س)`, and the ballot account against the form's `(ب)`. Those
are two different totals on two different parts of the sheet, and a misread digit
almost never satisfies both.

One row is published without being certified. On 13051110102 all five ballot
cells are legible — `(ب) 1100`, `(ج) 0238`, `(د) 0000`, `(ر) 0962` — and the
account comes to 1200 against 1100 delivered. Its papers block closes exactly at
238, so the reading is not in doubt; the *form* is out by a hundred, which is one
sealed pack. The values go in because they are what the sheet says, and
`ballots_certified` stays off because nothing here can vouch for the account.

One row is left unread. 13050310201 is upright now and still too degraded to
resolve a single digit; that one really is the scan-quality floor.

Usage: python3 tools/merge_reoriented.py [--write]
"""
import argparse, csv, json, os, shutil, sys, tempfile

RESULTS = "data/pv_presidential_2024.csv"
LOG = "data/verification/reoriented_readings.jsonl"

# bureau -> ballot cells as the form reads them, once upright.
BALLOTS = {
    "08040710206": dict(d_damaged=0, r_remaining=1870, b_delivered=2000),
    "08080110101": dict(s_extracted=236, d_damaged=4, r_remaining=660,
                        b_delivered=900),
    "08080210201": dict(d_damaged=2, r_remaining=715, b_delivered=1000),
    "08110510103": dict(d_damaged=0, r_remaining=590, b_delivered=800),
    "08110610201": dict(d_damaged=1, r_remaining=405, b_delivered=500),
    "08140110201": dict(d_damaged=1, r_remaining=649, b_delivered=901),
    "08140210205": dict(d_damaged=0, r_remaining=1013, b_delivered=1200),
    "14140610402": dict(d_damaged=0, r_remaining=636, b_delivered=1000),
    "17030410203": dict(d_damaged=0, r_remaining=811, b_delivered=1000),
    "17071010101": dict(d_damaged=0, r_remaining=602, b_delivered=900),
    "13051110102": dict(s_extracted=238, d_damaged=0, r_remaining=962,
                        b_delivered=1100),
}
# Where the account does not reach (ب), the cells are published and the flag is
# withheld rather than the reading being bent to close.
NOT_CERTIFIED = {"13051110102"}

# bureau -> papers cells, for rows whose block was never published.
PAPERS = {
    "08020810201": dict(blank=2, spoilt=11),
    "08110910302": dict(blank=3, spoilt=14),
}


def as_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    rows = list(csv.DictReader(open(RESULTS, encoding="utf-8")))
    fields = list(rows[0].keys())
    by = {r["bureau_code"]: r for r in rows}
    notes = []

    print("ballot accounts")
    for code, new in BALLOTS.items():
        r = by.get(code)
        if r is None:
            sys.exit(f"{code} is not in the dataset")
        before = {k: r[k] for k in new}
        for k, v in new.items():
            r[k] = str(v)
        s, d, rr, b = (as_int(r[k]) for k in
                       ("s_extracted", "d_damaged", "r_remaining", "b_delivered"))
        if None in (s, d, rr, b):
            sys.exit(f"{code}: the account is incomplete after the reading")
        closes = s + d + rr == b
        if code in NOT_CERTIFIED:
            if closes:
                sys.exit(f"{code}: listed as not certifiable but the account "
                         "balances — check the list, not the reading")
        elif not closes:
            sys.exit(f"{code}: {s}+{d}+{rr} != (ب) {b} — refusing to write")
        # The papers block is the second, independent check: it closes against
        # (س), which the ballot account does not use.
        v, bl, sp = (as_int(r[k]) for k in ("valid", "blank", "spoilt"))
        if None not in (v, bl, sp) and v + bl + sp != s:
            sys.exit(f"{code}: papers {v}+{bl}+{sp} != (س) {s}"
                     " — refusing to write")
        if closes:
            r["ballots_certified"] = "1"
        r["status"] = "read_by_eye"
        notes.append({"bureau_code": code, "kind": "ballots",
                      "was": before, "now": {k: str(x) for k, x in new.items()},
                      "closes_b": closes,
                      "note": "read off the scan after tools/fix_orientation.py "
                              "turned the cached page upright"})
        print(f"  {code}: " + ", ".join(
            f"{k} {before[k] or '-'} -> {x}" for k, x in new.items())
            + ("" if closes else f"   account {s + d + rr} vs (ب) {b}"
                                 " — published, not certified"))

    print("\npapers blocks")
    for code, new in PAPERS.items():
        r = by.get(code)
        if r is None:
            sys.exit(f"{code} is not in the dataset")
        before = {k: r[k] for k in new}
        for k, v in new.items():
            r[k] = str(v)
        v, bl, sp, s = (as_int(r[k]) for k in ("valid", "blank", "spoilt",
                                               "s_extracted"))
        if None in (v, bl, sp, s) or v + bl + sp != s:
            sys.exit(f"{code}: papers {v}+{bl}+{sp} != (س) {s}"
                     " — refusing to write")
        r["papers_certified"] = "1"
        r["status"] = "read_by_eye"
        notes.append({"bureau_code": code, "kind": "papers",
                      "was": before, "now": {k: str(x) for k, x in new.items()},
                      "note": f"read off the upright page; {v}+{bl}+{sp} = (س) {s}"})
        print(f"  {code}: " + ", ".join(
            f"{k} {before[k] or '-'} -> {x}" for k, x in new.items())
            + f"   ({v}+{bl}+{sp} = {s})")

    for flag in ("papers_certified", "ballots_certified"):
        n = sum(1 for r in rows if r[flag] == "1")
        print(f"\n{flag:20s} {n:,} of {len(rows):,} ({100 * n / len(rows):.1f}%)")
    lack = sum(1 for r in rows if r["ballots_certified"] != "1")
    print(f"rows with no ballot account: {lack}")

    if not a.write:
        print("\ndry run, dataset untouched")
        return

    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(RESULTS) or ".")
    with os.fdopen(fd, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    if sum(1 for _ in open(tmp, encoding="utf-8")) != len(rows) + 1:
        os.unlink(tmp)
        sys.exit("refusing to install a dataset of the wrong length")
    shutil.move(tmp, RESULTS)
    os.chmod(RESULTS, 0o644)
    with open(LOG, "w", encoding="utf-8") as fh:
        for n in notes:
            fh.write(json.dumps(n, ensure_ascii=False) + "\n")
    print(f"\n-> {RESULTS}\n-> {LOG}")


if __name__ == "__main__":
    main()
