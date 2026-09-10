# Datasets from the ISIE archive

Nine were scoped; eight are built, plus one the scoping did not think possible,
and the 2019 elections — which the archive does not hold at all — recovered from
the ISIE's own report and the Wayback Machine. Read `docs/SOURCE_INVENTORY.md`
first: the archive is 97% empty folders, and that fact shapes everything below.

| # | Dataset | Unit | Rows | Status |
|---|---|---|---|---|
| 1 | Polling-centre directory with USSD codes | polling centre | 4,578 | **built** |
| 2 | Electoral geography gazetteer | geography node | 26,484 | **built** |
| 3 | 2024 presidential sponsorship-form aspirants | aspirant | 45 | **built** |
| 4 | ISIE regulatory corpus | document | 172 | **built** |
| 5 | Local 2023 results (candidates / constituencies) | candidate | 3,475 / 1,715 | **built** |
| 6 | Procurement register | tender | 72 | **built** |
| 7 | ISIE communications timeline | news item | 136 | **built** (titles only) |
| 8 | Polling-station PV index | PV scan | 23,509 | **built** from the live site |
| 9 | Electoral register statistics | constituency | — | **not obtainable** |
| 10 | **Polling-station results, 2024 presidential** | polling bureau | 9,417 with certified votes of 9,448 | **built** |

All built datasets live in `data/` (dataset 2 in `inventory/`), are reproducible
from `tools/`, and are documented field by field in
[`docs/CODEBOOK.md`](CODEBOOK.md).

## What changed once the datasets were actually built

Three things turned out differently from the initial scoping:

**The PV corpus is recoverable after all.** The scoping said datasets 8 and 9
needed re-sourcing. isie.tn is still live, and its procès-verbaux browser
(a `php_file_tree` widget) emits the entire file tree inline — so three page
fetches recover an index of **23,509 PV scans**, with complete national coverage
for the 2024 presidential election (24 governorates, 279 delegations, 5,088
polling centres). The archive's empty skeleton was an accurate map of a corpus
that does exist; it simply was not mirrored. The scans themselves are handwritten
forms, so this is an index, not results data.

**OCR was cheaper than expected, and self-validating.** Tesseract's Arabic model
handles these 200 dpi scans well, and the results decisions print every vote count
twice — in digits and spelled out in words. Parsing the Arabic number words
(`tools/arabic_numerals.py`) gives an independent check on every figure: 91% of
candidate vote counts are word-validated, and the words correct the digits in 1,040
cases. That redundancy is what makes dataset 5 usable rather than indicative.

**Turnout figures remain weak.** They are printed glued to the following Arabic
word ("247ناخبا"), have no spelled-out backup, and OCR truncates them often. Two
OCR passes are reconciled against the ballot identity, but a substantial share
still fails and is flagged rather than silently patched.

**Dataset 9 is genuinely gone.** The registration-statistics page is still served
but its content is empty — 97 characters via the WordPress REST API. The figures
were rendered client-side and are not in the archive, the page, or the API.

---

## Built

### 1. Polling-centre directory with USSD codes — `data/polling_centres_2022.csv`

The strongest single artefact in the archive. `Annuaire-codes-USSD-centres-de-Vote-en-Tunisie.pdf`
(2022) is the only born-digital tabular PDF, and it yields a complete national gazetteer:

- **4,578 rows**, one per polling centre, each with a unique USSD code (1001–5578)
- Columns: governorate / constituency / delegation / imada / centre name (Arabic) /
  centre name (French) / USSD code
- Covers all **24 governorates** and **274 delegations**

Built by `tools/extract_polling_centres.py`. Two extraction problems had to be solved and
one remains:

- *Solved:* Arabic is stored as glyphs in visual order, so cells are rebuilt from raw
  characters sorted right-to-left rather than by reversing pdfplumber's string.
- *Solved:* the embedded font's `ToUnicode` map is defective for some Arabic final forms,
  so short cells come out with swapped letters (`مدنري` for `مدنين`). Governorate names are
  snapped onto a canonical list taken from the archive's own folder names — which are clean
  UTF-8 — giving exactly 24 governorates with 0 unmatched.
