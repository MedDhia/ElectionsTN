"""Dataset 3 — 2024 presidential candidacy applicants.

uploads/2024/07/ holds one PDF per aspirant to the 2024 presidential election:
a personalised "استمارة تزكية شعبية 2024" (popular sponsorship form), which an
aspirant distributes to collect the endorsements required to stand. Each carries
a machine-readable text overlay with the aspirant's name and their assigned
number, so no OCR is needed for the fields we want.
"""
import csv, os, re, sys, unicodedata
from concurrent.futures import ThreadPoolExecutor

import pdfplumber

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _fetch import manifest, fetch

OUT = "data/presidential_applicants_2024.csv"
SRC_DIR = "/wp-content/uploads/2024/07/"
# Applicant filenames are personal names built around the patronymic "بن" / "BEN";
# everything else in the folder is a decision, guide or tender document.
IS_APPLICANT = re.compile(r"(^|-)(بن|BEN)(-|$)")
ARABIC = re.compile(r"[؀-ۿ]")


def fix_arabic(s):
    """Overlay Arabic is stored as presentation forms in visual order.

    Reverse before normalising, not after: NFKC expands the lam-alef ligature
    (ﻻ) into two characters, and reversing afterwards would flip them.
    """
    s = s.strip()
    if not ARABIC.search(unicodedata.normalize("NFKC", s)):
        return s
    return unicodedata.normalize("NFKC", s[::-1])


def parse(row):
    path = fetch(row)
    if not path:
        return {**row, "error": "download failed"}
    with pdfplumber.open(path) as pdf:
        pages = len(pdf.pages)
        text = (pdf.pages[0].extract_text() or "").strip()
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    number = next((ln for ln in lines if ln.isdigit()), "")
    name = fix_arabic(next((ln for ln in lines if not ln.isdigit()), ""))
    return {
        "name_overlay": name,
        "name_from_filename": os.path.splitext(row["name"])[0].replace("-", " "),
        "sponsorship_number": number,
        "script": "latin" if re.search(r"[A-Za-z]", name) else "arabic",
        "pages": pages,
        "source_file": row["name"],
        "drive_id": row["drive_id"],
        "source_url": row["download_url"],
    }


def main():
    rows = manifest(lambda r: r["path"].startswith(SRC_DIR) and r["ext"] == "pdf"
                    and IS_APPLICANT.search(os.path.splitext(r["name"])[0]))
    print(f"{len(rows)} applicant files")
    with ThreadPoolExecutor(max_workers=8) as pool:
        out = list(pool.map(parse, rows))
    out.sort(key=lambda r: int(r["sponsorship_number"]) if r.get("sponsorship_number", "").isdigit() else 0)
    fields = ["sponsorship_number", "name_overlay", "name_from_filename", "script", "pages",
              "source_file", "drive_id", "source_url"]
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(out)
    missing = [r for r in out if not r.get("sponsorship_number")]
    # The overlay drops some intra-name spaces, and the filenames spell hamza
    # in decomposed form (yeh + U+0654) where the overlay uses the precomposed
    # letter, so compare on a space-stripped, NFC-normalised key.
    def key(v):
        return unicodedata.normalize("NFC", re.sub(r"\s+", "", v))
    agree = [r for r in out if key(r["name_overlay"]) == key(r["name_from_filename"])]
    print(f"wrote {len(out)} rows -> {OUT}")
    print(f"  with sponsorship number: {len(out) - len(missing)}")
    print(f"  overlay name matches filename: {len(agree)}/{len(out)}")
    for r in out:
        if r not in agree:
            print(f"    differs: {r['name_overlay']!r} vs {r['name_from_filename']!r}")


if __name__ == "__main__":
    main()
