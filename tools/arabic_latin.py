"""Match Arabic place names against their French transliterations.

Nothing in this repo could do this. The four existing folds
(`canonicalise_polling_centres.py`, `parse_local_results_2023.py`,
`arabic_numerals.py`, `pv_orient.py`) all normalise Arabic against Arabic, and
`latin_names.py` folds Latin against Latin. The PV datasets name every place in
Arabic; the INS delegation list names them in French. Joining them needs a
comparison that crosses scripts.

Two ideas carry the work.

**Consonant skeletons.** Arabic script writes consonants and long vowels; French
transliteration writes every vowel. So `سوسة` and `Sousse` look nothing alike
character by character, but reduce both to consonants and they are both `sws`.
Vowels are where transliteration is least predictable, so dropping them removes
most of the disagreement. `السيجومي` and `Sijoumi` both give `sjm`; `المدينة`
and `La Medina` both give `mdn`.

**Qualifiers are translated, not transliterated.** A delegation's compass suffix
is Arabic in one file and French in the other: `بنزرت الشمالية` is
`Bizerte Nord`. Transliterating الشمالية gives `cmly`, which resembles `Sud`
about as much as it resembles `Nord` — so a skeleton matcher will cheerfully
return the wrong half of a north/south pair. These words therefore go through a
lexicon, and a candidate whose qualifier disagrees is rejected outright rather
than scored.
"""

import re
import unicodedata

# Arabic normalisation, matching the fold already used in
# tools/parse_local_results_2023.py and tools/pv_orient.py.
AR_FOLD = str.maketrans("أإآىئؤ", "اااييو")
TASHKEEL = re.compile(r"[ً-ْـٰ]")
AR_ARTICLE = re.compile(r"^(?:ال|ٱل)")

# Arabic letter -> coarse consonant class. Emphatic and plain pairs collapse
# (ص/س, ط/ت, ض/د, ظ/ز) because French transliteration does not distinguish them.
#
# ا, ى, ة and ي all drop. ي earns a word of explanation: in place names it is
# almost always the long vowel /i:/, which French writes as `i`, `ie` or `ï`
# (`سيجومي` is `Sijoumi`, `المدينة` is `Medina`, `القيروان` is `Kairouan`).
# Keeping it as `y` while the Latin side strips its vowels made the two scripts
# disagree on 9 of 11 test names; dropping it on both sides is symmetric, and
# still works where ي really is consonantal, because French writes that as a
# `Y` that also drops (`يوسف` and `Youssef` both give `wsf`).
#
# و is the opposite case and is kept: French writes it `ou`, which the digraph
# table turns back into `w`, so `سوسة` and `Sousse` both give `sws`.
AR_CONSONANT = {
    "ب": "b", "ت": "t", "ث": "t", "ج": "j", "ح": "h", "خ": "k", "د": "d",
    "ذ": "d", "ر": "r", "ز": "z", "س": "s", "ش": "c", "ص": "s", "ض": "d",
    "ط": "t", "ظ": "z", "ع": "", "غ": "g", "ف": "f", "ق": "k", "ك": "k",
    "ل": "l", "م": "m", "ن": "n", "ه": "h", "و": "w", "ي": "",
    "ا": "", "ة": "", "ء": "", "ﻻ": "l",
}

# French graphemes mapped onto the same consonant classes, longest first. These
# are applied in ONE left-to-right pass, never as successive replacements: run
# sequentially, `ch` -> `c` turns `Echebika` into `ecebika`, whereupon the
# `ce` -> `se` rule fires on a `c` that was never there and yields `esebika`.
# That bug matched الشابة to `Chorbane` instead of `Chebba`.
#
# `ou` becomes `w` because that is how Arabic و is written in French, so
# `Sousse` gives `sws` and matches سوسة. `x` becomes `ks`, which is what صفاقس
# spells out letter by letter. `c` is /s/ before a front vowel (`Cebalet` for
# سبالة) and /k` otherwise (`Carthage` for قرطاج).
LAT_MAP = {
    "tch": "c", "sch": "c", "ch": "c", "kh": "k", "gh": "g", "dh": "d",
    "th": "t", "ph": "f", "dj": "j", "ou": "w", "qu": "k", "ck": "k",
    "oo": "w", "ce": "se", "ci": "si", "cy": "sy", "x": "ks", "c": "k",
    # `gh` is غ and plain `g` is ق, and the distinction has to survive: fold
    # them together and `Agareb` (عقارب) and `Ghraiba` (الغريبة) both reduce to
    # `krb`, so each ties with the other's Arabic name at a perfect score and
    # the margin guard rejects both. Two real Sfax delegations lost that way.
    "gh": "g", "g": "k",
    # Arabic ق and ك both give `k`, so a Latin `q` must land there too --
    # leaving it as its own class stranded `Utique` (أوتيك) at `tq`.
    "q": "k",
}
LAT_PATTERN = re.compile("|".join(sorted(LAT_MAP, key=len, reverse=True)))

