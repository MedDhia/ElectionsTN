"""Repair the values where the reader turned a blank leading cell into a seven.

Across the corpus, 120 published values exceed 1500 and every single one begins
with a 7: 21 extracted-ballot counts, 20 signed-voter counts, 11 Saied figures,
and so on down. Reading the scans says what is happening. The four-digit fields
are four separate cells, and a clerk who counts 403 valid ballots often writes
`403` and leaves the leftmost cell **empty** rather than writing `0403`. The
classifier has no class for an empty cell, so it emits its nearest guess, and its
nearest guess for blank paper is a 7.

The damage is not cosmetic. Bureau 02090610103 publishes Saied 7357 against a
valid of 7403, and 41 + 5 + 7357 = 7403 exactly, so the votes identity — the gate
that vouches for 9,424 rows — passes it without complaint. The form says 41 / 5 /
357 against 403. Eleven certified rows carry an inflated Saied figure this way,
77,000 votes in total, 3.2% of his certified count.

The repair is not a guess. Stripping the spurious leading digit is accepted only
where doing so makes the form's identities close *and* leaving it does not: the
same standard of evidence the rest of the pipeline uses. Where that test cannot
separate the two readings, the value is withdrawn rather than repaired, because a
number nothing vouches for should not be published.

Usage: python3 tools/fix_leading_seven.py [--write]
"""
import argparse, collections, csv, os, shutil, tempfile

RESULTS = "data/pv_presidential_2024.csv"
CAND = ("zammel", "maghzaoui", "saied")
SUSPECT = ("a_registered", "b_delivered", "c_signed", "d_damaged", "r_remaining",
           "s_extracted", "valid", "blank", "spoilt", "w_voted", "q_declared",
           "zammel", "maghzaoui", "saied")
LIMIT = 1500        # above this, a four-digit field on this form is suspect
HEADROOM = 1.2      # how far past the observed maximum a value may still be real


def as_int(v):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def identities(r):
    """Which of the form's identities the row's published values satisfy."""
    g = {k: as_int(r.get(k)) for k in SUSPECT}
    out = []
    if all(g[c] is not None for c in CAND):
        for total in ("valid", "q_declared"):
            if g[total] is not None:
                out.append(sum(g[c] for c in CAND) == g[total])
    if all(g[k] is not None for k in ("s_extracted", "valid", "blank", "spoilt")):
        out.append(g["s_extracted"] == g["valid"] + g["blank"] + g["spoilt"])
    if all(g[k] is not None for k in ("s_extracted", "d_damaged", "r_remaining",
                                      "b_delivered")):
        out.append(g["s_extracted"] + g["d_damaged"] + g["r_remaining"]
                   == g["b_delivered"])
    return out


def score(r):
    ids = identities(r)
    return sum(ids), len(ids)


def ceilings(rows):
    """The largest value each column reaches among readings the artefact spared.

    The identities alone cannot always separate the two readings: when the
    spurious seven lands on a candidate and on the total together, both readings
    satisfy `zammel + maghzaoui + saied == valid` exactly. That is the same blind
    spot this whole exercise is about, and arithmetic cannot close it.

    Physical possibility can. Across 9,392 stations whose `valid` the artefact did
    not touch, the largest is 662; `saied` reaches 628, `s_extracted` 723. A
    station with 7,403 valid ballots does not exist, and a reading that says one
    does is not a competing hypothesis — it is an impossible one. Only
    `a_registered` and `b_delivered` are legitimately larger, at 2,137 and 2,100,
    and the ceilings are measured per column so that stays true.
    """
    out = {}
    for c in SUSPECT:
        v = [as_int(r.get(c)) for r in rows]
        v = [x for x in v if x is not None
             and not (x > LIMIT and str(x).startswith("7"))]
        if v:
            out[c] = max(v) * HEADROOM
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    rows = list(csv.DictReader(open(RESULTS, encoding="utf-8")))
    cols = list(rows[0].keys())
    cap = ceilings(rows)
    print("  column ceilings, from the readings the artefact spared:")
    print("   " + "  ".join(f"{c}<{int(v)}" for c, v in sorted(cap.items())) + "\n")
    tally = collections.Counter()
    notes = []

    for r in rows:
        hit = [c for c in SUSPECT
               if (as_int(r.get(c)) or 0) > LIMIT and str(r[c]).startswith("7")]
        if not hit:
            continue
        r_before = dict(r)
        before_ok, before_n = score(r)
        trial = dict(r)
        for c in hit:
            trial[c] = str(int(str(r[c])[1:]))
        after_ok, after_n = score(trial)

        impossible = [c for c in hit
                      if c in cap and (as_int(r[c]) or 0) > cap[c]]
        if after_ok > before_ok or (impossible and after_ok >= before_ok):
            for c in hit:
                r[c] = trial[c]
            if as_int(r.get("candidate_sum")) is not None and all(
                    as_int(r.get(x)) is not None for x in CAND):
                r["candidate_sum"] = str(sum(as_int(r[x]) for x in CAND))
            tally["repaired"] += 1
            why = ("identities" if after_ok > before_ok else
                   "beyond what the column ever reaches: "
                   + ", ".join(f"{c}={r_before[c]}" for c in impossible))
            notes.append(f"  {r['bureau_code']:12s} repaired {', '.join(hit)} "
                         f"({before_ok}/{before_n} -> {after_ok}/{after_n}; {why})")
        elif after_ok == before_ok and before_n == 0:
            for c in hit:
                r[c] = ""
            tally["withdrawn"] += 1
            notes.append(f"  {r['bureau_code']:12s} withdrew {', '.join(hit)} — "
                         f"no identity to separate the two readings")
        else:
            tally["left alone"] += 1
            notes.append(f"  {r['bureau_code']:12s} left alone: {', '.join(hit)} "
                         f"({before_ok}/{before_n} before, {after_ok}/{after_n} after)")

    for k, v in tally.most_common():
        print(f"  {k:12s} {v:4d}")
    print()
    for n in notes:
        print(n)

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
