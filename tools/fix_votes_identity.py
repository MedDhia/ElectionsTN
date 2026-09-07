"""Repair the five rows published with a votes certification that does not close.

`votes_certified` asserts `zammel + maghzaoui + saied == valid`. Five rows carry
it while their own published columns do not satisfy it — found by
`tools/audit_identities.py`, which re-derives the identities from the finished
file rather than from inside the tool that wrote each block.

These are not reachable from the decoder. Each block was solved and certified at
some point, and a later pass rewrote one cell of it: the certification survived
the value it was asserting. That is the failure mode a separate audit exists to
catch, and these five are what it caught.

Every fix below is read off the scan at magnification and confirmed by at least
two channels the changed cell is not part of:

- **04070510205** — `(ص)` reads 0216, `(ق)` reads 0216, the candidates sum to
  216 and `(ن)` 227 = 216 + 1 + 10. Published `valid` 217 and `blank` 0 are both
  wrong; the words read اثنان وعشرون / ستة / مائة وثمانية وثمانون.
- **04080410201** — the zammel cell has its units digit struck through and was
  read as 30. The words read واحد وثلاثون. At 31 two identities close at once:
  31 + 9 + 355 = 395 = `(ص)`, and 395 + 2 + 30 = 427 = `(ن)`. At 30 neither
  does. The form's own `(ق)` says 394, so the sheet contradicts itself by one —
  that stays visible in `q_declared` rather than being smoothed away.
- **05030910202** — `(ص)` 0216, `(ق)` 0216, candidates 216, `(ن)` 227 =
  216 + 5 + 6. Published `valid` 214 and `spoilt` 8 are wrong. The form's
  أسباب عدم التطابق line explains a ballot voided during voting.
- **07070810101** — the words read سبعة أصوات for Zammel, and 7 + 1 + 141 = 149
  = `(ص)`, with `(ن)` 155 = 149 + 2 + 4. Published zammel 4 is wrong, and `(ق)`
  reads 0149 rather than the published 146.
- **13051210101** — candidates 2 + 4 + 314 = 320, `(ق)` reads 0320, `(ص)` reads
  0320 and the words read صوتان فقط / أربعة أصوات / ثلاثمائة وأربعة عشر. Published
  `valid` 323 is wrong.

One of the five loses a flag rather than gaining a value. On 13051210101 `(ن)`
reads 0330, so `valid + blank + spoilt` must be 330; with `valid` corrected to
320 the published `blank` 5 and `spoilt` 2 reach only 327, and those two cells are
not legible enough on this scan to say which is wrong. So `papers_certified` is
**withdrawn** there. Correcting `valid` and leaving the papers flag standing
would publish a certification I had just disproved.

Usage: python3 tools/fix_votes_identity.py [--write]
"""
import argparse, csv, json, os, shutil, sys, tempfile

RESULTS = "data/pv_presidential_2024.csv"
LOG = "data/verification/votes_identity.jsonl"

CAND = ("zammel", "maghzaoui", "saied")
PAPERS = ("s_extracted", "valid", "blank", "spoilt")

# bureau -> (fields to set, what the scan says)
FIXES = {
    "04070510205": (dict(valid=216, blank=1),
                    "(ص) 0216, (ق) 0216, candidates 22+6+188 = 216 and "
                    "(ن) 0227 = 216+1+10; published valid 217 and blank 0"),
    "04080410201": (dict(zammel=31),
                    "the zammel units digit is struck through; the words read "
                    "واحد وثلاثون and 31+9+355 = 395 = (ص), with "
                    "(ن) 0427 = 395+2+30. The form's own (ق) 0394 is the outlier"),
    "05030910202": (dict(valid=216, spoilt=6),
                    "(ص) 0216, (ق) 0216, candidates 18+6+192 = 216 and "
                    "(ن) 0227 = 216+5+6; published valid 214 and spoilt 8"),
    "07070810101": (dict(zammel=7, q_declared=149),
                    "the words read سبعة أصوات; 7+1+141 = 149 = (ص) and "
                    "(ن) 0155 = 149+2+4. (ق) reads 0149, not the published 146"),
    "13051210101": (dict(valid=320, papers_certified=0),
                    "candidates 2+4+314 = 320, (ق) 0320, (ص) 0320 and the words "
                    "read صوتان فقط / أربعة أصوات / ثلاثمائة وأربعة عشر. (ن) 0330 "
                    "needs blank+spoilt = 10 against the published 7, and those "
                    "two cells are illegible here, so the papers flag is withdrawn"),
}

