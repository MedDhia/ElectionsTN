"""Shared access to the 2014 results as the Official Gazette published them.

2014 is the one election year where isie.tn holds no results at all — not the
files, not a page that once linked them. The media library still lists thirteen
2014 results documents under `uploads/2014/11/` and `uploads/2014/12/` and every
one of them 404s; the two pages built to carry them
(`نتائج-الانتخابات-الرئاسية`, `نتائج-الانتخابات-التشريعية`) render their
`php_file_tree` widget against directories that no longer exist, so the trick
that recovered 23,509 procès-verbaux for 2024 returns an empty tree here. The
ISIE's own 149-page report on the 2014 elections was re-uploaded in 2025 and is
narrative: it carries the registration statistics and not one vote count. And
the Wayback Machine, which supplied the one 2019 table isie.tn had lost, holds
captures of nine of those thirteen documents but was unreachable from this
network while these datasets were built.

None of that matters, because the results were never only on isie.tn. Article 4
of each declaring decision orders it published in the Official Gazette, and the
Gazette is a permanent record: the Imprimerie Officielle's full run is mirrored
at `lake.jort.tn`, indexed and searchable, and three 2014 issues carry the whole
of the 2014 result —

* **n° 94 of 21 November 2014** — ISIE decision n° 34, the final results of the
  legislative election of 26 October 2014. Seventeen pages of decision (per
  constituency: voters, valid votes, spoilt, blank, seats, electoral quotient
  and every elected member by name) and a 59-page annex giving every candidate
  list's vote and share in each of the 33 constituencies.
* **n° 99 of 9 December 2014** — ISIE decision n° 35, the final results of the
  first round of the presidential election of 23 November 2014: the national
  table with each of the 27 candidates' votes in digits and spelled out in
  Arabic words, then one table per collection centre.
* **n° 105 of 30 December 2014** — ISIE decision n° 36, the final results of the
  second round of 21 December 2014, with its annex table of the two candidates'
  votes in each of the 33 centres.

A fourth issue, **n° 32 of 21 April 2015**, carries the ISIE's report on the
year, which is the only one of the four that gives the size of the electoral
register.

This is the source of record rather than a substitute for one: the Gazette text
*is* the decision. It also reads far better than the 2019 material did. Every
figure comes off a text layer rather than a scan, and the decisions print each
national count twice — in digits and in Arabic words — which gives the same
independent reading of every total that the 2019 datasets rely on.

Four extraction quirks are handled here rather than in each builder, because
every one of them shows up in more than one issue.

* pdfium returns these pages with the words of each line in visual order, so a
  line has to be read back to front — `reorder`.
* A vowel mark is a separate glyph, emitted where it is drawn rather than where
  it is read, which splits the word around it and leaves the pieces reversed —
  `clean`.
* A label therefore cannot be matched literally: punctuation lands at the wrong
  end of a word, a figure is sometimes glued to one, and a ligature sometimes
  breaks one in two — `squeeze`.
* And in a table, the space the Gazette groups thousands with is
  indistinguishable in the text from the space between two columns, so a
  table's figures are read from the digit glyphs' own coordinates — `grid`.

One more is local to the legislative annex, whose fonts carry a broken `cmap`
that maps a dozen ligature glyphs onto unrelated codepoints. That damages the
list names and never the digits; `repair` undoes what is systematic, and
`tools/build_legislative_2014_lists.py` reads the names by OCR instead.
"""
import difflib, os, re, time, urllib.parse, urllib.request

import pypdfium2 as pdfium

from arabic_numerals import KNOWN, _fold, _split_conjunctions, parse

CACHE = ".cache/pdfs"
LAKE = "https://lake.jort.tn/journal-officiel/ar/{year}/{issue}.pdf"

# The three issues that carry the 2014 results, by the contest each declares,
# and the one that carries the ISIE's report on the year, which is where the
# size of the electoral register comes from.
ISSUES = {
    "legislative": (2014, "094"),
    "presidential_r1": (2014, "099"),
    "presidential_r2": (2014, "105"),
    "report": (2015, "032"),
}


def fetch(url, dest, tries=6):
    """Download `url` to `dest` once; later runs reuse the cached copy."""
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if os.path.exists(dest) and os.path.getsize(dest) > 1024:
        return dest
    quoted = urllib.parse.quote(url, safe=":/?&=%")
    for attempt in range(tries):
        try:
            req = urllib.request.Request(quoted, headers={"User-Agent": "Mozilla/5.0"})
            data = urllib.request.urlopen(req, timeout=600).read()
            if not data.startswith(b"%PDF"):
                raise OSError(f"not a PDF ({len(data)} bytes)")
            tmp = dest + ".part"
            with open(tmp, "wb") as fh:
                fh.write(data)
            os.replace(tmp, dest)
            return dest
        except Exception as exc:
            if attempt == tries - 1:
                raise
            print(f"  retry {attempt + 1}: {exc}")
            time.sleep(3 * (attempt + 1))


