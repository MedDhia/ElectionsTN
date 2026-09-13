"""Latin renderings of Arabic surnames, for filenames and secondary labels.

What this is for, and what it is not for
----------------------------------------
The surname maps print the surname in Arabic, shaped properly and set in Amiri.
That is the authoritative label. This module exists for the two places a figure
cannot carry Arabic: the **filename** on disk, and the **index CSV** a reader
greps. It also supplies a Latin subtitle, because every other figure in `maps/`
labels its geography in Latin and a surname map that named nothing in Latin
would be the odd one out.

Nothing here is ever used for matching. `tools/arabic_latin.py` already does
that, and does it by consonant skeleton precisely because transliteration is not
invertible. A transliteration that reads well and a key that compares equal are
different objects; conflating them is how a `Trabelsi`/`Traboulsi` pair silently
becomes one family.

The lexicon comes first
-----------------------
`SPELLINGS` holds the Latin spelling of a name where one is settled, keyed by the
same article-stripped normalised Arabic the maps pool on. It wins over every rule
below, because the rules cannot get these right even in principle:

* Arabic does not write gemination once tashkeel is stripped, so nothing in the
  letters says `همامي` is **Hammami** and not `Hamami`, or `جلاصي` **Jlassi**.
* The short vowel a cluster takes is not derivable either: `فرشيشي` is
  **Ferchichi**, `نفزي` **Nefzi**, but `مهذبي` is **Mhedhbi** with no vowel at
  all and `هميسي` **Hmissi**.
* ق is `g` in some Tunisian names and `k` or `q` in others -- `قاسمي` is
  **Guesmi**, `قرمازي` **Guermazi**, `راقوبي` **Ragoubi**, yet `حقي` is
  **Hakki**. The letter does not decide; usage does.

Entries here are the maintainer's spellings where they gave one, and the ordinary
Tunisian French spelling otherwise. A name with no entry falls through to the
rules, which give a readable approximation and not a person's own spelling of
their own name.

How it renders
--------------
Arabic writes consonants and long vowels and leaves the short vowels out, so a
letter-for-letter pass produces clusters no French speaker would write:
`طرابلسي` comes out `trablsi`, not `Trabelsi`. Two cluster rules fix most of it,
and both are ordinary Tunisian French orthography rather than invention:

* an initial consonant pair takes an `e` between its letters (`دربالي` ->
  `Derbali`);
* a medial run of three consonants takes an `e` after the first (`طرابلسي` ->
  `Trabelsi`).

The inserted vowel is `e` rather than `a` because that is what the corrected
spellings show wherever one appears at all -- Ferchichi, Nefzi, Khemiri,
Derbali -- and never `a`.

The letter table follows French usage as Tunisia writes it -- `ch` for ش, `ou`
for و, `kh` for خ, `gh` for غ, `dj`-free `j` for ج -- so the output looks like a
Tunisian name rather than an academic transliteration with dots under letters.

The result is a readable approximation, not a person's own spelling of their own
name. Where the two differ, the Arabic on the figure is what is true.
"""

import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from arabic_latin import ar_norm

# One pass, longest first. ء and ع carry no French letter of their own; ع
# becomes a vowel because that is how Tunisian French writes it (`معلاوي` ->
# `Maalaoui`), and ء drops.
LETTERS = {
    "ا": "a", "ب": "b", "ت": "t", "ث": "th", "ج": "j", "ح": "h", "خ": "kh",
    "د": "d", "ذ": "dh", "ر": "r", "ز": "z", "س": "s", "ش": "ch", "ص": "s",
    "ض": "dh", "ط": "t", "ظ": "dh", "ع": "a", "غ": "gh", "ف": "f", "ق": "q",
    "ك": "k", "ل": "l", "م": "m", "ن": "n", "ه": "h", "و": "ou", "ي": "i",
    "ة": "a", "ى": "a", "ء": "", "لا": "la",
}

VOWELS = set("aeiou")

# Letters that stand for a vowel in Arabic spelling, used to decide when ي is
# the consonant `y` rather than the vowel `i`: between two of these it is a
# glide, which is why `العياري` is `Ayari` and not `Aiari`.
VOWEL_LETTERS = set("اوىةع")

# Consonant pairs French writes as one onset. Without this the initial-pair
# rule would break `tr` and turn `طرابلسي` into `Tarabelsi`.
ONSET_FIRST = {"t", "d", "b", "g", "k", "f", "p", "kh", "gh", "ch", "th", "dh"}
ONSET_SECOND = {"r", "l"}

# Particles and given names that appear inside a compound surname and have a
# settled Tunisian French spelling of their own. A patronymic surname is a
# phrase -- `بن ضيف الله` -- and letter rules alone would render its parts as
# though nobody had ever written them down before.
WORDS = {
    "بن": "Ben", "ابن": "Ben", "بو": "Bou", "ابو": "Abou", "ولد": "Ould",
    "ال": "Al", "سيدي": "Sidi", "عبد": "Abd", "الله": "Allah",
    "الدين": "Eddine", "الحاج": "El Haj", "حاج": "Haj",
    "محمد": "Mohamed", "علي": "Ali", "صالح": "Saleh", "عمر": "Omar",
    "احمد": "Ahmed", "الطيب": "Tayeb", "سالم": "Salem", "ضيف": "Dhif",
    "امبارك": "Mbarek", "مبارك": "Mbarek", "الحسين": "Hsine",
}

