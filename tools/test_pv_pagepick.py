"""Regression test: page selection on the bundles that used to be got wrong.

The archive holds several images for about a fifth of the bureaux, and only one
of them is the counting record. The first version of the orient stage chose the
page whose masthead OCR'd best; it was wrong on 126 bureaux, because a poor scan
of the record OCRs to nothing while the correction decision beside it -- same
ISIE masthead -- scores 2, so any legible other page wins.

Ground truth here is the page the representatives table was actually read off,
station by station, and recorded in data/verification/representatives_pages.csv.
Those readings are in the published dataset, so the page behind each is known.

Usage: python3 tools/test_pv_pagepick.py [limit]
"""
import csv, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

TRUTH = "data/verification/representatives_pages.csv"


def load_truth():
    """bureau_code -> {(basename, page index)} the table was read from."""
    if not os.path.exists(TRUTH):
        raise SystemExit(f"missing {TRUTH}")
    lines = [l for l in open(TRUTH, encoding="utf-8") if not l.startswith("#")]
    out = {}
    for r in csv.DictReader(lines):
        out.setdefault(r["bureau_code"], set()).add(
            (os.path.basename(r["source"]), int(r["page"])))
    return out


def archived(codes):
    seen = {}
    for r in csv.DictReader(open(".cache/pv_all_manifest.csv", encoding="utf-8")):
        if r["bureau_code"] in codes and os.path.exists(r["local_path"]):
            seen.setdefault(r["bureau_code"], set()).add(r["local_path"])
    return {c: sorted(v) for c, v in seen.items()}


def main():
    import extract_pvs as E
    truth = load_truth()
    files = archived(set(truth))
    codes = sorted(files)
    if len(sys.argv) > 1:
        codes = codes[:int(sys.argv[1])]
    ok = bad = 0
    t0 = time.time()
    for code in codes:
        img, deg, score, why = E._pick_page(files[code])
        if img is None:
            bad += 1
            print(f"  {code}: no readable page")
            continue
        got = (os.path.basename(why["src"]), why["page"])
        if got in truth[code]:
            ok += 1
        else:
            bad += 1
            print(f"  {code}: picked {got[0]} p{got[1]} on {why['decisive']}, "
                  f"table is on {sorted(truth[code])}")
    n = ok + bad
    print(f"\npage picker: {ok}/{n} land on the page carrying the table")
    print(f"{(time.time() - t0) / max(n, 1):.1f}s per bureau")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
