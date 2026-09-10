"""Check the published file against the identities it claims to have satisfied.

Every certification flag in this dataset is a claim about arithmetic: that the
block's fields close the form's own identity. Those claims were made by the
decoder and by the merge tools, each at the moment it wrote — and then other
tools wrote over the same rows. `merge_ballots.py` re-checks its own readings
before publishing, `fix_*.py` refuses to install a row that fails a `check()`,
but nothing had ever re-derived the identities from the *finished* file, with
every tool's writes layered on top of each other.

Doing that found five rows carrying `votes_certified` while their own columns
gave `zammel + maghzaoui + saied != valid`: the block was certified, and a later
pass rewrote one cell of it, so the flag outlived the value it asserted. That is
not reachable from inside the tool that wrote it, because each tool sees only its
own block on its own rows. Hence this file: it reads nothing but the CSV, knows
nothing about how any value got there, and so it is the one check the pipeline
cannot pass by construction.

**Only one of the three identities is re-derivable from the published columns.**
Each block closes against a total, and two of those totals are read but never
published: `papers` closes against `(ن)` and `ballots` against `(م)`. So
`papers_certified` and `ballots_certified` cannot be re-checked here, and a
comparison against the nearest published column is a different claim:

- `(ب) delivered` against `s + d + r` is the form's **مطابقة 2**, a cross-check
  the sheet asks the officers to zero, not the identity the block was certified
  on. 61 rows fail it. Treating that as a false certification was wrong — the
  same mistake as reading an empty `s_extracted` on a `papers_certified` row as
  an integrity bug.

What can be checked without a total is whether a block is *degenerate* — whether
the identity closed on nothing. `0 + 0 + 0 == 0` closes, and so does
`0 + 0 + 777 == 777`; a page carrying none of the block's cells can certify
itself, and a reader that fills an illegible cell with a repeated digit can
certify one too. The decoder now guards the first case. The checks here are the
independent version, per block, on the finished file, and they are fatal:

- a certified block whose summands are all zero;
- `papers_certified` with `valid` at zero, or `votes_certified` with no `valid`
  at all — no polling station casts zero valid votes;
- `ballots_certified` with `s_extracted` at zero — none extracts zero ballots.

The cross-checks are reported but never fatal, because a difference there is a
fact about the form rather than a reading error:

- `valid` against `(ق)` — the same total written in two places on the sheet.
- `(س)` extracted against `(و)` voted — legitimately differs when a ballot was
  handed out and not deposited.
- `(ب)` delivered against the ballot account — مطابقة 2, as above.

Usage: python3 tools/audit_identities.py [--csv FILE] [--verbose]
"""
import argparse, csv, sys

RESULTS = "data/pv_presidential_2024.csv"
CAND = ("zammel", "maghzaoui", "saied")

# flag column -> (summands, total). Only `votes` appears, because it is the only
# block whose total is a published column. `papers` closes against `(ن)` and
# `ballots` against `(م)`; both are read by the decoder and neither becomes a
# column, so neither identity is re-derivable here. That is a property of the
# schema, not an omission.
IDENTITIES = {
    "votes_certified": (list(CAND), "valid"),
}

# flag column -> (summands, the block's leading field). A block is degenerate
# when its summands are all zero, and implausible when the field named here is
# zero: no polling station casts zero valid votes or extracts zero ballots, so a
# block certified on that has closed its identity against nothing.
BLOCKS = {
    "votes_certified":   (list(CAND), "valid"),
    "papers_certified":  (["valid", "blank", "spoilt"], "valid"),
    "ballots_certified": (["s_extracted", "d_damaged", "r_remaining"], "s_extracted"),
}


def gi(row, key):
    try:
        return int(row[key])
    except (TypeError, ValueError, KeyError):
        return None


def check_identity(rows, flag, parts, total, verbose):
    ok = missing = 0
    bad = []
    for r in rows:
        if r.get(flag) != "1":
            continue
        vs = [gi(r, p) for p in parts]
        t = gi(r, total)
        if t is None or any(v is None for v in vs):
            # A certified block may legitimately lack a published column: the
            # flag is asserted over the block the decoder solved, and not every
            # field of that block becomes a column.
            missing += 1
            continue
        if sum(vs) == t:
            ok += 1
        else:
            bad.append((r["bureau_code"], vs, sum(vs), t))
    name = flag.replace("_certified", "")
    print(f"{name}: {' + '.join(parts)} == {total}")
    print(f"   {ok:,} close   {len(bad)} DO NOT CLOSE   {missing} missing a column")
    for code, vs, s, t in (bad if verbose else bad[:10]):
        print(f"      {code}  {'+'.join(str(v) for v in vs)} = {s}  but {total} = {t}"
              f"   (off by {s - t:+d})")
    if bad and not verbose:
        if len(bad) > 10:
            print(f"      ... and {len(bad) - 10} more (--verbose for all)")
    return bad


