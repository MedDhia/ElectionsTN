# Codebook

Eight datasets built from the ISIE archive. Provenance, method and known limits
for each; see `docs/DATASETS.md` for why these and not others, and
`docs/SOURCE_INVENTORY.md` for what the source archive contains.

Every dataset is reproducible from `tools/` — nothing here was hand-edited.

## Cross-cutting caveats

**Arabic text.** Three distinct corruptions appear in the sources and are handled
separately: PDF text stored as glyphs in *visual* order (reversed on read);
embedded fonts with a defective `ToUnicode` map (letters silently swapped); and
OCR error on scans. Where a field has been repaired, the raw value is kept in a
parallel column so the repair can be audited.

**Coverage is per-collection, never assume national.** The mirror is partial and
says so in different places for different elections. Counts below are what the
sources actually yield, not what the elections actually had.

---

## 1. `data/polling_centres_2022.csv` — polling-centre directory
4,578 rows, one per polling centre. Built by `tools/extract_polling_centres.py`
then `tools/canonicalise_polling_centres.py`.

Source: `uploads/2022/06/Annuaire-codes-USSD-centres-de-Vote-en-Tunisie.pdf`, the
only born-digital tabular PDF in the archive.

| column | meaning |
|---|---|
| `governorate` | canonical governorate (24 distinct, 0 unmatched) |
| `constituency_ar` | constituency as printed (not canonicalised) |
| `delegation`, `imada`, `centre_name` | canonicalised against archive folder names; blank where no confident match |
| `centre_name_fr` | centre name in French, straight from the PDF |
| `ussd_code` | USSD lookup code, 1001–5578, unique per centre |
| `delegation_ar`, `imada_ar`, `centre_name_ar` | raw extracted Arabic, before canonicalisation |
| `*_score` | similarity of the accepted match, 0–1 |
| `source_page` | page of the source PDF |

Resolution: delegation 96.4%, imada 89.2%, centre name 72.3%. Thresholds are
0.72 / 0.75 / 0.82 — centre names need a higher floor because different schools
score ~0.75 on shared boilerplate. **`centre_name_fr` and `ussd_code` are the
reliable join keys**; use `*_score` to tighten the Arabic further.

## 2. `inventory/electoral_geography.csv` — electoral geography gazetteer
26,484 rows parsed from the archive's folder skeleton by `tools/build_manifests.py`.
Covers nine election events; see `docs/DATASETS.md`. Superseded for the PV
collections by dataset 8, which has the real files.

## 3. `data/presidential_applicants_2024.csv` — 2024 presidential aspirants
45 rows. Built by `tools/build_presidential_applicants.py`.

Source: `uploads/2024/07/`, one personalised "استمارة تزكية شعبية 2024" (popular
sponsorship form) per aspirant — the form used to collect the endorsements
required to stand.

| column | meaning |
|---|---|
| `sponsorship_number` | number assigned to the aspirant, 039–999 |
| `name_overlay` | name from the PDF text overlay (authoritative) |
| `name_from_filename` | name from the filename |
| `script` | `arabic` or `latin` |
| `pages`, `source_file`, `drive_id`, `source_url` | provenance |

All 45 carry a number, and overlay and filename agree for 45/45 once spacing and
decomposed hamza are normalised. This is the set issued sponsorship forms, **not**
the set whose candidacies were accepted — three candidates reached the ballot.

## 4. `data/regulatory_corpus.csv` — ISIE regulatory documents
172 rows. Built by `tools/build_document_registers.py` from the dated media
library. Filenames are structured, so the index needs no OCR; `title_from_ocr`
is added where a first-page OCR is cached.

