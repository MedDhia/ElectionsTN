"""Read the 57 rows where (ب) does not balance the ballot account.

مطابقة 2 is the sheet's own request that `(ب) delivered - (م) = 0`, and 57 rows
failed it. Unlike the (د)/(ر) mis-splits, the sum does not survive here: a value
is genuinely lost, so one of the four cells is wrong or the form does not
balance. The identity cannot tell those apart, and neither can a rule. Each was
read off the scan.

They come out in three groups, and the split is the finding:

**34 are reading errors, and recoverable.** Almost all are one digit. The
dominant shape is a *dropped leading digit in* `(ر)`: 01040110103 reads
`(ر) 1088` where the dataset published 88, and 112 + 1088 = 1200 = `(ب)`
exactly; 23050710502 reads 1023 against a published 23; 09090710101 reads 904
against 4. The rest are a misread `(ب)` — 2100 for 1100, 1400 for 1000, 990 for
900 — or a single wrong digit. After repair 31 of the 34 balance `(ب)` exactly.

**3 are illegible, and lose their value rather than gain one.** On 01151010103
the `(ب)` box is written over and reads 1099 or 1100, not the published 1200; on
05010210101 `(ر)` is 905 or 909, not the published 209; on 13070210101 both
`(ب)` and `(ر)` carry strike-throughs. In each case the published number is
demonstrably wrong and the right one cannot be read, so the cell is emptied and
the certification withdrawn. Choosing between 905 and 909 by which one closes
`(ب)` would be letting the identity pick the digit — which is the circularity
this whole file exists to check.

**20 are not reading errors at all: the form does not balance.** Every published
value matches the scan, and the sheet's own arithmetic is short or over. On most
of them the officers wrote why, on the أسباب عدم التطابق line, and the
explanations are specific and mundane — a sealed pack that held 99 ballots
instead of 100, or 101; a voter who signed the roll and left without voting; two
ballots found stuck together. 21120110102 says simply **لا يوجد تفسير**, "there
is no explanation". Three more carry no note and are short by 3, over by 4, and
short by 800.

Those twenty are left exactly as published. They are the reason مطابقة 2 is
reported by `tools/audit_identities.py` and never treated as a violation: a form
that does not balance is a fact about the count, and overwriting it to make the
column tidy would be destroying the only evidence that it happened.

Nothing here touches a candidate vote, `valid`, or `s_extracted`; the ballot
account carries no result.

Usage: python3 tools/fix_ballot_delivered.py [--write]
"""
import argparse, csv, json, os, shutil, sys, tempfile

RESULTS = "data/pv_presidential_2024.csv"
LOG = "data/verification/ballot_delivered.jsonl"

