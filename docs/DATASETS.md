# Datasets we can build from the ISIE archive

Nine candidate datasets, grouped by what it actually costs to produce them. Read
`docs/SOURCE_INVENTORY.md` first — the archive is 97% empty folders, and that fact drives
most of the ranking below.

Effort is rough: **S** = hours, **M** = days, **L** = weeks or needs re-sourcing.

| # | Dataset | Unit | Rows (est.) | Effort | Status |
|---|---|---|---|---|---|
| 1 | Polling-centre directory with USSD codes | polling centre | 4,578 | S | **built** |
| 2 | Electoral geography gazetteer | geography node | 26,484 | S | **built** |
| 3 | 2024 presidential candidacy applicants | applicant | 45 | S | ready |
| 4 | ISIE regulatory corpus (decisions & guides) | document | ~174 | M | needs OCR |
| 5 | Local elections 2023 results decisions | delegation | ~248 | M | needs OCR |
| 6 | Procurement / tender register | tender | 70 | M | needs OCR |
| 7 | ISIE communications timeline | news item | 134 | S | partial |
| 8 | Polling-station-level results panel | polling station | ~50,000 | L | **not in archive** |
| 9 | Electoral register statistics | constituency | ~280 | L | **not in archive** |

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

## Ready, small

### 3. 2024 presidential candidacy applicants

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

## Needs Arabic OCR

The 537 PDFs are ~200 DPI RGB scans with no text layer. Quality is good enough for OCR, but
Arabic OCR on scanned administrative tables is the real cost in every dataset below. Budget
for a human validation pass — these are legal and results documents where digit errors
matter.

### 4. ISIE regulatory corpus

289 PDFs sit in dated `uploads/YYYY/MM/` folders spanning 2018–2024 (2018: 3, 2020: 15,
2021: 22, 2022: 80, 2023: 60, 2024: 109). Of these, 70 are procurement (dataset 6) and 45
are candidacy receipts (dataset 3), leaving ~174 regulatory documents: numbered decisions
(`قرار عدد N لسنة YYYY`, `Décision n° YYYY-NN`), campaign-finance guides, polling and
counting manuals, candidacy guides, and joint decisions with the audiovisual regulator
HAICA. Filenames alone already yield decision number, year and language — a usable index
without any OCR. Full text would give a corpus of Tunisia's electoral administrative law
across three constitutional periods.

### 5. Local elections 2023 results decisions

`uploads/2023/ResultatsLocales2023/` is the largest collection with real files: **145 PDFs**
organised governorate → delegation, named
`قرار الهيئة لمعتمدية <delegation>__<n>__<governorate>.PDF` (9–12 pages each). These are the
Instance's formal decisions proclaiming local council results. `2024/ResultatsFinaux2emeTour/`
adds **103 more** for the second round, organised by numbered constituency
(`03_بن عروس/BA02_المحمدية/`). Together ~248 delegation-level results documents — the only
actual *results* content in the archive. OCR would yield candidate names, vote counts and
turnout per delegation for the 2023 local elections.

Note the gap: 145 + 103 documents against 306 constituencies. Coverage is partial, and the
manifest lets you say exactly which delegations are missing before committing to OCR.

### 6. Procurement / tender register

70 PDFs named `CC-*`, `CAO-*`, `AO-*`, `CONS-*` (cahiers des charges, tender awards,
consultations), 2021–2024. Filenames give reference number, year and type. OCR would add
subject, budget and award. A niche but clean dataset on electoral-administration spending —
and the one collection with steady year-on-year coverage rather than event-driven gaps.

---

## Not in the archive — re-sourcing required

These are the datasets the folder structure *promises* and does not deliver. Listing them
matters, because the skeleton is detailed enough to make them look available.

### 8. Polling-station-level results panel

The prize, and it is absent. `PvCvPresidentielle24`, `PvLegTour1`, `ElecLocPvTour1` and
`pv-legislative2019` describe ~23,000 nodes reaching individual bureaux — including
document-type leaves like `قرار تصحيح 03041020105`, whose numeric suffix looks like a
bureau identifier. Every one of those folders is empty. Building a station-level panel for
2019 / 2023 / 2024 means fetching the PVs from the live isie.tn, the Wayback Machine, or by
request to ISIE. **The skeleton is still the right starting point**: it is a complete,
pre-built target list of exactly which documents to fetch and where each belongs in the
hierarchy, which is normally the expensive part of such a scrape.

### 9. Electoral register statistics

`/statistiques-dinscription/`, `/electeurs/` and `ListesElecteurs06Juillet2024` (187 nodes,
constituency-level, coded `1501_القصرين الجنوبية - حاسي الفريد`) are all empty or shells.
The registration figures were served dynamically and were not mirrored. Same remedy as #8;
the constituency codes here are a useful join key once the numbers are obtained.

---

## Suggested order of work

1. **Finish dataset 1's Arabic** by fuzzy-matching its delegation and imada columns against
   the clean folder-name vocabulary in dataset 2. This is self-contained, needs no OCR, and
   produces the join spine everything else uses.
2. **Ship dataset 3** — 45 rows, an afternoon.
3. **Pilot OCR on dataset 5**, on one governorate. It is the only real results content, and
   a pilot tells you whether the whole OCR-dependent tier (4, 5, 6) is worth funding.
4. **Use dataset 2 as a fetch plan for dataset 8.** Whether or not the PVs can be recovered
   determines if this archive supports station-level analysis or only
   delegation-level — the single biggest open question about its research value.