- *Open:* the same defect affects delegation, imada and Arabic centre names, which are
  **not** canonicalised. Treat `centre_name_fr` and `ussd_code` as the reliable keys and the
  remaining Arabic columns as needing review. Fixing them properly means either OCR of the
  rendered pages or fuzzy-matching against the folder-name vocabulary from dataset 2.

**Why it matters:** a USSD-coded centre list is the natural join key between any
polling-station results data and administrative geography. It is the spine other datasets
attach to.

### 2. Electoral geography gazetteer — `inventory/electoral_geography.csv`

The empty PV folders are not worthless: their *paths* encode ISIE's official administrative
hierarchy for each election, down to individual polling bureaux. Parsing 26,484 nodes gives
a longitudinal gazetteer:

| Election | Nodes | Deepest level reached |
|---|---|---|
| Législatives 2019 | 7,246 | bureau + document type |
| Présidentielle 2024 | 6,334 | 4,302 distinct polling centres |
| Locales 2023 (T1) | 4,996 | imada → centre → bureau |
| Législatives 2023 (T1) | 4,740 | 3,422 centres, 1,041 bureaux |
| Locales 2024 (T2) | 1,894 | delegation |
| Locales 2023 results | 757 | delegation |
| Locales 2024 (T1) | 306 | delegation |
| Électeurs 2024 | 187 | constituency |
| Conseils locaux 2024 | 24 | governorate |

Because the same places recur across four election cycles under different districting
(2019 constituencies vs. 2023's 161 single-member seats vs. 2024's local councils), this
supports something genuinely hard to get elsewhere: **a crosswalk of Tunisian electoral
geography across the 2011-2021 and post-2022 constitutional orders.** The 2019 and 2023
trees also include the out-of-country constituencies (`الخارج` → country → city).

Two caveats. The Arabic here is clean, which is why it anchors dataset 1. But the
presidential 2024 tree has 23 governorates, not 24 — Tunis is absent — so the mirror is
incomplete, and coverage must be stated per collection rather than assumed national.

---

## The small ones

### 3. 2024 presidential sponsorship-form aspirants

`uploads/2024/07/` holds 45 PDFs, one per person who filed for the 2024 presidential
election. Each is a scanned receipt with a machine-readable overlay carrying the applicant's
name and a file number (observed range 235–880). Names appear in Arabic, one in Latin
script. A row per applicant — name, file number, filing document — is a few hours' work and
covers the full applicant pool, not just the three who reached the ballot.

Alongside them sit `دليل-الترشحات-للانتخابات-الرئاسية-لسنة-2024.pdf` (the candidacy
guide), `قرار-الهيئة-عدد-543-لسنة-2024.pdf` and `محضر-جلسة-4-جويلية-2024.pdf` (a council
session record) — context for how applications were adjudicated.

### 7. ISIE communications timeline

`/actualites/YYYY/MM/DD/<slug>/` survives as folder names even though the article bodies do
not. That gives **134 dated items, 2018–2024** (2018: 29, 2019: 27, 2020: 7, 2021: 18,
2022: 24, 2023: 6, 2024: 23) — slug plus exact date, in French at the root and Arabic under
`/ar/`. Enough for a communications-activity timeline; not enough for text analysis. Bodies
would have to come from the Wayback Machine.

---

## The OCR tier

Nearly all 537 PDFs are ~200 dpi scans with no text layer. Tesseract's Arabic
model handles them well once `OMP_THREAD_LIMIT=1` stops parallel workers
thrashing — about 1 second per page, so the whole tier is minutes, not days.

### 4. ISIE regulatory corpus — 172 documents

289 PDFs sit in dated `uploads/YYYY/MM/` folders spanning 2018–2024 (2018: 3,
2020: 15, 2021: 22, 2022: 80, 2023: 60, 2024: 109). Of these 72 are procurement
(dataset 6) and 45 are sponsorship forms (dataset 3), leaving 172 regulatory
documents: numbered decisions (`قرار عدد N لسنة YYYY`, `Décision n° YYYY-NN`),
campaign-finance guides, polling and counting manuals, candidacy guides, codes of
conduct, and joint decisions with the audiovisual regulator HAICA.