def issue(contest):
    """Path to the cached Gazette issue declaring `contest`, fetching it once."""
    year, number = ISSUES[contest]
    dest = os.path.join(CACHE, f"jort_{year}_{number}_ar.pdf")
    return fetch(LAKE.format(year=year, issue=number), dest)


def pages(path):
    """Every page's text, as pdfium lays it out."""
    pdf = pdfium.PdfDocument(path)
    return [pdf[i].get_textpage().get_text_range() for i in range(len(pdf))]


TASHKEEL = re.compile(r"[ً-ْٰ]+")
# n° 105 sets its diacritics from a private-use range instead, and emits them
# as tokens of their own rather than inside the word.
PRIVATE = re.compile(r"[-]+")


CENTRE = "مركز جمع"


def centres():
    """The 33 units, named as the first-round presidential decision names them.

    Every 2014 table is broken down the same way, and the three decisions name
    the unit three different ways: a collection centre (مركز جمع) in the
    presidential annexes, a described electoral constituency ("the first
    electoral constituency of the governorate of Tunis") in the legislative
    decision, and an abbreviation ("تونس 1") in its annex. The presidential
    round-one tables head each of theirs with the short, undamaged form, so
    that is the spelling every 2014 dataset here is keyed to.
    """
    names, seen = [], set()
    for text in pages(issue("presidential_r1")):
        for line in map(clean, lines(text)):
            if line.startswith(CENTRE):
                name = clean(line[len(CENTRE):])
                if name and name not in seen:
                    seen.add(name)
                    names.append(name)
    return names


def canonical(name, names):
    """`name` snapped onto the closest of `names`, or None if none is close.

    The three decisions spell a handful of the 33 differently — the legislative
    one writes "الدول العربية وبقية دول العالم" where the presidential one has
    "وباقي" — so a name is matched rather than compared, and only when one
    candidate is clearly the best.
    """
    scored = sorted(((difflib.SequenceMatcher(None, _fold(name), _fold(other))
                      .ratio(), other) for other in names), reverse=True)
    if not scored or scored[0][0] < 0.6:
        return None
    if len(scored) > 1 and scored[1][0] > scored[0][0] - 0.05:
        return None
    return scored[0][1]


def clean(text):
    """Drop the diacritics, and put back the letters they displace.

    A vowel mark is its own glyph, drawn above the letter it belongs to, and
    pdfium emits it where it is drawn rather than where it is read. That splits
    the word around it and leaves the pieces in visual order, so "الجملي"
    arrives as "مليُالج" — "ملي", the mark, then "الج". Splitting on the marks
    and putting the pieces back in reading order undoes it; a word with no mark
    is untouched.
    """
    words = []
    for word in PRIVATE.sub("", text).split():
        parts = TASHKEEL.split(word)
        words.append("".join(reversed(parts)) if len(parts) > 1 else word)
    return " ".join(w for w in words if w)


def reorder(line):
    """Read one line back to front, which is the order it was written in.

    These pages come out of pdfium with each line's words in visual order —
    rightmost first in a right-to-left script means last — so a line is
    reversed word by word. Letters within a word are already in reading order.
    """
    return " ".join(reversed(line.split()))


def lines(text):
    """The non-empty lines of one page, each already reordered."""
    return [l for l in (reorder(x) for x in text.split("\n")) if l.strip()]


# --------------------------------------------------------------- glyph repair

