"""Correct the rows where the same slip landed twice and the identity closed.

`zammel + maghzaoui + saied == valid` is one equation in four unknowns. It
catches a misread candidate — unless the reader made a matching error somewhere
else in the same equation. Two shapes of that turned up:

- **the candidate rows transposed.** Rows 2 and 3 of the table are Maghzaoui and
  Saied; read in the wrong order the total is untouched and the identity closes
  exactly. Four stations were published with hundreds of Saied's votes credited
  to Maghzaoui.
- **the same leading-digit slip in two fields.** A reader that drops the leading
  3 from `saied` and from `valid` produces 29 + 6 + 19 == 54, which closes and is
  wrong by three hundred. One station gained a leading 1 in both instead, and one
  pair of candidates traded a hundred between them.

`tools/screen_split_errors.py` shortlisted 49 rows out of the 1,768 the words
column disagrees with; reading all 49 by eye found the eleven below and cleared
the other 38. Every correction here is what the **Arabic words** on the form say,
which is the one channel on the page that is independent of the digit cells, and
every one is checked against the form's identities before it is written.

Usage: python3 tools/fix_split_errors.py [--write]
"""
import argparse, csv, json, os, shutil, sys, tempfile

RESULTS = "data/pv_presidential_2024.csv"
LOG = "data/verification/split_errors.jsonl"

CAND = ("zammel", "maghzaoui", "saied")

# bureau -> (fields to set, one-line reason). The reason is what the words say.
FIXES = {
    # --- candidate rows 2 and 3 transposed -------------------------------
    "03070410202": (dict(maghzaoui=2, saied=178),
                    "rows 2 and 3 transposed; the words read اثنان for Maghzaoui "
                    "and مائة و ثمانية و سبعون for Saied"),
    "03070510201": (dict(maghzaoui=5, saied=359),
                    "rows 2 and 3 transposed; the words read خمسة for Maghzaoui "
                    "and ثلاث مائة و تسعة و خمسون for Saied"),
    "06090610201": (dict(maghzaoui=4, saied=184),
                    "rows 2 and 3 transposed; the words read أربعة for Maghzaoui "
                    "and مائة و أربعة و ثمانون for Saied"),
    "11010510101": (dict(maghzaoui=5, saied=468),
                    "rows 2 and 3 transposed; the words read خمسة أصوات for "
                    "Maghzaoui and أربعة مائة و ثمانية و ستون for Saied"),
    # --- a hundred traded between two candidates, total untouched --------
    "13030310101": (dict(zammel=11, saied=170),
                    "a leading 1 added to Zammel and dropped from Saied; the "
                    "words read eleven and مائة و سبعون"),
    "23010310102": (dict(maghzaoui=2, saied=93),
                    "the split is simply wrong; the words read صوتان for "
                    "Maghzaoui and ثلاثة و تسعون صوتا for Saied"),
    # --- the same slip in a candidate and in the total --------------------
    "05080810101": (dict(saied=207, valid=208, q_declared=208, spoilt=15),
                    "Saied and the total both one short; the words read مئتان و "
                    "سبعة and the form's (ق) box states 0208, with (ف) 0015"),
    "23040510301": (dict(saied=319, valid=354, q_declared=354,
                         s_extracted=375, blank=10, spoilt=11),
                    "the leading 3 dropped from Saied and from the total; the "
                    "words read ثلاثمائة و تسعة عشر صوتا and (ق) states 0354"),
    "23090710308": (dict(saied=70, valid=79, q_declared=79,
                         s_extracted=82, blank=0, spoilt=3),
                    "the leading 7 dropped from Saied and from the total; the "
                    "words read سبعون صوتا and (ق) states 0079"),
    "24051110101": (dict(saied=39, valid=40, q_declared=40,
                         s_extracted=40, blank=0, spoilt=0),
                    "a 1 written into the empty hundreds cell of Saied and of "
                    "the total; the words read تسعة و ثلاثون and (ق) states 0040"),
    # --- a papers column contradicted by three other fields ---------------
    "07070710102": (dict(s_extracted=231, ballots_certified=0),
                    "(س) published as 31 against 231 signed, 231 voted and "
                    "197+6+28 = 231; (ب) or (ر) is misread, so the ballot "
                    "account is withdrawn rather than balanced on a wrong (س)"),
}

PAPERS = ("s_extracted", "valid", "blank", "spoilt")


def as_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def check(code, r):
    """The corrected row must satisfy every identity its fields can express."""
    vals = {k: as_int(r[k]) for k in
            CAND + PAPERS + ("q_declared", "d_damaged", "r_remaining", "b_delivered")}
    if all(vals[c] is not None for c in CAND) and vals["valid"] is not None:
        if sum(vals[c] for c in CAND) != vals["valid"]:
            sys.exit(f"{code}: candidates sum to {sum(vals[c] for c in CAND)}, "
                     f"valid {vals['valid']} — refusing to write")
    if vals["q_declared"] is not None and vals["valid"] is not None:
        if vals["q_declared"] != vals["valid"]:
            sys.exit(f"{code}: (ق) {vals['q_declared']} != (ص) {vals['valid']}"
                     " — refusing to write")
    if r["papers_certified"] == "1" and all(vals[k] is not None for k in PAPERS):
        if vals["s_extracted"] != sum(vals[k] for k in PAPERS[1:]):
            sys.exit(f"{code}: {vals['s_extracted']} extracted != "
                     f"{vals['valid']}+{vals['blank']}+{vals['spoilt']}"
                     " — refusing to write")
    if r["ballots_certified"] == "1" and all(
            vals[k] is not None for k in ("s_extracted", "d_damaged",
                                          "r_remaining", "b_delivered")):
        if (vals["s_extracted"] + vals["d_damaged"] + vals["r_remaining"]
                != vals["b_delivered"]):
            sys.exit(f"{code}: ballots do not account to {vals['b_delivered']}"
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
        for k, v in new.items():
            r[k] = str(v)
        for c in CAND:
            if c in new:
                moved[c] += int(new[c]) - (as_int(before[c]) or 0)
        if all(r[c] for c in CAND):
            r["candidate_sum"] = str(sum(int(r[c]) for c in CAND))
            if as_int(r["valid"]):
                r["saied_share_pct"] = str(round(100 * int(r["saied"])
                                                 / int(r["valid"]), 2))
        if as_int(r["a_registered"]) and as_int(r["w_voted"]):
            r["turnout_pct"] = str(round(100 * int(r["w_voted"])
                                         / int(r["a_registered"]), 2))
        if "s_extracted" in new and r["papers_certified"] != "1":
            r["papers_certified"] = "1"
        check(code, r)
        r["reading"] = "vision"
        r["status"] = "read_by_eye"
        r["split_corroborated"] = "1"
        notes.append({"bureau_code": code, "note": why,
                      "was": before, "now": {k: str(v) for k, v in new.items()}})
        print(f"  {code}: " + ", ".join(
            f"{k} {before[k] or '-'} -> {v}" for k, v in new.items()))

    print("\nnet movement across the eleven rows:")
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
    shutil.move(tmp, RESULTS)
    with open(LOG, "w", encoding="utf-8") as fh:
        for n in notes:
            fh.write(json.dumps(n, ensure_ascii=False) + "\n")
    print(f"\n-> {RESULTS}\n-> {LOG}")


if __name__ == "__main__":
    main()