The filenames are structured enough to carry the index on their own — decision
number, year, language and type all parse out without OCR, which is why this one
came in cheaper than scoped. Classification found more than expected: alongside
48 decisions and 34 sets of council minutes there are 9 polling-geography
documents (including a 2023 local-election polling-centre list), 6 statistical
releases on constituency and seat allocation, and 8 campaign-finance ceilings.
16 documents remain unclassified.

### 5. Local elections 2023 results — 3,475 candidate rows

`uploads/2023/ResultatsLocales2023/` holds **145 PDFs**, governorate → delegation,
named `قرار الهيئة لمعتمدية <delegation>__<n>__<governorate>.PDF` (9–12 pages
each): the Instance's formal decisions proclaiming local council results.
`uploads/2024/ResultatsFinaux2emeTour/` adds **103** for the second round, held in
early 2024. All 248 were OCR'd and parsed into 1,715 constituency rows and 3,475
candidate rows.

What makes this dataset trustworthy is a quirk of the source: every vote count is
printed **twice**, in digits and spelled out in Arabic words ("بلسان القلم").
`tools/arabic_numerals.py` parses the words, giving an independent reading of
every figure. 89% of candidate votes are word-validated, and the words correct a
misread digit string in 1,040 cases.

The turnout figures do not have that backup — they are printed glued to the
following Arabic word ("247ناخبا"), which OCR truncates often. Two OCR passes are
reconciled against `valid + spoilt + blank == voters` and `candidate_sum ==
valid`, and rows that still fail are flagged rather than patched. Filter on
`ballot_identity_ok` and `candidate_sum_ok` before using turnout; `candidate_sum`
is the dependable measure of valid votes.

Coverage is partial: the first round spans 15 of 27 constituencies. The manifest
says exactly which delegations are missing.

### 6. Procurement register — 72 tenders

PDFs named `CC-*`, `CAO-*`, `AO-*`, `CONS-*`, `CCTP-*` and `كراس شروط` (cahiers
des charges, tender awards, consultations), 2020–2024: 28 appels d'offres, 25
cahiers des charges, 11 simplified appels d'offres, 7 consultations. Filenames
give reference number, year and procedure. A niche but clean dataset on
electoral-administration spending, and the one collection with steady
year-on-year coverage rather than event-driven gaps.

---

## The two that were not in the archive

The folder skeleton promises these and does not deliver them. One turned out to
be recoverable elsewhere; the other is genuinely gone.

### 8. Polling-station PV index — 23,509 scans, recovered

`PvCvPresidentielle24`, `PvLegTour1`, `ElecLocPvTour1` and `pv-legislative2019`
describe ~23,000 nodes reaching individual bureaux, and every one of those folders
is empty in the archive.

**They are not empty on the live site.** isie.tn still serves the PVs, and its
browser is a `php_file_tree` widget that emits the entire tree inline — so three
page fetches recover the whole index. `tools/build_pv_index.py` yields **23,509
files**: 10,527 for the 2024 presidential election, 12,199 for the 2023 local
first round, 783 for the second round. Coverage for 2024 is complete — 24
governorates, 279 delegations, 5,088 polling centres — better than the archive's
own skeleton, which was missing Tunis.

Each leaf is named for its polling bureau (an 11-digit code such as
`03010110101`), so the index joins to the geography datasets and gives a
per-bureau target list. The files themselves are scans of **handwritten** PV forms
(20,915 JPG, 2,378 PDF). Reading results off them is a much larger undertaking
than the printed decisions in dataset 5, and is not attempted here.

The archive's empty skeleton was, in the end, an accurate map of a corpus that
exists — it simply was not mirrored.

**The scans have since been read — see dataset 10.** A 30-bureau pilot established
that they could be ([`docs/PV_PILOT.md`](PV_PILOT.md), `data/pv_pilot_2024.csv`),
and the corpus was then read offline in full.

### 10. Polling-station results, 2024 presidential — `data/pv_presidential_2024.csv`

The handwritten forms, turned into numbers, with no model API and no hand-labelling
beyond the pilot's 30 forms. What makes it possible is that the PV is an
error-correcting code: the turnout count is written five times and the valid-vote
total twice, so twelve of the twenty fields are determined by the other eight. That
redundancy first lets the corpus label its own digit classifier — 245,748 cells
certified by the forms' arithmetic, against 1,490 labelled by hand — and then
corrects what the classifier still gets wrong.