LAT_VOWELS = re.compile(r"[aeiouy]")

# Articles carry no information: Arabic drops ال per word, and French writes
# `El`, `La`, `Es-`, `Ez-` inconsistently (`El Ksour` against `القصور`).
LAT_ARTICLES = {"el", "le", "la", "les", "er", "ez", "es", "en", "ed", "et", "l"}

# Arabic qualifier -> the French words that may render it. `مدينة` takes either,
# since the INS list writes both `Sfax Ville` and `Gabes Medina`.
QUALIFIERS = {
    "شمالية": {"nord"}, "شمالي": {"nord"},
    "جنوبية": {"sud"}, "جنوبي": {"sud"},
    "شرقية": {"est"}, "شرقي": {"est"},
    "غربية": {"ouest"}, "غربي": {"ouest"},
    "مدينة": {"ville", "medina"},
    "جديدة": {"nouvelle"},
    "اعلى": {"superieur"}, "علوية": {"superieur"},
    "سفلى": {"inferieur"},
    "حي": {"cite"},
}
LAT_QUALIFIERS = {"nord", "sud", "est", "ouest", "ville", "medina", "cite",
                  "nouvelle", "superieur", "inferieur"}


def ar_norm(s):
    """Normalise Arabic: unify hamza carriers, drop tashkeel and tatweel."""
    s = unicodedata.normalize("NFC", (s or "").strip()).translate(AR_FOLD)
    return TASHKEEL.sub("", s).replace("ـ", "")


def ar_words(s):
    """Split Arabic into words with the definite article removed from each."""
    return [w for w in (AR_ARTICLE.sub("", p)
                        for p in re.split(r"[\s\-–_/]+", ar_norm(s)) if p) if w]


def lat_words(s):
    """Split a French name into words, dropping articles."""
    s = unicodedata.normalize("NFKD", (s or "").strip())
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"['’`´]", "", s)
    return [w for w in re.split(r"[^a-z0-9]+", s) if w and w not in LAT_ARTICLES]


def _collapse(s):
    """De-double. Consonant classes are already unified by the two maps."""
    return re.sub(r"(.)\1+", r"\1", s)


def ar_skeleton(words):
    """Arabic words -> consonant skeleton."""
    out = ["".join(AR_CONSONANT.get(c, "") for c in w) for w in words]
    return _collapse("".join(out))


def lat_skeleton(words):
    """French words -> the same consonant skeleton."""
    out = []
    for w in words:
        w = LAT_PATTERN.sub(lambda m: LAT_MAP[m.group(0)], w)
        out.append(LAT_VOWELS.sub("", w))
    return _collapse("".join(out))


# The Arabic keys above are written as they appear in the sources, but lookups
# happen after ar_norm, which folds ى to ي and unifies hamza carriers. Normalise
# the keys so `اعلى` and `سفلى` are actually reachable -- before this, the
# qualifier on `العمران الاعلى` was silently invisible and it matched the
# unqualified `El Omrane`, letting two ISIE units claim one delegation.
QUALIFIERS = {ar_norm(k): v for k, v in QUALIFIERS.items()}


def split_qualifier(words, vocab, is_arabic):
    """Separate a name's qualifier words from its stem.

    Returns (stem_words, qualifier_set). Matching is by whole word: `Est` is a
    substring of both `Ouest` and `Testour`, and حي of both الروحية and حيدرة,
    so a substring test mislabels them.
    """
    stem, quals = [], set()
    for w in words:
        if is_arabic and w in vocab:
            quals |= vocab[w]
        elif not is_arabic and w in vocab:
            quals.add(w)
        else:
            stem.append(w)
    return stem, quals