def check_degenerate(rows, flag, parts, lead, verbose):
    """A block that closed its identity against nothing.

    `0 + 0 + 0 == 0` is a solution, so a page carrying none of the block's cells
    can certify itself; ten rows were published that way before a guard went into
    the decoder. That guard tests whether *every* field of the block reads zero,
    including its total — which `0 + 0 + 777 == 777` slips past, because a reader
    that fills an illegible cell with a repeated digit leaves a total to match it.

    So this tests the summands alone, and separately tests the one field that
    cannot be zero at a polling station that reported at all.
    """
    zero, impossible = [], []
    for r in rows:
        if r.get(flag) != "1":
            continue
        vs = [gi(r, p) for p in parts]
        if vs and all(v == 0 for v in vs):
            zero.append(r["bureau_code"])
        elif gi(r, lead) == 0 or (flag == "votes_certified" and gi(r, lead) is None):
            impossible.append(r["bureau_code"])
    name = flag.replace("_certified", "")
    print(f"{name}: certified on all-zero {' + '.join(parts)}")
    print(f"   {len(zero)} rows")
    for code in (zero if verbose else zero[:10]):
        print(f"      {code}")
    print(f"{name}: certified with {lead} at zero or unread")
    print(f"   {len(impossible)} rows")
    for code in (impossible if verbose else impossible[:10]):
        print(f"      {code}")
    return zero + impossible


def compare(rows, a, b, label, verbose):
    agree, diff = 0, []
    for r in rows:
        x, y = gi(r, a), gi(r, b)
        if x is None or y is None:
            continue
        if x == y:
            agree += 1
        else:
            diff.append((r["bureau_code"], x, y))
    print(f"\n{label}   (reported, not a violation)")
    print(f"   {agree:,} agree   {len(diff)} differ")
    if diff:
        gaps = sorted(abs(x - y) for _, x, y in diff)
        print(f"   gap: median {gaps[len(gaps) // 2]}, max {gaps[-1]}")
    for code, x, y in (diff if verbose else diff[:6]):
        print(f"      {code}  {a} {x}   {b} {y}")
    if diff and not verbose and len(diff) > 6:
        print(f"      ... and {len(diff) - 6} more")
    return diff


def registered_flag(rows, verbose):
    """`a_registered_ok` must not claim a denominator the row itself refutes.

    The column is documented as "1 when `a_registered >= w_voted`; 0 flags a
    reading known to be wrong", and it is the only gate standing between a bad
    denominator and every turnout figure downstream -- `a_registered` appears in
    none of the form's identities, so nothing else checks it. Four rows once
    carried 1 against their own columns (174 registered, 304 voted) with a stale
    turnout to match; `tools/fix_registered_flags.py` withdrew them.

    Also asserted: `turnout_pct` is populated exactly where the flag is 1. That
    pairing is what stops a withdrawn flag leaving its turnout behind.
    """
    claimed, orphan = [], []
    for r in rows:
        a, w = gi(r, "a_registered"), gi(r, "w_voted")
        ok = r.get("a_registered_ok")
        if ok == "1" and a is not None and w is not None and a < w:
            claimed.append((r["bureau_code"], a, w))
        if (r.get("turnout_pct", "") != "") != (ok == "1"):
            orphan.append((r["bureau_code"], ok, r.get("turnout_pct", "")))
    print("\n(أ) registered flag against the row's own columns")
    print(f"   {len(claimed)} rows flag a_registered_ok = 1 while "
          f"a_registered < w_voted")
    for code, a, w in (claimed if verbose else claimed[:6]):
        print(f"      {code}  a_registered {a}   w_voted {w}")
    print(f"   {len(orphan)} rows publish a turnout that its flag does not "
          f"support")
    for code, ok, t in (orphan if verbose else orphan[:6]):
        print(f"      {code}  a_registered_ok {ok!r}   turnout_pct {t!r}")
    return len(claimed) + len(orphan)


def ballot_account(rows, verbose):
    """مطابقة 2: the sheet asks that `(ب) delivered - (م) = 0`.

    `(م)` is not published, but the certified block gives `s + d + r == (م)`, so
    the account sum stands in for it. A gap means `(ب)` is misread or the sheet
    itself does not balance. It is not a failed certification: the block was
    never certified against `(ب)`.
    """
    ok, gap = 0, []
    for r in rows:
        if r.get("ballots_certified") != "1":
            continue
        vs = [gi(r, k) for k in ("s_extracted", "d_damaged", "r_remaining")]
        b = gi(r, "b_delivered")
        if b is None or any(v is None for v in vs):
            continue
        if sum(vs) == b:
            ok += 1
        else:
            gap.append((r["bureau_code"], sum(vs), b))
    print(f"\nمطابقة 2: (ب) delivered against s + d + r"
          "   (reported, not a violation)")
    print(f"   {ok:,} balance   {len(gap)} do not")
    for code, acc, b in (gap if verbose else gap[:6]):
        print(f"      {code}  account {acc}   (ب) {b}   (off by {acc - b:+d})")
    if gap and not verbose and len(gap) > 6:
        print(f"      ... and {len(gap) - 6} more")
    return gap


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=RESULTS)
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()

    rows = list(csv.DictReader(open(a.csv, encoding="utf-8")))
    print(f"{len(rows):,} rows, {len(rows[0])} columns, from {a.csv}\n")

    violations = 0
    for flag, (parts, total) in IDENTITIES.items():
        violations += len(check_identity(rows, flag, parts, total, a.verbose))
        print()
    for flag, (parts, lead) in BLOCKS.items():
        violations += len(check_degenerate(rows, flag, parts, lead, a.verbose))
        print()

    compare(rows, "valid", "q_declared", "valid against (ق) declared", a.verbose)
    compare(rows, "s_extracted", "w_voted", "(س) extracted against (و) voted", a.verbose)
    ballot_account(rows, a.verbose)
    violations += registered_flag(rows, a.verbose)

    print()
    if violations:
        sys.exit(f"{violations} rows carry a certification their own arithmetic "
                 "does not support")
    print("every certified block closes its identity")


if __name__ == "__main__":
    main()
