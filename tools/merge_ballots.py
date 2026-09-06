"""Publish the ballot accounts read by eye.

The third of the form's three blocks: `(ب) delivered == (س) extracted +
(د) damaged + (ر) remaining`. It is the one block that carries no vote — it
accounts for ballot stock, not results — which is why it was left until last, and
why nothing here can move a candidate total.

Readings come from `data/verification/ballot_readings.jsonl`, written by the
recorder, which refuses any reading that does not satisfy the identity against
the `(س)` the dataset already publishes. This re-checks that before writing, and
publishes `a_registered` and `c_signed` alongside when they were legible.

Where the reading disagrees with an already-published `b_delivered`, the reading
wins: the published value came from the decoder, the reading closes the identity
against a `(س)` it was not derived from, and the disagreements are logged.

Usage: python3 tools/merge_ballots.py [--write]
"""
import argparse, csv, json, os, shutil, sys, tempfile

RESULTS = "data/pv_presidential_2024.csv"
READINGS = "data/verification/ballot_readings.jsonl"


def as_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--readings", default=READINGS)
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    if not os.path.exists(a.readings):
        sys.exit(f"{a.readings} not found")
    readings = {}
    for line in open(a.readings, encoding="utf-8"):
        d = json.loads(line)
        readings[d["bureau_code"]] = d

    rows = list(csv.DictReader(open(RESULTS, encoding="utf-8")))
    fields = list(rows[0].keys())
    merged, changed, skipped = 0, [], 0

    for r in rows:
        d = readings.get(r["bureau_code"])
        if d is None:
            continue
        s = as_int(r["s_extracted"])
        if s is None:
            skipped += 1
            continue
        if s + d["d_damaged"] + d["r_remaining"] != d["b_delivered"]:
            print(f"  {r['bureau_code']}: no longer closes against (س) {s} "
                  "— not merged")
            skipped += 1
            continue
        # `m_total` is read but is not a published column, like `n_total`; the
        # identity is asserted against it and `b_delivered` carries the value.
        for col in ("b_delivered", "d_damaged", "r_remaining"):
            was = r[col]
            r[col] = str(d[col])
            if was and was != r[col]:
                changed.append((r["bureau_code"], col, was, r[col]))
        for col in ("a_registered", "c_signed"):
            if col in d and not r[col]:
                r[col] = str(d[col])
        if as_int(r["a_registered"]) and as_int(r["w_voted"]):
            r["a_registered_ok"] = str(int(int(r["a_registered"])
                                           >= int(r["w_voted"])))
            r["turnout_pct"] = str(round(100 * int(r["w_voted"])
                                         / int(r["a_registered"]), 2))
        r["ballots_certified"] = "1"
        merged += 1

    print(f"{len(readings)} readings: {merged} merged, {skipped} held back")
    if changed:
        print(f"\n{len(changed)} published values the reading overrules:")
        for code, col, was, now in changed[:40]:
            print(f"  {code}  {col} {was} -> {now}")
        if len(changed) > 40:
            print(f"  ... and {len(changed) - 40} more")

    n = sum(1 for r in rows if r["ballots_certified"] == "1")
    print(f"\nballots_certified: {n:,} of {len(rows):,} "
          f"({100 * n / len(rows):.1f}%)")

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
    print(f"\n-> {RESULTS}")


if __name__ == "__main__":
    main()
