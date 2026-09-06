"""Resolve the rows where the ballots column and the paper account disagree.

`valid_corroborated == 0` marks the stations where `(س) extracted` and
`(ص) + (ع) + (ف)` do not agree. Two quite different things live under that flag,
and only reading the scan separates them:

- **a reading error in one cell.** Most of them. The form is legible and one of
  the four numbers was misread — a 9 taken for a 2, a leading 2 dropped, a blank
  cell read as zero. Correcting that one cell makes the identity close exactly,
  which is itself the evidence the correction is right: an arbitrary change does
  not land on a closing sum.
- **a discrepancy the form itself records.** The counting officers wrote two
  numbers that differ, which is why the form carries a `مطابقة 3` box for
  `(و) - (ن)`. Nothing is wrong with the reading and nothing here should touch
  it.

All 29 were rendered and read. 21 are the first kind and are corrected below; 8
are the second kind or could not be settled, and are left alone with the reason
recorded. Every correction is checked against the identity before it is written,
and none of them moves a candidate value — `valid` is never touched, because
that would put the votes identity out.

Usage: python3 tools/fix_papers_contradictions.py [--write]
"""
import argparse, csv, json, os, shutil, sys, tempfile

RESULTS = "data/pv_presidential_2024.csv"
LOG = "data/verification/papers_contradictions.jsonl"
PAPERS = ("s_extracted", "valid", "blank", "spoilt")

# bureau -> (fields to set, what the form says)
FIXES = {
    "23041110201": (dict(s_extracted=239, blank=5, spoilt=2),
                    "(س) 0239, (ع) 0005, (ف) 0002 against 4/0/0 published"),
    "19070910201": (dict(s_extracted=274), "(س) 0274; the leading 2 was dropped"),
    "10120710301": (dict(spoilt=19), "(ف) 0019, read as 12"),
    "07010710301": (dict(s_extracted=106), "(س) 0106, read as 100"),
    "10120910103": (dict(blank=2, spoilt=5), "(ع) 0002 and (ف) 0005"),
    "03010710104": (dict(blank=7), "(ع) 0007, read as 3"),
    "03060110101": (dict(s_extracted=376), "(س) 0376, read as 372"),
    "13040110403": (dict(spoilt=4), "(ف) 0004, read as 0"),
    "15020110102": (dict(spoilt=4), "(ف) 0004, read as 8"),
    "18090510101": (dict(blank=4), "(ع) 0004, read as 0"),
    "04080310104": (dict(spoilt=13), "(ف) 0013, read as 11"),
    "10070310202": (dict(blank=2), "(ع) 0002, read as 0"),
    "22060110101": (dict(blank=2), "(ع) 0002, read as 0"),
    "01100510102": (dict(blank=6), "(ع) 0006, read as 5"),
    "02090410302": (dict(spoilt=7), "(ف) 0007, read as 8"),
    "05030110204": (dict(s_extracted=347), "(س) 0347, read as 346"),
    "06030210101": (dict(s_extracted=127), "(س) 0127, read as 126"),
    "06070310201": (dict(s_extracted=447), "(س) 0447, read as 446"),
    "17070910201": (dict(s_extracted=455), "(س) 0455, read as 454"),
    "21130210101": (dict(spoilt=5), "(ف) 0005, read as 4"),
    "24070410102": (dict(spoilt=2), "(ف) 0002, read as 3"),
}

# Read and deliberately not changed. The dataset keeps valid_corroborated == 0
# for these, which is the correct thing for it to say.
LEFT = {
    "13040410402": "the form itself is off by 10: (س) 0465 against (ص) 0455 "
                   "with (ع) and (ف) both zero",
    "02110310201": "the form itself is off by 4: (س) 0506 against 483+9+10",
    "02111210201": "the form itself is off by 4, and its scan is identical to "
                   "02110310201's — the archive may hold one file under two codes",
    "05070410503": "the form's (ص) reads 0196 but the candidates sum to 195; "
                   "changing (ص) would put the votes identity out",
    "12060810201": "(س) and (ص) are both overwritten and neither reading settles",
    "18070510106": "the form itself is off by 1: (س) 0231 against 224+4+4",
    "22090310301": "the last digit of (س) is an ambiguous 8/9; 129 would close "
                   "and 128 would not, which is not enough to overrule the scan",
    "13120810101": "the cached page is rotated 90 degrees and the block could "
                   "not be laid out for reading",
}


def as_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    rows = list(csv.DictReader(open(RESULTS, encoding="utf-8")))
    fields = list(rows[0].keys())
    by = {r["bureau_code"]: r for r in rows}

    flagged = {r["bureau_code"] for r in rows if r["valid_corroborated"] == "0"}
    unaccounted = flagged - set(FIXES) - set(LEFT)
    if unaccounted:
        sys.exit("flagged but not accounted for by this tool: "
                 + ", ".join(sorted(unaccounted)))

    notes = []
    for code, (new, why) in FIXES.items():
        r = by.get(code)
        if r is None:
            sys.exit(f"{code} is not in the dataset")
        before = {k: r[k] for k in new}
        for k, v in new.items():
            r[k] = str(v)
        vals = {k: as_int(r[k]) for k in PAPERS}
        if any(v is None for v in vals.values()):
            sys.exit(f"{code}: the papers block is incomplete — refusing to write")
        if vals["s_extracted"] != sum(vals[k] for k in PAPERS[1:]):
            sys.exit(f"{code}: {vals['s_extracted']} extracted != "
                     f"{vals['valid']}+{vals['blank']}+{vals['spoilt']}"
                     " — refusing to write")
        r["papers_certified"] = "1"
        notes.append({"bureau_code": code, "outcome": "corrected", "note": why,
                      "was": before, "now": {k: str(v) for k, v in new.items()}})
        print(f"  {code}: " + ", ".join(
            f"{k} {before[k] or '-'} -> {v}" for k, v in new.items())
            + f"   [{why}]")

    print()
    for code, why in LEFT.items():
        notes.append({"bureau_code": code, "outcome": "left", "note": why})
        print(f"  {code}: left as it is — {why}")

    print(f"\n{len(FIXES)} corrected, {len(LEFT)} left")
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
