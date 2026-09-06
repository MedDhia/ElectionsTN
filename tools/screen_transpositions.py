"""Find candidate rows read in the wrong order, by asking the words which is which.

The three identities on the form constrain the candidate **total**, so a
transposition of two candidate rows is invisible to every one of them: the sum
does not move. Four such rows were found by reading a 49-row shortlist by eye,
which is no way to search 9,417 stations.

The words column is. Each candidate's score is written twice — digits in cells,
and spelled out in Arabic beside them — and a transposition shows up as a
**permutation**: the set of three numbers is right and the assignment is wrong.
That is a signature a 3.6% whole-number error rate does not produce by accident.
Two candidates swapping values by chance would need the reader to make two
specific compensating mistakes on the same form.

Four classes are reported, most specific first:

- **permutation** — the three word values are the three digit values, reordered.
  Near-certain transposition.
- **pair swap** — two candidates hold each other's word value and the third
  agrees. The same thing, stated for the case where the reader could only read
  two of the three words.
- **centre outlier** — a candidate's share far above the median of the other
  stations in his own polling centre. This test never looks at the words, so it
  is the one that still covers the stations whose words could not be read.
- **large disagreement** — one candidate differs from its words by `--gap` or
  more (default 25). Not a transposition; the tail where a misread digit costs
  real votes, ranked so the worst are read first.

`--control` re-runs the permutation test against the six rows already known to
have been wrong, using the digits as they stood before `fix_split_errors.py`.
A screen that reports nothing is worth only as much as its sensitivity, and this
is how that claim is checked rather than asserted.

Nothing here changes a value: a disagreement between two fallible readers is a
reason to look at the scan, not to overwrite one with the other.

Usage: python3 tools/screen_transpositions.py [--gap 25] [--control] [--out FILE]
"""
import argparse, collections, csv, json, os, statistics, sys

RESULTS = "data/pv_presidential_2024.csv"
WORDS = "data/verification/word_readings.jsonl"
CAND = ("zammel", "maghzaoui", "saied")

# The digits as published before tools/fix_split_errors.py corrected them. Used
# only by --control, to show the screen finds the class it says it finds.
KNOWN_BAD = {
    "03070410202": (11, 178, 2), "03070510201": (19, 359, 5),
    "06090610201": (4, 184, 4), "11010510101": (7, 468, 5),
    "13030310101": (111, 6, 70), "23010310102": (13, 80, 15),
}

# A candidate is a centre outlier when his share is this far above the median of
# the other stations in the same centre, and that far above it in ratio too. A
# transposition hands one candidate another's votes, so it shows as both.
OUT_MIN_SHARE = 15.0
OUT_MIN_POINTS = 12.0
OUT_MIN_RATIO = 3.0
OUT_MIN_STATIONS = 3


