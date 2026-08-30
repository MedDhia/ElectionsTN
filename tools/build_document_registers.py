"""Datasets 4 and 6 — ISIE regulatory corpus and procurement register.

Both are built from the dated media library (uploads/YYYY/MM/). Filenames are
themselves structured — they carry document type, reference number, year and
language — so the registers are usable without OCR. Where a first-page OCR is
present in .cache/ocr it is used to add a title line; run

    python3 tools/ocr_cache.py /wp-content/uploads/ 200 4 1 ara+fra

first to populate it.

Usage: python3 tools/build_document_registers.py
"""
import csv, os, re, sys, unicodedata
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _fetch import manifest

OCR_DIR = ".cache/ocr"
OCR_SUFFIX = ".p1.ara+fra.txt"
OUT_REG = "data/regulatory_corpus.csv"
OUT_PROC = "data/procurement_register.csv"
DATED = re.compile(r"^/wp-content/uploads/(\d{4})/(\d{2})/")

# Procurement documents are named after the procedure that produced them.
PROCUREMENT = re.compile(
    r"^(CC|CAO|AO|AOS|CONS|CCAP|CAOCCAP|CCC|CCAO|CCTP|CPS|CAHIERS?|"
    r"consultations?|ANNEXES?)\b|^كراس", re.I)
PROCEDURE = [
    ("appel d'offres simplifié", r"\bAOS\b"),
    ("appel d'offres", r"\bAO\s*-?\s*\d|\bAO\d|\bAPPEL"),
    ("consultation", r"\bCONS\b|consultation"),
    ("cahier des charges", r"^CC|CAHIER|\bCPS\b|\bCCTP\b|^كراس"),
]
DOC_TYPES = [
    ("decision", r"قرار|مرسوم|أمر عدد|Décret|Decret|Décision|Decision|decision"),
    ("statistics", r"معطيات|إحصائيات|احصائيات|statistiques"),
    ("code_of_conduct", r"مدونة سلوك"),
    ("calendar", r"روزنامة|calendrier"),
    ("polling_geography", r"مراكز الاقتراع|الدوائر الانتخابية|مكاتب الاقتراع|"
                          r"مكاتب تحيين|عناوين مقرات|centres de Vote"),
    ("candidate_list", r"القائمات المقبولة|قائمة المترشحين|قائمات المترشحين"),
    ("campaign_finance", r"السقف الجملي|تمويل الحملة"),
    ("recruitment", r"مناظرة|انتداب|\bCV\b|recrutement"),
    ("legal_text", r"الدستور|constitution|القانون الأساسي"),
    ("guide", r"دليل|Guide|guide|منهجي"),
    ("annex", r"ملحق|ANNEXE|Annexe"),
    ("results", r"نتائج|Résultat|Resultat|النتائج"),
    ("list", r"قائمة|قائمه|liste|Liste"),
    ("minutes", r"محضر|محاضر|PV\b"),
    ("communique", r"بلاغ|Communiqué|communique"),
    ("form", r"استمارة|مطبوعة|formulaire"),
    ("report", r"تقرير|rapport|Rapport"),
]
# "قرار عدد 7 لسنة 2018" or "Décision n° 2021-12"
NUM_AR = re.compile(r"عدد[\s\-]*(\d+)[\s\-]*لسنة[\s\-]*(\d{4})")
NUM_FR = re.compile(r"n[°ورo]?\s*[\-\s]*(\d{4})[\-\s](\d+)|n[°o]\s*[\-\s]*(\d+)[\-\s](\d{4})", re.I)
REF = re.compile(r"(\d{1,3})\s*[\-–]\s*(20\d{2})|(20\d{2})\s*[\-–]\s*(\d{1,3})")
TASHKEEL = re.compile(r"[ً-ْـ]")


def clean(name):
    stem = os.path.splitext(name)[0]
    stem = unicodedata.normalize("NFC", stem).replace("-", " ").replace("_", " ")
    return re.sub(r"\s+", " ", TASHKEEL.sub("", stem)).strip()


