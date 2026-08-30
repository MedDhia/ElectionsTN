"""Dataset 5 — 2023 local election results, from ISIE's delegation-level decisions.

Each decision (قرار) proclaims the result for one delegation, broken down by
local constituency (دائرة انتخابية محلية). For each constituency the document
gives registered voters, voters, valid votes, spoilt and blank ballots, then a
table of candidates with the vote count written twice — in words and in digits.

The dual encoding and the ballot identity are used as checks:
    votes_valid + votes_spoilt + votes_blank == voters
    sum(candidate votes)                    == votes_valid
Rows that fail are kept and flagged rather than dropped, so the OCR's error rate
is visible instead of hidden.

Candidate votes come out reliable because of the spelled-out column. The turnout
figures have no such backup and are printed glued to the following Arabic word
("247ناخبا"), which OCR often truncates, so each document is read twice — at
200 dpi with the Arabic model and at 300 dpi with Arabic+English — and for each
constituency the combination of readings that best satisfies the two identities
is chosen. Where the passes disagree and neither combination works, the first
pass is kept and the row is flagged.

Usage: python3 tools/parse_local_results_2023.py
"""
import itertools
import csv, glob, os, re, sys, unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from arabic_numerals import KNOWN, _split_conjunctions, check, parse
from _fetch import manifest

OCR_DIR = ".cache/ocr"
# (filename suffix, label) for each OCR pass, in order of preference.
PASSES = [("", "200dpi/ara"), (".ara+eng", "300dpi/ara+eng")]
OUT_RESULTS = "data/local_2023_candidate_results.csv"
OUT_CONSTIT = "data/local_2023_constituency_turnout.csv"

AR = r"[؀-ۿ]"
NUM = r"([\d٠-٩]+)"


# Arabic diacritics are stripped as well as folded: Python's \w does not match
# combining marks (they are not alphanumeric), so a shadda inside a word like
# "المصرّح" would otherwise defeat every \w* in the patterns below.
TASHKEEL = re.compile(r"[\u064B-\u0652\u0640\u0670]")


def fold(s):
    s = unicodedata.normalize("NFC", s).translate(str.maketrans("أإآىئؤة", "اااييوه"))
    return TASHKEEL.sub("", s)


def digits(s):
    return s.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))


# Turnout labels. The document text is folded (hamza carriers unified, ة -> ه)
# before matching, so the patterns are folded the same way — otherwise a literal
# like "بالدائرة" would never match its folded form. Each is anchored on a
# distinctive stem because OCR mangles shadda and hamza freely.
#
# "بالدائرة" scopes these to the per-constituency figures; the same labels also
# appear without it in the document-level summary.
FIELDS = [
    ("registered", r"المسجل\w*\s*بالدائرة[^\d\n]{0,40}" + NUM),
    ("voters", r"قامو?ا\s*بالت?تصويت[^\d\n]{0,40}" + NUM),
    ("votes_valid", r"المصر\w*\s*بها\s*لكل\w*\s*المترشح\w*\s*بالدائرة[^\d\n]{0,40}" + NUM),
    ("votes_spoilt", r"الملغاة\s*بالدائرة[^\d\n]{0,40}" + NUM),
    ("votes_blank", r"البيضاء\s*بالدائرة[^\d\n]{0,40}" + NUM),
]
FIELDS = [(name, fold(pattern)) for name, pattern in FIELDS]
BLOCK_START = re.compile(fold(r"العدد\s*الجملي\s*للناخبين\s*المسجلين"))
HEADING = re.compile(fold(r"الدائرة\s*الانتخابي\w*\s*المحلي\w*") + r"\s*(.{2,60}?)\s*(?:" + fold("من\s*معتمدي") + r"|[:\.\n])")
HEADER_DOC = re.compile(fold(r"معتمدي\w*") + r"\s*(.{2,40}?)\s*" + fold(r"من\s*ولاية") + r"\s*(.{2,30}?)\s*" + fold(r"لسنة") + r"\s*(\d{4})")
DATE_DOC = re.compile(fold(r"المؤرخ\s*في") + r"\s*(\d{1,2})\s*([^\s\d]+)\s*(\d{4})")
WINNER = re.compile(fold(r"لتحصل\s*المترشح") + r"\w*\s*\(?\w?\)?\s*(.{2,50}?)\s*" + fold(r"على\s*الأغلبية"))
RUNOFF = re.compile(fold(r"لعدم\s*حصول"))