# bureau -> (fields to set, what the scan says)
REPAIRS = {
    "01040110103": (dict(r_remaining=1088), "(ر) reads 1088; the leading 1 was dropped"),
    "01151410202": (dict(r_remaining=707), "(ر) reads 0707; the 7 was read as a 3"),
    "02070110204": (dict(b_delivered=1100), "(ب) reads 1100, not 1102"),
    "02100710204": (dict(r_remaining=941), "(ر) reads 0941; the leading 9 was dropped"),
    "02120110102": (dict(b_delivered=1100), "(ب) reads 1100, not 1700"),
    "02120210101": (dict(r_remaining=675), "(ر) reads 0675; the leading 6 was dropped"),
    "03060110101": (dict(r_remaining=423), "(ر) reads 0423, not 427"),
    "05030110204": (dict(r_remaining=753), "(ر) reads 0753, not 754"),
    "05030510202": (dict(r_remaining=726), "(ر) reads 0726; the 7 was read as a 3"),
    "06030210101": (dict(r_remaining=172), "(ر) reads 0172, not 173"),
    "06030510101": (dict(b_delivered=1099),
                    "(ب) reads 1099, not 1100; the أسباب line says the second "
                    "pack held ninety-nine"),
    "07060510101": (dict(r_remaining=512), "(ر) reads 0512; the leading 5 was dropped"),
    "07070310301": (dict(r_remaining=733), "(ر) reads 0733; the leading 7 was dropped"),
    "07100810201": (dict(b_delivered=1100), "(ب) reads 1100, not 1900"),
    "07100910201": (dict(b_delivered=801), "(ب) reads 0801, not 802"),
    "08120810101": (dict(d_damaged=1), "(د) reads 0001, not 0000"),
    "09030810201": (dict(r_remaining=410), "(ر) reads 0410; the leading 4 was dropped"),
    "09090710101": (dict(r_remaining=904), "(ر) reads 0904; the leading 9 was dropped"),
    "10120610101": (dict(b_delivered=1100), "(ب) reads 1100, not 2100"),
    "10120610403": (dict(r_remaining=717), "(ر) reads 0717; the leading 7 was dropped"),
    "120206103":   (dict(b_delivered=900), "(ب) reads 0900, not 990"),
    "12030210302": (dict(d_damaged=0), "(د) reads 0000, not 0001"),
    "120811102":   (dict(b_delivered=600), "(ب) reads 0600, not 604"),
    "13060310301": (dict(r_remaining=209), "(ر) reads 0209; the leading 2 was dropped"),
    "13130610201": (dict(b_delivered=1000), "(ب) reads 1000, not 1004"),
    "14010810301": (dict(b_delivered=1300), "(ب) reads 1300, not 1308"),
    "15020110401": (dict(b_delivered=1000, r_remaining=630),
                    "(ب) reads 1000, not 1400, and (ر) reads 0630 against a "
                    "published 30"),
    "17070310201": (dict(b_delivered=800), "(ب) reads 0800, not 840"),
    "18150410102": (dict(b_delivered=1000), "(ب) reads 1000, not 1050"),
    "19070810202": (dict(r_remaining=590), "(ر) reads 0590; the leading 5 was dropped"),
    "21120910102": (dict(b_delivered=1199), "(ب) reads 1199, not 1200"),
    "22080310101": (dict(b_delivered=1100), "(ب) reads 1100, not 1102"),
    "23050710502": (dict(r_remaining=1023), "(ر) reads 1023; the leading 1 was dropped"),
    "23060810301": (dict(b_delivered=600, r_remaining=501),
                    "(ب) reads 0600 against a published 100, and (ر) reads 0501 "
                    "against a published 0"),
}

# Repairs that still leave a gap, because the *form* has one and says so. Each
# of these three has its أسباب عدم التطابق line filled in describing a sealed
# pack that held 101 ballots instead of 100 — which is exactly the residual.
RESIDUAL_DOCUMENTED = {"02070110204", "14010810301", "22080310101"}

# Cells that cannot be read, whose published value is nonetheless wrong.
ILLEGIBLE = {
    "01151010103": (("b_delivered",),
                    "(ب) is written over and reads 1099 or 1100, not the "
                    "published 1200; the account is 1100 and choosing between "
                    "them by which one closes would be the identity picking the "
                    "digit"),
    "05010210101": (("r_remaining",),
                    "(ر) reads 0905 or 0909, not the published 209; 909 closes "
                    "against (ب) 1200 and 905 does not, which is not a reason to "
                    "prefer it"),
    "13070210101": (("b_delivered", "r_remaining"),
                    "(ب) has its leading cell struck through and (ر) has an "
                    "illegible hundreds digit; the published (ر) 15 is certainly "
                    "wrong, the cell holding a three-digit value"),
}

