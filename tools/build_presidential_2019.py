"""Dataset 11 — 2019 presidential results, from ISIE's own election report.

The 2019 results pages on isie.tn are gone: `الانتخابات التشريعية 2019` renders
"هذه الصفحة قيد الإنشاء", the news posts the results were published in return
404, and every `uploads/2019/09/` and `uploads/2019/10/` results PDF the media
library still lists is a dead link. What survives is the ISIE's own retrospective,
`تقرير-الانتخابات-الرئاسية-والتشريعية-لسنة-2019.pdf`, re-uploaded in January 2026
under `uploads/2026/01/` — 576 pages, and unlike almost everything else in this
project it carries a real text layer.

Two tables come out of it:

* **Annex 7** (33 pages, one per collection centre) — round one, every candidate's
  vote count and share in each of the 33 constituencies. Each page prints its own
  total, so every page validates itself: 26 candidates, ranks 1–26, votes summing
  to the printed total, shares summing to 100%.
* **The national tables** — round one preliminary, round one final and round two
  final. Each prints every count twice, in digits and spelled out in Arabic words,
  the same redundancy `tools/arabic_numerals.py` exploits for the 2023 local
  results, and each is checked here against a sum computed from another table.

The checks pass and they cross the document: annex 7's 858 vote counts sum to
3,372,973, the round-one valid-vote total stated on the preceding page, and each
candidate's 33 constituency counts sum to the national figure printed for them.

Flaws in the source survive into the data rather than being papered over. Each
round-one national table drops a different candidate — the final one omits محمد
لطفي المرايحي and his 221,190 votes, the preliminary one omits عمر منصور and his
10,160 — and in both cases the table's rows fall short of the national total by
exactly that candidate's count, which is how the omission was identified rather
than assumed. Separately, one spelled-out figure in both tables drops the word
"ألفا", so the words read 1,190 where the digits — corroborated by the
constituency sum — read 239,951. All of it is reported and flagged.

pdfplumber extracts nothing from this file — its embedded fonts have no usable
`ToUnicode` map — but pdfium's text page reads it fine, so that is what is used.
That text layer also stores every "لا" as "ال", so Arabic read out of the prose
fonts is ligature-damaged; the chart on page 303 uses a font that is not, and it
is the chart the canonical candidate names are taken from.

Usage: python3 tools/build_presidential_2019.py
"""
import csv, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from arabic_numerals import KNOWN, _fold, _split_conjunctions, parse
from _rapport_2019 import clean, pages as page_text, report

OUT_CONSTIT = "data/presidential_2019_r1_constituency.csv"
OUT_NATIONAL = "data/presidential_2019_national.csv"

CENTRE = "مركز جمع"
CHART = "0 100000 200000 300000 400000 500000 600000 700000"
# "الترتيب | المترشح | عدد الأصوات المصرح بها لكل مترشح | النسبة ...", one line
# per candidate. A stray space sometimes lands inside a number ("2,9 1%"), hence
# the whitespace inside the last two groups.
ROW = re.compile(r"^(\d{1,2})\s+(.*?)\s+([\d\s]+)\s+([\d,\s]+)%$")
# The per-page total, printed with a dash in the (empty) percentage cell.
TOTAL = re.compile(r"(\d{4,})\s*-?\s*$")
# End of the header of a national table; the rows start after it.
NATIONAL_HEAD = "باألرقام"
# The rest of that header line trails the cut; so does the previous row's
# stray percent sign when the % is set as its own token.
HEADER_TAIL = ("األصوات", "امل", "%")
VOTES = re.compile(r"\d{4,}")
SHARE = re.compile(r"%?(\d+[,.]\d+)%?")
# arabic_numerals stops at thousands, which is all the 2023 local results need.
# Round two's totals are seven figures, so millions are handled here.
MILLIONS = {"مليون": 1, "مليونان": 2, "مليونين": 2, "ملايين": 1, "مالين": 1}
# Round two's valid-vote total, printed in the "معطيات عامة" block before it.
R2_VALID = 3820825


def numeral(word):
    """Recognise an Arabic number word, repairing the report's lam-alef swap.

    This text layer stores every "لا" as "ال" — "ثلاثمائة" arrives as "ثالثمائة",
    "آلاف" as "آالف". Undoing that blindly would corrupt real words (the definite
    article looks identical), so a swap is only accepted when it turns the token
    into a number the parser already knows. The same test absorbs the accusative
    "ألفا" for "ألف". Returns the repaired word, or None if it is not a numeral.
    """
    for candidate in (word, word.replace("ال", "لا"), word.rstrip("ا"),
                      word.replace("ال", "لا").rstrip("ا")):
        parts = _split_conjunctions(_fold(candidate))
        if parts and all(p in KNOWN or p in MILLIONS for p in parts):
            return candidate
    return None