# The definite article is dropped from a surname rather than written `El`:
# `الطرابلسي` is `Trabelsi` on every Tunisian identity card. It is kept where
# dropping it would leave less than three letters.
ARTICLE = re.compile(r"^ال")


# Settled spellings, keyed by the normalised name with the definite article
# stripped -- the same key `make_surname_dots.family_key` pools on, so
# `الطرابلسي` and `طرابلسي` find the same entry. These override the rules.
#
# Provenance: every spelling the maintainer corrected is theirs, verbatim. The
# rest are ordinary Tunisian French usage, and are the ones to check first if a
# name looks wrong on a figure -- one line here changes it everywhere, including
# the filename.
SPELLINGS = {
    # corrected by the maintainer
    "همامي": "Hammami", "بجاوي": "Bjaoui", "بناني": "Bannani",
    "برهومي": "Barhoumi", "جلاصي": "Jlassi", "يعقوبي": "Yaacoubi",
    "ماجري": "Mejri", "مرزوقي": "Marzouki", "فرشيشي": "Ferchichi",
    "قاسمي": "Guesmi", "خميري": "Khemiri", "مهذبي": "Mhedhbi",
    "نفزي": "Nefzi", "زغبي": "Zoghbi", "ورغي": "Ouerghi",
    "هميسي": "Hmissi", "حقي": "Hakki", "ماطوسي": "Mattoussi",
    "قرمازي": "Guermazi", "راقوبي": "Ragoubi", "مجبري": "Mejbri",
    # the rest of the drawn set, in ordinary Tunisian French usage
    "طرابلسي": "Trabelsi", "دريدي": "Dridi", "عياري": "Ayari",
    "عبيدي": "Abidi", "وسلاتي": "Ouslati", "عرفاوي": "Arfaoui",
    "حمروني": "Hamrouni", "رياحي": "Riahi", "تليلي": "Tlili",
    "ذوادي": "Dhouadi", "هيشري": "Hichri", "لواتي": "Louati",
    "هواري": "Houari", "صنهاجي": "Sanhaji", "مثلوثي": "Methlouthi",
    "عكرمي": "Akremi", "عكريمي": "Akrimi",
    "سعيدي": "Saidi", "غربي": "Gharbi", "جبالي": "Jebali",
    "علوي": "Alaoui", "حمدي": "Hamdi", "خليفي": "Khelifi",
    "سالمي": "Salmi", "عيادي": "Ayadi", "ساسي": "Sassi",
    "حامدي": "Hamedi", "عباسي": "Abbassi", "مناعي": "Mannai",
    "شريف": "Cherif", "عامري": "Ameri", "صالحي": "Salhi",
    "عوني": "Aouni", "عمري": "Amri", "سعيداني": "Saidani",
    "محمدي": "Mohamedi",
    "ضيفاوي": "Dhifaoui", "حرزي": "Harzi", "فزعي": "Fezai",
    "عويساوي": "Aouissaoui", "زايري": "Zairi", "بوزازي": "Bouzazi",
    "فقيري": "Fkiri", "معلاوي": "Maalaoui", "دربالي": "Derbali",
}


def lexicon_key(name):
    """The key `SPELLINGS` is indexed by: normalised, article stripped."""
    s = " ".join(ar_norm(name or "").split())
    if s.startswith("ال") and len(s) > 3:
        s = s[2:]
    return s


def _tokens(word):
    """Arabic letters to Latin tokens, each token one sound."""
    toks = []
    for i, ch in enumerate(word):
        t = LETTERS.get(ch, "")
        if ch == "ي":
            prev = word[i - 1] if i else ""
            nxt = word[i + 1] if i + 1 < len(word) else ""
            if prev in VOWEL_LETTERS and nxt in VOWEL_LETTERS:
                t = "y"
        if t:
            toks.append(t)
    return toks


def _is_vowel(tok):
    return tok[0] in VOWELS


def _open_clusters(toks):
    """Insert the vowels Arabic does not write. See the module docstring."""
    if (len(toks) > 2 and not _is_vowel(toks[0]) and not _is_vowel(toks[1])
            and not (toks[0] in ONSET_FIRST and toks[1] in ONSET_SECOND)):
        toks = [toks[0], "e"] + toks[1:]
    out = []
    for i, tok in enumerate(toks):
        out.append(tok)
        if (0 < i < len(toks) - 2 and not _is_vowel(tok)
                and not _is_vowel(toks[i + 1]) and not _is_vowel(toks[i + 2])):
            out.append("e")
    return "".join(out)


def translit(name):
    """The settled Latin spelling of one Arabic surname, or a rendering of it."""
    settled = SPELLINGS.get(lexicon_key(name))
    if settled:
        return settled
    words = [w for w in re.split(r"\s+", ar_norm(name)) if w]
    out = []
    for w in words:
        if w in WORDS:
            out.append(WORDS[w])
            continue
        stripped = ARTICLE.sub("", w)
        if len(stripped) >= 3:
            w = stripped
        latin = _open_clusters(_tokens(w))
        if latin:
            out.append(latin[0].upper() + latin[1:])
    return " ".join(out)


def slug(name):
    """A filename stem: lowercase, ASCII, hyphen-separated."""
    s = translit(name).lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "surname"


if __name__ == "__main__":
    for n in sys.argv[1:]:
        print(f"{n}\t{translit(n)}\t{slug(n)}")
