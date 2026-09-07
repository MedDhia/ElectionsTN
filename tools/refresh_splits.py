"""Recompute the words/digits agreement flag against the digits as published now.

`flag_splits.py` reads the Arabic words column and publishes one bit per station:
do the words say what the digits say. It ran once, at the point the words reader
was finished — and then the *digit* side kept moving. Whole-field reading,
alternate-page selection, the correction decisions and the hand-repairs all
changed published candidate values afterwards, and nothing re-ran the flag. So
the column in the dataset compares the current words against digits that in
places no longer exist.

It is stale in both directions, and only one of them is harmless:

- **1,045 rows read `0` but now agree.** Understated corroboration. Anyone
  filtering on the flag was throwing away good rows.
- **134 rows read `1` but now disagree.** Overstated, and this is the one that
  matters: the codebook offers `split_corroborated == 1` as the filter to trust
  when you need the split to be right, and 134 rows were sitting inside it
  without the words actually backing them.

No candidate value changes here — on every one of those 134 the digits close the
votes identity and the words do not, so the words are the failing channel. What
changes is the flag's honesty about which rows it has evidence for.

Two things this does that the original could not:

- It computes from `data/verification/word_readings.jsonl`, the dump of what the
  words reader actually read, so the flag can be recomputed against new digits
  without a 35-minute model run — and so the comparison is auditable rather than
  buried inside a worker process.
- It leaves the flag **blank, not `0`**, where `correction == "applied"`. There
  the published value comes from a correction decision that supersedes the
  counting record, and the words the reader sees are the *superseded* figure. A
  disagreement is the expected outcome and says nothing about the published
  value, so scoring it as a contradiction is a false alarm by construction.

And one thing it must not do: overwrite a row whose words were read **by eye**.
Where a hand correction was made against the Arabic words at magnification, that
reading is better evidence on the split than the model's pass over the same
cells — on 04080410201 the model skipped a table row and read the three
candidates one row out. Those rows keep the flag the hand reading set, and the
count of them is printed so the exemption stays visible rather than silent.

Usage: python3 tools/refresh_splits.py [--write]
"""
import argparse, collections, csv, json, os, shutil, sys, tempfile

RESULTS = "data/pv_presidential_2024.csv"
READINGS = "data/verification/word_readings.jsonl"
LOG = "data/verification/split_flag_refresh.jsonl"
# Logs of rows corrected by eye against the words on the form. The flag these
# set outranks the model's own reading of the same cells.
HAND_READ = ("data/verification/split_errors.jsonl",
             "data/verification/votes_identity.jsonl")
COLUMN = "split_corroborated"
CAND = ("zammel", "maghzaoui", "saied")


def as_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def fresh_flag(row, words):
    """"1" agree, "0" disagree, "" no comparison is possible or meaningful."""
    if row["votes_certified"] != "1":
        return ""
    if row["correction"] == "applied":
        return ""          # the words are the figure the decision superseded
    w = words.get(row["bureau_code"])
    if w is None:
        return ""
    dig = [as_int(row[c]) for c in CAND]
    if any(d is None for d in dig):
        return ""
    return "1" if all(w[c] == d for c, d in zip(CAND, dig)) else "0"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--readings", default=READINGS)
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    if not os.path.exists(a.readings):
        sys.exit(f"{a.readings} not found — run tools/harvest_word_values.py")
    words = {}
    for line in open(a.readings, encoding="utf-8"):
        d = json.loads(line)
        words[d["bureau_code"]] = d

    hand = set()
    for path in HAND_READ:
        if os.path.exists(path):
            hand |= {json.loads(l)["bureau_code"]
                     for l in open(path, encoding="utf-8")}

    rows = list(csv.DictReader(open(RESULTS, encoding="utf-8")))
    fields = list(rows[0].keys())
    if COLUMN not in fields:
        sys.exit(f"{COLUMN} is not a column of {RESULTS}")

    moved = collections.Counter()
    notes = []
    for r in rows:
        if r["bureau_code"] in hand:
            moved[(r[COLUMN], r[COLUMN])] += 1
            continue
        was, now = r[COLUMN], fresh_flag(r, words)
        moved[(was, now)] += 1
        if was == now:
            continue
        w = words.get(r["bureau_code"], {})
        # A downgrade is the only move worth a record: it withdraws a claim the
        # dataset was making. Log what the two channels each say so the withdrawal
        # can be checked without re-running anything.
        if was == "1":
            notes.append({
                "bureau_code": r["bureau_code"], "was": was, "now": now,
                "digits": {c: as_int(r[c]) for c in CAND},
                "words": {c: w.get(c) for c in CAND},
                "valid": as_int(r["valid"]),
                "digits_close": sum(as_int(r[c]) or 0 for c in CAND) == as_int(r["valid"]),
                "correction": r["correction"],
            })
        r[COLUMN] = now

    print(f"{'stored':>8} {'fresh':>7}   rows")
    for k in sorted(moved):
        mark = "" if k[0] == k[1] else "  <- changed"
        print(f"{k[0] or '(blank)':>8} {k[1] or '(blank)':>7}  {moved[k]:6d}{mark}")

    n1 = sum(1 for r in rows if r[COLUMN] == "1")
    n0 = sum(1 for r in rows if r[COLUMN] == "0")
    nb = sum(1 for r in rows if r[COLUMN] == "")
    print(f"\n{COLUMN}: {n1:,} corroborated, {n0:,} contradicted, {nb:,} no comparison")
    print(f"  {n1:,} of {len(rows):,} stations ({100 * n1 / len(rows):.1f}%)")
    print(f"  {len(hand)} rows left as they are, read by eye against the words")

    if notes:
        closes = sum(1 for n in notes if n["digits_close"])
        print(f"\n{len(notes)} claims withdrawn; on {closes} of them the digits "
              "close the votes identity\nand the words do not, so the digits stand "
              "and the words are the failing channel.")

    # The refresh must not be able to gut the column by accident: a readings dump
    # that is truncated or from another corpus would silently zero it out.
    if n1 < 0.5 * len(rows):
        sys.exit(f"refusing to install a flag that corroborates only {n1} rows")

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
    print(f"\n-> {RESULTS} ({COLUMN})\n-> {LOG}")


if __name__ == "__main__":
    main()
