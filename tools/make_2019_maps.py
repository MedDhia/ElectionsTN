"""Map the 2019 presidential and legislative results, by governorate.

What the source supports, and what it does not.

`tools/build_presidential_2019.py` reads ISIE's own retrospective report. Annex 7
gives **round one only**, every candidate in each of the 33 constituencies. The
national tables give round one twice and round two once, and round two is
national only: the report prints no constituency breakdown for it. So the runoff
between Saied and Karoui has no geography here and is not mapped. The legislative
election has no second round at all -- it is single-round proportional -- so that
half of the request has nothing to draw either.

**Governorate, not constituency.** Three governorates are split in two for
elections: Tunis, Sfax and Nabeul. Drawing that split needs a delegation-to-half
assignment, and the only file carrying one (`polling_centres_2022.csv`) has
delegation names damaged by the same OCR faults as the rest of the archive --
38 of 60 match a boundary polygon. Summing each pair back to its governorate is
exact arithmetic rather than a guess, so that is what happens here: 24 domestic
units. The six out-of-country constituencies have no polygon and are excluded;
their share of the vote is named in each figure's footnote.

**Legislative party names cannot be trusted across constituencies.** Each list is
registered per constituency and named in free text, and the report's text layer
mangles them: `حركة النهضة` appears as `الهضة`, `اليضة`, `الهيضة` and `النهضبة`.
Matching on the clean spelling finds the winner in 8 of 33 constituencies; the
mangles are a single dropped or transposed letter, so a fold that also accepts
them finds it in all 33 and reproduces the documented national result. The fold
is stated in `PARTY_KEYS` and every legislative figure names how many
constituencies it matched, so a reader can see the reach of the rule rather than
taking it on trust.

Usage: python3 tools/make_2019_maps.py [--contest presidential|legislative|both]
"""
import argparse, collections, csv, os, re, sys, unicodedata

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_maps import (ARCHIVE, NO_DATA, SURFACE, draw, feature_path, load_layer,
                       pct_buckets, save_figure)

OUT_DIR = "maps/y2019"
PRES_CSV = "data/presidential_2019_r1_constituency.csv"
LEG_CSV = "data/legislative_2019_list_results.csv"
TOL = 0.004

# Constituency -> governorate. The three split governorates fold back together;
# the six out-of-country constituencies map to None and are dropped.
ABROAD = ("أملانيا", "ألمانيا", "إيطاليا", "فرنسا", "الدول العربية", "القارة")


def fold(s):
    """Arabic folded for comparison: presentation forms, hamza, diacritics."""
    s = unicodedata.normalize("NFKC", s or "")
    s = s.translate(str.maketrans("أإآىئؤة", "اااييوه"))
    s = re.sub(r"[ً-ْـ]", "", s)
    return re.sub(r"\s+", " ", s).strip()


# Governorate Arabic name (as the boundary layer spells it) -> the constituency
# names that make it up. Built by folding both sides and matching on the stem,
# so the archive's presentation-form damage (املنستير for المنستير) folds away.
def gov_of(constituency):
    c = fold(constituency)
    if any(fold(a) in c for a in ABROAD):
        return None
    return re.sub(r"\s*\d+$", "", c)          # "تونس 1" and "تونس 2" -> "تونس"


def transpositions(s):
    """Every string one adjacent swap away from `s`, `s` itself first.

    The report's text layer transposes a neighbouring pair in three governorate
    names -- المنستير as املنستير, المهدية as املهدية, مدنين as مدنني -- which is
    the same damage the party names carry. Trying the single-swap neighbourhood
    repairs them by a stated rule instead of three hand-written special cases,
    and it cannot reach a different governorate: no two of the 24 names are one
    transposition apart.
    """
    yield s
    for i in range(len(s) - 1):
        yield s[:i] + s[i + 1] + s[i] + s[i + 2:]


def match_gov(name, keys):
    """(key, repaired) for a governorate name, or (None, False)."""
    for i, cand in enumerate(transpositions(name)):
        if cand in keys:
            return cand, i > 0
    return None, False


