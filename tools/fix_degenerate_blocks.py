"""Withdraw the certifications that closed on nothing, and blank the zeros that mean "unread".

Two defects, both found by `tools/audit_identities.py` reading the finished file.

**A block can close its identity against nothing.** The decoder already refuses a
block whose every field reads zero — `0 + 0 + 0 == 0` closes as exactly as any
real reading, and ten stations were once published on it. But the guard tests the
whole block including its total, and there are two ways past that:

- `0 + 0 + 777 == 777`. A reader that fills an illegible cell with a repeated
  digit leaves a total to match, and the block certifies. Five stations carry
  `papers_certified` on `valid 0 + blank 0 + spoilt 777`.
- `444 + 444 + 3`. One station has `blank` filled with the same 444 as `valid` —
  the reader duplicated the cell above — and 444 blank ballots at a station of
  444 valid votes is not a number the form can mean.

Nine papers blocks and two ballot blocks are withdrawn here. Nothing is invented
to replace them: the block goes back to uncertified, which is what it was worth.

**Zero is not the same as unread.** A cell the reader could not see was in places
published as `0`. For most fields that is indistinguishable from a true zero and
has to stand, but four fields cannot be zero at a station that reported at all,
so a zero there is a reading and not a fact:

- `(ب) delivered` — 21 rows. No station extracts 400 ballots from a box it was
  delivered none of.
- `(س) extracted` — 4 rows, one of them alongside 317 valid votes.
- `(أ) registered` — 2 rows, one alongside 415 voters who voted.
- `(و) voted` — 26 rows, almost all alongside a valid-vote count in the hundreds.

Those are emptied. A blank column says "not read", which is true; a zero says
"none", which is false, and it is false in the direction that silently drags any
average computed over the column.

The counterexample is `(د) damaged`, which is genuinely zero at most stations and
is left alone.

Usage: python3 tools/fix_degenerate_blocks.py [--write]
"""
import argparse, csv, json, os, shutil, sys, tempfile

RESULTS = "data/pv_presidential_2024.csv"
LOG = "data/verification/degenerate_blocks.jsonl"

CAND = ("zammel", "maghzaoui", "saied")

# --- the certifications withdrawn, and the junk cell each rested on -----------
WITHDRAW = {
    "08010410101": (dict(papers_certified=0),
                    "papers certified on valid 0 + blank 0 + spoilt 0; the page "
                    "carries none of the block's cells"),
    "08040210405": (dict(papers_certified=0),
                    "papers certified on valid 0 + blank 0 + spoilt 0; the page "
                    "carries none of the block's cells"),
    "11020110104": (dict(papers_certified=0, spoilt=None),
                    "papers certified on 0 + 0 + 777; 777 is the reader filling "
                    "an illegible cell, and the total matched it"),
    "11020110301": (dict(papers_certified=0, spoilt=None),
                    "papers certified on 0 + 0 + 777; 777 is the reader filling "
                    "an illegible cell, and the total matched it"),
    "11020610302": (dict(papers_certified=0, spoilt=None),
                    "papers certified on 0 + 0 + 777; 777 is the reader filling "
                    "an illegible cell, and the total matched it"),
    "11040310102": (dict(papers_certified=0, spoilt=None),
                    "papers certified on 0 + 0 + 777; 777 is the reader filling "
                    "an illegible cell, and the total matched it"),
    "11060110101": (dict(papers_certified=0, spoilt=None),
                    "papers certified on 0 + 0 + 777; 777 is the reader filling "
                    "an illegible cell, and the total matched it"),
    "03020510201": (dict(papers_certified=0, blank=None),
                    "blank published as 444, the same value as valid — the cell "
                    "above duplicated; the votes block is sound and is kept"),
    "05050710201": (dict(ballots_certified=0),
                    "ballots certified on 0 + 0 + 0 against a delivered count of "
                    "0; the account is empty, not balanced"),
    "20110110203": (dict(ballots_certified=0),
                    "ballots certified on 0 + 0 + 0; the account is empty, not "
                    "balanced"),
}

# --- (ص) recovered from (ق) --------------------------------------------------
# Four rows carry `votes_certified` with `valid` empty: read by eye off forms
# whose (ص) box is washed out, with the total taken from (ق) instead. On all
# four (ق) equals the candidate sum exactly, so filling `valid` from it publishes
# the total the form states rather than one this tool computed — and the votes
# identity then closes in the published columns, not only inside the decoder.
FILL_VALID_FROM_Q = ("02100710107", "03040310105", "04060710104", "21120810101")