# Rows where the sheet itself disagrees with the corrected total, so the
# published `q_declared` is left contradicting `valid` on purpose. Smoothing it
# would hide a discrepancy that is on the paper, not in the reading.
Q_MAY_DIFFER = {"04080410201"}


def as_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def check(code, r):
    """Refuse to install a row that still fails an identity it can express."""
    v = {k: as_int(r[k]) for k in
         CAND + PAPERS + ("q_declared", "d_damaged", "r_remaining", "b_delivered")}
    if r["votes_certified"] == "1":
        if any(v[c] is None for c in CAND) or v["valid"] is None:
            sys.exit(f"{code}: certified votes with an unreadable field")
        if sum(v[c] for c in CAND) != v["valid"]:
            sys.exit(f"{code}: candidates sum to {sum(v[c] for c in CAND)}, "
                     f"valid {v['valid']} — refusing to write")
    if (code not in Q_MAY_DIFFER and v["q_declared"] is not None
            and v["valid"] is not None and v["q_declared"] != v["valid"]):
        sys.exit(f"{code}: (ق) {v['q_declared']} != (ص) {v['valid']}"
                 " — refusing to write")
    if r["papers_certified"] == "1" and all(v[k] is not None for k in PAPERS):
        if v["s_extracted"] != sum(v[k] for k in PAPERS[1:]):
            sys.exit(f"{code}: (س) {v['s_extracted']} != "
                     f"{v['valid']}+{v['blank']}+{v['spoilt']}"
                     " — refusing to write")
    if r["ballots_certified"] == "1" and all(
            v[k] is not None for k in ("s_extracted", "d_damaged",
                                       "r_remaining", "b_delivered")):
        if v["s_extracted"] + v["d_damaged"] + v["r_remaining"] != v["b_delivered"]:
            sys.exit(f"{code}: ballots do not account to {v['b_delivered']}"
                     " delivered — refusing to write")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    rows = list(csv.DictReader(open(RESULTS, encoding="utf-8")))
    fields = list(rows[0].keys())
    by = {r["bureau_code"]: r for r in rows}

    moved = {c: 0 for c in CAND}
    notes = []
    for code, (new, why) in FIXES.items():
        r = by.get(code)
        if r is None:
            sys.exit(f"{code} is not in the dataset")
        before = {k: r[k] for k in new}
        for k, val in new.items():
            r[k] = str(val)
        for c in CAND:
            if c in new:
                moved[c] += int(new[c]) - (as_int(before[c]) or 0)
        if all(r[c] for c in CAND):
            r["candidate_sum"] = str(sum(int(r[c]) for c in CAND))
            if as_int(r["valid"]):
                r["saied_share_pct"] = str(round(100 * int(r["saied"])
                                                 / int(r["valid"]), 2))
        check(code, r)
        r["reading"] = "vision"
        r["status"] = "read_by_eye"
        # The words were read by eye here, against the corrected digits; that is
        # better evidence on the split than the word model's own pass, so the
        # flag is set and `refresh_splits.py` leaves these rows alone.
        r["split_corroborated"] = "1"
        notes.append({"bureau_code": code, "note": why, "was": before,
                      "now": {k: str(val) for k, val in new.items()}})
        print(f"  {code}: " + ", ".join(
            f"{k} {before[k] or '-'} -> {val}" for k, val in new.items()))

    print("\nnet movement in candidate votes:")
    for c in CAND:
        print(f"  {c:10s} {moved[c]:+d}")

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