# The legislative annex is set in fonts whose `cmap` is wrong: a ligature is one
# glyph in the font and each of these maps to whatever codepoint sits near it,
# so the two or three letters it draws arrive as one unrelated character. Digits
# are unaffected — they are separate glyphs with a correct mapping — so only the
# list names need this, and every repair below was read off the corpus by
# comparing a damaged name with the same name in the decision's own text, which
# is set in a different font and is undamaged.
#
# Single letters first. Each of these codepoints stands for exactly one letter
# or ligature everywhere it appears, and every reading below is corroborated by
# what Tesseract makes of the same cell.
LETTERS = {
    "؅": "ت",   # ARABIC NUMBER MARK ABOVE  — الترتيب, الاشتراكي
    "؄": "ب",   # ARABIC SIGN SAMVAT        — ديسمبر, البرنامج
    "؈": "ي",   # ARABIC RAY                — الديمقراطيين, القيروان
    "ڴ": "ل",   # GAF WITH THREE DOTS ABOVE — الجملي
    "ڲ": "ل",   # GAF WITH TWO DOTS BELOW   — الليبرالي, العالي
    "ڤ": "ع",   # VEH                       — الاجتماعي
    "ࢭ": "ف",   # LOW ALEF                  — في
    "ࢮ": "ق",   # DAL WITH THREE DOTS BELOW — الرقي
    "ࡪ": "ق",   # SYRIAC MALAYALAM SSA      — وباقي
    "ہ": "ه",   # HEH GOAL                  — هي
    "ۂ": "ه",   # HEH GOAL WITH HAMZA       — هي
    "٭ڈ": "به",   # FIVE POINTED STAR + DDAL   — بها
    "ܣۚ": "ني",   # SEMKATH + SMALL HIGH JEEM  — الوطني
    "ܣۜ": "ي",    # SEMKATH + SMALL HIGH SEEN  — التونسي
    "ܣۗ": "بي",   # SEMKATH + QAF-LAM-ALEF     — الشعبي
    "ܣ": "ي",     # SEMKATH alone, at a word's end — البيئي
}
# A ligature glyph is placed where it is drawn, not where it is read, so these
# four arrive detached from the word they belong to and have to be moved as well
# as translated. The two hamza marks belong on the word's first alef; the
# Semkath forms are a word's last letters and belong at its end.
TRAILING = {"ܣۚ", "ܣۜ", "ܣۗ", "ܣ"}
HAMZA = {"ٔ": "أ", "ٕ": "إ"}
# What is left is the lam-alef ligature, which the same fault writes as "ال":
# "الإصلاح" arrives as "الاصالح". Undoing that blindly would wreck the definite
# article, and unlike the 2019 report there is no dictionary of numbers to test a
# candidate against, so these are listed one by one — as are the four words whose
# damage is not systematic at all. Two of the glyphs are genuinely ambiguous in
# the text layer: "ڈ" is the medial heh of a ligature whose first letter the font
# drops, and a dotted letter's medial form is the same whether it is a beh or a
# noon, so "الجبهة" and "النهضة" arrive indistinguishable but for their tails.
# Each entry below is a word the rules above cannot finish, and each was read off
# the OCR of the same cell.
WORDS = {
    "الاصالح": "الإصلاح", "الاصالحو": "الإصلاح و", "لالصالح": "للإصلاح",
    "الاسالمي": "الإسلامي", "الائتالف": "الائتلاف", "الفالحين": "الفلاحين",
    "الاقالع": "الإقلاع", "الانقاذ": "الإنقاذ", "الاعالم": "الإعلام",
    "الاستقالل": "الاستقلال", "الاغالبية": "الأغلبية", "استقاللية": "استقلالية",
    "الاصالة": "الأصالة", "الاصالةو": "الأصالة و", "الاادةر": "الإرادة",
    "لالنقاذ": "للإنقاذ", "لالمركزية": "للامركزية", "الانطالق": "الانطلاق",
    "الاقالعو": "الإقلاع و", "الاادةو": "الإرادة و", "لبالدنا": "لبلادنا",
    "الجڈة": "الجبهة", "جڈة": "جبهة", "ڈضةٔال": "النهضة",
    "روتنا؆ل": "لثروتنا", "قرت؇ب": "بنزرت", "قرت؇بب": "ببنزرت",
    "قاهة؇تيارال": "تيار النزاهة",
}
CORRUPT = re.compile("[؄-؈ٕٔۚۜۗ"
                     "ڈ٭ܣڴڲڤࢭࢮࡪہۂ]")


def _repair_word(word):
    if word in WORDS:
        return WORDS[word]
    for bad, good in LETTERS.items():
        if bad in word:
            word = (word.replace(bad, "") + good if bad in TRAILING
                    else word.replace(bad, good))
    for mark, carrier in HAMZA.items():
        if mark in word:
            word = word.replace(mark, "")
            # The mark sits on the first bare alef, which is the article's
            # second letter in "الأصوات" and the first letter otherwise.
            i = word.find("ا", 2) if word.startswith("ال") else word.find("ا")
            if i >= 0:
                word = word[:i] + carrier + word[i + 1:]
    return WORDS.get(word, word)


def repair(text):
    """Undo the annex fonts' broken glyph mapping, word by word.

    Returns the text with every mapping this module knows applied. A name that
    still holds a damaged codepoint afterwards is left as it is and reported by
    the builder rather than guessed at.
    """
    out = []
    for word in text.split():
        fixed = _repair_word(word)
        # "المـ" is drawn with a lam-alef-lam ligature and arrives as "امل".
        if fixed.startswith("امل") and len(fixed) > 3:
            fixed = "الم" + fixed[3:]
        out.extend(fixed.split())
    return " ".join(out)


def damaged(text):
    """True if `text` still carries a codepoint the repair table does not know."""
    return bool(CORRUPT.search(text))