# --- fields where a published 0 can only mean the cell was not read ----------
NOT_ZERO = ("b_delivered", "s_extracted", "a_registered", "w_voted")


def as_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def derive(r):
    """Recompute the columns that are functions of others, after a change."""
    if all(r[c] for c in CAND):
        r["candidate_sum"] = str(sum(int(r[c]) for c in CAND))
        if as_int(r["valid"]):
            r["saied_share_pct"] = str(round(100 * int(r["saied"])
                                             / int(r["valid"]), 2))
    a, w = as_int(r["a_registered"]), as_int(r["w_voted"])
    if a and w is not None:
        r["a_registered_ok"] = str(int(a >= w))
        r["turnout_pct"] = str(round(100 * w / a, 2))
    else:
        # Blanking (أ) or (و) has to blank what was derived from them too, or the
        # row keeps a turnout computed from a number it no longer publishes.
        r["a_registered_ok"] = ""
        r["turnout_pct"] = ""


def check(code, r):
    """No change here may leave a certified block failing its own identity."""
    v = {k: as_int(r[k]) for k in CAND + ("valid", "q_declared")}
    if r["votes_certified"] == "1":
        if any(v[c] is None for c in CAND) or v["valid"] is None:
            sys.exit(f"{code}: certified votes with an unreadable field")
        if sum(v[c] for c in CAND) != v["valid"]:
            sys.exit(f"{code}: candidates sum to {sum(v[c] for c in CAND)}, "
                     f"valid {v['valid']} — refusing to write")
    for flag, parts in (("papers_certified", ("valid", "blank", "spoilt")),
                        ("ballots_certified", ("s_extracted", "d_damaged",
                                               "r_remaining"))):
        if r[flag] != "1":
            continue
        vs = [as_int(r[p]) for p in parts]
        if all(x == 0 for x in vs):
            sys.exit(f"{code}: {flag} still rests on an all-zero block")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    rows = list(csv.DictReader(open(RESULTS, encoding="utf-8")))
    fields = list(rows[0].keys())
    by = {r["bureau_code"]: r for r in rows}
    notes = []

    print("certifications withdrawn")
    for code, (new, why) in WITHDRAW.items():
        r = by.get(code)
        if r is None:
            sys.exit(f"{code} is not in the dataset")
        before = {k: r[k] for k in new}
        for k, val in new.items():
            r[k] = "" if val is None else str(val)
        derive(r)
        check(code, r)
        notes.append({"bureau_code": code, "kind": "withdrawn", "note": why,
                      "was": before, "now": {k: r[k] for k in new}})
        print(f"  {code}: " + ", ".join(
            f"{k} {before[k] or '-'} -> {r[k] or '(blank)'}" for k in new))

    print("\n(ص) filled from the form's own (ق)")
    for code in FILL_VALID_FROM_Q:
        r = by.get(code)
        if r is None:
            sys.exit(f"{code} is not in the dataset")
        q, s = as_int(r["q_declared"]), as_int(r["candidate_sum"])
        if q is None or q != s:
            sys.exit(f"{code}: (ق) {q} does not equal the candidate sum {s}"
                     " — refusing to fill valid from it")
        if r["valid"]:
            print(f"  {code}: valid already published, skipped")
            continue
        r["valid"] = str(q)
        derive(r)
        check(code, r)
        notes.append({"bureau_code": code, "kind": "valid_from_q",
                      "note": f"(ص) unread; (ق) states {q}, which equals the "
                              f"candidate sum {s}",
                      "was": {"valid": ""}, "now": {"valid": str(q)}})
        print(f"  {code}: valid - -> {q}   (candidates sum to {s})")

    print("\nzeros emptied, where zero can only mean the cell was not read")
    cleared = {k: 0 for k in NOT_ZERO}
    for r in rows:
        for k in NOT_ZERO:
            if as_int(r[k]) == 0:
                r[k] = ""
                cleared[k] += 1
                derive(r)
                check(r["bureau_code"], r)
    for k in NOT_ZERO:
        print(f"  {k:14s} {cleared[k]:3d} rows")

    print()
    for flag in ("votes_certified", "papers_certified", "ballots_certified"):
        n = sum(1 for r in rows if r[flag] == "1")
        print(f"{flag:20s} {n:,} of {len(rows):,} ({100 * n / len(rows):.1f}%)")

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
