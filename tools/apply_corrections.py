"""Apply the correction decisions to the dataset, but only where they identify themselves.

A *قرار تصحيح محضر فرز* names three things: the field, the value recorded in
error, and the value replacing it. That middle column is what makes the decision
safe to apply automatically. If the error value the decision names is what the
dataset currently holds for that field, the decision and the row are the same
station's and the same reading, and the replacement can be made. If it is not,
something is wrong — the wrong page, a misread digit, a mis-filed bundle — and
the decision is recorded but not applied.

The check is not decoration. Bureau 120611101 is filed with a decision whose own
header codes the station 12-06-11-1-01-01, while the archive folder gives a
nine-digit code and the dataset row under it holds a valid of 318 against the
decision's 418. Every error value fails to match, and the row is left alone.

After a correction lands, the votes block is re-certified from scratch: a
decision that changes a candidate can turn a closing form into a non-closing one
and vice versa, and the published flag has to follow the corrected numbers rather
than the ones they replaced.

Usage: python3 tools/apply_corrections.py [--write]
"""
import argparse, csv, json, os, shutil, tempfile

RESULTS = "data/pv_presidential_2024.csv"
REGISTER = "data/verification/corrections.jsonl"
READINGS = "data/verification/lowres_readings.jsonl"
CAND = ("zammel", "maghzaoui", "saied")
# decision row -> dataset column; rows with no published column map to None
FIELDS = {
    "a_registered": "a_registered", "b_delivered": "b_delivered",
    "c_signed": "c_signed", "d_damaged": "d_damaged", "r_remaining": "r_remaining",
    "s_extracted": "s_extracted", "valid": "valid", "blank": "blank",
    "spoilt": "spoilt", "q_declared": "q_declared",
    "zammel": "zammel", "maghzaoui": "maghzaoui", "saied": "saied",
    "match1": None, "match2": None, "match3": None, "match4": None,
    "n_sum": None, "other": None,
}


def as_int(v):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def readings():
    """What the counting record was read to say, for rows the gate did not publish.

    A station whose form does not close has empty cells in the dataset, so a
    decision's error value has nothing to match against there. But the reading
    exists — it is why the form was known not to close — and it is the counting
    record's own figure, which is exactly what the decision claims to supersede.
    So the match falls back to it, and the corrected values are then published.
    """
    out = {}
    if not os.path.exists(READINGS):
        return out
    for line in open(READINGS, encoding="utf-8"):
        d = json.loads(line)
        out[d["bureau_code"]] = d
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    rows = list(csv.DictReader(open(RESULTS, encoding="utf-8")))
    cols = list(rows[0].keys())
    by = {r["bureau_code"]: r for r in rows}
    read = readings()

    applied = skipped = unmatched = already = 0
    touched, seeded = set(), set()
    notes = []
    for line in open(REGISTER, encoding="utf-8"):
        d = json.loads(line)
        r = by.get(d["bureau_code"])
        if r is None:
            notes.append(f"  no dataset row for {d['bureau_code']}")
            unmatched += 1
            continue
        # A station whose form did not close has empty cells even where it was
        # read: merge_vision only publishes rows the arithmetic vouched for. The
        # decision is about to supply the missing piece, so seed the row from the
        # reading first — then the error values have something to match, and the
        # corrected row is complete rather than half-filled.
        src = read.get(d["bureau_code"])
        if src:
            for c in CAND + ("valid", "q_declared"):
                v = as_int(src.get(c))
                if v is not None and not r.get(c):
                    r[c] = str(v)
                    seeded.add(d["bureau_code"])

        for f in d["fields"]:
            col = FIELDS.get(f["field"], "missing")
            if col == "missing":
                notes.append(f"  {d['bureau_code']}: unknown field {f['field']!r}")
                continue
            if col is None:
                skipped += 1          # a reconciliation row; nothing published
                continue
            was, now = as_int(f.get("was")), as_int(f.get("now"))
            have = as_int(r.get(col))
            if now is not None and have == now:
                # The clerk often struck the wrong figure out on the counting
                # record itself as well as issuing the decision, and the reader
                # picked up the amended value. Nothing to do, and it is evidence
                # that the decision and the row are the same station's.
                already += 1
                continue
            if was is not None and have != was:
                notes.append(f"  {d['bureau_code']}: {col} says was={was} "
                             f"but dataset holds {r.get(col)!r} — not applied")
                unmatched += 1
                continue
            if was is None and have not in (None, ""):
                notes.append(f"  {d['bureau_code']}: {col} recorded as blank on the "
                             f"form but dataset holds {r.get(col)!r} — not applied")
                unmatched += 1
                continue
            if now is None:
                continue
            r[col] = str(now)
            applied += 1
            touched.add(d["bureau_code"])

    # re-certify the votes block wherever a correction landed
    flipped = []
    for code in sorted(touched):
        r = by[code]
        vals = [as_int(r[c]) for c in CAND]
        totals = [as_int(r[k]) for k in ("valid", "q_declared")]
        totals = [t for t in totals if t is not None]
        ok = (all(v is not None for v in vals) and totals
              and len(set(totals)) == 1 and sum(vals) == totals[0])
        before = r["votes_certified"]
        r["votes_certified"] = "1" if ok else "0"
        r["candidate_sum"] = str(sum(v for v in vals if v is not None))
        if before != r["votes_certified"]:
            flipped.append((code, before, r["votes_certified"]))

    print(f"{applied} field corrections applied across {len(touched)} bureaux; "
          f"{skipped} reconciliation rows carry no published column; "
          f"{unmatched} not applied; {already} already at the corrected value; "
          f"{len(seeded)} rows seeded from a reading first")
    for n in notes:
        print(n)
    for code, b, aft in flipped:
        print(f"  votes_certified {b} -> {aft} for {code}")

    if not a.write:
        print("dry run, dataset untouched")
        return
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(RESULTS), suffix=".csv")
    with os.fdopen(fd, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    shutil.move(tmp, RESULTS)
    print(f"-> {RESULTS}")


if __name__ == "__main__":
    main()