# Read, matching the scan exactly, and left alone: the form does not balance.
# Recorded so the reading is on the record and nobody reads them again.
UNBALANCED = {
    "01100610101": "أسباب: a voter signed the roll and no ballot was deposited",
    "03050610302": "أسباب: a voter signed and then refused to vote",
    "05011110201": "أسباب: a pack was ninety-nine ballots short of its count",
    "06020210301": "أسباب: a voter signed and left",
    "06070310201": "أسباب filled; the account is one over (ب)",
    "07040510103": "أسباب filled; the account is one short of (ب)",
    "08040210401": "أسباب: damaged ballots found; the account is two short",
    "12040910301": "أسباب filled; the account is two over (ب)",
    "14010810101": "أسباب: pack 1 held ninety-nine ballots, not a hundred",
    "14090310301": "أسباب: a damaged ballot; the account is one short",
    "14111110201": "أسباب: a voter signed and did not vote",
    "17060510102": "no أسباب note; the account is 598 short of (ب) 999",
    "17070910201": "أسباب: two ballots were found stuck together",
    "18050410205": "أسباب filled; the account is one short of (ب) 1100",
    "19100710101": "no أسباب note; the account is four over (ب) 900",
    "21100410201": "no أسباب note; the account is 800 short of (ب) 1100",
    "21100710305": "أسباب: one pack held 101 and another was short",
    "21110210101": "أسباب: a voter did not put the ballot in the box",
    "21120110102": "أسباب: لا يوجد تفسير — the officers record no explanation",
    "13090510301": "no أسباب note; the account is three short of (ب) 1100",
}


def as_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def account(r):
    vs = [as_int(r[k]) for k in ("s_extracted", "d_damaged", "r_remaining")]
    return None if any(v is None for v in vs) else sum(vs)


def check(code, r):
    """A repair must land on the form's own (ب), unless the form itself does not."""
    acc, b = account(r), as_int(r["b_delivered"])
    if acc is None or b is None:
        return
    if acc != b and code not in RESIDUAL_DOCUMENTED:
        sys.exit(f"{code}: account {acc} != (ب) {b} after repair"
                 " — refusing to write")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    rows = list(csv.DictReader(open(RESULTS, encoding="utf-8")))
    fields = list(rows[0].keys())
    by = {r["bureau_code"]: r for r in rows}
    notes = []

    print(f"repaired ({len(REPAIRS)})")
    for code, (new, why) in REPAIRS.items():
        r = by.get(code)
        if r is None:
            sys.exit(f"{code} is not in the dataset")
        before = {k: r[k] for k in new}
        for k, v in new.items():
            r[k] = str(v)
        check(code, r)
        acc, b = account(r), as_int(r["b_delivered"])
        tail = "" if acc == b else f"   residual {acc - b:+d}, documented on the form"
        notes.append({"bureau_code": code, "kind": "repaired", "note": why,
                      "was": before, "now": {k: str(v) for k, v in new.items()}})
        print(f"  {code}: " + ", ".join(
            f"{k} {before[k] or '-'} -> {v}" for k, v in new.items()) + tail)

    print(f"\nemptied, the cell being illegible ({len(ILLEGIBLE)})")
    for code, (cols, why) in ILLEGIBLE.items():
        r = by.get(code)
        if r is None:
            sys.exit(f"{code} is not in the dataset")
        before = {k: r[k] for k in cols}
        for k in cols:
            r[k] = ""
        r["ballots_certified"] = "0"
        notes.append({"bureau_code": code, "kind": "illegible", "note": why,
                      "was": before,
                      "now": {k: "" for k in cols} | {"ballots_certified": "0"}})
        print(f"  {code}: " + ", ".join(f"{k} {before[k] or '-'}" for k in cols)
              + " -> emptied, ballots_certified withdrawn")

    print(f"\nleft as published, the form itself not balancing ({len(UNBALANCED)})")
    for code, why in UNBALANCED.items():
        r = by.get(code)
        if r is None:
            sys.exit(f"{code} is not in the dataset")
        acc, b = account(r), as_int(r["b_delivered"])
        notes.append({"bureau_code": code, "kind": "unbalanced", "note": why,
                      "account": acc, "b_delivered": b,
                      "gap": None if None in (acc, b) else acc - b})
        print(f"  {code}: account {acc} vs (ب) {b}   {why}")

    gap = [r for r in rows if r["ballots_certified"] == "1"
           and account(r) is not None and as_int(r["b_delivered"]) is not None
           and account(r) != as_int(r["b_delivered"])]
    n = sum(1 for r in rows if r["ballots_certified"] == "1")
    print(f"\nمطابقة 2 failures remaining: {len(gap)}")
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