Each of the form's three accounts — ballots, papers, votes — is published on its
own evidence rather than requiring the whole form, which is what takes candidate
votes to **8,977 of 9,448 (95.0%)** from the reproducible pipeline alone, across
all 24 governorates and every delegation in the corpus. The whole form is published
for 8,056. A further 447 stations, the ones ISIE published at a resolution the
classifier cannot work at, were read off the scans by eye and admitted on the same
arithmetic test, taking candidate votes to **9,417 of 9,448 (99.7%)**;
`reading != "vision"` selects the reproducible subset.

On the pilot's hand-verified forms, every block the reader publishes is correct —
86 of 86, scored with a reader that never saw a pilot form. Against the widely
reported national result, which nothing in the pipeline has access to:

| | Saied | Zammel | Maghzaoui |
|---|---|---|---|
| widely reported national | 90.69% | 7.35% | 1.97% |
| all rows with certified votes (n=9,417) | 91.07% | 6.99% | 1.94% |
| reproducible pipeline only (n=8,977) | 91.11% | 6.96% | 1.93% |
| whole-form rows only (n=8,056) | 91.18% | 6.89% | 1.93% |

That comparison is weaker than it looks and is documented as such: these are
counting records from inside the republic while the reported total includes
out-of-country voting, and the stations still missing are not a random sample. Note
also that the identities constrain the candidate *total* but not the split between
the three candidates, so those three columns rest on the classifier;
`split_corroborated` flags the 7,083 rows where the score written out in words
beside the digits agrees with all three.

**Some of the form's figures were superseded before publication.** 388 bureaux are
filed with a *قرار تصحيح محضر فرز*, a decision naming a field of the counting
record, the value recorded in error, and the value replacing it. All 388 were read;
`data/verification/corrections.jsonl` records the 328 whose table carries anything
and `tools/apply_corrections.py` applies them, only where the error value the
decision names is what the dataset already holds. 29 of them touch a candidate
figure — the class the arithmetic gate cannot catch, since the counting record
closed before the correction and closes again after it. The `correction` column
marks the 51 rows a decision changed and the 19 whose published figures a decision
supersedes without being reconcilable with them.

Every published scan has been opened. The 31 stations still without certified
votes are a closed list with a reason recorded for each in
`data/verification/unreadable_scans.jsonl`: 9 whose bundle contains no counting
record, 8 whose scan is cut off mid-table, 4 below any readable resolution or
contrast, and 3 that are legible and read but whose candidates do not sum to the
total the form itself states. Method, validation and the negative results in
[`docs/PV_OFFLINE_READING.md`](PV_OFFLINE_READING.md).

### 9. Electoral register statistics — not obtainable

`/statistiques-dinscription/` is still live, but its content is now empty: 97
characters via the WordPress REST API, with the figures previously rendered
client-side. `/electeurs/` and `ListesElecteurs06Juillet2024` (187 nodes,
constituency-level, coded `1501_القصرين الجنوبية - حاسي الفريد`) are shells in the
archive. Neither the archive, the live page, nor the API has the numbers. The
constituency codes remain a useful join key if the figures are ever obtained from
ISIE directly.

---

### 11. Administrative geography, Latin-script — three files

Two files supplied outside the archive: the **official 2024 INS delegation list**
(264 rows, with INS, merged, SALB/UN and 1984 codes plus a centroid each) and a
hand-built **historical locality file** (1,276 rows carrying colonial-era source
names and the caïdats, contrôles civils and 1956 delegations they sat in). Both
are committed verbatim under `data/sources/`.

They share no join key. `id_2024` in the locality file reads like a 2024
delegation code but is a row index running 1–1278 — only 28 of 1,276 values
happen to equal an `id_delegation` — `id_geonames` is a local sequence rather
than a GeoNames id, and `id_census` keys the source census table. Names and
coordinates are the only link, so the naming had to be made coherent before
anything could be joined to it.