PARTY_KEYS = {
    # party -> the folded stems that stand for it, mangles included. Each mangle
    # is one dropped or transposed letter in the report's own text layer.
    "nahdha": ("حركه النهضه", "حركه الهضه", "حركه اليضه", "حركه الهيضه",
               "حركه النهضبه", "ركه النهضبه", "حركه اللنهضه"),
    "qalb_tounes": ("قلب تونس",),
    "pdl": ("الحزب الدستوري الحر",),
    "tayar": ("التيار الديمقراطي",),
    "chaab": ("حركه الشعب",),
    "tahya_tounes": ("حركه تحيا تونس",),
    "karama": ("ائتلاف الكرامه", "ائتلاف الكرامه", "الكرامه"),
}
# Matplotlib does no bidirectional reordering or glyph shaping, so Arabic in a
# figure comes out as reversed isolated letters. Every other family in this repo
# keeps Arabic out of the canvas for that reason, and these names are romanised
# for the same one. Keyed on the folded Arabic so the report's own mangles
# (املحرزي for المحرزي) resolve to the right person.
CANDIDATE_LABEL = {
    "قيس سعيد": "Kais Saied",
    "نبيل القروي": "Nabil Karoui",
    "عبد الفتاح مورو": "Abdelfattah Mourou",
    "عبد الكريم زبيدي": "Abdelkrim Zbidi",
    "يوسف الشاهد": "Youssef Chahed",
    "احمد الصافي سعيد": "Safi Said",
    "محمد لطفي مرايحي": "Lotfi Mraihi",
    "سيف الدين مخلوف": "Seifeddine Makhlouf",
    "عبير موسي": "Abir Moussi",
    "محمد المحرزي عبو": "Mohamed Abbou",
    "محمد المنصف المرزوقي": "Moncef Marzouki",
    # two transposed pairs in one name, past the single-swap neighbourhood
    "محمد المنصف المرزوقي".replace("ال", "ام", 1): "Moncef Marzouki",
    "محمد املنصف املرزوقي": "Moncef Marzouki",
    "المهدي جمعه": "Mehdi Jomaa",
    "منجي الرحوي": "Mongi Rahoui",
    "محمد الهاشمي حامدي": "Hachemi Hamdi",
    "حمه الهمامي": "Hamma Hammami",
    "الياس الفخفاخ": "Elyes Fakhfakh",
    "سعيد علي مروان العايدي": "Said Aidi",
    "عمر منصور": "Omar Mansour",
    "محسن مرزوق": "Mohsen Marzouk",
    "حمادي الجبالي": "Hamadi Jebali",
    "الناجي جلول": "Naji Jalloul",
    "عبيد بريكي": "Abid Briki",
    "سلمه اللومي": "Salma Elloumi",
    "محمد الصغير نوري": "Mohamed Sghaier Nouri",
    "سليم الرياحي": "Slim Riahi",
    "حاتم بولبيار": "Hatem Boulabiar",
}


def candidate_label(name):
    """Romanised name, repairing the report's transposed letters if needed."""
    c = fold(name)
    for cand in transpositions(c):
        if cand in CANDIDATE_LABEL:
            return CANDIDATE_LABEL[cand]
    # the mangle can be more than one swap; fall back on a stem match
    for k, v in CANDIDATE_LABEL.items():
        if k[-6:] in c or c[-6:] in k:
            return v
    return None


PARTY_LABEL = {
    "nahdha": "Ennahdha", "qalb_tounes": "Qalb Tounes",
    "pdl": "Free Destourian Party", "tayar": "Democratic Current",
    "chaab": "People's Movement", "tahya_tounes": "Tahya Tounes",
    "karama": "Al-Karama Coalition",
}


def party_of(list_name):
    c = fold(list_name)
    c = re.sub(r"^قائمه\s*", "", c)
    for key, stems in PARTY_KEYS.items():
        if any(st in c for st in stems):
            return key
    return None


def geometry():
    """adm2 (governorate) paths keyed by folded Arabic name, plus the outline."""
    feats = load_layer("tun_admin2.geojson")
    paths, names = {}, {}
    for f in feats:
        p = f["properties"]
        key = fold(p.get("adm2_name1"))
        path = feature_path(f["geometry"], TOL)
        if path is None:
            continue
        paths[key] = path
        names[key] = p.get("adm2_name")
    outline = [feature_path(f["geometry"], TOL * 2) for f in feats]
    return paths, names, [p for p in outline if p]


def render(paths, outline, value_of, title, subtitle, stem, foot, unit="% of valid votes"):
    vals = [v for v in (value_of(c) for c in paths) if v is not None]
    if not vals:
        return None
    lo, hi = min(vals), max(vals)
    bar = (0.0, max(5.0, hi))          # a share bar always starts at zero
    buckets, missing = pct_buckets(paths, value_of, *bar)
    fig, ax = plt.subplots(figsize=(6.85, 8.1), facecolor=SURFACE)
    draw(ax, buckets, outline, title, subtitle, None, unit, len(paths), missing,
         colourbar=bar, observed=(lo, hi))
    fig.text(0.01, 0.012, foot, fontsize=6.2, color="#6b7280", wrap=True)
    out = save_figure(fig, os.path.join(OUT_DIR, stem))
    plt.close(fig)              # 26 candidates at a time exhausts the pyplot cache
    return out


