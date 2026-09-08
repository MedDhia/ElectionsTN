"""Folding and canonicalisation for Latin-script Tunisian place names.

The repo already folds Arabic in four places (canonicalise_polling_centres.py,
parse_local_results_2023.py, arabic_numerals.py, pv_orient.py). Those all fold
Arabic against Arabic. Nothing here transliterates: this module only makes two
Latin spellings of the same place compare equal.

The two source files disagree on house style rather than on content. The INS
delegation list writes `Menzel Bourguiba`, `M’saken`, `Béja`; the historical
locality file writes `Menzel-Bourguiba`, `El M'nagha`, `Beja`. Folding hyphens,
apostrophes and combining accents away lets a place resolve across both without
either file being rewritten to the other's convention.
"""

import re
import unicodedata

# Both apostrophe glyphs in use (U+0027 in the locality file, U+2019 in the INS
# list), plus the modifier letter and acute accent that turn up in scraped text.
APOSTROPHES = re.compile(r"['’ʼ`´]")

_NONALNUM = re.compile(r"[^a-z0-9]+")

# `Délégation de Sfax`, `Délégation du Fahs`, `Délégation d'El Jem`. The 1956
# column stores the unit's full title where every other column stores a bare
# name, so none of its 32 distinct values matched anything until the title was
# removed.
DELEGATION_PREFIX = re.compile(r"^d[eé]l[eé]gation\s+(?:de|du|d)\s*['’]?\s*", re.IGNORECASE)

# `sources_lat_lon` holds three sources written eight ways.
SOURCE_CANON = {
    "google maps": "Google Maps",
    "geonames": "Geonames",
    "mindat": "Mindat",
}


def strip_accents(s):
    """`Béja` -> `Beja`, `Chaâl` -> `Chaal`, `Aïn` -> `Ain`."""
    return "".join(
        c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)
    )


def fold(s):
    """Reduce a Latin place name to a comparison key.

    Accents, case, apostrophes and the hyphen/space distinction all vary freely
    between the two files and within each of them, and none of that variation
    carries meaning. Everything else is left alone, so `Souk El-Arba (Jendouba)`
    keeps its qualifier and stays distinct from `Souk El-Arba`.
    """
    s = strip_accents(unicodedata.normalize("NFKC", (s or "").strip()))
    s = APOSTROPHES.sub("", s.lower())
    return " ".join(_NONALNUM.sub(" ", s).split())


def strip_delegation_prefix(s):
    """`Délégation de Sfax` -> `Sfax`. Leaves anything else untouched."""
    return DELEGATION_PREFIX.sub("", (s or "").strip()).strip()


def canonical_source(s):
    """`google maps` -> `Google Maps`. Unknown values pass through trimmed."""
    s = (s or "").strip()
    return SOURCE_CANON.get(fold(s), s)


def article_variant(a, b):
    """True when two folded names differ only by a leading Arabic article.

    `azib`/`el azib`, `munchar`/`el munchar`. Used as evidence that two
    co-located rows are one place spelled two ways, never on its own.
    """
    articles = ("el ", "le ", "la ", "les ", "er ", "ez ", "es ")
    for x, y in ((a, b), (b, a)):
        for art in articles:
            if x.startswith(art) and x[len(art):] == y:
                return True
    return False


def vowel_skeleton(s):
    """A folded name with its vowels dropped, for spotting vowel-only variants.

    `bani hassen`/`beni hassen` and `oued zerga`/`oued zarga` are the same name
    transliterated twice; they share a consonant skeleton. Distinct places do
    not normally collide here, but this is evidence toward a merge rather than a
    decision on its own — every merge is also distance-gated and logged.
    """
    return re.sub(r"[aeiouy]+", "", fold(s))