def parse_candidate_line(line):
    """'عدنان العلوش أربعمائة وثمانية وأربعون 448' -> (name, spelled, digits)."""
    toks = digits(line).split()
    nums = []
    while toks and re.fullmatch(r"[\d.,%]+", toks[-1]):
        nums.insert(0, toks.pop())
    def is_number_word(tok):
        pieces = _split_conjunctions(fold(tok.strip("،.:")))
        return bool(pieces) and all(p in KNOWN for p in pieces)

    spelled = []
    while toks and is_number_word(toks[-1]):
        spelled.insert(0, toks.pop())
    if not toks:
        return None
    # After the words come the digits, then optionally a percentage.
    vote_digits = next((n for n in nums if n.isdigit()), "")
    return " ".join(toks), " ".join(spelled), vote_digits


TURNOUT_FIELDS = ["registered", "voters", "votes_valid", "votes_spoilt", "votes_blank"]


def reconcile(variants, candidate_sum):
    """Pick the reading of the turnout fields that best fits the identities.

    `variants` is one dict per OCR pass. Scores each combination of the observed
    values on: voters == valid + spoilt + blank, and valid == candidate_sum.
    """
    options = []
    for field in TURNOUT_FIELDS:
        seen = [v[field] for v in variants if v.get(field) != ""]
        options.append(list(dict.fromkeys(seen)) or [""])

    best, best_score = None, -1
    for combo in itertools.product(*options):
        row = dict(zip(TURNOUT_FIELDS, combo))
        score = 0
        v, va, sp, bl = (row["voters"], row["votes_valid"],
                         row["votes_spoilt"], row["votes_blank"])
        if "" not in (v, va, sp, bl) and va + sp + bl == v:
            score += 2
        if va != "" and candidate_sum and va == candidate_sum:
            score += 2
        # Prefer readings that are populated and internally plausible.
        score += sum(1 for x in combo if x != "") * 0.1
        if row["registered"] != "" and v != "" and row["registered"] >= v:
            score += 0.5
        if score > best_score:
            best, best_score = row, score
    return best


def parse_document(raw, meta):
    text = fold(raw)
    blocks = [m.start() for m in BLOCK_START.finditer(text)]
    if not blocks:
        return [], []
    bounds = blocks + [len(text)]
    constituencies, candidates = [], []

    for i, start in enumerate(blocks):
        body = text[start:bounds[i + 1]]
        lead = text[max(0, start - 400):start]

        name = ""
        for source in (body, lead):
            m = HEADING.search(source)
            if m:
                name = re.sub(r"\s+", " ", m.group(1)).strip(" -:.")
                break

        row = {**meta, "constituency": name, "block_index": i + 1}
        for field, pattern in FIELDS:
            m = re.search(pattern, body)
            row[field] = int(digits(m.group(1))) if m else ""

        cands = []
        for line in body.splitlines():
            line = line.strip()
            if not line or not re.search(AR, line) or "اسم المترشح" in line:
                continue
            if re.search(r"العدد|عدد أوراق|المصرح بها لكل|تبعا|تنظم|تصرح", line):
                continue
            parsed = parse_candidate_line(line)
            if not parsed:
                continue
            cname, spelled, dgt = parsed
            if not spelled and not dgt:
                continue
            value, status = check(spelled, dgt)
            if value is None:
                continue
            cands.append({**meta, "constituency": name, "candidate": cname,
                          "votes": value, "votes_digits_ocr": dgt,
                          "votes_words_ocr": spelled, "vote_source": status})

        m = WINNER.search(body)
        row["outcome"] = "runoff" if RUNOFF.search(body) else ("elected" if m else "")
        row["winner"] = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
        row["n_candidates"] = len(cands)

        # Consistency checks.
        v, sp, bl, va = (row.get(k) for k in ("voters", "votes_spoilt", "votes_blank", "votes_valid"))
        row["ballot_identity_ok"] = (
            "" if "" in (v, sp, bl, va) else str(va + sp + bl == v).lower())
        total = sum(c["votes"] for c in cands)
        row["candidate_sum"] = total
        row["candidate_sum_ok"] = "" if va == "" else str(total == va).lower()

        constituencies.append(row)
        candidates.extend(cands)
    return constituencies, candidates