`tools/build_geo_crosswalk.py` produces `data/delegations_ins.csv`,
`data/hist_localities.csv` and `data/hist_unit_crosswalk.csv`;
`tools/audit_locality_names.py` checks twelve invariants over them and exits
non-zero on a violation.

What coherence needed. Neither file's house style was rewritten to the other's —
the locality file hyphenates, the INS list uses spaces — and both gained a folded
`name_key` (`tools/latin_names.py`) that makes a place resolve across them, with
0 collisions across the 263 distinct INS delegation names. Fixed in place: 31
untrimmed cells, three coordinate sources written eight ways, the `Délégation de`
title on 49 cells (until it was removed, none of the 1956 delegation names
matched anything), and 10 spelling variants. `city_name_sources` is a verbatim
quotation from a census or gazetteer and is byte-identical to the upload; no row
was deleted, because a row is a source observation.

1,264 of 1,276 localities (99.1%) now carry a modern delegation or governorate,
each with the method and distances that justified it rather than a confidence
score — the fallback cannot be self-calibrated, since the only subset with an
independent answer is delegation seats, which sit on centroids by construction.
Two negative results worth keeping: a nearest/second-nearest **margin guard is
the wrong guard** (it would withhold 14 correct assignments and still admit the
one real error), and **fuzzy matching alone is unsafe** on the historical unit
names — at a 0.70 cutoff it files a Gafsa-steppe tribal confederation onto a
Nabeul beach town. All 70 historical names are therefore decided individually,
with ten marked as having no modern counterpart rather than forced onto a match.

Full column-by-column detail in `docs/CODEBOOK.md` §10–13.

### 12. The Arabic-Latin bridge — `data/delegation_crosswalk.csv`

The election data names every place in Arabic and carries no code but
`bureau_code`; the INS list names the same delegations in French with official
codes. Nothing joined them, and the repo had no way to compare the two scripts:
its four existing folds all match Arabic against Arabic. `tools/arabic_latin.py`
adds the missing capability and `tools/bridge_delegations.py` applies it, giving
**279 ISIE delegation units mapped onto all 264 official delegations**, plus a
per-station map (`data/pv_delegation_map.csv`) that gives each of the 9,448
stations an INS code. `data/pv_presidential_2024.csv` is untouched.

Matching reduces both scripts to consonant skeletons — Arabic writes consonants
and long vowels, French writes every vowel, and vowels are where transliteration
is least predictable, so `سوسة` and `Sousse` both become `sws`. Compass suffixes
are the exception and go through a lexicon instead: `بنزرت الشمالية` is
`Bizerte Nord`, and transliterating الشمالية resembles `Sud` as much as `Nord`,
so the first prototype confidently returned the wrong half of north/south pairs.

The check that matters is the bijection — every official delegation claimed by
exactly one ISIE unit, none claimed twice — because a cross-script matcher fails
by pairing names that merely look alike, and that always surfaces as one
delegation claimed twice while another goes unclaimed. It caught three real bugs,
including folding ق, غ and ك into one class, which made `Agareb` and `Ghraiba`
identical skeletons and lost two Sfax delegations. 226 of the 264 matches are
independently corroborated by the French centre names in
`polling_centres_2022.csv`, with no contradictions.

**Two findings about ISIE's own data.** Its `bureau_code` turns out to carry a
delegation code in its first four digits — not INS codes, which is why comparing
them to `id_delegation` finds nothing, and why this repo had recorded the code as
undecomposable. And that code contradicts ISIE's folder tree in one place: the
tree nests Ben Guerdane and Beni Khedech *inside* Djerba Ajim
(`.../مدنين/جربة أجيم/بنقردان/...`), which is why Djerba Ajim carried 135
stations against Djerba Midoun's 55 and why two delegations appeared to be
missing from a dataset covering every station in the country. 110 stations are
corrected by code, with the `sector` column corroborating.

15 ISIE units (184 stations, 1.9%) have no counterpart in this INS list and are
left unmatched rather than forced onto a neighbour.

Detail in `docs/CODEBOOK.md` §14–16.

### 13. Candidate margins and maps — `data/station_margins.csv`, `maps/`

