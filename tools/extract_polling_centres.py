"""Extract the national polling-centre directory (USSD codes) from the ISIE PDF.

Source: /wp-content/uploads/2022/06/Annuaire-codes-USSD-centres-de-Vote-en-Tunisie.pdf

The PDF is born-digital and has real ruled table structure, but its Arabic is
stored as individual glyphs laid out left-to-right in visual order. Reversing
pdfplumber's extracted string is not reliable (word grouping scrambles some
letters), so each cell is rebuilt from its raw characters sorted by x-position:
descending for Arabic cells, ascending for Latin/numeric cells.

Usage: python3 tools/extract_polling_centres.py [out.csv]
"""
import csv, io, re, sys, urllib.request

import pdfplumber

FILE_ID = "1yNJPtG8Azr8hAjEff-OiVEC93NE0aHwz"
COLUMNS = [
    "governorate_ar", "constituency_ar", "delegation_ar", "imada_ar",
    "centre_name_ar", "centre_name_fr", "ussd_code",
]

# The embedded font's ToUnicode map is defective for some Arabic final forms, so
# short cells come out with swapped letters (e.g. "مدنري" for "مدنين"). The Drive
# archive's own folder names carry clean Arabic, so they supply the canonical
# vocabulary and raw values are snapped onto it.
GOVERNORATES = [
    "أريانة", "باجة", "بن عروس", "بنزرت", "تطاوين", "توزر", "تونس", "جندوبة",
    "زغوان", "سليانة", "سوسة", "سيدي بوزيد", "صفاقس", "قابس", "قبلي", "قفصة",
    "القصرين", "القيروان", "الكاف", "مدنين", "منوبة", "المنستير", "المهدية", "نابل",
]


def canonical_governorate(raw):
    """Snap a raw governorate string onto the canonical list, or return ''."""
    import difflib
    key = re.sub(r"\s+", "", raw)
    best, score = "", 0.0
    for g in GOVERNORATES:
        r = difflib.SequenceMatcher(None, key, re.sub(r"\s+", "", g)).ratio()
        if r > score:
            best, score = g, r
    return best if score >= 0.6 else ""
ARABIC = re.compile(r"[؀-ۿﭐ-﷿ﹰ-﻿]")


def cell_text(page, bbox):
    """Rebuild a table cell from raw glyphs, honouring reading direction."""
    if not bbox:
        return ""
    x0, top, x1, bottom = bbox
    chars = [c for c in page.chars
             if c["x0"] >= x0 - 0.5 and c["x1"] <= x1 + 0.5
             and c["top"] >= top - 0.5 and c["bottom"] <= bottom + 0.5]
    if not chars:
        return ""
    rtl = any(ARABIC.match(c["text"]) for c in chars)
    # Group into visual lines, then order glyphs within each line.
    lines = {}
    for c in chars:
        lines.setdefault(round(c["top"] / 3), []).append(c)
    out = []
    for key in sorted(lines):
        glyphs = sorted(lines[key], key=lambda c: -c["x0"] if rtl else c["x0"])
        out.append("".join(g["text"] for g in glyphs))
    return " ".join(s.strip() for s in out if s.strip()).strip()


def extract(pdf_bytes):
    rows = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page_no, page in enumerate(pdf.pages, 1):
            for table in page.find_tables():
                for row in table.rows:
                    if len(row.cells) != len(COLUMNS):
                        continue
                    values = [cell_text(page, c) for c in row.cells]
                    code = values[-1]
                    if not code.isdigit():          # header / blank row
                        continue
                    rec = dict(zip(COLUMNS, values))
                    rec["governorate"] = canonical_governorate(rec["governorate_ar"])
                    rec["source_page"] = page_no
                    rows.append(rec)
    return rows


def download(file_id):
    url = f"https://drive.google.com/uc?export=download&id={file_id}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=180).read()


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "data/polling_centres_2022.csv"
    rows = extract(download(FILE_ID))
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS + ["governorate", "source_page"])
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows -> {out}")
    print("governorates (canonical):", len({r["governorate"] for r in rows}))
    print("unmatched governorate cells:", sum(1 for r in rows if not r["governorate"]))
    print("delegations :", len({(r["governorate_ar"], r["delegation_ar"]) for r in rows}))
    print("USSD codes  :", len({r["ussd_code"] for r in rows}))


if __name__ == "__main__":
    main()