def parse_words(spelled):
    """`arabic_numerals.parse`, extended over the million a round-two total needs."""
    tokens = spelled.split()
    for i, token in enumerate(tokens):
        word = _fold(token).lstrip("و")
        if word in MILLIONS:
            head = parse(" ".join(tokens[:i]))
            millions = MILLIONS[word] if MILLIONS[word] > 1 else (head or 1)
            return millions * 1000000 + (parse(" ".join(tokens[i + 1:])) or 0)
    return parse(spelled)


def name_key(name):
    """(first word, last word), folded — enough to identify a candidate."""
    words = [_fold(w) for w in clean(name).split() if _fold(w)]
    return (words[0], words[-1]) if words else ()


# ---------------------------------------------------------------- annex 7

def annex7(pages):
    """Round one, by collection centre. Yields (centre, rows, printed total)."""
    start = next(i for i, t in enumerate(pages) if "ملحق عدد .7" in t)
    for i in range(start, len(pages)):
        lines = [l.strip() for l in pages[i].split("\r\n") if l.strip()]
        centres = [l for l in lines if l.startswith(CENTRE)]
        if not centres:
            break
        rows, total = [], None
        for line in lines:
            m = ROW.match(line)
            if m:
                rows.append({
                    "rank": int(m.group(1)),
                    "candidate": clean(m.group(2)),
                    "votes": int(re.sub(r"\s", "", m.group(3))),
                    "share_pct": float(re.sub(r"\s", "", m.group(4)).replace(",", ".")),
                })
            elif "الجمل" in _fold(line) and TOTAL.search(line):
                total = int(TOTAL.search(line).group(1))
        yield clean(centres[0][len(CENTRE):]), rows, total


# ------------------------------------------------------------ the chart

def chart(pages):
    """The round-one bar chart: 26 (rank, name, votes), in rank order.

    Its labels are drawn in a font that escaped the lam-alef damage, so these
    are the candidate names the rest of the output is keyed to.
    """
    page = next(i for i, t in enumerate(pages) if CHART in " ".join(t.split()))
    lines = [l.strip() for l in pages[page].split("\r\n") if l.strip()]
    axis = next(i for i, l in enumerate(lines) if " ".join(l.split()) == CHART)
    votes = [int(l) for l in lines[:axis] if VOTES.fullmatch(l)]
    names = [clean(l) for l in lines[axis + 1:axis + 1 + len(votes)]]
    if len(votes) != 26 or len(names) != 26:
        raise ValueError(f"chart on page {page + 1}: {len(votes)} values, {len(names)} names")
    return page, [{"rank": i + 1, "candidate": n, "votes": v}
                  for i, (n, v) in enumerate(zip(names, votes))]


# ------------------------------------------------------- national tables

def national(pages, page_no, limit):
    """Read one national per-candidate table, spanning pages if it has to."""
    rows, words, names = [], [], []
    for page in range(page_no, len(pages)):
        if NATIONAL_HEAD not in pages[page]:
            break
        text = pages[page]
        tokens = text[text.index(NATIONAL_HEAD) + len(NATIONAL_HEAD):].split()
        i = 0
        while i < len(tokens) and tokens[i] in HEADER_TAIL:
            i += 1
        while i < len(tokens) and len(rows) < limit:
            token = tokens[i]
            if VOTES.fullmatch(token):
                share, i = None, i + 1
                if i < len(tokens) and SHARE.fullmatch(tokens[i]):
                    share = float(SHARE.fullmatch(tokens[i]).group(1).replace(",", "."))
                    i += 1
                if i < len(tokens) and tokens[i] == "%":
                    i += 1
                rows.append({"names": names, "words": words, "votes": int(token),
                             "share": share, "page": page})
                words, names = [], []
                continue
            repaired = numeral(token)
            (words if repaired else names).append(repaired or token)
            i += 1
        if len(rows) >= limit:
            break
    # A spelled figure that wraps inside its cell comes back split across the
    # digits that follow it, so its tail lands at the head of the next row. Move
    # it back, but only when doing so makes the words match the digits exactly.
    for row, following in zip(rows, rows[1:]):
        if parse_words(" ".join(row["words"])) == row["votes"]:
            continue
        for k in range(1, len(following["words"]) + 1):
            if parse_words(" ".join(row["words"] + following["words"][:k])) == row["votes"]:
                row["words"] += following["words"][:k]
                following["words"] = following["words"][k:]
                break

    out = []
    for row in rows:
        spelled = " ".join(row["words"])
        out.append({"name_in_table": clean(" ".join(row["names"])),
                    "votes": row["votes"], "share_pct": row["share"],
                    "votes_spelled": spelled, "words_value": parse_words(spelled),
                    "source_page": row["page"] + 1})
    return out