def main():
    rows = manifest(lambda r: "ResultatsLocales2023" in r["path"] and r["ext"] == "pdf")
    by_id = {r["drive_id"]: r for r in rows}

    constituencies, candidates, missing = [], [], 0
    for drive_id, src in by_id.items():
        available = [(sfx, os.path.join(OCR_DIR, f"{drive_id}{sfx}.txt"))
                     for sfx, _ in PASSES
                     if os.path.exists(os.path.join(OCR_DIR, f"{drive_id}{sfx}.txt"))]
        if not available:
            missing += 1
            continue
        text = open(available[0][1], encoding="utf-8").read()
        parts = src["path"].split("/")
        meta = {
            "governorate": parts[-3] if len(parts) > 3 else "",
            "delegation_folder": parts[-2] if len(parts) > 2 else "",
            "source_file": src["name"],
            "drive_id": drive_id,
        }
        folded = fold(text)
        m = HEADER_DOC.search(folded)
        meta["delegation"] = re.sub(r"\s+", " ", m.group(1)).strip() if m else meta["delegation_folder"]
        meta["year"] = m.group(3) if m else "2023"
        d = DATE_DOC.search(folded)
        meta["decision_date_raw"] = " ".join(d.groups()) if d else ""
        c, k = parse_document(text, meta)

        # Second pass, used only to repair the turnout figures.
        if len(available) > 1:
            alt, _ = parse_document(open(available[1][1], encoding="utf-8").read(), meta)
            if len(alt) == len(c):
                for row, other in zip(c, alt):
                    fixed = reconcile([row, other], row["candidate_sum"])
                    changed = [f for f in TURNOUT_FIELDS if row[f] != fixed[f]]
                    row.update(fixed)
                    row["turnout_repaired"] = ",".join(changed)
                    v, va = row["voters"], row["votes_valid"]
                    sp, bl = row["votes_spoilt"], row["votes_blank"]
                    row["ballot_identity_ok"] = (
                        "" if "" in (v, va, sp, bl) else str(va + sp + bl == v).lower())
                    row["candidate_sum_ok"] = (
                        "" if va == "" else str(row["candidate_sum"] == va).lower())
            else:
                for row in c:
                    row["turnout_repaired"] = "pass-misaligned"
        constituencies.extend(c)
        candidates.extend(k)

    cfields = ["governorate", "delegation", "constituency", "registered", "voters",
               "votes_valid", "votes_spoilt", "votes_blank", "candidate_sum",
               "n_candidates", "outcome", "winner", "ballot_identity_ok",
               "candidate_sum_ok", "turnout_repaired", "year", "decision_date_raw", "block_index",
               "delegation_folder", "source_file", "drive_id"]
    kfields = ["governorate", "delegation", "constituency", "candidate", "votes",
               "vote_source", "votes_digits_ocr", "votes_words_ocr", "year",
               "source_file", "drive_id"]
    for path, fields, data in ((OUT_CONSTIT, cfields, constituencies),
                               (OUT_RESULTS, kfields, candidates)):
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            w.writerows(data)
        print(f"wrote {len(data):5d} rows -> {path}")

    ok = sum(1 for r in constituencies if r["ballot_identity_ok"] == "true")
    sm = sum(1 for r in constituencies if r["candidate_sum_ok"] == "true")
    n = len(constituencies) or 1
    print(f"  documents parsed: {len(by_id) - missing}/{len(by_id)} (missing OCR: {missing})")
    print(f"  ballot identity holds: {ok}/{len(constituencies)} ({100*ok/n:.0f}%)")
    print(f"  candidate sum matches: {sm}/{len(constituencies)} ({100*sm/n:.0f}%)")
    from collections import Counter
    print("  vote source:", dict(Counter(c["vote_source"] for c in candidates)))


if __name__ == "__main__":
    main()
