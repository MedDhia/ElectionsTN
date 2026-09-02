"""Find the correction decisions hiding among the PV scans.

Some bureaux were filed with more than one document, and one of the documents is
a *قرار تصحيح محضر فرز* — a decision naming a field of the counting record, the
value recorded in error, and the value that replaces it, with a tick-box per
field and a section for the three candidates by name. Where one exists the
counting record's figure is superseded, so publishing the counting record
unchanged publishes the number the commission struck out.

Worse, a decision that changes a candidate cannot be caught by the arithmetic
gate: the counting record closed before the correction and still closes after it.
So those rows pass every check and are wrong anyway. They have to be found by
looking.

Two cheap tests do the finding. The counting record is the only thing in the
archive printed on a pink ground, so the pink fraction separates it from
everything else at one render per page. Then the decision is three pages of a
fixed form — a cover, the table of corrections, and the signatures — so
correlating a thumbnail against one known example of each page identifies which
is which: on the bundles checked by hand the table page scores 0.35-1.00 and
every other page at most 0.13.

An earlier version of this file scanned only multi-page PDFs. That was wrong
twice over: it also demanded a fraction of near-black pixels, on the theory that
the decision's section headers are solid bars, when they are often grey (0.0007
of the page for 02020310202 against a threshold of 0.015, which discarded
precisely the page carrying the corrected numbers); and 629 bureaux hold more
than one *file*, so a decision can sit in a second JPEG rather than a second PDF
page. Every file of every bureau is scanned now.

Usage: python3 tools/find_corrections.py [--out FILE] [--render DIR]
"""
import argparse, csv, os

import cv2
import numpy as np
import pypdfium2 as pdfium

MANIFEST = ".cache/pv_all_manifest.csv"
DPI = 110            # enough for both tests; reading happens elsewhere
PINK = 0.06          # below this the page is not the counting record
TABLE = 0.20         # above this the page is a decision's table of corrections

# One bundle whose three decision pages are known by inspection, used as the
# reference for page type. Keeping it as a code rather than checked-in images
# means the references are regenerated from the archive and can be re-checked.
REF = ("02020310202", {1: "cover", 2: "table", 3: "signs"})
THUMB = (120, 170)


def measure(bgr):
    """Fraction of the page that is unmistakably the counting record's pink."""
    b, _g, r = cv2.split(bgr.astype("int16"))
    return float(np.mean((r - b > 28) & (r > 140)))


def _unit(a):
    a = a - a.mean()
    return a / (np.linalg.norm(a) + 1e-6)


def thumb(bgr):
    return _unit(cv2.resize(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY),
                            THUMB).astype("float32"))


def references():
    code, pages = REF
    path = [r["local_path"] for r in csv.DictReader(open(MANIFEST, encoding="utf-8"))
            if r["bureau_code"] == code][0]
    doc = pdfium.PdfDocument(path)
    out = {}
    for i, name in pages.items():
        im = doc[i].render(scale=DPI / 72).to_pil().convert("RGB")
        out[name] = thumb(cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR))
    return out


def pages(path):
    """Every page of one file as BGR."""
    if path.lower().endswith(".pdf"):
        try:
            doc = pdfium.PdfDocument(path)
        except Exception:
            return
        for i in range(len(doc)):
            try:
                im = doc[i].render(scale=DPI / 72).to_pil().convert("RGB")
            except Exception:
                continue
            yield i, cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR)
    else:
        img = cv2.imread(path)
        if img is not None:
            yield 0, img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=".cache/corrections.csv")
    ap.add_argument("--render", default=None, help="write flagged pages here")
    a = ap.parse_args()
    if a.render:
        os.makedirs(a.render, exist_ok=True)

    refs = references()
    files = list(csv.DictReader(open(MANIFEST, encoding="utf-8")))
    found = []
    for n, r in enumerate(files):
        path = r["local_path"]
        if not os.path.exists(path):
            continue
        stem = os.path.basename(path).rsplit(".", 1)[0]
        for i, bgr in pages(path):
            pink = measure(bgr)
            if pink >= PINK:
                continue
            t = thumb(bgr)
            score = {k: float((t * v).sum()) for k, v in refs.items()}
            kind = max(score, key=score.get)
            if score[kind] < 0.12:
                kind = "other"
            found.append((r["bureau_code"], stem, i, round(pink, 4),
                          kind, round(score["table"], 3)))
            if a.render and score["table"] >= TABLE:
                cv2.imwrite(os.path.join(a.render, f"{stem}_p{i}.png"), bgr)
        if n % 500 == 0:
            print("scanned", n, "files,", len(found), "pages", flush=True)

    with open(a.out, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["bureau_code", "stem", "page", "pink", "kind", "table_score"])
        w.writerows(found)
    tables = {f[0] for f in found if f[5] >= TABLE}
    print(f"{len(found)} non-counting-record pages across "
          f"{len({f[0] for f in found})} bureaux; "
          f"{len(tables)} bureaux have a decision table page -> {a.out}")


if __name__ == "__main__":
    main()