Each candidate's share and margin at station, imada and delegation level, plus
474 figures and the joined geometry as GeoJSON. The figures are grouped by
family in `maps/{national,cartograms,surfaces,comparative,levels,zoom,micro}/`,
one folder per producing tool. Built by `tools/build_margins.py` and the six
`tools/make_*.py` renderers, checked by `tools/audit_margins.py`.

This became possible because of the delegation bridge above: `adm3_pcode` in the
OCHA/HDX COD-AB boundary set is `TN` + the INS `id_delegation`, so the delegation
join is **by code, 264 for 264, with nothing fuzzy in it** — which also
corroborates that bridge from a direction it was not built against. Below the
delegation, admin4 supplies 2,084 imadas with Arabic names, and 99.6% of stations
resolve into 2,042 of them by name inside their own delegation. The 184 stations
that previously carried no delegation are now all placed, by matching their sector
name to an imada elsewhere in the governorate and taking that imada's parent.

Summing the station table reproduces the published national figures exactly —
2,303,043 / 176,525 / 47,847 = 2,527,415, shares 91.12 / 6.98 / 1.89 — which is
the end-to-end check on the whole chain.

**The audit measures geography, not just arithmetic.** A name-based join can
scramble which unit gets which result while every total still adds up. So the
audit computes how much of the variance in Saied's share the parent unit explains
and compares it against a shuffle of the same values: 44.7% against 8.6% at
delegation level, 62.1% against 12.3% at imada level. The finer level is *more*
coherent, which is what correct nesting predicts; permuting whole result blocks
drops it to 13.4% and the check fires.

Two caveats live in `maps/README.md` and matter more than the styling: these are
equal-area maps, and **the ten largest delegations are 40.6% of the map but 2.29%
of the votes**, so the pale southern desert is visually dominant and electorally
almost weightless; and **two scales are published as a pair**. Everything
outside `maps/fitted/` runs on one fixed 0–100% scale, so a shade means the same
number on every figure in the directory, at the price that most maps read flat —
99.6% of delegations fall in one seventh of the range for Maghzaoui. `fitted/`
holds the same maps with the ramp over each one's own range, which recovers the
geography at the price that a shade means nothing elsewhere. The gain rises with
how coarse the units are: 23.5× for the region-level margin rollups, 6.8× for
Maghzaoui at delegation level, 1.3× for turnout at imada level and a slight loss
for the imada margin. Each figure carries the other's name.

Detail in `docs/CODEBOOK.md` §17–18.

### 14. Spatial clusters — `data/{delegation,imada}_clusters.csv`, `maps/clusters/`

Where each candidate's support is clustered beyond chance, and what the
electoral regions look like when the administrative ones are ignored. Built by
`tools/make_clusters.py`, checked by `tools/audit_clusters.py`.

This is the only part of the repo that attaches a **null model**. Everything
else describes where a value is, and a choropleth of pure noise still looks
patchy — so a spatial claim was a description, not a finding. Local Moran's I
and Getis-Ord Gi* against 9,999 conditional permutations, corrected across all
2,042 simultaneous tests with Benjamini-Hochberg.

Two results stand out. At delegation level the only significant cluster in the
country is the Tunis metropolitan core, and the candidates' maps nest rather
than standing apart: Saied's eight low-among-low delegations are a strict subset
of Zammel's nine high-among-high, which is the arithmetic of a 91% result.
Maghzaoui's is a separate, real cluster in the Kebili and Gafsa oases.

And **six contiguity-constrained electoral regions explain more of the vote than
all twenty-four governorates** (R² 0.670 against 0.457 at delegation level;
0.482 against 0.302 at imada). Ward maximises that criterion by construction, so
only the size of the gap is informative — but administrative geography is
measurably a poor container for this vote.

Two methodological cautions are recorded because they changed the answer: at
999 permutations two of the six candidate-level analyses reported *zero*
significant units, a false negative manufactured entirely by the p-value floor;
and under conditional permutation LISA and Gi* are the same test, so the two
figure families are one piece of evidence drawn two ways, not two.

Detail in `docs/CODEBOOK.md` §19.

### 15. Turnout — repaired, and mapped — `maps/turnout/`