def as_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gap", type=int, default=25,
                    help="report a single-candidate disagreement this large")
    ap.add_argument("--words", default=WORDS)
    ap.add_argument("--control", action="store_true",
                    help="check the screen against the rows known to be wrong")
    ap.add_argument("--out", help="write the bureau codes here, one per line")
    a = ap.parse_args()

    if not os.path.exists(a.words):
        sys.exit(f"{a.words} not found — run tools/harvest_word_values.py first")

    rows = {r["bureau_code"]: r for r in csv.DictReader(open(RESULTS, encoding="utf-8"))}
    words = {}
    for line in open(a.words, encoding="utf-8"):
        w = json.loads(line)
        words[w["bureau_code"]] = w

    if a.control:
        print("control — the screen run against the rows already known to be "
              "wrong, using the digits as they stood before they were fixed:\n")
        for code, was in KNOWN_BAD.items():
            w = words.get(code)
            if not w:
                print(f"  {code}: words not read"); continue
            wr = tuple(w[c] for c in CAND)
            if sorted(was) == sorted(wr) and was != wr:
                verdict = "PERMUTATION"
            else:
                verdict = ("large disagreement, off by %d"
                           % max(abs(x - y) for x, y in zip(was, wr)))
            print(f"  {code}  was {'/'.join(map(str, was)):>12s}  "
                  f"words {'/'.join(map(str, wr)):>12s}  -> {verdict}")
        print()

    perms, swaps, gaps = [], [], []
    checked = 0

    for w in words.values():
        r = rows.get(w["bureau_code"])
        if r is None or r["votes_certified"] != "1":
            continue
        dig = {c: as_int(r[c]) for c in CAND}
        if any(dig[c] is None for c in CAND) or any(c not in w for c in CAND):
            continue
        wrd = {c: w[c] for c in CAND}
        checked += 1
        if dig == wrd:
            continue

        # A transposition keeps the multiset and changes the assignment.
        if sorted(dig.values()) == sorted(wrd.values()):
            perms.append((r, dig, wrd))
            continue

        # Two candidates holding each other's value, the third agreeing.
        pair = [c for c in CAND if dig[c] != wrd[c]]
        if len(pair) == 2 and dig[pair[0]] == wrd[pair[1]] and dig[pair[1]] == wrd[pair[0]]:
            swaps.append((r, dig, wrd))
            continue

        worst = max(abs(dig[c] - wrd[c]) for c in CAND)
        if worst >= a.gap:
            gaps.append((worst, r, dig, wrd))

    def show(r, dig, wrd, note=""):
        d = "/".join(str(dig[c]) for c in CAND)
        v = "/".join(str(wrd[c]) for c in CAND)
        print(f"  {r['bureau_code']}  digits {d:>16s}   words {v:>16s}   "
              f"{r['reading']:8s} {r['governorate']}/{r['delegation']} {note}")

    print(f"{checked} stations where both channels read all three candidates\n")
    print(f"PERMUTATION — the three values are right, the order is not "
          f"({len(perms)}):")
    for r, d, w in perms:
        show(r, d, w)
    print(f"\nPAIR SWAP — two candidates hold each other's value ({len(swaps)}):")
    for r, d, w in swaps:
        show(r, d, w)

    # The words-free test. A transposition hands one candidate another's votes,
    # which puts his share far above every other station in the same centre.
    centres = collections.defaultdict(list)
    for r in rows.values():
        if r["votes_certified"] != "1" or not r["valid"] or as_int(r["valid"]) in (None, 0):
            continue
        if any(as_int(r[c]) is None for c in CAND):
            continue
        centres[(r["governorate"], r["delegation"], r["polling_centre"])].append(r)
    outliers = []
    for group in centres.values():
        if len(group) < OUT_MIN_STATIONS:
            continue
        for c in CAND:
            shares = [100 * int(x[c]) / int(x["valid"]) for x in group]
            med = statistics.median(shares)
            for x, s in zip(group, shares):
                if (s >= OUT_MIN_SHARE and s > med + OUT_MIN_POINTS
                        and s > OUT_MIN_RATIO * max(med, 0.5)):
                    outliers.append((s - med, x, c, s, med, len(group)))
    outliers.sort(reverse=True, key=lambda t: t[0])
    print(f"\nCENTRE OUTLIER — a candidate far above his own centre, words not "
          f"consulted ({len(outliers)}):")
    for _, r, c, s, med, n in outliers:
        print(f"  {r['bureau_code']}  {c:10s} {s:5.1f}% vs centre median "
              f"{med:4.1f}% over {n} stations   "
              f"{r['zammel']}/{r['maghzaoui']}/{r['saied']} of {r['valid']}   "
              f"{r['governorate']}/{r['delegation']}")

    gaps.sort(reverse=True, key=lambda x: x[0])
    print(f"\nLARGE DISAGREEMENT — one candidate off by {a.gap} or more "
          f"({len(gaps)}), worst first:")
    for worst, r, d, w in gaps:
        show(r, d, w, f"[off by {worst}]")

    if a.out:
        codes = ([r["bureau_code"] for r, _, _ in perms]
                 + [r["bureau_code"] for r, _, _ in swaps]
                 + [r["bureau_code"] for _, r, _, _ in gaps])
        with open(a.out, "w") as fh:
            fh.write("\n".join(codes) + "\n")
        print(f"\n{len(codes)} codes -> {a.out}")


if __name__ == "__main__":
    main()
