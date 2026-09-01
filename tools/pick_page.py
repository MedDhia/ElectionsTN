"""Choose the page that actually carries the counting record, by registering it.

The bundle a bureau is filed under is not always the counting record. 741 of the
presidential files are multi-page PDFs, and the page chooser picked among them by
masthead: the counting record scores 6-9 on the header words and the accompanying
paperwork scores 0-2, so the top scorer wins.

That rule breaks on two shapes of file. A correction decision
(قرار تصحيح محضر فرز) carries the same ISIE masthead as the counting record, so
it scores just as well. And some scans put the landscape counting record inset in
the middle of a portrait A4 page, where the masthead is small enough that the
detector scores it 0 and the paperwork beside it wins on 2. All 60 bureaux whose
cached page has no recoverable grid and no alternative scan came out of a PDF
bundle this way; the counting record was in the bundle the whole time.

Registration tells the two apart where the masthead cannot. Cropping a rendered
page to its ink and fitting it to the reference layout scores the counting record
at 0.93-0.96 and every other page in the bundle at or below 0.31 — and the crop
is also the fix, because an inset form is far outside the warp search's capture
range until the white margin is gone.

So: render every page of every scan held for a bureau, crop, register at each
rotation, and keep whichever page fits the counting-record layout best. A bureau
is only touched when the winner clearly beats the page already cached, so a scan
that already reads cannot be traded for a worse one.

Usage: python3 tools/pick_page.py [--limit N] [--workers 4] [--all]
"""
import argparse, collections, csv, json, os, sys
from concurrent.futures import ProcessPoolExecutor

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

RESULTS = "data/pv_presidential_2024.csv"
MANIFEST = ".cache/pv_all_manifest.csv"
ALT_DIR = ".cache/pv_alt"
UPRIGHT = ".cache/pv_upright"
LONG_EDGE = int(os.environ.get("PV_LONG_EDGE", "1600"))
PDF_DPI = int(os.environ.get("PV_PDF_DPI", "250"))

TAKE = 0.85          # registration this good is the counting record; stop looking
KEEP = 0.80          # replace the cached page only for a fit at least this good
BEAT = 0.05          # ...and only if it beats the cached page by this much

_REF = None


def reference():
    global _REF
    if _REF is None:
        import pv_template
        _REF = pv_template.reference()[0]
    return _REF


