"""OCR cached PDFs to text, one .txt per document, with page separators.

Renders each page with pypdfium2 and runs tesseract in Arabic. Results are
cached so downstream parsers can be re-run without repeating the OCR.

Usage: python3 tools/ocr_cache.py <path-substring> [dpi] [workers] [max_pages] [lang]
"""
import os, sys
from concurrent.futures import ProcessPoolExecutor

# Tesseract's OpenMP pool oversubscribes when several instances run in
# parallel — each worker then thrashes instead of scaling. One thread per
# process is ~40x faster here at four workers.
os.environ.setdefault("OMP_THREAD_LIMIT", "1")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _fetch import manifest, fetch

OCR_DIR = ".cache/ocr"
PAGE_SEP = "\n\n===== PAGE {n} =====\n"


def ocr_one(args):
    row, dpi, max_pages, lang = args
    import pypdfium2 as pdfium, pytesseract
    # Cache key carries the settings, so runs with different page limits or
    # language packs do not overwrite each other.
    suffix = (f".p{max_pages}" if max_pages else "") + ("" if lang == "ara" else f".{lang}")
    dest = os.path.join(OCR_DIR, f"{row['drive_id']}{suffix}.txt")
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return dest, "cached"
    src = fetch(row)
    if not src:
        return dest, "download failed"
    try:
        doc = pdfium.PdfDocument(src)
        parts = []
        n = min(len(doc), max_pages) if max_pages else len(doc)
        for i in range(n):
            img = doc[i].render(scale=dpi / 72).to_pil()
            parts.append(PAGE_SEP.format(n=i + 1) + pytesseract.image_to_string(img, lang=lang))
        tmp = dest + ".part"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write("".join(parts))
        os.replace(tmp, dest)
        return dest, f"{n}p"
    except Exception as exc:
        return dest, f"error: {exc}"


def main():
    pattern = sys.argv[1]
    dpi = int(sys.argv[2]) if len(sys.argv) > 2 else 200
    workers = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    max_pages = int(sys.argv[4]) if len(sys.argv) > 4 else 0
    lang = sys.argv[5] if len(sys.argv) > 5 else "ara"
    os.makedirs(OCR_DIR, exist_ok=True)
    rows = manifest(lambda r: pattern in r["path"] and r["ext"] == "pdf")
    print(f"{len(rows)} documents match {pattern!r}", flush=True)
    done = 0
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for _, status in pool.map(ocr_one, [(r, dpi, max_pages, lang) for r in rows]):
            done += 1
            if status.startswith("error") or status.endswith("failed"):
                print(f"  [{done}] {status}", flush=True)
            elif done % 10 == 0:
                print(f"  {done}/{len(rows)}", flush=True)
    print(f"done: {done} documents -> {OCR_DIR}")


if __name__ == "__main__":
    main()
