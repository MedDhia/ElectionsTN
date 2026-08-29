# ElectionsTN

Scoping work on the archived **www.isie.tn** mirror — the website of Tunisia's
*Instance Supérieure Indépendante pour les Élections* — held in
[this Google Drive folder](https://drive.google.com/drive/folders/1FfyVtwp-YqLpS4VCDOnoM03bjDn1oL0_).

This repo answers one question: **what datasets can we build from it?**

## Start here

- **[`docs/SOURCE_INVENTORY.md`](docs/SOURCE_INVENTORY.md)** — what the archive actually
  contains. Short version: 28,936 nodes, but only **791 files**. The rest is empty folders.
- **[`docs/DATASETS.md`](docs/DATASETS.md)** — nine candidate datasets, ranked by what they
  cost to produce, including the ones the archive *looks* like it has but doesn't.

## Contents

```
data/       polling_centres_2022.csv      4,578 polling centres w/ USSD codes  (built)
inventory/  drive_tree.csv                28,936 nodes — full archive manifest
            files.csv                     791 files with direct download URLs
            electoral_geography.csv       26,484 geography nodes across 9 elections
            collections_summary.csv       nodes vs. files vs. empty folders
            drive_tree.jsonl.gz           raw crawl output
tools/      crawl_drive.py                enumerate a public Drive folder tree
            build_manifests.py            crawl output -> the CSVs above
            extract_polling_centres.py    build data/polling_centres_2022.csv
```

## Reproducing

```bash
pip install pdfplumber
python3 tools/crawl_drive.py                 # ~30 min -> inventory/drive_tree.jsonl (gzip it)
python3 tools/build_manifests.py
python3 tools/extract_polling_centres.py
```

## Two findings worth knowing up front

**The PV archive is a skeleton.** ~23,000 folders map ISIE's procès-verbaux down to
individual polling bureaux for the 2019 and 2023 legislative, 2023 local and 2024
presidential elections — and every one of them is empty. No station-level results are in
this archive. The skeleton is still useful: it is a complete, pre-built target list for
fetching those documents from elsewhere, and a gazetteer in its own right.

**Arabic text extraction is the recurring obstacle.** Nearly all 537 PDFs are ~200 DPI
scans with no text layer, so OCR gates most of the corpus. Even the one born-digital
tabular PDF stores Arabic as visually-ordered glyphs with a defective font encoding —
`tools/extract_polling_centres.py` documents both problems and how far they can be worked
around.
