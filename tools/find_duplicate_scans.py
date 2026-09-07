"""Find the bureau codes the archive backs with the same scan.

Every row in this dataset is one bureau code, because that is how ISIE publishes
the archive: one file per code, 9,448 of them. That count is the denominator for
every share in the codebook, so it is worth checking that the files behind it are
actually distinct.

They are not, in 8 cases. **17 bureau codes are backed by 8 distinct scans.** For
6 of the 8 the *source files themselves* are byte-identical — the archive serves
the same PV under two different names — so this is a property of the published
archive, not of the pipeline reading it.

Two shapes, and they mean different things:

- **a malformed code.** `0101011205` is ten digits where every real code is
  eleven, `211301120201` is twelve. Each shares its scan with a well-formed
  sibling in the same polling centre. These read as the archive publishing one
  station twice, once under a typo.
- **two real stations, one scan.** `02110310201` and `02111210201` are different
  polling centres in مرناق, and only one form was published. One of those two
  rows therefore holds the other station's numbers, and nothing in the archive
  says which.

Nothing is deleted here. Which of a pair is "the real one" is not a question the
scans can answer, and dropping rows would silently change the denominator. The
rows are marked instead, so anyone summing stations can decide for themselves.

Usage: python3 tools/find_duplicate_scans.py [--write]
"""
import argparse, collections, csv, glob, hashlib, json, os, shutil, sys, tempfile

RESULTS = "data/pv_presidential_2024.csv"
UPRIGHT = ".cache/pv_upright"
MANIFEST = ".cache/pv_all_manifest.csv"
OUT = "data/verification/duplicate_scans.jsonl"
COLUMN = "duplicate_scan"
CODE_LEN = 11


def digest(path):
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    groups = collections.defaultdict(list)
    for p in glob.glob(os.path.join(UPRIGHT, "*.jpg")):
        groups[digest(p)].append(os.path.basename(p)[:-4])
    dups = {k: sorted(v) for k, v in groups.items() if len(v) > 1}

    sources = collections.defaultdict(list)
    if os.path.exists(MANIFEST):
        for r in csv.DictReader(open(MANIFEST, encoding="utf-8")):
            sources[r["bureau_code"]].append(r["local_path"])

    rows = list(csv.DictReader(open(RESULTS, encoding="utf-8")))
    fields = list(rows[0].keys())
    by = {r["bureau_code"]: r for r in rows}

    print(f"{len(groups)} distinct scans behind {sum(len(v) for v in groups.values())} "
          f"bureau codes")
    print(f"{len(dups)} scans are shared, covering "
          f"{sum(len(v) for v in dups.values())} codes\n")

    notes, marked, doubled = [], set(), 0
    for codes in sorted(dups.values()):
        src = {}
        for c in codes:
            paths = [p for p in sources.get(c, []) if os.path.exists(p)]
            src[c] = digest(paths[0]) if paths else None
        same_source = len(set(v for v in src.values() if v)) == 1
        centres = {by[c]["polling_centre"] for c in codes if c in by}
        malformed = [c for c in codes if len(c) != CODE_LEN]
        kind = ("a malformed code duplicating a well-formed one" if malformed
                else "two well-formed codes, one scan")
        print(f"  {' '.join(codes)}")
        print(f"      source files {'identical' if same_source else 'differ'}; "
              f"{len(centres)} distinct polling centre name(s); {kind}")
        certified = [c for c in codes if c in by and by[c]["votes_certified"] == "1"]
        if len(certified) > 1:
            doubled += sum(int(by[c]["valid"]) for c in certified[1:]
                           if by[c]["valid"])
        for c in codes:
            if c not in by:
                continue
            marked.add(c)
            notes.append({
                "bureau_code": c, "shares_scan_with": [x for x in codes if x != c],
                "source_files_identical": same_source,
                "code_malformed": len(c) != CODE_LEN,
                "distinct_centre_names": len(centres),
                "note": "the archive publishes this scan under more than one "
                        "bureau code; the values on this row are not "
                        "independently sourced",
            })

    print(f"\n{len(marked)} rows marked. If every code in a group is counted, "
          f"{doubled:,} valid votes are counted more than once.")

    if COLUMN not in fields:
        fields.append(COLUMN)
    for r in rows:
        r[COLUMN] = "1" if r["bureau_code"] in marked else ""

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
    with open(OUT, "w", encoding="utf-8") as fh:
        for n in notes:
            fh.write(json.dumps(n, ensure_ascii=False) + "\n")
    print(f"\n-> {RESULTS} (+{COLUMN})\n-> {OUT}")


if __name__ == "__main__":
    main()