Turnout at station, imada, delegation, governorate and region level, plus how
much of each unit the figure actually rests on. Built by `tools/make_turnout.py`
from columns that `tools/build_margins.py` now computes correctly, checked by
`tools/audit_turnout.py`.

**The published turnout column was wrong in three ways and none of them showed
in the national figure.** A dropped quality gate let 40 stations publish
impossible turnout, the worst at 13,133%. The aggregates summed numerator and
denominator over different stations, so 167 of 264 delegations reported a ratio
that was nobody's turnout — Houmt Souk read 1.1% against 17.3% on the matched
subset. And four PV rows carried a flag their own columns refuted. Mapping the
column as it stood would have drawn a turnout collapse across the south that
does not exist.

This is also the one quantity here that rests on an **uncertified** field. The
registered count appears in none of the form's identities, so turnout is a
certified numerator over an uncertified denominator, and coverage is published
alongside every figure because the gaps are structured rather than random.

Two findings: turnout and Saied's share are essentially uncorrelated (r = +0.058
across stations), so he did not do better where turnout collapsed; and
participation is *less* spatially clustered than vote choice.

Item 4 below — "tighten the turnout figures" — is partly answered by this: the
basis is now correct and checkable. What remains is coverage, which needs OCR
work rather than arithmetic.

Detail in `docs/CODEBOOK.md` §20.

---

## The 2019 elections

