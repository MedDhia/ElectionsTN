# ElectionsTN

Datasets built from the archived **www.isie.tn** mirror — the website of Tunisia's
*Instance Supérieure Indépendante pour les Élections* — held in
[this Google Drive folder](https://drive.google.com/drive/folders/1FfyVtwp-YqLpS4VCDOnoM03bjDn1oL0_).

Nine datasets were scoped; **eight are built** — plus the 2019 presidential and
legislative results, which the archive does not hold at all and which were
recovered from the ISIE's own election report and the Wayback Machine.

## Start here

- **[`docs/DATASETS.md`](docs/DATASETS.md)** — the nine datasets, what each one is,
  and what changed once they were actually built.
- **[`docs/CODEBOOK.md`](docs/CODEBOOK.md)** — field-by-field documentation, provenance
  and known limits.
- **[`docs/PV_PILOT.md`](docs/PV_PILOT.md)** — can the 23,509 procès-verbaux be read?
  A 30-bureau pilot says yes, with numbers.
- **[`docs/PV_FULL_RUN.md`](docs/PV_FULL_RUN.md)** — scaling that to all 9,448
  presidential bureaux: inputs prepared, pipeline written, cost ~$93.
- **[`docs/PV_OFFLINE_ATTEMPT.md`](docs/PV_OFFLINE_ATTEMPT.md)** — routes tried to
  avoid needing an API key, and why none of them replaces one.
- **[`docs/SOURCE_INVENTORY.md`](docs/SOURCE_INVENTORY.md)** — what the archive contains.
  Short version: 28,936 nodes, but only **791 files**. The rest is empty folders.
- **[`maps/README.md`](maps/README.md)** — 743 figures of the 2024 presidential
  result, in ten folders by family: `national/`, `cartograms/`, `surfaces/`,
  `comparative/`, `levels/`, `zoom/`, `micro/`, `clusters/`, `turnout/` and
  `fitted/`. Read it before reading the maps — it explains why area is not votes,
  and what each scale costs. **Two scales are published as a pair**: everything
  outside `fitted/` runs on one fixed 0–100% scale, so a shade means the same
  number on every figure at the price that most maps read flat; `fitted/` holds
  the same maps with the ramp spanning only each one's own range, which is where
  the geography becomes legible at the price that a shade means nothing
  elsewhere. `clusters/` is the only family with a null model: it tests whether
  the pattern beats chance, rather than describing it.

## The datasets

| file | rows | what |
|---|---|---|
| `data/pv_index.csv` | 23,509 | polling-station PV scans, indexed by bureau code |
| `data/polling_centres_2022.csv` | 4,578 | polling centres with USSD codes |
| `data/local_2023_candidate_results.csv` | 3,475 | 2023 local election votes per candidate, both rounds |
| `data/local_2023_constituency_turnout.csv` | 1,715 | turnout and outcome per constituency |
| `data/regulatory_corpus.csv` | 172 | ISIE decisions, guides, statistics 2018–2024 |
| `data/communications_timeline.csv` | 136 | dated communications, 2018–2024 |
| `data/procurement_register.csv` | 72 | tenders and cahiers des charges |
| `data/presidential_applicants_2024.csv` | 45 | 2024 presidential sponsorship-form aspirants |
| `data/pv_pilot_2024.csv` | 30 | polling-bureau results read from PV scans, each verified against the form's own arithmetic |
| `inventory/electoral_geography.csv` | 26,484 | geography skeleton across 9 elections |

And for 2019, which the archive holds only as empty folders:

| file | rows | what |
|---|---|---|
| `data/legislative_2019_list_results.csv` | 1,492 | 2019 legislative votes per list per constituency, 99% of the national vote |
| `data/presidential_2019_r1_constituency.csv` | 858 | 2019 presidential round one, 26 candidates × 33 constituencies |
| `data/presidential_2019_national.csv` | 52 | national totals, three stages, digits and Arabic words |
| `data/legislative_2019_constituency_seats.csv` | 33 | seats won per constituency, split by gender |
| `data/legislative_2019_seats.csv` | 31 | seats won per list, 217 in all |
| `data/elections_2019_turnout.csv` | 3 | registered, voters, valid, spoilt, blank per contest |

Plus the archive manifests in `inventory/`: `drive_tree.csv` (28,936 nodes),
`files.csv` (791 files with download URLs), `collections_summary.csv`.

## Reproducing

```bash
pip install -r requirements.txt
apt-get install -y tesseract-ocr tesseract-ocr-ara tesseract-ocr-fra

python3 tools/crawl_drive.py            # ~30 min -> inventory/drive_tree.jsonl (gzip it)
python3 tools/build_manifests.py        # manifests + geography gazetteer
python3 tools/extract_polling_centres.py
python3 tools/canonicalise_polling_centres.py
python3 tools/build_presidential_applicants.py
python3 tools/build_communications_timeline.py
python3 tools/build_document_registers.py
python3 tools/build_pv_index.py         # fetches from the live isie.tn

python3 tools/ocr_cache.py ResultatsLocales2023 200 4          # ~25 min
python3 tools/ocr_cache.py ResultatsLocales2023 300 4 0 ara+eng
python3 tools/ocr_cache.py ResultatsFinaux2emeTour 200 4
python3 tools/ocr_cache.py /wp-content/uploads/ 200 4 1 ara+fra   # register titles
python3 tools/parse_local_results_2023.py

python3 tools/sample_pv_pilot.py 30 7      # PV pilot: sample + download
python3 tools/pv_tesseract_baseline.py     # conventional-OCR baseline
python3 tools/validate_pv_pilot.py         # seven-constraint validation

python3 tools/build_presidential_2019.py       # fetches the 2019 report (50 MB)
python3 tools/build_legislative_2019.py
python3 tools/build_2019_turnout.py
python3 tools/build_legislative_2019_lists.py  # ~12 min; scan via the Wayback Machine
```

PDFs and OCR text cache under `.cache/` (gitignored); reruns are incremental.

## Three things worth knowing up front

**The PV archive is a skeleton — but the files still exist.** ~23,000 folders map
ISIE's procès-verbaux down to individual polling bureaux, and every one is empty in
the Drive archive. isie.tn is still live, and its file-tree browser emits the whole
tree inline, so three page fetches recover an index of 23,509 PV scans with complete
national coverage for 2024. The empty skeleton was an accurate map of a corpus that
was simply never mirrored.

**The PVs are readable, and they validate themselves too.** A 30-bureau pilot on
the 2024 presidential forms: Tesseract recovered the bureau code in 0 of 30, but a
vision reading passed all seven of the form's internal consistency checks on 28 of
30 — and the candidate vote counts verified in **30 of 30**. Pooled vote shares land
within a point of the published national result. See `docs/PV_PILOT.md`.

**The results decisions validate themselves.** Every vote count is printed twice —
in digits and spelled out in Arabic words. Parsing the words
(`tools/arabic_numerals.py`) gives an independent reading of every figure: 91% of
candidate votes are word-validated, and the words correct a misread digit string in
1,040 cases. Turnout figures have no such backup and are flagged where they fail
the ballot identity.

**Arabic text extraction is the recurring obstacle.** Three separate corruptions
show up and are handled separately: glyphs stored in visual order, embedded fonts
with a broken `ToUnicode` map, and ordinary OCR error. Where a field is repaired the
raw value is kept alongside it, so every repair can be audited.

**2019 is gone from the archive and from isie.tn, and came back anyway.**
`pv-legislative2019` is the mirror's largest collection and holds 7,246 folders
and no files; the live site's 2019 pages say "قيد الإنشاء", the posts that carried
the results 404, and every 2019 results PDF the media library still lists is a
dead link. The ISIE's own 576-page report on those elections, re-uploaded in 2026,
carries the presidential results and the seat allocation as text; the Wayback
Machine carries the one table it does not. See `docs/DATASETS.md`.
