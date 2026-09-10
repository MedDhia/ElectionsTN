"""Look for the representatives table on the archive's *other* pages.

The orientation stage keeps one image per bureau. Where the archive holds
several -- a bundle of four JPGs, or a PDF of four to six pages -- it picks the
page whose masthead scores highest, and the decision correcting a counting
record carries the same masthead as the record itself. So a bureau can end up
represented by the wrong sheet, and the representatives table sits unread on a
page nothing ever opened.

This walks every archived page for a list of bureaux, runs the table locator on
each, and reports which page carries a table. The locator is the right test
because it is structural: it wants two interior column rules at 0.20 and 0.60 of
a band's width and rows at fixed fractions of it, which no other block of the
form has. Nothing else on these pages fits that.

Usage: python3 tools/reps_pages.py <codes.txt> <out.json> [workers]
"""
import csv, json, os, sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor

MANIFEST = ".cache/pv_all_manifest.csv"
PDF_DPI = 200


def archived(codes):
    """bureau_code -> the paths the download stage actually left on disk."""
    seen = defaultdict(set)
    for r in csv.DictReader(open(MANIFEST, encoding="utf-8")):
        if r["bureau_code"] in codes and os.path.exists(r["local_path"]):
            seen[r["bureau_code"]].add(r["local_path"])
    return {c: sorted(v) for c, v in seen.items()}


def _pages(path):
    """Every page of `path` as a BGR array: one for an image, N for a PDF."""
    import cv2
    import numpy as np
    if not path.lower().endswith(".pdf"):
        img = cv2.imread(path)
        return [] if img is None else [(0, img)]
    import pypdfium2 as pdfium
    out = []
    try:
        doc = pdfium.PdfDocument(path)
        for i in range(len(doc)):
            pil = doc[i].render(scale=PDF_DPI / 72).to_pil().convert("RGB")
            out.append((i, cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)))
    except Exception:
        pass
    return out


def _scan(args):
    code, path = args
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import pv_reps_geom as G
    hits = []
    for page, img in _pages(path):
        try:
            loc, _, deg, _ = G.locate_any(img)
        except Exception:
            loc = None
        if loc is not None:
            hits.append({"path": path, "page": page, "rotation": deg,
                         "col_rules": loc["col_rules"], "row_rules": loc["row_rules"]})
    return code, hits


def main():
    codes = {l.strip() for l in open(sys.argv[1], encoding="utf-8") if l.strip()}
    out_path = sys.argv[2]
    workers = int(sys.argv[3]) if len(sys.argv) > 3 else (os.cpu_count() or 4)
    files = archived(codes)
    jobs = [(c, p) for c, ps in files.items() for p in ps]
    print(f"{len(codes)} bureaux, {len(jobs)} archived files, {workers} workers",
          flush=True)
    found = defaultdict(list)
    with ProcessPoolExecutor(workers) as ex:
        for i, (code, hits) in enumerate(ex.map(_scan, jobs), 1):
            found[code] += hits
            if i % 25 == 0:
                print(f"  {i}/{len(jobs)}  {sum(1 for v in found.values() if v)} "
                      f"bureaux with a table", flush=True)
    found = {c: v for c, v in found.items() if v}
    json.dump(found, open(out_path, "w"), indent=1)
    print(f"\n{len(found)} of {len(codes)} bureaux have a page carrying the table "
          f"-> {out_path}")


if __name__ == "__main__":
    main()
