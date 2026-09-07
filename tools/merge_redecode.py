"""Merge a re-decode additively: fill empty cells, never move a published one.

A better reader is only useful if it can be applied, and applying it by
re-decoding the corpus and replacing `data/pv_presidential_2024.csv` would throw
away everything this project has established by hand — the correction decisions,
the transposition repairs, the identity fixes, the readings taken at
magnification. Those are worth more than any classifier's output.

So the merge is strictly additive, under one rule that makes it impossible to
regress: **a column is written only if it is currently empty.** No published
number can move, so no hand correction can be undone and no verified row can
change. What a re-decode can do is fill gaps — and gaps are exactly what a
reader trained on low-resolution forms should close.

A certification flag is then set only if the block's identity closes **using the
values now in the published row**, not the values in the re-decode. That
distinction matters: a re-decode may certify a block on four fields of its own
while two of those fields were already published differently, in which case the
block does not close in the file and the flag would be a lie. The audit in
`tools/audit_identities.py` would catch it afterwards; this refuses to write it
in the first place.

Two blocks are checkable here and one is not, for the reason recorded in that
audit: `votes` closes against the published `valid`, `ballots` and `papers`
close against `(م)` and `(ن)`, which are read and never published. Where the
total is missing, the flag is only carried over if `(س)` can stand in for `(ن)`
(that is, `valid + blank + spoilt == s_extracted`) or the ballot account reaches
the published `(ب)`. If neither is available the values are filled and the flag
is withheld — a published number with no flag is honest; a flag with nothing
behind it is not.

Usage: python3 tools/merge_redecode.py --decoded FILE [--write]
"""
import argparse, csv, json, os, shutil, sys, tempfile

RESULTS = "data/pv_presidential_2024.csv"
LOG = "data/verification/redecode_merge.jsonl"

CAND = ("zammel", "maghzaoui", "saied")
BLOCK_COLS = {
    "votes": ("zammel", "maghzaoui", "saied", "valid"),
    "papers": ("valid", "blank", "spoilt"),
    "ballots": ("s_extracted", "d_damaged", "r_remaining"),
}
# Columns a re-decode may fill. Derived columns are recomputed, not copied.
FILLABLE = ("a_registered", "b_delivered", "c_signed", "d_damaged",
            "r_remaining", "s_extracted", "valid", "blank", "spoilt",
            "w_voted", "q_declared", "zammel", "maghzaoui", "saied")


def as_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def empty(v):
    return (v or "").strip() == ""


def closes(r, block):
    """Does this block's identity hold in the published row as it now stands?"""
    g = lambda k: as_int(r.get(k))
    if block == "votes":
        vs, t = [g(c) for c in CAND], g("valid")
        return t is not None and all(v is not None for v in vs) and sum(vs) == t
    if block == "papers":
        vs, t = [g("valid"), g("blank"), g("spoilt")], g("s_extracted")
        return t is not None and all(v is not None for v in vs) and sum(vs) == t
    vs, t = [g("s_extracted"), g("d_damaged"), g("r_remaining")], g("b_delivered")
    return t is not None and all(v is not None for v in vs) and sum(vs) == t


def derive(r):
    if all(r[c] for c in CAND):
        r["candidate_sum"] = str(sum(int(r[c]) for c in CAND))
        if as_int(r["valid"]):
            r["saied_share_pct"] = str(round(100 * int(r["saied"])
                                             / int(r["valid"]), 2))
    a, w = as_int(r["a_registered"]), as_int(r["w_voted"])
    if a and w is not None:
        r["a_registered_ok"] = str(int(a >= w))
        r["turnout_pct"] = str(round(100 * w / a, 2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--decoded", required=True,
                    help="a decode_all output CSV from the retrained reader")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    if not os.path.exists(a.decoded):
        sys.exit(f"{a.decoded} not found")
    new = {r["bureau_code"]: r for r in
           csv.DictReader(open(a.decoded, encoding="utf-8"))}
    rows = list(csv.DictReader(open(RESULTS, encoding="utf-8")))
    fields = list(rows[0].keys())
    print(f"{len(new):,} re-decoded rows against {len(rows):,} published")

    filled, flagged, notes = 0, {k: 0 for k in BLOCK_COLS}, []
    for r in rows:
        d = new.get(r["bureau_code"])
        if d is None:
            continue
        got = {}
        for col in FILLABLE:
            if col in fields and empty(r[col]) and not empty(d.get(col)):
                if as_int(d[col]) is None:
                    continue
                r[col] = str(as_int(d[col]))
                got[col] = r[col]
        if not got:
            continue
        derive(r)
        filled += 1
        gained = []
        for block, cols in BLOCK_COLS.items():
            flag = f"{block}_certified"
            if r[flag] == "1" or d.get(flag) != "1":
                continue
            if not closes(r, block):
                continue
            if any(empty(r[c]) for c in cols):
                continue
            r[flag] = "1"
            flagged[block] += 1
            gained.append(block)
        notes.append({"bureau_code": r["bureau_code"], "filled": got,
                      "certified": gained})

    print(f"\n{filled} rows gained at least one value")
    for block, n in flagged.items():
        print(f"  {block + '_certified':22s} +{n}")
    if notes:
        print("\nfirst few:")
        for n in notes[:15]:
            print(f"  {n['bureau_code']}  " +
                  ", ".join(f"{k}={v}" for k, v in n["filled"].items()) +
                  (f"   -> certified {', '.join(n['certified'])}"
                   if n["certified"] else ""))

    for flag in ("votes_certified", "papers_certified", "ballots_certified"):
        n = sum(1 for x in rows if x[flag] == "1")
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
