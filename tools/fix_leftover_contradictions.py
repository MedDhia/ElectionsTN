"""Close three of the eight papers contradictions that were read and left.

`tools/fix_papers_contradictions.py` repaired 21 rows where a papers cell was
misread and left 8 where the reading did not settle it. Three of those eight are
settled now, two of them by things learned since.

**13120810101 — the scan is sideways.** It was left because "the cached page is
rotated 90 degrees and the block could not be laid out for reading". Rendering it
at 270 degrees makes the whole form legible, and it reads clean: `(س) 0183`,
`(ص) 0177`, `(ع) 0000`, `(ف) 0006`, which closes at 183, and a ballot account of
`(ب) 0600`, `(د) 0000`, `(ر) 0417` closing at 600. The published `s_extracted`
185 was the misread. This row gains a whole ballot account it never had.

**22090310301 — the ambiguous digit resolves.** It was left because "the last
digit of (س) is an ambiguous 8/9; 129 would close and 128 would not, which is not
enough to" decide. At magnification the glyph has a closed bowl and a descending
tail: a 9. Read as 129 the papers block closes exactly, `125 + 2 + 2`. It costs a
one-ballot gap in مطابقة 2 — and a one-ballot gap there is the single commonest
discrepancy in this corpus, appearing on twenty forms whose officers wrote down
why. A papers block off by one is a reading error; a ballot account off by one is
an ordinary night at a polling station.

**05070410503 — the form contradicts itself, so a flag comes off.** The form's
`(ص)` reads 0196 and is corroborated by everything around it: `196 + 3 + 6 = 205`
matches `(س)`, `(ن)` and `(و)`, and the ballot account `205 + 0 + 695` matches
`(ب) 0900`. But its candidate table sums to 195, and the Arabic words agree with
the digits there, so both readers would have to have made the same error. The
discrepancy is on the paper: the candidate rows are one short of the sheet's own
valid-vote total.

The dataset publishes one `valid` column, and it cannot be 195 for the votes
identity and 196 for the papers one. The candidate total is the number that
carries the result and it has two independent readers behind it, so it stays at
195 and `papers_certified` is withdrawn. Recording the form's own 196 in the log
rather than in the column is the only way to keep both facts.

Five of the eight remain, all read and all logged: 13040410402 (off by 10),
02110310201 and 02111210201 (off by 4, and one scan serving both codes),
12060810201 (both `(س)` and `(ص)` written over), and 18070510106 (off by 1).
Those are forms that do not add up, not readings that failed.

Usage: python3 tools/fix_leftover_contradictions.py [--write]
"""
import argparse, csv, json, os, shutil, sys, tempfile

RESULTS = "data/pv_presidential_2024.csv"
LOG = "data/verification/leftover_contradictions.jsonl"

CAND = ("zammel", "maghzaoui", "saied")

FIXES = {
    "13120810101": (dict(s_extracted=183, d_damaged=0, r_remaining=417,
                         b_delivered=600, ballots_certified=1),
                    "rendered at 270 degrees the form reads (س) 0183, (ص) 0177, "
                    "(ع) 0000, (ف) 0006 closing at 183, and (ب) 0600 with "
                    "(د) 0000 and (ر) 0417 closing at 600; the published (س) 185 "
                    "was the misread"),
    "22090310301": (dict(s_extracted=129),
                    "the last digit of (س) is a 9, not an 8: 125 + 2 + 2 = 129 "
                    "closes the papers block, at the cost of a one-ballot gap in "
                    "مطابقة 2 of the kind twenty other forms document"),
    "05070410503": (dict(papers_certified=0),
                    "the form's (ص) reads 0196 and closes with (ع) 3 and (ف) 6 "
                    "against (س), (ن), (و) 0205 and a ballot account of 0900, but "
                    "its candidate table sums to 195 and the Arabic words agree "
                    "with the digits; one `valid` column cannot be both, so the "
                    "candidate total stands and the papers flag comes off"),
}


def as_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def check(code, r):
    v = {k: as_int(r[k]) for k in
         CAND + ("valid", "blank", "spoilt", "s_extracted", "d_damaged",
                 "r_remaining", "b_delivered")}
    if r["votes_certified"] == "1":
        if any(v[c] is None for c in CAND) or v["valid"] is None:
            sys.exit(f"{code}: certified votes with an unreadable field")
        if sum(v[c] for c in CAND) != v["valid"]:
            sys.exit(f"{code}: candidates sum to {sum(v[c] for c in CAND)} "
                     f"against valid {v['valid']} — refusing to write")
    # (س) stands in for the unpublished (ن) wherever مطابقة 1 is zero, which is
    # the only reason the papers block can be checked here at all.
    if r["papers_certified"] == "1" and all(
            v[k] is not None for k in ("s_extracted", "valid", "blank", "spoilt")):
        if v["s_extracted"] != v["valid"] + v["blank"] + v["spoilt"]:
            sys.exit(f"{code}: (س) {v['s_extracted']} != "
                     f"{v['valid']}+{v['blank']}+{v['spoilt']}"
                     " — refusing to write")
    if r["ballots_certified"] == "1" and all(
            v[k] is not None for k in ("s_extracted", "d_damaged", "r_remaining")):
        acc = v["s_extracted"] + v["d_damaged"] + v["r_remaining"]
        if v["b_delivered"] is not None and acc != v["b_delivered"]:
            print(f"      note: {code} account {acc} vs (ب) {v['b_delivered']}"
                  f" — مطابقة 2 gap {acc - v['b_delivered']:+d}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    rows = list(csv.DictReader(open(RESULTS, encoding="utf-8")))
    fields = list(rows[0].keys())
    by = {r["bureau_code"]: r for r in rows}
    notes = []

    for code, (new, why) in FIXES.items():
        r = by.get(code)
        if r is None:
            sys.exit(f"{code} is not in the dataset")
        before = {k: r[k] for k in new}
        for k, v in new.items():
            r[k] = str(v)
        check(code, r)
        notes.append({"bureau_code": code, "note": why, "was": before,
                      "now": {k: str(v) for k, v in new.items()}})
        print(f"  {code}: " + ", ".join(
            f"{k} {before[k] or '-'} -> {v}" for k, v in new.items()))

    for flag in ("votes_certified", "papers_certified", "ballots_certified"):
        n = sum(1 for r in rows if r[flag] == "1")
        print(f"\n{flag:20s} {n:,} of {len(rows):,} ({100 * n / len(rows):.1f}%)")

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
