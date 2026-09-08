"""Merge a re-decode additively: fill empty cells, never move a published one.

A better reader is only useful if it can be applied, and applying it by
re-decoding the corpus and replacing `data/pv_presidential_2024.csv` would throw
away everything this project has established by hand — the correction decisions,
the transposition repairs, the identity fixes, the readings taken at
magnification. Those are worth more than any classifier's output.

So the merge is strictly additive: **a column is written only if it is currently
empty.** No published number can move, so no hand correction can be undone and no
verified row can change. What a re-decode can do is fill gaps — and gaps are
exactly what a reader trained on low-resolution forms should close.

**That rule alone is not enough, and the first dry run proved it.** An empty cell
does not only mean "never read". It can also mean "read, and *withdrawn* because
the reading was wrong" — and those two look identical in the CSV. Re-decoding the
170 rows without a ballot account offered back, among other things:

- `01151010103 b_delivered = 1200`, a cell emptied precisely because its `(ب)`
  box is written over and reads 1099 or 1100 — certainly not 1200;
- `05010210101 r_remaining = 209`, emptied because `(ر)` reads 905 or 909;
- `03020510201 blank = 444`, emptied because 444 was `valid` duplicated into the
  cell below it;
- `b_delivered = 0`, `s_extracted = 0` and `w_voted = 0` across twelve rows — the
  "zero means unread" class that `fix_degenerate_blocks.py` exists to clear;
- and three all-zero candidate blocks certified as votes, because `0 + 0 + 0 == 0`
  closes as exactly as any real reading.

So three further guards, each one a defect this tool would otherwise have
reintroduced:

1. **A cell recorded as deliberately emptied is never refilled.** The
   verification logs carry the evidence: a record whose `now` maps a column to an
   empty string is a withdrawal, and those `(bureau, column)` pairs are frozen.
   Integer `0` in a log is a real reading, not a withdrawal, and is not frozen.
2. **Zero is never written** into the four fields where zero cannot be a reading
   at a station that reported at all — the same list `fix_degenerate_blocks.py`
   uses.
3. **A block whose summands are all zero is neither filled nor certified**,
   mirroring the `degenerate()` guard in `decode_all.py`. Refusing only the
   certification is not enough, and the second dry run showed why: four rows
   still had `zammel = maghzaoui = saied = valid = 0` written into them, which
   publishes "this station cast no votes for anyone" when the truth is that the
   page carries no candidate table. Zero is a legitimate reading for one
   candidate at a small station and never for all of them at once, so the test
   has to be per block rather than per field.

Two more came out of the dry run over the 1,369-row re-decode, and both are the
same shape: a fill that is individually well-formed but contradicts something
the row already publishes.

5. **`(أ)` registered is never filled below the published `(و)` voted.** The
   re-decode offered `a_registered = 76` on a station where 412 people voted.
   `a_registered_ok` would have recorded the impossibility rather than prevented
   it.
6. **`(ب)` delivered is never filled when the row's ballot account is already
   certified and the value would not match it.** Nine rows would have gained a
   `(ب)` contradicting their own certified `s + d + r` — one by 1,000 ballots —
   manufacturing exactly the مطابقة 2 failures this session spent its time
   reading off scans and resolving.
7. **`(و)` voted is never filled more than 50 from the published `(س)`.** This one
   only became visible *after* a write: the merge passed the audit — exit 0,
   مطابقة 2 unchanged at 24 — and yet the `(س)`/`(و)` comparison showed a maximum
   gap of **7,000**. Eight `w_voted` fills were impossible against the row's own
   `(س)`: 7,310 against 310, 1,210 against 210, 9 against 289, 100 against 284.
   `w_voted` sits in no identity, so nothing in the pipeline or the audit could
   catch it — the error is only visible against a *sibling* field. The bound is
   empirical, and the cap restricts only new fills; it never touches a large gap
   already published, because recording what the sheet says and adding a claim
   of one's own deserve different bars.

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
# Fields where a published 0 can only mean the cell was not read.
NOT_ZERO = ("b_delivered", "s_extracted", "a_registered", "w_voted")
# How far a filled (و) may sit from the published (س). Of the 8,689 rows that
# publish both, 99.3% are identical, the 99.9th percentile gap is 30, and only 6
# exceed 50.
W_VOTED_MAX_GAP = 50


def withdrawn_cells(dirname="data/verification"):
    """(bureau, column) pairs some tool deliberately emptied.

    An empty cell is ambiguous — never read, or read and withdrawn — so the
    logs are the only way to tell. A record whose `now` maps a column to an
    empty string withdrew it; integer 0 there is a real reading and stays
    fillable.
    """
    import glob
    out = set()
    for path in glob.glob(os.path.join(dirname, "*.jsonl")):
        for line in open(path, encoding="utf-8"):
            try:
                r = json.loads(line)
            except ValueError:
                continue
            now = r.get("now")
            if not isinstance(now, dict) or "bureau_code" not in r:
                continue
            for col, v in now.items():
                if v is None or (isinstance(v, str) and not v.strip()):
                    out.add((r["bureau_code"], col))
    return out


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


def degenerate(r, block):
    """Every summand zero. Closes any identity, and means nothing."""
    cols = {"votes": CAND, "papers": ("valid", "blank", "spoilt"),
            "ballots": ("s_extracted", "d_damaged", "r_remaining")}[block]
    return all(as_int(r.get(c)) == 0 for c in cols)


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

    frozen = withdrawn_cells()
    print(f"{len(frozen)} (bureau, column) pairs are frozen: deliberately "
          "emptied by an earlier tool")

    filled, flagged, notes = 0, {k: 0 for k in BLOCK_COLS}, []
    refused = {"withdrawn": 0, "zero": 0, "degenerate": 0, "degenerate_fill": 0,
               "impossible": 0, "contradicts": 0, "implausible_w": 0}
    for r in rows:
        d = new.get(r["bureau_code"])
        if d is None:
            continue
        # A block the re-decode reads as all zeros contributes nothing, so none
        # of its columns are eligible — not just its flag.
        dead = set()
        for block in BLOCK_COLS:
            if degenerate(d, block):
                dead |= set(BLOCK_COLS[block])
        got = {}
        for col in FILLABLE:
            if col in dead:
                refused["degenerate_fill"] += 1
                continue
            if col in fields and empty(r[col]) and not empty(d.get(col)):
                v = as_int(d[col])
                if v is None:
                    continue
                if (r["bureau_code"], col) in frozen:
                    refused["withdrawn"] += 1
                    continue
                if v == 0 and col in NOT_ZERO:
                    refused["zero"] += 1
                    continue
                # (أ) below the published (و) is not a reading, it is impossible.
                if col == "a_registered":
                    w = as_int(r.get("w_voted"))
                    if w is not None and v < w:
                        refused["impossible"] += 1
                        continue
                # A (ب) that contradicts an account already certified would
                # manufacture a مطابقة 2 failure rather than record one.
                # (و) far from the published (س) is a misread, not a reading:
                # مطابقة 3 asks them to be equal, and 99.3% of published pairs are.
                if col == "w_voted":
                    sx = as_int(r.get("s_extracted"))
                    if sx is not None and abs(v - sx) > W_VOTED_MAX_GAP:
                        refused["implausible_w"] += 1
                        continue
                if col == "b_delivered" and r.get("ballots_certified") == "1":
                    acc = [as_int(r.get(k)) for k in
                           ("s_extracted", "d_damaged", "r_remaining")]
                    if all(x is not None for x in acc) and sum(acc) != v:
                        refused["contradicts"] += 1
                        continue
                r[col] = str(v)
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
            if degenerate(r, block):
                refused["degenerate"] += 1
                continue
            r[flag] = "1"
            flagged[block] += 1
            gained.append(block)
        notes.append({"bureau_code": r["bureau_code"], "filled": got,
                      "certified": gained})

    print(f"\nrefused: {refused['withdrawn']} cells frozen as withdrawn, "
          f"{refused['zero']} zeros where zero means unread, "
          f"{refused['degenerate_fill']} cells in all-zero blocks, "
          f"{refused['impossible']} impossible (أ) below (و), "
          f"{refused['contradicts']} (ب) contradicting a certified account, "
          f"{refused['implausible_w']} (و) too far from (س), "
          f"{refused['degenerate']} degenerate blocks not certified")
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