# ------------------------------------------------------------------- numerals

# arabic_numerals stops at thousands. Every national total here is seven
# figures, so the million is handled on top of it, exactly as the 2019
# presidential builder does.
MILLIONS = {"مليون": 1, "مليونان": 2, "مليونين": 2, "ملايين": 1}


def parse_words(spelled):
    """`arabic_numerals.parse`, extended over the million a total needs."""
    tokens = [numeral(t) or t for t in clean(spelled).split()]
    for i, token in enumerate(tokens):
        if token in MILLIONS:
            head = parse(" ".join(tokens[:i]))
            millions = MILLIONS[token] if MILLIONS[token] > 1 else (head or 1)
            return millions * 1000000 + (parse(" ".join(tokens[i + 1:])) or 0)
    return parse(" ".join(tokens))


def numeral(token):
    """`token` as a number word the parser knows, or None if it is not one.

    The decisions decline these words — a count of thousands is written "ألفا",
    the accusative of "ألف" — so a token that is not recognised is tried again
    without its final alef, and the stripped form is accepted only when it is a
    number word, which leaves ordinary words alone.
    """
    word = _fold(token.strip(".,،:")).lstrip("و")
    for candidate in (word, word.rstrip("ا")):
        if not candidate:
            continue
        parts = _split_conjunctions(candidate)
        if all(p in KNOWN or p in MILLIONS for p in parts):
            return candidate
    return None


def is_number_word(token):
    """True if `token` is one word of a spelled-out Arabic number."""
    return numeral(token) is not None


# --------------------------------------------------------------------- digits

PUNCT = re.compile(r"[:.,،؛()\u2013\u2014-]+")


def squeeze(text):
    """`text` with punctuation, digits and every space taken out.

    A label cannot be matched literally in these decisions. Reversing a line
    moves its punctuation to the wrong end of the word it was attached to, so
    "عدد المقاعد" arrives as "عدد :المقاعد"; the figure is sometimes glued
    against a word, as in "صوت171193"; and a word is sometimes broken by a
    space where a ligature ends, so "المصرح" appears also as "المصر ح" and
    "ا لمصرح". Squeezing both sides of the comparison makes all three
    harmless.
    """
    return re.sub(r"[\s\d]+", "", PUNCT.sub("", clean(text)))


def numbers(text):
    """Every integer in `text`, commas removed and adjacent letters ignored.

    Enough for a line of prose, where each figure stands alone — even where the
    reversal has glued it to a word, as in "صوت171193". It is *not* enough for
    a table: the Gazette groups thousands with a space in some of them and the
    space survives extraction, so "28 362" would read as two numbers here.
    Tables use `grid`, which cuts on the glyphs' own spacing.
    """
    return [int(t) for t in
            re.findall(r"\d+", re.sub(r"(?<=\d),(?=\d)", "", text))]


def grid(path, index, gap=6.0, row_gap=4.0):
    """Every number on one page of `path`, grouped into rows, by glyph position.

    Reading a table's digits off the text alone is ambiguous, because the space
    inside "28 362" looks exactly like the space between two columns. The glyphs
    are not ambiguous: the space inside a number is about two points wide and
    the gap between columns is twenty, so a number ends where the gap does.

    Returns [(top, bottom, [(x0, x1, value), ...]), ...], rows top to bottom
    and each row's numbers left to right. The top and bottom are the digits'
    own, which is what a caller cropping the row out of a rendering wants.
    """
    pdf = pdfium.PdfDocument(path)
    textpage = pdf[index].get_textpage()
    glyphs = []
    for i in range(textpage.count_chars()):
        char = textpage.get_text_range(i, 1)
        if char.isdigit():
            left, bottom, right, top = textpage.get_charbox(i)
            glyphs.append(((bottom + top) / 2, left, right, top, bottom, char))
    rows = []
    for y, left, right, top, bottom, char in sorted(
            glyphs, key=lambda g: (-g[0], g[1])):
        if rows and abs(rows[-1][0] - y) <= row_gap:
            rows[-1][1].append((left, right, top, bottom, char))
        else:
            rows.append((y, [(left, right, top, bottom, char)]))
    out = []
    for y, chars in rows:
        cells, digits, x0, x1 = [], "", None, None
        # A row's glyphs sit a fraction of a point apart vertically, so the
        # sort above can leave them out of reading order within the row.
        for left, right, _, _, char in sorted(chars):
            if digits and left - x1 > gap:
                cells.append((x0, x1, int(digits)))
                digits = ""
            x0 = left if not digits else x0
            x1, digits = right, digits + char
        if digits:
            cells.append((x0, x1, int(digits)))
        out.append((max(c[2] for c in chars), min(c[3] for c in chars), cells))
    return out