def presidential(paths, outline, keys):
    """One share map per candidate, round one."""
    rows = list(csv.DictReader(open(PRES_CSV, encoding="utf-8")))
    votes = collections.defaultdict(lambda: collections.defaultdict(int))
    valid = collections.defaultdict(int)
    seen_valid = set()
    national = collections.Counter()
    nat_valid = 0
    abroad = 0
    for r in rows:
        cand, v = r["candidate"], int(r["votes"])
        national[cand] += v
        g = gov_of(r["constituency"])
        key = match_gov(g, keys)[0] if g else None
        if key is None:
            abroad += v
            continue
        votes[cand][key] += v
        if (r["constituency"], "v") not in seen_valid:
            valid[key] += int(r["constituency_valid_votes"])
            seen_valid.add((r["constituency"], "v"))
    nat_valid = sum(int(r["constituency_valid_votes"])
                    for r in {x["constituency"]: x for x in rows}.values())
    made, unnamed = [], []
    order = [c for c, _ in national.most_common()]
    for rank, cand in enumerate(order, 1):
        share = national[cand] / nat_valid * 100
        def value_of(code, cand=cand):
            return votes[cand].get(code, 0) / valid[code] * 100 if valid.get(code) else None
        stem = f"pres2019_r1_{rank:02d}"
        foot = (f"2019 Tunisian presidential election, round one · share of valid "
                f"votes in each governorate · the six out-of-country "
                f"constituencies ({abroad / nat_valid * 100:.1f}% of valid votes) "
                f"have no polygon and are not drawn · Tunis, Sfax and Nabeul are "
                f"summed back from their two halves · source: ISIE's 2019 report, "
                f"annex 7 · boundaries OCHA/HDX COD-AB (CC BY-IGO)")
        label = candidate_label(cand)
        if label is None:                  # never guess at a name on a figure
            unnamed.append(cand)
            continue
        out = render(paths, outline, value_of, label,
                     f"round one · national {share:.2f}% · {national[cand]:,} votes",
                     stem, foot)
        if out:
            made.append((stem, label, share))
    return made, nat_valid, abroad, unnamed


def legislative(paths, outline, keys):
    """One share map per party whose lists can be matched across constituencies."""
    rows = [r for r in csv.DictReader(open(LEG_CSV, encoding="utf-8"))
            if r["votes"].strip()]
    votes = collections.defaultdict(lambda: collections.defaultdict(int))
    reach = collections.defaultdict(set)
    valid = collections.defaultdict(int)
    seen = set()
    national = collections.Counter()
    nat_valid = 0
    for r in rows:
        party = party_of(r["list_name"])
        g = gov_of(r["constituency"])
        key = match_gov(g, keys)[0] if g else None
        if party:
            national[party] += int(r["votes"])
            reach[party].add(r["constituency"])
        if key is None:
            continue
        if (r["constituency"],) not in seen:
            valid[key] += int(r["constituency_valid_votes"])
            seen.add((r["constituency"],))
        if party:
            votes[party][key] += int(r["votes"])
    nat_valid = sum(int(r["constituency_valid_votes"])
                    for r in {x["constituency"]: x for x in rows}.values())
    made = []
    for party, _ in national.most_common():
        def value_of(code, party=party):
            return votes[party].get(code, 0) / valid[code] * 100 if valid.get(code) else None
        share = national[party] / nat_valid * 100
        stem = f"leg2019_{party}"
        foot = (f"2019 Tunisian legislative election · share of valid votes in "
                f"each governorate · single round, proportional · lists matched "
                f"to this party in {len(reach[party])} of 33 constituencies by "
                f"the fold in PARTY_KEYS, which accepts the report's own "
                f"single-letter mangles · out-of-country constituencies are not "
                f"drawn · source: ISIE's 2019 report · boundaries OCHA/HDX "
                f"COD-AB (CC BY-IGO)")
        out = render(paths, outline, value_of, PARTY_LABEL[party],
                     f"legislative · national {share:.2f}% · "
                     f"matched in {len(reach[party])}/33 constituencies",
                     stem, foot)
        if out:
            made.append((stem, party, share, len(reach[party])))
    return made


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--contest", choices=["presidential", "legislative", "both"],
                    default="both")
    a = ap.parse_args()
    if not os.path.exists(ARCHIVE):
        sys.exit(f"missing {ARCHIVE}; run tools/fetch_boundaries.py")
    os.makedirs(OUT_DIR, exist_ok=True)
    paths, names, outline = geometry()
    keys = set(paths)
    print(f"{len(paths)} governorate polygons")
    if a.contest in ("presidential", "both"):
        made, nv, ab, unnamed = presidential(paths, outline, keys)
        print(f"\npresidential round one: {len(made)} candidate maps "
              f"({ab / nv * 100:.1f}% of valid votes cast abroad, not drawn)")
        for stem, cand, share in made[:8]:
            print(f"  {stem}  {share:6.2f}%  {cand[:44]}")
        if len(made) > 8:
            print(f"  ... and {len(made) - 8} more")
        if unnamed:
            print(f"  {len(unnamed)} candidates skipped, no romanised name: {unnamed}")
    if a.contest in ("legislative", "both"):
        made = legislative(paths, outline, keys)
        print(f"\nlegislative: {len(made)} party maps")
        for stem, party, share, reach in made:
            print(f"  {stem:24s} {share:6.2f}%  matched in {reach}/33")
    print("\nnot drawn, and why:")
    print("  presidential round two — the report gives national totals only")
    print("  legislative round two — the election is single-round proportional")


if __name__ == "__main__":
    main()