def find_national(pages):
    """First page of each national table: preliminary R1, final R1, final R2.

    The column header repeats on the page a table spills onto, so a page only
    starts a table if the page before it does not carry the header too.
    """
    heads = [i for i, t in enumerate(pages) if NATIONAL_HEAD in t]
    starts = [i for i in heads if i - 1 not in heads]
    if len(starts) != 3:
        raise LookupError(f"expected 3 national tables, found pages {starts}")
    return starts


def main():
    pages = page_text(report())
    print(f"{len(pages)} pages, {sum(len(p) for p in pages)} characters of text")

    # --- annex 7 -------------------------------------------------------
    rows, sums, failures = [], {}, 0
    for centre, table, total in annex7(pages):
        summed = sum(r["votes"] for r in table)
        shares = sum(r["share_pct"] for r in table)
        ok = (len(table) == 26
              and sorted(r["rank"] for r in table) == list(range(1, 27))
              and total == summed and abs(shares - 100) < 0.5)
        if not ok:
            failures += 1
            print(f"  ! {centre}: {len(table)} rows, sum {summed}, printed {total}, "
                  f"shares {shares:.2f}")
        for r in table:
            sums[r["rank"]] = sums.get(r["rank"], 0) + r["votes"]
            rows.append({"constituency": centre, "rank": r["rank"],
                         "candidate": r["candidate"], "votes": r["votes"],
                         "share_pct": f"{r['share_pct']:.2f}",
                         "constituency_valid_votes": total})
    centres = len({r["constituency"] for r in rows})
    print(f"annex 7: {len(rows)} rows across {centres} centres, "
          f"{failures} failing their own arithmetic")

    os.makedirs("data", exist_ok=True)
    with open(OUT_CONSTIT, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, ["constituency", "rank", "candidate", "votes",
                                     "share_pct", "constituency_valid_votes"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {OUT_CONSTIT} ({len(rows)} rows)")

    # --- national tables ------------------------------------------------
    chart_page, canonical = chart(pages)
    by_votes = {c["votes"]: c for c in canonical}
    by_name = {name_key(c["candidate"]): c for c in canonical}
    mismatch = [c["rank"] for c in canonical if sums.get(c["rank"]) != c["votes"]]
    print(f"chart on page {chart_page + 1}: 26 candidates; constituency sums "
          f"{'match' if not mismatch else 'DIFFER for ranks ' + str(mismatch)} "
          f"the national figures")

    prelim, final, r2 = find_national(pages)
    stages = [("r1_preliminary", prelim, 26), ("r1_final", final, 26), ("r2_final", r2, 2)]

    national_rows = []
    for stage, page_no, limit in stages:
        table = national(pages, page_no, limit)
        total = sum(r["votes"] for r in table)
        if stage.startswith("r1"):
            expected = sum(sums.values())
            missing = [c["rank"] for c in canonical
                       if c["votes"] not in {r["votes"] for r in table}]
        else:
            expected, missing = R2_VALID, []
        note = "sums to the stated total" if total == expected else \
               f"sums to {total}, not {expected}"
        print(f"{stage}: {len(table)} rows, {note}"
              + (f"; missing rank(s) {missing}" if missing else ""))
        for r in table:
            # Round one identifies a row by its (unique) vote count; round two
            # repeats two of the same candidates, so it matches on the name.
            match = (by_votes.get(r["votes"]) if stage.startswith("r1")
                     else by_name.get(name_key(r["name_in_table"])))
            words = r["words_value"]
            national_rows.append({
                "stage": stage,
                "rank": match["rank"] if match else "",
                "candidate": match["candidate"] if match else r["name_in_table"],
                "votes": r["votes"],
                "share_pct": r["share_pct"],
                "constituency_sum": sums.get(match["rank"], "") if match else "",
                "votes_spelled": r["votes_spelled"],
                "words_value": words if words is not None else "",
                "words_check": ("agree" if words == r["votes"]
                                else "unparsed" if words is None else "words-differ"),
                "name_in_table": r["name_in_table"],
                "source_page": r["source_page"],
            })
    agree = sum(1 for r in national_rows if r["words_check"] == "agree")
    print(f"national: {len(national_rows)} rows, {agree} word-validated")

    with open(OUT_NATIONAL, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, ["stage", "rank", "candidate", "votes", "share_pct",
                                     "constituency_sum", "votes_spelled", "words_value",
                                     "words_check", "name_in_table", "source_page"])
        writer.writeheader()
        writer.writerows(national_rows)
    print(f"wrote {OUT_NATIONAL} ({len(national_rows)} rows)")


if __name__ == "__main__":
    main()
