# ElectionsTN

Datasets built from the archived **www.isie.tn** mirror — the website of Tunisia's
*Instance Supérieure Indépendante pour les Élections* — held in
[this Google Drive folder](https://drive.google.com/drive/folders/1FfyVtwp-YqLpS4VCDOnoM03bjDn1oL0_).

Nine datasets were scoped; **eight are built** — plus two whole elections the
archive does not hold at all: **2019**, recovered from the ISIE's own election
report and the Wayback Machine, and **2014**, recovered from the Official
Gazette, down to the 217 members of the assembly it elected.

## Start here

- **[`docs/DATASETS.md`](docs/DATASETS.md)** — the nine datasets, what each one is,
  and what changed once they were actually built.
- **[`docs/CODEBOOK.md`](docs/CODEBOOK.md)** — field-by-field documentation, provenance
  and known limits.
- **[`docs/REPRESENTATIVES.md`](docs/REPRESENTATIVES.md)** — who was in the room
  when the votes were counted. The counting record's `ممثلي المترشحين` table,
  read at **9,439 of 9,448 stations** — the whole corpus bar nine pages ISIE
  published cut off: 56.7% of stations recorded a candidate representative, 94.8% of those
  representatives were Kais Saied's, and Ayachi Zammel's campaign had none at a
  single station in the country.
- **[`docs/PV_PILOT.md`](docs/PV_PILOT.md)** — can the 23,509 procès-verbaux be read?
  A 30-bureau pilot says yes, with numbers.
- **[`docs/PV_FULL_RUN.md`](docs/PV_FULL_RUN.md)** — scaling that to all 9,448
  presidential bureaux: inputs prepared, pipeline written, cost ~$93.
- **[`docs/PV_OFFLINE_ATTEMPT.md`](docs/PV_OFFLINE_ATTEMPT.md)** — routes tried to
  avoid needing an API key, and why none of them replaces one.
- **[`docs/SOURCE_INVENTORY.md`](docs/SOURCE_INVENTORY.md)** — what the archive contains.
  Short version: 28,936 nodes, but only **791 files**. The rest is empty folders.
- **[`maps/README.md`](maps/README.md)** — 489 figures (1,219 files) of the 2024
  presidential result, in ten folders by family: `national/`, `cartograms/`, `surfaces/`,
  `comparative/`, `levels/`, `zoom/`, `micro/`, `clusters/`, `turnout/` and
  `fitted/`. Read it before reading the maps — it explains why area is not votes,
  and what each scale costs. **Two scales are published as a pair**: everything
  outside `fitted/` runs on one fixed 0–100% scale, so a shade means the same
  number on every figure at the price that most maps read flat; `fitted/` holds
  the same maps with the ramp spanning only each one's own range, which is where
  the geography becomes legible at the price that a shade means nothing
  elsewhere — 206 of the 277 fixed-scale figures now have such a counterpart,
  and only three that could are still missing one. `clusters/` is the only family
  with a null model: it tests whether the pattern beats chance, rather than
  describing it, and the six `levels/representatives_*` panels are the only ones
  whose subject is not the vote at all.

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
| `data/pv_representatives_2024.csv` | 9,448 | candidate representatives at each polling station, read off the counting records |
| `data/representatives_by_governorate.csv` | 24 | the same, aggregated, with Wilson intervals |
| `data/representatives_by_delegation.csv` | 264 | |
| `data/representatives_by_imada.csv` | 2,042 | |
| `data/presidential_applicants_2024.csv` | 45 | 2024 presidential sponsorship-form aspirants |
| `data/pv_pilot_2024.csv` | 30 | polling-bureau results read from PV scans, each verified against the form's own arithmetic |
| `inventory/electoral_geography.csv` | 26,484 | geography skeleton across 9 elections |

And for 2019, which the archive holds only as empty folders:

| file | rows | what |
|---|---|---|
| `data/legislative_2019_list_results.csv` | 1,506 | 2019 legislative votes per list per constituency, every constituency reconciled |
| `data/presidential_2019_r1_constituency.csv` | 858 | 2019 presidential round one, 26 candidates × 33 constituencies |
| `data/presidential_2019_national.csv` | 52 | national totals, three stages, digits and Arabic words |
| `data/legislative_2019_constituency_seats.csv` | 33 | seats won per constituency, split by gender |
| `data/legislative_2019_seats.csv` | 31 | seats won per list, 217 in all |
| `data/elections_2019_turnout.csv` | 3 | registered, voters, valid, spoilt, blank per contest |

And for 2014, which isie.tn has lost entirely and the Official Gazette never did:

| file | rows | what |
|---|---|---|
| `data/legislative_2014_list_results.csv` | 1,326 | 2014 legislative votes per list per constituency, every figure validated |
| `data/presidential_2014_constituency.csv` | 957 | both presidential rounds by collection centre |
| `data/legislative_2014_elected_members.csv` | 217 | the assembly as declared: member, list, constituency |
| `data/presidential_2014_centre_turnout.csv` | 66 | voters, valid, spoilt, blank per centre per round |
| `data/legislative_2014_constituency_results.csv` | 33 | voters, votes, seats and electoral quotient per constituency |
| `data/presidential_2014_national.csv` | 29 | national totals, both rounds, digits and Arabic words |
| `data/legislative_2014_seats.csv` | 18 | seats won per list, 217 in all |
| `data/elections_2014_turnout.csv` | 3 | registered, voters, valid, spoilt, blank per contest |

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

python3 tools/download_all_pvs.py 8        # candidate representatives:
python3 -c "import sys;sys.path.insert(0,'tools');import extract_pvs;extract_pvs.stage_orient(4)"
python3 tools/harvest_representatives.py 4 # locate the table on every form
python3 tools/reps_reading_plan.py plan    # deficit-ordered reading plan
python3 tools/reps_reading_plan.py sheets  # contact sheets, read by eye
python3 tools/reps_readings.py build .cache/reps_transcripts/*.txt
python3 tools/build_representatives.py
python3 tools/reps_geography.py
python3 tools/make_reps_maps.py
python3 tools/build_presidential_2019.py       # fetches the 2019 report (50 MB)
python3 tools/build_legislative_2019.py
python3 tools/build_2019_turnout.py
python3 tools/build_legislative_2019_lists.py  # ~12 min; scan via the Wayback Machine

python3 tools/build_presidential_2014.py       # fetches the Official Gazette
python3 tools/build_legislative_2014.py
python3 tools/build_legislative_2014_lists.py  # ~1 min; OCR of the annex names
python3 tools/build_2014_turnout.py
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

**The form records who was watching, and that is a different dataset.** Below the
vote counts, every counting record carries a table of the candidates'
representatives — name, candidate, signature. Read at 9,439 stations, 99.9% of
the corpus, it says 56.7% of polling stations had a candidate representative
present, that 94.8% of those represented Kais Saied, and that Ayachi Zammel had
none at any of them — zero across the country, which bounds his presence under
0.041% of stations. Presence barely tracks the vote (r = 0.10 with Saied's
share), so it maps organisation rather than support: within Tunis alone it runs
from 5% of stations in Sidi El Béchir to 92% in Cité El Khadra, and in Kebili it
was Zouhair Maghzaoui who came closest to holding the room (55 stations against
Saied's 63). See
`docs/REPRESENTATIVES.md`.

**Arabic text extraction is the recurring obstacle.** Three separate corruptions
show up and are handled separately: glyphs stored in visual order, embedded fonts
with a broken `ToUnicode` map, and ordinary OCR error. Where a field is repaired the
raw value is kept alongside it, so every repair can be audited.

**2014 was not on isie.tn at all, and the Official Gazette had it all along.**
Every one of the thirteen 2014 results documents the media library lists is a
dead link, the pages built to carry them render an empty file tree, and the
ISIE's own report on the year holds no vote counts. But each declaring decision
orders itself published in the Gazette, whose full run is mirrored and
searchable: three issues of 2014 carry the entire result, with a real text layer,
every national count printed twice, and the 217 elected members by name. Every
check in all four 2014 builders passes.

**2019 is gone from the archive and from isie.tn, and came back anyway.**
`pv-legislative2019` is the mirror's largest collection and holds 7,246 folders
and no files; the live site's 2019 pages say "قيد الإنشاء", the posts that carried
the results 404, and every 2019 results PDF the media library still lists is a
dead link. The ISIE's own 576-page report on those elections, re-uploaded in 2026,
carries the presidential results and the seat allocation as text; the Wayback
Machine carries the one table it does not. See `docs/DATASETS.md`.