def language(name):
    has_ar = bool(re.search(r"[؀-ۿ]", name))
    has_lat = bool(re.search(r"[A-Za-z]{3}", name))
    if re.search(r"[\-_](ar|AR)\b", name):
        return "ar"
    if re.search(r"[\-_](fr|FR)\b", name):
        return "fr"
    return "ar" if has_ar and not has_lat else ("fr" if has_lat and not has_ar else "mixed")


def first_line(drive_id):
    path = os.path.join(OCR_DIR, f"{drive_id}{OCR_SUFFIX}")
    if not os.path.exists(path):
        return ""
    for line in open(path, encoding="utf-8"):
        line = re.sub(r"\s+", " ", line).strip()
        # Skip the letterhead, which is the same on every ISIE document.
        if len(line) > 25 and not re.search(r"الجمهورية التونسية|الهيئة العليا|المستقلة للانتخابات", line):
            return line[:200]
    return ""


def classify(stem):
    for label, pattern in DOC_TYPES:
        if re.search(pattern, stem):
            return label
    return "other"


def procedure_of(name):
    for label, pattern in PROCEDURE:
        if re.search(pattern, name, re.I):
            return label
    return "other"


def main():
    rows = [r for r in manifest(lambda r: r["ext"] == "pdf") if DATED.match(r["path"])]
    # The 2024 presidential sponsorship forms are their own dataset (tools/
    # build_presidential_applicants.py); they are not regulatory documents.
    sponsorship = re.compile(r"(^|-)(بن|BEN)(-|$)")
    rows = [r for r in rows
            if not (r["path"].startswith("/wp-content/uploads/2024/07/")
                    and sponsorship.search(os.path.splitext(r["name"])[0]))]
    reg, proc = [], []
    for r in rows:
        y, mo = DATED.match(r["path"]).groups()
        stem = clean(r["name"])
        base = {
            "year_published": y, "month_published": mo,
            "title_from_filename": stem,
            "title_from_ocr": first_line(r["drive_id"]),
            "language": language(r["name"]),
            "source_file": r["name"], "drive_id": r["drive_id"],
            "source_url": r["download_url"],
        }
        if PROCUREMENT.match(r["name"]):
            m = REF.search(r["name"])
            ref_no, ref_year = "", ""
            if m:
                g = [x for x in m.groups() if x]
                ref_no, ref_year = (g[0], g[1]) if len(g[0]) <= 3 else (g[1], g[0])
            proc.append({**base, "procedure": procedure_of(r["name"]),
                         "reference_number": ref_no, "reference_year": ref_year})
        else:
            m = NUM_AR.search(stem)
            num, num_year = (m.group(1), m.group(2)) if m else ("", "")
            if not num:
                m = NUM_FR.search(stem)
                if m:
                    g = [x for x in m.groups() if x]
                    num, num_year = (g[1], g[0]) if len(g[0]) == 4 else (g[0], g[1])
            reg.append({**base, "doc_type": classify(stem),
                        "reference_number": num, "reference_year": num_year})

    rfields = ["doc_type", "reference_number", "reference_year", "year_published",
               "month_published", "language", "title_from_filename", "title_from_ocr",
               "source_file", "drive_id", "source_url"]
    pfields = ["procedure", "reference_number", "reference_year", "year_published",
               "month_published", "language", "title_from_filename", "title_from_ocr",
               "source_file", "drive_id", "source_url"]
    for path, fields, data in ((OUT_REG, rfields, reg), (OUT_PROC, pfields, proc)):
        data.sort(key=lambda d: (d["year_published"], d["month_published"], d["source_file"]))
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            w.writerows(data)
        print(f"wrote {len(data):4d} rows -> {path}")
    print("  regulatory types:", dict(Counter(r["doc_type"] for r in reg).most_common()))
    print("  procurement types:", dict(Counter(r["procedure"] for r in proc).most_common()))
    print("  with OCR title: reg %d/%d, proc %d/%d" % (
        sum(1 for r in reg if r["title_from_ocr"]), len(reg),
        sum(1 for r in proc if r["title_from_ocr"]), len(proc)))


if __name__ == "__main__":
    main()
