"""Withdraw four `a_registered_ok` flags that contradict their own row.

The defect
----------
`a_registered_ok` is documented as "1 when `a_registered >= w_voted`; 0 flags a
reading known to be wrong". Four rows carry `1` while their own columns say
otherwise -- 174 registered against 304 who voted, and three like it. Their
`turnout_pct` is stale to match: bureau `01170210104` publishes `4.24` where its
columns give 174.7%. A repair tool changed the counts at some point and did not
refresh what was derived from them.

Nothing here re-reads a scan. The four rows are demoted to what the form's own
arithmetic says they are worth: `a_registered_ok = 0`, and the turnout blanked,
which is exactly what the file already does for every other unusable
denominator. `tools/audit_identities.py` gains the check so it cannot recur.

Why not simply re-derive every row
----------------------------------
Because it would make the file worse, which was measured before choosing:
re-running `fix_degenerate_blocks.derive()` over all 9,448 rows would touch
**977** of them. It would publish a **343.94%** turnout on rows the file
currently and rightly leaves blank -- that helper computes `100*w/a` whenever
`a` is positive, without asking whether the reading is usable -- and it would
blank 626 flags that are doing their job. The published file's conventions are
stricter than the helper's, so they are preserved rather than overwritten.

The invariant that matters, `turnout_pct` is populated exactly when
`a_registered_ok == 1`, holds on all 9,448 rows before this change and still
holds after it: setting a flag to 0 blanks the turnout in the same step.

Left alone deliberately
-----------------------
A further 74 rows write `''` where 626 otherwise-identical rows write `'0'` for
a denominator that is missing entirely. Both mean "unusable" and nothing reads
the difference, so churning 74 rows of a published dataset to tidy it would be
cost without benefit. It is recorded here rather than silently ignored.
"""

import argparse
import csv
import io
import json
import os
import sys

PV = "data/pv_presidential_2024.csv"
LOG = "data/verification/registered_flags.jsonl"


def as_int(v):
    return int(v) if v not in (None, "", "NA") else None


def offenders(rows):
    """Rows claiming a sound denominator that their own columns contradict."""
    out = []
    for r in rows:
        a, w = as_int(r["a_registered"]), as_int(r["w_voted"])
        if r.get("a_registered_ok") == "1" and a is not None and w is not None \
                and a < w:
            out.append(r)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--write", action="store_true",
                    help="apply the change (default is a dry run)")
    args = ap.parse_args()

    with open(PV, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        fields = reader.fieldnames
        rows = list(reader)

    bad = offenders(rows)
    print(f"{len(rows):,} rows; {len(bad)} carry a_registered_ok = 1 against "
          f"their own columns")
    records = []
    for r in bad:
        a, w = as_int(r["a_registered"]), as_int(r["w_voted"])
        print(f"  {r['bureau_code']}  a_registered={a:>6}  w_voted={w:>6}  "
              f"turnout_pct={r.get('turnout_pct','')!r} -> blank   "
              f"(columns imply {100.0 * w / a:.1f}%)")
        records.append({
            "bureau_code": r["bureau_code"], "a_registered": a, "w_voted": w,
            "turnout_pct_withdrawn": r.get("turnout_pct", ""),
            "implied_turnout_pct": round(100.0 * w / a, 2),
            "a_registered_ok": "1 -> 0",
            "reason": "a_registered < w_voted, so the denominator cannot be "
                      "the one the form reports",
        })

    # The invariant this must not break, checked before and after.
    def consistent(rs):
        return all((r.get("turnout_pct", "") != "")
                   == (r.get("a_registered_ok") == "1") for r in rs)

    if not consistent(rows):
        sys.exit("turnout_pct/a_registered_ok were already inconsistent; "
                 "investigate before writing")

    for r in bad:
        r["a_registered_ok"] = "0"
        r["turnout_pct"] = ""

    if not consistent(rows):
        sys.exit("the change broke the turnout_pct/a_registered_ok invariant")
    still = offenders(rows)
    if still:
        sys.exit(f"{len(still)} offending rows survived the change")
    print("invariant holds after the change: turnout_pct is populated exactly "
          "where a_registered_ok == 1")

    if not args.write:
        print("\ndry run; pass --write to apply")
        return 0

    # csv writes \r\n by default and the published file is CRLF, so this is
    # kept explicit rather than left to the default -- a line-ending flip would
    # rewrite all 9,448 rows instead of the four that changed.
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields, lineterminator="\r\n")
    w.writeheader()
    w.writerows(rows)
    with open(PV, "w", encoding="utf-8", newline="") as fh:
        fh.write(buf.getvalue())
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
    print(f"\nwrote {PV} and {LOG} ({len(records)} records)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
