"""Dataset 1, completion — snap the polling-centre directory's Arabic onto the
archive's own clean folder-name vocabulary.

The USSD annuaire PDF is born-digital but its embedded font has a defective
ToUnicode map, so extracted Arabic contains swapped letters. The Drive archive's
folder names are clean UTF-8, so they supply the reference vocabulary:

  delegations   <- 2024/Resultats1erTour and 2023/TemplateCandidats2023, which
                   between them name all 279 delegations as "<GG><nn>_<arabic>"
                   under a numbered constituency folder
  imadas        <- 2023/ElecLocPvTour1 (imada level)
  polling centres <- 2024/PvCvPresidentielle24 (centre level)

Matching runs hierarchically: the delegation is resolved within its governorate,
then the imada and polling centre are resolved only within that delegation. A
governorate-wide search over ~4,300 centre names produced confident-looking but
wrong matches between different schools; restricting to the delegation's own
handful of centres removes almost all of that. Anything below the threshold is
left blank rather than guessed, and reported.

Usage: python3 tools/canonicalise_polling_centres.py
"""
import collections, csv, difflib, re, sys, unicodedata

GEO = "inventory/electoral_geography.csv"
SRC = "data/polling_centres_2022.csv"
OUT = "data/polling_centres_2022.csv"
# Per-field similarity floors. Delegations are matched against a small,
# well-formed pool so a low floor is safe; centre names are long and numerous,
# and below ~0.8 the matches stop being trustworthy (different schools scoring
# 0.75 on shared boilerplate like "م إبتدائية"). The score is kept in the output
# so a caller can tighten further.
THRESHOLDS = {"delegation": 0.72, "imada": 0.75, "centre_name": 0.82}

# Orthographic variants that carry no distinction for matching purposes.
FOLD = str.maketrans("أإآىئؤ", "اااييو")


def norm(s):
    s = unicodedata.normalize("NFC", (s or "").strip()).translate(FOLD)
    s = s.replace("ة", "ه").replace("ـ", "")
    return re.sub(r"[\s\-_.]+", "", s)


def best_match(raw, choices, threshold):
    """Closest vocabulary entry to `raw`, or ('', score) if none is close enough."""
    key = norm(raw)
    if not key or not choices:
        return "", 0.0
    best, score = "", 0.0
    for clean, clean_key in choices:
        r = difflib.SequenceMatcher(None, key, clean_key).ratio()
        if r > score:
            best, score = clean, r
    return (best, score) if score >= threshold else ("", score)


def governorate_of(constituency):
    """'01_تونس 1' / '23_صفاقس 1' -> 'تونس' / 'صفاقس'."""
    name = re.sub(r"^[A-Z0-9]+[_-]", "", constituency).strip()
    return re.sub(r"\s*\d+$", "", name).strip()


def build_vocab():
    with open(GEO, encoding="utf-8") as fh:
        geo = list(csv.DictReader(fh))

    delegations = collections.defaultdict(set)   # keyed by governorate
    imadas = collections.defaultdict(set)        # keyed by (governorate, delegation)
    centres = collections.defaultdict(set)       # keyed by (governorate, delegation)

    for r in geo:
        coll = r["collection"]
        if coll in ("2024/Resultats1erTour", "2023/TemplateCandidats2023",
                    "2024/ResultatsFinaux2emeTour", "2023/ElecLocPvTour1"):
            gov = governorate_of(r["constituency"])
            deleg = re.sub(r"^[A-Z]{2}\d+[_-]", "", r["delegation"]).strip()
            if gov and deleg:
                delegations[gov].add(deleg)
                if r["imada"].strip():
                    imadas[(gov, deleg)].add(r["imada"].strip())
        elif coll == "2024/PvCvPresidentielle24":
            gov, deleg = r["governorate"].strip(), r["delegation"].strip()
            if gov and deleg:
                delegations[gov].add(deleg)
                if r["sector"].strip():
                    imadas[(gov, deleg)].add(r["sector"].strip())
                if r["polling_centre"].strip():
                    centres[(gov, deleg)].add(r["polling_centre"].strip())
        elif coll == "2023/ResultatsLocales2023":
            gov = r["governorate"].strip()
            if gov and r["delegation"].strip():
                delegations[gov].add(r["delegation"].strip())

    # Governorate spellings differ across collections by hamza carrier, so key
    # the vocabulary on the normalised form and merge variants together.
    def prep(d):
        merged = collections.defaultdict(set)
        for key, vs in d.items():
            nk = norm(key) if isinstance(key, str) else tuple(norm(k) for k in key)
            merged[nk] |= vs
        return {k: [(v, norm(v)) for v in vs] for k, vs in merged.items()}

    return prep(delegations), prep(imadas), prep(centres)


def main():
    delegations, imadas, centres = build_vocab()
    print(f"vocabulary: {sum(len(v) for v in delegations.values())} delegations, "
          f"{sum(len(v) for v in imadas.values())} imadas, "
          f"{sum(len(v) for v in centres.values())} centres")

    with open(SRC, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    stats = collections.Counter()
    for r in rows:
        gov = norm(r["governorate"])
        deleg, dscore = best_match(r["delegation_ar"], delegations.get(gov, []),
                                   THRESHOLDS["delegation"])
        r["delegation"], r["delegation_score"] = deleg, f"{dscore:.2f}"
        stats["delegation"] += bool(deleg)

        # Imada and centre are only searched inside the resolved delegation.
        scope = (gov, norm(deleg)) if deleg else None
        for raw_col, out_col, vocab in (("imada_ar", "imada", imadas),
                                        ("centre_name_ar", "centre_name", centres)):
            match, score = (best_match(r[raw_col], vocab.get(scope, []), THRESHOLDS[out_col])
                            if scope else ("", 0.0))
            r[out_col] = match
            r[f"{out_col}_score"] = f"{score:.2f}"
            stats[out_col] += bool(match)

    fields = ["governorate", "constituency_ar", "delegation", "imada", "centre_name",
              "centre_name_fr", "ussd_code",
              "delegation_ar", "imada_ar", "centre_name_ar",
              "delegation_score", "imada_score", "centre_name_score", "source_page"]
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    n = len(rows)
    print(f"wrote {n} rows -> {OUT}")
    for col in ("delegation", "imada", "centre_name"):
        print(f"  {col:12s} resolved: {stats[col]:5d}/{n} ({100*stats[col]/n:.1f}%)")
    unresolved = collections.Counter(r["governorate"] for r in rows if not r["delegation"])
    if unresolved:
        print("  delegations unresolved by governorate:", dict(unresolved.most_common(8)))


if __name__ == "__main__":
    main()