| column | meaning |
|---|---|
| `doc_type` | decision, minutes, guide, statistics, polling_geography, campaign_finance, candidate_list, code_of_conduct, recruitment, legal_text, calendar, communique, list, report, results, other |
| `reference_number`, `reference_year` | parsed from "قرار عدد N لسنة YYYY" or "Décision n° YYYY-NN" |
| `year_published`, `month_published` | from the uploads path, i.e. publication not enactment |
| `language` | ar / fr / mixed, inferred from the filename |
| `title_from_filename`, `title_from_ocr` | subject |

`year_published` is when the file was uploaded and can differ from the document's
own date. 16 rows remain `other`.

## 5. `data/procurement_register.csv` — procurement
72 rows, same builder. `procedure` is one of appel d'offres, appel d'offres
simplifié, consultation, cahier des charges, other. `reference_number` /
`reference_year` are parsed from the filename. 2020–2024.

## 6. `data/local_2023_constituency_turnout.csv` and
##    `data/local_2023_candidate_results.csv` — 2023 local election results
1,202 constituency rows and 2,640 candidate rows from all 145 delegation-level
decisions. Built by `tools/ocr_cache.py` then `tools/parse_local_results_2023.py`,
with Arabic number-word parsing in `tools/arabic_numerals.py`.

Candidate table (`local_2023_candidate_results.csv`):

| column | meaning |
|---|---|
| `governorate`, `delegation`, `constituency` | where the seat is |
| `candidate` | candidate name as OCR'd |
| `votes` | vote count |
| `vote_source` | `agree` (words and digits match), `digits-wrong` (words used), `words-only`, `digits-only` |
| `votes_digits_ocr`, `votes_words_ocr` | the two raw readings |

**Why `votes` is trustworthy:** the source prints every count twice, in digits and
spelled out ("بلسان القلم"). The spelled form wins when they disagree. 91% of rows
are word-validated; the `digits-only` remainder is not, and is marked as such.

Constituency table adds `registered`, `voters`, `votes_valid`, `votes_spoilt`,
`votes_blank`, `candidate_sum`, `n_candidates`, `outcome` (`elected` / `runoff`),
`winner`, plus the quality flags `ballot_identity_ok`
(`votes_valid + spoilt + blank == voters`), `candidate_sum_ok`
(`candidate_sum == votes_valid`) and `turnout_repaired`.

**The turnout figures are the weak part.** They are printed glued to the following
Arabic word ("247ناخبا") and have no spelled-out backup, so OCR truncates them
often. Two passes are reconciled against the identities, but a substantial share
still fails; filter on the flags before using them. `candidate_sum` is derived
from word-validated votes and is the dependable measure of valid votes.

## 7. `data/communications_timeline.csv` — ISIE communications
136 rows, 2018–2024. Built by `tools/build_communications_timeline.py` from
surviving dated permalink folders. Article **bodies were not mirrored**: this is
titles-from-slugs and dates only. The Arabic section's pagination stubs run to
page 14, so the live site carried far more than the 2 Arabic items captured.

## 8. `data/pv_index.csv` — polling-station PV index
23,509 rows. Built by `tools/build_pv_index.py` **from the live isie.tn**, not the
Drive archive — the archive has these folders but every one is empty.

| column | meaning |
|---|---|
| `election` | presidentielle_2024, locales_2023_t1, locales_2023_t2 |
| `governorate`, `delegation`, `constituency`, `sector`, `polling_centre` | path hierarchy (columns used vary by election) |
| `bureau_code` | 8–13 digit polling-bureau identifier from the filename |
| `filename`, `file_ext`, `file_url`, `path` | the scan itself |

Coverage for the 2024 presidential is complete: 24 governorates, 279 delegations,
5,088 polling centres. The files are **scans of handwritten PV forms** (20,915 JPG,
2,378 PDF); this is the index, not their contents. Reading the results off them is
a separate and much larger undertaking.

---

## Not built

**Electoral register statistics.** `/statistiques-dinscription/` is still live but
its content is now empty (97 characters via the WordPress REST API), and the
figures were rendered client-side. Neither the archive nor the live site has them.
