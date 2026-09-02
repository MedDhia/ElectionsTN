"""Find the correction decisions hiding inside the PV bundles.

Some bureaux were filed with more than one document, and one of the documents is
a *قرار إصلاح* — a decision that names a field of the counting record, the value
recorded in error, and the value that replaces it. Where one exists, the counting
record's own figure for that field is superseded, so publishing the counting
record unchanged publishes the number the commission struck out.

Telling the two apart is a colour question before it is a reading question. The
counting record is printed on a pink ground and nothing else in the bundle is, so
one number per page separates them, at one render each, where registering every
page against the layout costs seconds each.

An earlier version of this file also required a fraction of near-black pixels, on
the theory that the decision's section headers are solid black bars. They are
often grey: on the bundle for 02020310202 the header bars measure 0.0007 of the
page against a threshold of 0.015, so the test threw away the very page that
carries the corrected numbers. The pink test alone is both simpler and right.

This only finds the pages. Reading the ticked rows is a separate step, because a
decision may tick nothing that affects the published columns.

Usage: python3 tools/find_corrections.py [--out FILE] [--render DIR]
"""
import argparse, csv, os

import cv2
import numpy as np
import pypdfium2 as pdfium

MANIFEST = ".cache/pv_all_manifest.csv"
DPI = 110            # enough for the colour test; reading happens elsewhere
PINK = 0.06          # fraction of pixels clearly red-over-blue


def measure(bgr):
    """Fraction of the page that is unmistakably the counting record's pink."""
    b, _g, r = cv2.split(bgr.astype("int16"))
    return float(np.mean((r - b > 28) & (r > 140)))


def bundles():
    """Every bureau filed with more than one page, and where its file is.

    A single-page file cannot hide a second document, so counting pages first
    keeps the colour test off the 9,900-odd bundles that cannot contain one.
    """
    for r in csv.DictReader(open(MANIFEST, encoding="utf-8")):
        p = r["local_path"]
        if not p.lower().endswith(".pdf") or not os.path.exists(p):
            continue
        try:
            n = len(pdfium.PdfDocument(p))
        except Exception:
            continue
        if n > 1:
            yield r["bureau_code"], p, n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=".cache/corrections.csv")
    ap.add_argument("--render", default=None, help="write flagged pages here")
    a = ap.parse_args()
    if a.render:
        os.makedirs(a.render, exist_ok=True)

    found = []
    for scanned, (code, path, _n) in enumerate(bundles()):
        try:
            doc = pdfium.PdfDocument(path)
        except Exception:
            continue
        for i in range(len(doc)):
            try:
                im = doc[i].render(scale=DPI / 72).to_pil().convert("RGB")
            except Exception:
                continue
            bgr = cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR)
            pink = measure(bgr)
            if pink < PINK:
                found.append((code, i, round(pink, 4)))
                if a.render:
                    cv2.imwrite(os.path.join(a.render, f"{code}_p{i}.png"), bgr)
        if scanned % 100 == 0:
            print("scanned", scanned, "bundles,", len(found), "pages", flush=True)

    with open(a.out, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["bureau_code", "page", "pink"])
        w.writerows(found)
    codes = {f[0] for f in found}
    print(f"{len(found)} candidate correction pages across {len(codes)} bureaux "
          f"-> {a.out}")


if __name__ == "__main__":
    main()

