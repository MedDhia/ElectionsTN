# Source inventory — ISIE Google Drive archive

**Source:** [Drive folder `1FfyVtwp-YqLpS4VCDOnoM03bjDn1oL0_`](https://drive.google.com/drive/folders/1FfyVtwp-YqLpS4VCDOnoM03bjDn1oL0_)
**Enumerated:** 2026-08-29, via `tools/crawl_drive.py` (complete traversal, 0 folders left unexpanded)
**Archive date:** all nodes carry a Drive timestamp of 26 March 2025

## What it is

The folder is a `wget`-style offline mirror of **www.isie.tn**, the site of Tunisia's
*Instance Supérieure Indépendante pour les Élections*. The mirror preserves the site's
URL layout as a directory tree: each page path (`/actualites/2024/03/06/<slug>/`) became a
folder, each page's `index.html` became a Google Doc, and `/wp-content/uploads/` holds the
media library. Both language trees are present — French at the root, Arabic under `/ar/`.

## The headline finding: the tree is mostly empty

| | count |
|---|---|
| Total nodes | 28,936 |
| Folders | 28,145 |
| **Actual files** | **791** |
| Folders containing at least one file | 521 (1.9%) |

**97% of the archive is empty folders.** The mirror captured the complete *directory
skeleton* of ISIE's procès-verbaux (PV) archive — down to individual polling bureaux — but
none of the PV scans themselves. Every one of these collections has zero files:

| Collection | Nodes | Files |
|---|---|---|
| `filebases/pv-legislative2019` | 7,246 | **0** |
| `2024/PvCvPresidentielle24` | 6,334 | **0** |
| `2023/ElecLocPvTour1` | 4,996 | **0** |
| `2023/PvLegTour1` | 4,740 | **0** |
| `2024/PV2emeTour` | 1,202 | **0** |
| `2023/TemplateCandidats2023` | 306 | **0** |
| `2024/Resultats1erTour` | 306 | **0** |
| `2024/Resultats2emeTour` | 281 | **0** |
| `2024/ListesElecteurs06Juillet2024` | 187 | **0** |

Spot-checks against Drive confirm these are genuinely empty, not a crawler artefact.
The same is true of the news archive: `/actualites/` has 382 nodes and 1 file — the dated
article *slugs* survive as folder names, the article bodies do not.

## The 791 real files

| Type | Count | Notes |
|---|---|---|
| PDF | 537 | 289 in dated `uploads/YYYY/MM/`; the rest in results collections |
| Google Doc | 228 | mirrored HTML pages (mostly navigation shells, see below) |
| JPG | 9 | news attachments |
| JSON | 8 | WordPress REST API dumps (`/wp-json/`) |
| JS / other | 3 | site assets |

Two caveats that shape everything downstream:

**1. Most PDFs are scans with no text layer.** Sampling across document types
(decisions, results, candidate lists, procedure manuals) returned 0 characters of
extractable text. The scans are 1654×2340 px RGB (≈200 DPI A4) — good quality, but
Arabic OCR is required. The one significant exception is the polling-centre directory
(see below).

**2. Page mirrors are navigation shells.** The results pages (`/resultats-finaux-<gov>/`,
`/resultats-preliminaires-<gov>/`) rendered their tables client-side, so the mirrored
Google Docs contain only site chrome — menus, footer, a list of delegation names — and no
result figures.

## What *is* directly usable

- **`uploads/2022/06/Annuaire-codes-USSD-centres-de-Vote-en-Tunisie.pdf`** — 87 pages,
  born-digital with ruled table structure: a national polling-centre directory,
  4,578 centres with Arabic and French names and USSD codes. Extracted; see
  `data/polling_centres_2022.csv`.
- **`uploads/2024/07/*.pdf`** — 45 per-person PDFs, one per 2024 presidential candidacy
  applicant, each carrying a machine-readable name and file number.
- **The folder skeleton itself** — 26,484 geography nodes across nine election events,
  which is a substantial dataset in its own right (see `docs/DATASETS.md`).
- **`/elections/`** — section trees for every Tunisian election 2011–2019 (constituent
  assembly 2011, legislative and presidential 2014 and 2019, partial legislative 2017,
  municipal 2018, CSM 2016/2019), subdivided into `cadre-juridique`, `candidatures`,
  `calendrier`, `campagne-electorale`, `electeurs`, `resultats`, `manuels-de-procedures`.

## Manifests in this repo

| File | Rows | Contents |
|---|---|---|
| `inventory/drive_tree.csv` | 28,936 | every node: path, kind, MIME, Drive ID, depth |
| `inventory/files.csv` | 791 | downloadable files with direct download URLs |
| `inventory/electoral_geography.csv` | 26,484 | folder skeleton parsed into election / geography columns |
| `inventory/collections_summary.csv` | 176 | nodes vs. files vs. empty folders per collection |
| `inventory/drive_tree.jsonl.gz` | 28,936 | raw crawl output (gzipped) |
