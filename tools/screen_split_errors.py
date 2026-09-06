"""Screen for the error the votes identity cannot see: the same slip twice.

`zammel + maghzaoui + saied == valid` catches a misread candidate — unless the
same misreading lands in `valid` as well. A reader that drops the leading 3 from
both `saied` and `valid` produces 29 + 6 + 19 == 54, which closes exactly and is
wrong by three hundred votes. Three such rows were found by hand while reading
the ballots column, so the class is real and worth screening for.

The words column is the channel that notices: all three were already flagged
`split_corroborated == 0`. But 1,768 rows carry that flag and most are the
classifier disagreeing about a single digit, so the flag alone is not a
shortlist. This narrows it with three independent tests, any one of which is
enough to put a row in front of the eye:

- **the ballots column contradicts by 50 or more.** `(س) extracted` is stated
  separately from the candidate rows, so a `valid` inflated by 200 shows up as a
  200-vote gap in an identity the candidates never touch.
- **an implausible share.** A leading-digit slip on one candidate and the total
  moves the winner's share to an extreme. 100% and 0% are both real at small
  stations, so this test finds candidates for reading, not errors.
- **an outlier against its own polling centre.** Stations in one centre are
  sized alike, so a `valid` under 40% or over 250% of the centre's median, where
  the centre has at least three stations, is worth a look.

Nothing here changes a value. It prints a list to read by eye, which is the only
thing that can actually settle one of these.

Usage: python3 tools/screen_split_errors.py [--out FILE]
"""
import argparse, collections, csv, statistics

RESULTS = "data/pv_presidential_2024.csv"
BALLOTS_GAP = 50      # votes; below this the gap is a clerical one or two
SHARE_LOW, SHARE_HIGH = 55.0, 99.5
CENTRE_MIN = 3        # stations needed before a centre median means anything
CENTRE_LO, CENTRE_HI = 0.4, 2.5


def as_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", help="write the bureau codes here, one per line")
    a = ap.parse_args()

    rows = list(csv.DictReader(open(RESULTS, encoding="utf-8")))

    centres = collections.defaultdict(list)
    for r in rows:
        v = as_int(r["valid"])
        if v is not None and r["votes_certified"] == "1":
            centres[r["polling_centre"]].append(v)

    flagged = []
    for r in rows:
        if r["votes_certified"] != "1" or r["split_corroborated"] != "0":
            continue
        why = []

        if r["valid_corroborated"] == "0":
            s, v, b, f = (as_int(r[k]) for k in
                          ("s_extracted", "valid", "blank", "spoilt"))
            if None not in (s, v, b, f) and abs(s - (v + b + f)) >= BALLOTS_GAP:
                why.append("ballots off by %+d" % (s - (v + b + f)))

        if r["saied_share_pct"]:
            share = float(r["saied_share_pct"])
            if share < SHARE_LOW or share > SHARE_HIGH:
                why.append("share %.2f" % share)

        v = as_int(r["valid"])
        peers = centres[r["polling_centre"]]
        if v and len(peers) >= CENTRE_MIN:
            med = statistics.median(peers)
            if med and not (CENTRE_LO * med <= v <= CENTRE_HI * med):
                why.append("valid %d vs centre median %.0f" % (v, med))

        if why:
            flagged.append((r, "; ".join(why)))

    print(f"{len(flagged)} rows to read by eye "
          f"(of {sum(1 for r in rows if r['split_corroborated'] == '0')} "
          "where the words disagree with the digits)\n")
    for r, why in flagged:
        print(f"  {r['bureau_code']}  {r['reading']:8s} "
              f"{r['zammel']:>4s}/{r['maghzaoui']:>4s}/{r['saied']:>4s} "
              f"of {r['valid']:>4s}   {why}")

    if a.out:
        with open(a.out, "w") as fh:
            fh.write("\n".join(r["bureau_code"] for r, _ in flagged) + "\n")
        print(f"\n-> {a.out}")


if __name__ == "__main__":
    main()