def ink_crop(bgr, margin=0.01, min_area=0.05):
    """The page cropped to its ink, or None if that is most of the page anyway."""
    g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    b = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    b = cv2.morphologyEx(b, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    ys, xs = np.nonzero(b)
    if len(xs) < 1000:
        return None
    H, W = g.shape
    m = int(margin * max(H, W))
    x0, x1 = max(0, int(xs.min()) - m), min(W, int(xs.max()) + m)
    y0, y1 = max(0, int(ys.min()) - m), min(H, int(ys.max()) + m)
    if (x1 - x0) * (y1 - y0) < min_area * H * W:
        return None
    return bgr[y0:y1, x0:x1]


def fit(bgr):
    """Best registration correlation against the counting-record layout.

    Rotations are tried here rather than left to the masthead detector because
    an inset form gives the masthead nothing to score, and the correlation is
    the more reliable signal on exactly the pages the masthead cannot call.
    """
    import pv_template as T
    ref = reference()
    if ref is None:
        return 0.0, None
    best, best_img = 0.0, None
    rots = ((0, None), (90, cv2.ROTATE_90_CLOCKWISE), (180, cv2.ROTATE_180),
            (270, cv2.ROTATE_90_COUNTERCLOCKWISE))
    for _deg, flag in rots:
        page = bgr if flag is None else cv2.rotate(bgr, flag)
        crop = ink_crop(page)
        for cand in ([page] if crop is None else [crop, page]):
            for mode in T.SIGNALS:
                A, cc = T.align(cand, ref, mode)
                if A is not None and cc > best:
                    best, best_img = cc, cand
                if best >= TAKE:
                    return best, best_img
    return best, best_img


def pages(src):
    """Every page of a scan as BGR, rendered once."""
    if src.lower().endswith(".pdf"):
        import pypdfium2 as pdfium
        try:
            doc = pdfium.PdfDocument(src)
        except Exception:
            return
        for i in range(len(doc)):
            try:
                im = doc[i].render(scale=PDF_DPI / 72).to_pil()
            except Exception:
                continue
            yield i, cv2.cvtColor(np.array(im.convert("RGB")), cv2.COLOR_RGB2BGR)
    else:
        img = cv2.imread(src)
        if img is not None:
            yield 0, img


def shrink(img):
    h, w = img.shape[:2]
    if max(h, w) <= LONG_EDGE:
        return img
    f = LONG_EDGE / max(h, w)
    return cv2.resize(img, (max(1, round(w * f)), max(1, round(h * f))),
                      interpolation=cv2.INTER_AREA)


def cached_fit(code):
    """How well the page already cached for this bureau fits, from its note."""
    meta = os.path.join(UPRIGHT, f"{code}.jpg.json")
    if os.path.exists(meta):
        try:
            j = json.load(open(meta, encoding="utf-8"))
        except Exception:
            return None, {}
        if "fit" in j:
            return float(j["fit"]), j
        return None, j
    return None, {}


def choose(job):
    """Register every page held for one bureau; return the best and its score."""
    code, sources = job
    have, meta = cached_fit(code)
    if have is None:
        cur = cv2.imread(os.path.join(UPRIGHT, f"{code}.jpg"))
        have = fit(cur)[0] if cur is not None else 0.0
    best, best_img, best_src = have, None, None
    for src in sources:
        for i, page in pages(src):
            cc, img = fit(page)
            if cc > best and img is not None:
                best, best_img, best_src = cc, img, f"{src}#{i}"
            if best >= TAKE and best_img is not None:
                break
        if best >= TAKE and best_img is not None:
            break
    if best_img is None or best < KEEP or best < have + BEAT:
        return code, have, best, None
    dest = os.path.join(UPRIGHT, f"{code}.jpg")
    cv2.imwrite(dest, shrink(best_img), [cv2.IMWRITE_JPEG_QUALITY, 92])
    meta.update({"fit": round(best, 4), "picked_from": best_src,
                 "previous_fit": round(have, 4)})
    json.dump(meta, open(dest + ".json", "w"))
    return code, have, best, best_src


def jobs(want_all):
    res = list(csv.DictReader(open(RESULTS, encoding="utf-8")))
    man = {r["bureau_code"]: r["local_path"]
           for r in csv.DictReader(open(MANIFEST, encoding="utf-8"))}
    alt = collections.defaultdict(list)
    if os.path.isdir(ALT_DIR):
        for f in sorted(os.listdir(ALT_DIR)):
            alt[f.split("__", 1)[0]].append(os.path.join(ALT_DIR, f))
    out = []
    for r in res:
        code = r["bureau_code"]
        if not want_all and r["votes_certified"] == "1":
            continue
        srcs = [p for p in [man.get(code)] if p and os.path.exists(p)]
        srcs += [p for p in alt.get(code, []) if p not in srcs]
        if srcs:
            out.append((code, srcs))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--all", action="store_true",
                    help="also revisit bureaux whose votes are already certified")
    ap.add_argument("--codes", help="comma-separated bureau codes, for spot checks")
    a = ap.parse_args()

    todo = jobs(a.all)
    if a.codes:
        want = set(a.codes.split(","))
        todo = [j for j in todo if j[0] in want]
    if a.limit:
        todo = todo[:a.limit]
    print(f"{len(todo)} bureaux to re-pick a page for", flush=True)

    swapped = 0
    with ProcessPoolExecutor(a.workers) as pool:
        for n, (code, had, got, src) in enumerate(pool.map(choose, todo, chunksize=4), 1):
            if src:
                swapped += 1
                print(f"  {code}  {had:.2f} -> {got:.2f}  {src}", flush=True)
            if n % 50 == 0:
                print(f"  ...{n}/{len(todo)}, {swapped} swapped", flush=True)
    print(f"\nswapped the cached page for {swapped} of {len(todo)} bureaux")
    print("re-run tools/decode_all.py to pick the improvements up")


if __name__ == "__main__":
    main()
