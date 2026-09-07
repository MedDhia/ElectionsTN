"""Check `valid` against a second block, and publish whether it held.

The votes identity is `q == valid == zammel + maghzaoui + saied`. It is what
gates 9,424 rows, and it has a blind spot that no amount of care inside the block
can close: a misreading that moves a candidate and the total together satisfies
it exactly. Bureau 07070810101 was published as 4/1/141 against a valid of 146.
That is arithmetically perfect. It is also wrong — the form says 7/1/141 against
149 — and nothing in the votes block could ever have said so.

`valid` is not only the votes total. It is also one of the three kinds of paper
drawn from the box, so the form states it a second time, in a different identity:

    (س) extracted  ==  (ص) valid + (ع) blank + (ف) spoilt

That second statement is independent of the candidates. Where the dataset
publishes the whole ballots column, it can be checked, and a `valid` that
survives both identities is corroborated in a way one identity alone can never
make it. Where the column is not published, `valid` rests on the votes identity
alone, and this column says so rather than leaving the reader to assume
otherwise.

This is the same move as `split_corroborated`, one level up: that column
corroborates the split between candidates against the Arabic words, this one
corroborates their total against the ballots.

Usage: python3 tools/cross_check.py [--write]
"""
import argparse, collections, csv, os, shutil, tempfile

RESULTS = "data/pv_presidential_2024.csv"
FLAG = "valid_corroborated"
PAPERS = ("s_extracted", "valid", "blank", "spoilt")


def as_int(v):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    rows = list(csv.DictReader(open(RESULTS, encoding="utf-8")))
    cols = list(rows[0].keys())
    if FLAG not in cols:
        cols.append(FLAG)

    tally = collections.Counter()
    failures = []
    for r in rows:
        r.setdefault(FLAG, "")
        if r["votes_certified"] != "1":
            r[FLAG] = ""
            tally["not certified"] += 1
            continue
        vals = {k: as_int(r.get(k)) for k in PAPERS}
        if any(v is None for v in vals.values()):
            r[FLAG] = ""
            tally["ballots column not published"] += 1
            continue
        ok = vals["s_extracted"] == vals["valid"] + vals["blank"] + vals["spoilt"]
        r[FLAG] = "1" if ok else "0"
        tally["corroborated" if ok else "contradicted"] += 1
        if not ok:
            failures.append((r["bureau_code"], r["reading"],
                             vals["s_extracted"] - (vals["valid"] + vals["blank"]
                                                    + vals["spoilt"])))

    for k, v in tally.most_common():
        print(f"  {k:30s} {v:6d}")
    n = tally["corroborated"] + tally["contradicted"]
    if n:
        print(f"\n  {tally['corroborated']}/{n} = {tally['corroborated']/n:.4f} of the "
              f"checkable rows have `valid` corroborated by the ballots column")
    print(f"\n  {len(failures)} contradicted:")
    for code, route, diff in sorted(failures, key=lambda x: -abs(x[2])):
        print(f"    {code:12s} {route:8s} extracted is {diff:+d} against valid+blank+spoilt")

    # A standing guard, not a one-off repair. The blank-cell artefact that
    # fix_leading_seven.py cleans up was invisible for the life of this project
    # because nothing ever asked whether a published number was a number a
    # polling station could produce. Now something does, on every run.
    impossible = []
    for r in rows:
        for c, v in ((c, as_int(r.get(c))) for c in PAPERS + ("saied", "zammel",
                                                              "maghzaoui", "q_declared",
                                                              "c_signed", "w_voted")):
            if v is not None and v > 1500:
                impossible.append((r["bureau_code"], c, v))
    if impossible:
        print(f"\n  WARNING: {len(impossible)} published values a polling station "
              f"cannot have had:")
        for code, c, v in impossible[:20]:
            print(f"    {code} {c}={v}")
        print("  run tools/fix_leading_seven.py")

    if not a.write:
        print("\ndry run, dataset untouched")
        return
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(RESULTS), suffix=".csv")
    with os.fdopen(fd, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    shutil.move(tmp, RESULTS)
    os.chmod(RESULTS, 0o644)
    print(f"\n-> {RESULTS}")


if __name__ == "__main__":
    main()
