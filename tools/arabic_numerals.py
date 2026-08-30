"""Parse Arabic number words ("ستة وخمسون" -> 56).

ISIE results tables print every vote count twice: once in digits and once
spelled out ("بلسان القلم"). OCR misreads digits far more often than words, so
the spelled form is treated as authoritative and the digits as a cross-check.
"""
import re
import unicodedata

FOLD = str.maketrans("أإآىئؤة", "اااييوه")
TASHKEEL = re.compile(r"[\u064B-\u0652\u0640\u0670]")


def _fold(s):
    """Unify hamza carriers and ta-marbuta, and drop diacritics."""
    return TASHKEEL.sub("", unicodedata.normalize("NFC", s).translate(FOLD))


_UNITS = {
    "صفر": 0, "واحد": 1, "احد": 1, "اثنان": 2, "اثنين": 2, "اثنتان": 2, "اثنتين": 2,
    "ثلاثة": 3, "ثلاث": 3, "أربعة": 4, "أربع": 4, "خمسة": 5, "خمس": 5,
    "ستة": 6, "ست": 6, "سبعة": 7, "سبع": 7, "ثمانية": 8, "ثمان": 8, "ثماني": 8,
    "تسعة": 9, "تسع": 9,
}
_TEENS = {"عشر": 10, "عشرة": 10}
_TENS = {
    "عشرون": 20, "عشرين": 20, "ثلاثون": 30, "ثلاثين": 30, "أربعون": 40, "أربعين": 40,
    "خمسون": 50, "خمسين": 50, "ستون": 60, "ستين": 60, "سبعون": 70, "سبعين": 70,
    "ثمانون": 80, "ثمانين": 80, "تسعون": 90, "تسعين": 90,
}
_HUNDREDS = {
    "مائة": 100, "مئة": 100, "ماية": 100,
    "مائتان": 200, "مائتين": 200, "مئتان": 200, "مئتين": 200, "مايتان": 200, "مايتين": 200,
    "ثلاثمائة": 300, "ثلاثمئة": 300, "أربعمائة": 400, "أربعمئة": 400,
    "خمسمائة": 500, "خمسمئة": 500, "ستمائة": 600, "ستمئة": 600,
    "سبعمائة": 700, "سبعمئة": 700, "ثمانمائة": 800, "ثمانمئة": 800, "ثمانيمائة": 800,
    "تسعمائة": 900, "تسعمئة": 900,
}
# Multipliers act on the group of units/tens/hundreds that precedes them.
_THOUSAND = {"ألف": 1000, "الف": 1000, "آلاف": 1000, "الاف": 1000}
_THOUSAND_FIXED = {"ألفان": 2000, "ألفين": 2000, "الفان": 2000, "الفين": 2000}

VALUES = {_fold(k): v for k, v in {**_UNITS, **_TEENS, **_TENS, **_HUNDREDS}.items()}
MULT = {_fold(k): v for k, v in _THOUSAND.items()}
MULT_FIXED = {_fold(k): v for k, v in _THOUSAND_FIXED.items()}
KNOWN = set(VALUES) | set(MULT) | set(MULT_FIXED)


def _split_conjunctions(word):
    """'سبعةوخمسون' -> ['سبعة', 'خمسون']; leading 'و' is stripped."""
    if word in KNOWN:
        return [word]
    if word.startswith("و") and word[1:] in KNOWN:
        return [word[1:]]
    for i in range(1, len(word)):
        if word[i] != "و":
            continue
        head, tail = word[:i], word[i + 1:]
        if head in KNOWN and tail:
            return [head] + _split_conjunctions(tail)
    return [word]


def _tokens(text):
    text = re.sub(r"[^\w\s]", " ", _fold(text))
    out = []
    for word in text.split():
        out.extend(_split_conjunctions(word))
    return out


def parse(text):
    """Return the integer spelled by `text`, or None if no number is present."""
    if not text:
        return None
    total, group, seen = 0, 0, False
    for word in _tokens(text):
        if word in MULT_FIXED:
            total += MULT_FIXED[word]
            group, seen = 0, True
        elif word in MULT:
            total += (group or 1) * MULT[word]
            group, seen = 0, True
        elif word in VALUES:
            group += VALUES[word]
            seen = True
    return total + group if seen else None


def check(spelled, digits):
    """Compare the spelled value with an OCR'd digit string.

    Returns (value, status); status is agree / digits-wrong / words-only /
    digits-only / missing. The spelled form wins when the two disagree.
    """
    words = parse(spelled)
    num = int(digits) if digits and str(digits).isdigit() else None
    if words is not None and num is not None:
        return (words, "agree") if words == num else (words, "digits-wrong")
    if words is not None:
        return words, "words-only"
    if num is not None:
        return num, "digits-only"
    return None, "missing"
