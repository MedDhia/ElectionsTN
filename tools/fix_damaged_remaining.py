"""Repair the ballot rows where (د) took the leading digits of (ر).

`s_extracted + d_damaged + r_remaining == (م)` is the ballot block's identity, and
it constrains the total, not how the total is split. Value moved from `(د)` to
`(ر)` leaves the sum untouched, so the identity closes either way — the same
blind spot the candidate-row transpositions live in, one block over.

Nineteen rows show it, and they were not found by the identity. They were found
by asking a question the arithmetic cannot: whether the numbers are *possible*.
`(د)` is ballots damaged in handling, a few per station; 800 damaged out of 1,100
delivered is not a quantity the form can mean, and neither is 17 remaining after
only 283 of 1,100 were used. Both cells are wrong together, in a way that cancels.

Reading all nineteen off the scans confirms the mechanism exactly. On the form
`(د)` is almost always **0000** and `(ر)` carries the whole remainder; the reader
split `(ر)`'s digits across the two cells. On 01160610102 the form reads
`(د) 0000` and `(ر) 0817` where the dataset published 800 and 17 — and
`800 + 17 = 817`, so the sum survived and the identity never noticed.

Two are not the plain case, which is why every one was read rather than
transformed by rule: 08140310301 has `(د) 0003` with `(ر) 0623` against a
published 603 and 23, and 120208102 has `(د) 0001` with `(ر) 0961` against 201
and 761. A rule that forced `(د)` to zero would have been wrong on both.

One row is withdrawn instead of repaired. On 23090810102 `(د)` reads 0000, but
`(ر)` reads about 850 against a published `d + r` of 200 — so the sum did *not*
survive, and this is a whole account misread rather than a mis-split. The scan is
too faint to say what it should be, so `ballots_certified` comes off and the two
cells are emptied.

Because `d + r` is preserved on the eighteen repairs, no total moves: the ballot
account sums to the same `(م)`, `(ب)` still balances where it balanced before,
and no candidate vote is touched. What changes is that the two columns now say
what the form says.

Usage: python3 tools/fix_damaged_remaining.py [--write]
"""
import argparse, csv, json, os, shutil, sys, tempfile

RESULTS = "data/pv_presidential_2024.csv"
LOG = "data/verification/damaged_remaining.jsonl"

# bureau -> (d_damaged, r_remaining) as the form's (د) and (ر) boxes read.
READINGS = {
    "01160610102": (0, 817),
    "03030110306": (0, 856),
    "05011110201": (0, 445),
    "05071110101": (0, 953),
    "07070510302": (0, 889),
    "07080610202": (0, 839),
    "08140310301": (3, 623),
    "08140410205": (0, 930),
    "120208102":   (1, 961),
    "120702103":   (0, 426),
    "13040110203": (0, 883),
    "13040410603": (0, 867),
    "14081110101": (0, 622),
    "15120610203": (0, 888),
    "17010410101": (0, 594),
    "18040110203": (0, 765),
    "20040410205": (0, 763),
    "20080710105": (0, 1040),
}

# Rows read but not repairable: the account does not survive the reading.
WITHDRAW = {
    "23090810102": "(د) reads 0000 and (ر) about 850 against a published d+r of "
                   "200, so the account was misread rather than mis-split; the "
                   "scan is too faint to settle it",
}

# The forms whose own (ب) does not equal the account, before or after this. Kept
# so the repair is not blamed for a discrepancy that is on the paper: 05011110201
# reads (ب) 0600 against an account of 599 and has its أسباب عدم التطابق line
# filled in explaining a shortfall of ballots.
B_MAY_DIFFER = {"05011110201"}


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

    print("(د) and (ر) as the form reads them")
    for code, (d_new, r_new) in READINGS.items():
        r = by.get(code)
        if r is None:
            sys.exit(f"{code} is not in the dataset")
        d_old, r_old = as_int(r["d_damaged"]), as_int(r["r_remaining"])
        if d_old is None or r_old is None:
            sys.exit(f"{code}: (د) or (ر) is not published — nothing to re-split")
        # The whole claim of this file is that the two cells were mis-split and
        # the sum survived. If a reading breaks that, it is a different error and
        # must not be written as if it were this one.
        if d_new + r_new != d_old + r_old:
            sys.exit(f"{code}: {d_new}+{r_new} != published {d_old}+{r_old}"
                     " — that is not a mis-split, refusing to write")
        s, b = as_int(r["s_extracted"]), as_int(r["b_delivered"])
        if (code not in B_MAY_DIFFER and s is not None and b is not None
                and s + d_new + r_new != b):
            sys.exit(f"{code}: {s}+{d_new}+{r_new} != (ب) {b}"
                     " — refusing to write")
        r["d_damaged"], r["r_remaining"] = str(d_new), str(r_new)
        notes.append({"bureau_code": code, "kind": "resplit",
                      "was": {"d_damaged": d_old, "r_remaining": r_old},
                      "now": {"d_damaged": d_new, "r_remaining": r_new},
                      "note": "(د) and (ر) read off the scan; the reader had put "
                              "(ر)'s leading digits in (د), which the identity "
                              "cannot see because the sum is unchanged"})
        print(f"  {code}: (د) {d_old} -> {d_new},  (ر) {r_old} -> {r_new}"
              f"   (sum {d_old + r_old} unchanged)")

    print("\nwithdrawn")
    for code, why in WITHDRAW.items():
        r = by.get(code)
        if r is None:
            sys.exit(f"{code} is not in the dataset")
        was = {k: r[k] for k in ("d_damaged", "r_remaining", "ballots_certified")}
        r["d_damaged"] = r["r_remaining"] = ""
        r["ballots_certified"] = "0"
        notes.append({"bureau_code": code, "kind": "withdrawn",
                      "was": was, "now": {"d_damaged": "", "r_remaining": "",
                                          "ballots_certified": "0"},
                      "note": why})
        print(f"  {code}: " + ", ".join(f"{k} {v or '-'}" for k, v in was.items())
              + " -> withdrawn")

    plausible = sum(1 for r in rows if (as_int(r["d_damaged"]) or 0) >= 100)
    n = sum(1 for r in rows if r["ballots_certified"] == "1")
    print(f"\n(د) at 100 or more: {plausible} rows remaining")
    print(f"ballots_certified: {n:,} of {len(rows):,} ({100 * n / len(rows):.1f}%)")

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
        for note in notes:
            fh.write(json.dumps(note, ensure_ascii=False) + "\n")
    print(f"\n-> {RESULTS}\n-> {LOG}")


if __name__ == "__main__":
    main()