Nothing above touches 2019, and the archive is the reason: `pv-legislative2019`
is 7,246 folders and **zero files**, the largest single collection in the mirror
and the emptiest. The live site is no better. `الانتخابات التشريعية 2019` renders
"هذه الصفحة قيد الإنشاء" — this page is under construction. The pages that once
carried the results (`2019-نتائج-الانتخابات-التشريعية`, and one "بطاقة كشف
النتائج" post per governorate for each of the three ballots) still exist, but the
posts they link to 404 and the WordPress REST API returns no posts dated 2019 at
all. Every results PDF the media library still lists under `uploads/2019/09/`,
`/10/` and `/11/` is a dead link on the server.

Two things survive, and between them they carry the 2019 results:

**The ISIE's own report on the elections**, `تقرير-الانتخابات-الرئاسية-والتشريعية-لسنة-2019.pdf`
— 576 pages, re-uploaded to `uploads/2026/01/` and served today. It is the one
substantial document in this project with a real text layer, and it holds round
one by constituency, all three national result tables and the seat allocation.

**The Wayback Machine**, for the one table the report has only as page images:
the final legislative results by list, captured on 22 December 2019, three weeks
before the URL went dead.

### 16. Presidential 2019 — `data/presidential_2019_r1_constituency.csv`, `data/presidential_2019_national.csv`

858 rows: 26 candidates in each of the 33 constituencies, votes and share, from
the report's annex 7. Plus 52 national rows — the same candidates at three
stages (round one preliminary, round one final, the run-off), each vote count
printed twice, in digits and in Arabic words.

It is unusually well corroborated for a dataset in this repository, because the
report states the same numbers in four places and they agree. Every annex-7 page
sums to the total printed on it. The 33 constituency figures for each candidate
sum to that candidate's national total, for all 26. The 858 counts together sum
to 3,372,973 — the round-one valid-vote total stated on the preceding page. And
50 of the 52 national counts are confirmed by their own spelled-out form.

Two defects in the source are visible in the output rather than smoothed away.
The round-one **final** national table omits a candidate — محمد لطفي المرايحي and
his 221,190 votes are in the preliminary table, in the chart and in all 33 annex
pages, and simply absent here; the preliminary table omits a different one, عمر
منصور. Both gaps are exactly the size of the missing candidate's total, which is
how they were caught. And one spelled-out figure drops the word "ألفا", so its
words read 1,190 where its digits — corroborated by the constituency sum — read
239,951.

### 17. Legislative 2019, by list — `data/legislative_2019_list_results.csv`

The table the 2019 election is usually asked for: every candidate list's vote
count and share in every constituency. **1,492 rows across all 33
constituencies, carrying 2,843,466 votes — 99.06% of the national valid vote.**
This one is a scan, so it is OCR, and the approach is the cell-level one dataset
10 arrived at for the PVs rather than whole-page OCR — Tesseract reads these
Arabic list names well and the Latin digits beside them badly, and a
right-to-left table interleaves the two.

The grid is found without a single per-page constant. The vertical rules are
faint and the scans skewed, so no column is dark down the whole page; within one
row band the skew is nothing and a rule is the only thing spanning the band's
full height. Half a degree of scanner skew defeats even that, so each page is
first rotated by the angle that recovers the most rows. Together that reads all
55 pages, including the three where a first attempt found no table at all.

Each constituency then checks itself three ways: ranks 1..N with no gap, votes
summing to the total the table prints in its own last row, and every printed
share matching the share recomputed from votes and that total. The third check
is the one that catches OCR — a misread digit moves a share past the rounding
tolerance — so a validated row has had its vote count confirmed by a number
printed elsewhere on the page. **1,469 of 1,492 rows (98.5%) pass it**, and 18
of the 33 constituencies reproduce their printed total exactly. The other 15 are
short by one or two rows each — a band the rule-finder missed, never a row read
wrongly and kept — and every row carries the flags to see which.

Two things the source itself says. Its 33 printed totals come to 2,858,187,
which is **12,127 short of the 2,870,314 the report states as the national valid
vote** — a gap between two figures ISIE published, not one this pipeline
introduced, and the per-constituency shares corroborate the totals as printed.
And the list names have no backup of any kind: they are Arabic OCR of a 2019
scan, so join on constituency and rank, which the table's own numbering fixes.

### 18. Legislative 2019, seats — `data/legislative_2019_seats.csv`, `data/legislative_2019_constituency_seats.csv`

31 lists won the 217 seats; both the party breakdown and the men/women split by
constituency (164 / 53) come from the report's text and reproduce its own
printed totals.

### 19. 2019 turnout — `data/elections_2019_turnout.csv`

Three rows, one per contest: registered, voters, valid, spoilt, blank. The two
presidential rounds satisfy the ballot identity exactly. The legislative row does
not — its figures fall 207 short of its own stated turnout — and the gap is
recorded rather than adjusted.

Detail in `docs/CODEBOOK.md` §21–24.

## Where to go next

1. **Raise PV coverage past 87%.** 1,184 stations remain, and most of them have
   all twenty fields located — the cells are found and read wrongly, so the lever
   is per-cell accuracy rather than the locator. Only 73 scans yield no field map
   at all. ISIE has no better copy: files fetched back are byte-identical to those
   already held.
2. **Close the last 1% of the 2019 list results.** 15 of the 33 constituencies
   fall one or two rows short of their printed total, and the failure is always
   a row band the rule-finder did not see rather than a row read wrongly. The
   printed total and the rank sequence say exactly how many rows are missing and
   roughly where, so a second pass could search those pages at a finer band
   threshold instead of re-reading all 55.
3. **Fill dataset 5's gaps.** 15 of 27 constituencies. The live site may carry the
   rest, the same way it carried the PVs.
4. **Tighten the turnout figures.** A third OCR pass, or targeted re-reads of the
   flagged rows, would lift `ballot_identity_ok` well above its current rate.
5. **Join the geography — done at delegation level, open below it.** All 264
   official delegations now carry Arabic names, ISIE codes and INS codes, and
   every one of the 9,448 stations maps to one. The same bridge has not been run
   on the levels beneath: 1,874 Arabic `sector` (imada) values and 4,914
   `polling_centre` values, against `polling_centres_2022.csv`'s Arabic `imada`
   and its French `centre_name_fr`. `tools/arabic_latin.py` is the machinery, and
   `ussd_code` is a candidate key — but the delegation vocabulary was 264 names
   scoped ~11 at a time, while imadas are 1,874 scoped in the dozens, so the
   thresholds and the corroboration channel both need re-measuring rather than
   reusing. `data/hist_localities.csv`'s 1,276 Latin localities are the third
   corner of that join.
6. **Attach real boundaries.** Every locality is currently placed by nearest
   centroid, which is a point rather than a polygon; `id_delegation_salb_un`
   (`TUN0NNNNN`) is exactly the key SALB boundary files use, so a point-in-polygon
   pass would replace the distance columns with a definite answer.
