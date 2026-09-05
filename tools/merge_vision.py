"""Merge forms read by eye into the dataset, on the same evidence as the rest.

Most of what is missing is not illegible, it is small. The form draws candidate
cells 56x38 in reference coordinates and every other field about 23x24, so on the
560px scans ISIE published for much of Medenine the candidates land near 20px and
`valid` and `q_declared` near 8px. The classifier reads the candidates 61-78% of
the time there and `valid` once in 17, and because the votes identity is
`q == valid == the three candidates summed`, two unreadable fields veto a form
however well its candidates are read. 430 of the 478 uncertified stations already
have their candidate values sitting unpublished for that reason.

A reader who can magnify the scan does not hit that wall, so those forms were
read off the images directly.

**A row read this way is admitted on exactly the evidence every other row is
admitted on: the form's own arithmetic.** A reading is merged only if
`zammel + maghzaoui + saied == valid`, and `q_declared` too where the form fills
it in. That is the same test `certify_cells` applies, and a misread digit will
almost always break it — of the first 18 forms read, all 17 with a legible total
closed exactly.

What differs is reproducibility, and that is why the provenance is recorded
rather than blended in. Anyone can re-run `decode_all` and obtain the 8,970 rows
it certifies; nobody can re-run a pair of eyes. So these rows carry
`reading = "vision"` and `votes_certified = 1`, and the codebook says plainly
that filtering on `votes_certified` alone mixes the two provenances. Filter on
`reading != "vision"` for the reproducible subset.

Usage: python3 tools/merge_vision.py [--readings FILE] [--dry-run]
"""
import argparse, csv, json, os, shutil, sys, tempfile

RESULTS = "data/pv_presidential_2024.csv"
DEFAULT = "data/verification/lowres_readings.jsonl"
CAND = ("zammel", "maghzaoui", "saied")
PAPERS = ("extracted", "valid", "blank", "spoilt")


def papers_close(r):
    """True when the ballots drawn from the box account for themselves.

    The form's second identity: every paper taken out of the box is valid, blank
    or spoilt, so `s_extracted == valid + blank + spoilt`. It is independent of
    the votes identity — a reading can satisfy one and fail the other — so a
    papers block is published on its own evidence, exactly as `decode_all` does
    for the rows it reaches.
    """
    if any(r.get(k) is None for k in PAPERS):
        return False
    return int(r["extracted"]) == sum(int(r[k]) for k in PAPERS[1:])


def closes(r):
    """True when the form's own arithmetic vouches for the reading.

    The form states the total twice, as `valid` and again as `q_declared`, and
    either one checks the candidate split on its own. Requiring `valid`
    specifically threw away forms where it is washed out but `q` is legible,
    which is the same evidence written in a different box. Both are used when
    both can be read, and they must then agree.
    """
    if any(r.get(c) is None for c in CAND):
        return False
    totals = [int(r[k]) for k in ("valid", "q_declared") if r.get(k) is not None]
    if not totals or len(set(totals)) != 1:
        return False
    return sum(int(r[c]) for c in CAND) == totals[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--readings", default=DEFAULT)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    readings = [json.loads(l) for l in open(a.readings, encoding="utf-8")]
    good, bad, papers = {}, [], {}
    for r in readings:
        (good.setdefault(r["bureau_code"], r) if closes(r) else bad.append(r))
        if papers_close(r):
            papers.setdefault(r["bureau_code"], r)
    print(f"{len(readings)} readings: {len(good)} close the identity, "
          f"{len(bad)} do not and are not merged")
    for r in bad:
        s = None
        if all(r.get(c) is not None for c in CAND):
            s = sum(int(r[c]) for c in CAND)
        print(f"  held back {r['bureau_code']}: candidates sum to {s}, "
              f"valid {r.get('valid')}, q {r.get('q_declared')}")

    print(f"{len(papers)} readings also carry a papers block that closes")

    rows = list(csv.DictReader(open(RESULTS, encoding="utf-8")))
    fields = list(rows[0].keys())
    merged = skipped = 0
    merged_papers = []
    for row in rows:
        # The papers block travels separately: a station can have its ballots
        # accounted for and its votes not, or the reverse, and each is published
        # on the identity that vouches for it.
        r = papers.get(row["bureau_code"])
        if r is not None and row["papers_certified"] != "1":
            for k, col in zip(PAPERS, ("s_extracted", "valid", "blank", "spoilt")):
                row[col] = str(int(r[k]))
            row["papers_certified"] = "1"
            merged_papers.append(row["bureau_code"])

        r = good.get(row["bureau_code"])
        if r is None:
            continue
        if row["votes_certified"] == "1":
            # The reproducible route already has this one; never displace it.
            skipped += 1
            continue
        for c in CAND:
            row[c] = str(int(r[c]))
        total = sum(int(r[c]) for c in CAND)
        # The total is only written where the form was actually read; a value
        # the identity implies is not a reading and is not recorded as one.
        if r.get("valid") is not None:
            row["valid"] = str(int(r["valid"]))
        if r.get("q_declared") is not None:
            row["q_declared"] = str(int(r["q_declared"]))
        row["candidate_sum"] = str(total)
        row["votes_certified"] = "1"
        row["reading"] = "vision"
        row["status"] = "read_by_eye"
        merged += 1

    print(f"\nmerged {merged} vote blocks and {len(merged_papers)} papers blocks; "
          f"{skipped} already certified by the reproducible route and left alone")
    if a.dry_run:
        print("dry run, dataset untouched")
        return
    if not merged and not merged_papers:
        return
    fd, tmp = tempfile.mkstemp(dir="data", suffix=".csv")
    with os.fdopen(fd, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    if sum(1 for _ in open(tmp, encoding="utf-8")) != len(rows) + 1:
        os.unlink(tmp)
        sys.exit("refusing to install a dataset of the wrong length")
    shutil.move(tmp, RESULTS)
    os.chmod(RESULTS, 0o644)
    n = sum(1 for r in csv.DictReader(open(RESULTS, encoding="utf-8"))
            if r["votes_certified"] == "1")
    v = sum(1 for r in csv.DictReader(open(RESULTS, encoding="utf-8"))
            if r["reading"] == "vision")
    print(f"-> {RESULTS}: {n} certified, of which {v} read by eye")


if __name__ == "__main__":
    main()
