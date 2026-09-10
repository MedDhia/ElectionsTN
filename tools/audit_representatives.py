"""Standing check over `data/representatives_2024.csv`.

Reads only published files and exits non-zero on a violation, so the claims
made about the representative-presence field stay checkable rather than
resting on the one run that produced it. Every invariant here was shown to
fire against a deliberately perturbed copy of the file.
"""

import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import read_representatives as rr

REPS = rr.OUT
LOG = rr.LOG
PV = "data/pv_presidential_2024.csv"


def load(path):
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def main():
    fails = []

    def check(ok, msg):
        print(("  ok   " if ok else "  FAIL ") + msg)
        if not ok:
            fails.append(msg)

    for p in (REPS, LOG, PV):
        if not os.path.exists(p):
            sys.exit(f"missing {p}")

    rows = load(REPS)
    log = [json.loads(l) for l in open(LOG, encoding="utf-8") if l.strip()]
    method = next((r for r in log if r.get("record") == "method"), None)
    cover = next((r for r in log if r.get("record") == "coverage"), None)

    print(f"{REPS}: {len(rows)} rows")

    check(method is not None and cover is not None,
          "the log carries a method record and a coverage record")

    codes = [r["bureau_code"] for r in rows]
    check(len(set(codes)) == len(codes), "bureau_code is unique")
    check(all(len(c) == 11 and c.isdigit() for c in codes),
          "every bureau_code is 11 digits")

    pv = {r["bureau_code"] for r in load(PV)}
    missing = [c for c in codes if c not in pv]
    check(not missing,
          f"every bureau_code appears in {PV} ({len(missing)} do not)")

    if cover:
        check(cover.get("placed") == len(rows),
              f"the row count matches the log's placed count "
              f"({cover.get('placed')})")
        check(cover.get("placed", 0) + cover.get("unplaced", 0)
              == cover.get("scans"),
              "placed plus unplaced accounts for every scan")
        reasons = cover.get("unplaced_reasons") or {}
        check(sum(reasons.values()) == cover.get("unplaced"),
              f"the unplaced reasons account for every unread scan {reasons}")

    bad_flag = bad_sum = bad_pair = bad_cut = bad_cc = bad_shift = 0
    for r in rows:
        flags, scores = [], []
        for i in (1, 2, 3):
            f, s = r[f"rep_row{i}"], r[f"row{i}_score"]
            if (f == "") != (s == ""):
                bad_pair += 1
                continue
            if f == "":
                continue
            if f not in ("0", "1"):
                bad_flag += 1
                continue
            flags.append(int(f))
            scores.append(float(s))
            if (float(s) >= rr.CUT) != (f == "1"):
                bad_cut += 1
        if int(r["reps_rows_filled"]) != sum(flags):
            bad_sum += 1
        cc = float(r["register_cc"])
        if not (rr.MIN_CC <= cc <= 1.0):
            bad_cc += 1
        try:
            d = int(r["row_shift"])
        except ValueError:
            bad_shift += 1
        else:
            # a shift on the edge of the search window means no interior
            # optimum was found, and such forms are not published at all
            if abs(d) >= rr.SHIFT_SPAN:
                bad_shift += 1

    check(bad_flag == 0, f"rep_row* is 0, 1 or blank ({bad_flag} are not)")
    check(bad_pair == 0,
          f"a blank flag and a blank score always coincide ({bad_pair} do not)")
    check(bad_sum == 0,
          f"reps_rows_filled equals the sum of its row flags ({bad_sum} do not)")
    check(bad_cut == 0,
          f"every flag agrees with its score against the published cut "
          f"{rr.CUT} ({bad_cut} do not)")
    check(bad_cc == 0,
          f"register_cc lies in [{rr.MIN_CC}, 1] ({bad_cc} do not)")
    check(bad_shift == 0,
          f"every row_shift is an interior optimum, |d| < {rr.SHIFT_SPAN} "
          f"({bad_shift} are not)")

    filled = [int(r["reps_rows_filled"]) for r in rows]
    check(all(0 <= f <= 3 for f in filled),
          "reps_rows_filled lies in 0..3")
    if cover and cover.get("filled_row_counts"):
        want = {int(k): v for k, v in cover["filled_row_counts"].items()}
        got = {k: filled.count(k) for k in range(4)}
        check(want == got,
              f"the filled-row distribution matches the log {got}")

    # The load-bearing one: the published flags must still agree with the
    # cells that were labelled by hand. This ties the file to the labels
    # rather than to the code that produced it.
    by_code = {r["bureau_code"]: r for r in rows}
    disagree, checked = [], 0
    for labels in (rr.TUNING, rr.HELD_OUT):
        for code, want in labels.items():
            r = by_code.get(code)
            if r is None:
                continue
            for i in (1, 2, 3):
                if r[f"rep_row{i}"] == "":
                    continue
                checked += 1
                if (r[f"rep_row{i}"] == "1") != (i in want):
                    disagree.append(f"{code} row{i}")
    check(not disagree,
          f"all {checked} hand-labelled cells agree with the published flags"
          + (f" ({', '.join(disagree[:6])})" if disagree else ""))

    print(f"\n{len(fails)} failure(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
