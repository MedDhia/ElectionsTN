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
`reference_year` are parsed from the filename; `title_from_ocr` is filled for
65/72. 2020–2024.

## 6. `data/local_2023_constituency_turnout.csv` and
##    `data/local_2023_candidate_results.csv` — 2023 local election results
1,715 constituency rows and 3,475 candidate rows from all 248 delegation-level
decisions — 145 first-round (1,202 constituencies) and 103 second-round (513).
The second round was held in early 2024, so its files sit under `uploads/2024/`
despite belonging to the 2023 election; both carry `election = locales_2023` with
`round` 1 or 2. Built by `tools/ocr_cache.py` then
`tools/parse_local_results_2023.py`, with Arabic number-word parsing in
`tools/arabic_numerals.py`.

Candidate table (`local_2023_candidate_results.csv`):

| column | meaning |
|---|---|
| `election`, `round` | `locales_2023`, round 1 or 2 |
| `governorate`, `delegation`, `constituency` | where the seat is |
| `candidate` | candidate name as OCR'd |
| `votes` | vote count |
| `vote_source` | `agree` (words and digits match), `digits-wrong` (words used), `words-only`, `digits-only` |
| `votes_digits_ocr`, `votes_words_ocr` | the two raw readings |

**Why `votes` is trustworthy:** the source prints every count twice, in digits and
spelled out ("بلسان القلم"). The spelled form wins when they disagree. 3,084 of
3,475 rows (89%) are word-validated, and the words correct a misread digit string
in 1,040 cases. The 391 `digits-only` rows are not validated and are marked as such.

Constituency table (`local_2023_constituency_turnout.csv`):

| column | meaning |
|---|---|
| `registered`, `voters`, `votes_spoilt`, `votes_blank` | as OCR'd, reconciled across two passes |
| `votes_valid` | valid votes as OCR'd |
| `candidate_sum` | sum of the candidate votes above — independent of the OCR'd digits |
| `votes_valid_best` | `candidate_sum` where every candidate in the constituency was word-validated, else `votes_valid` |
| `votes_valid_source` | `candidate_sum` or `ocr`, so the choice above is visible |
| `voters_implied` | `votes_valid_best + spoilt + blank` |
| `n_candidates`, `outcome` (`elected` / `runoff`), `winner` | result |
| `ballot_identity_ok` | does `votes_valid + spoilt + blank == voters` on the OCR'd values |
| `candidate_sum_ok` | does `candidate_sum == votes_valid` |
| `turnout_repaired` | which fields the second pass changed, or `unpaired` / `pass-misaligned` |

**The turnout figures are the weak part.** They are printed glued to the following
Arabic word ("247ناخبا") and have no spelled-out backup, so OCR truncates them
often — `ballot_identity_ok` holds for only 27% of rows. Two passes (200 dpi
Arabic; 300 dpi Arabic+English) are reconciled against the identities, which
repairs 296 rows, but 398 could not be paired between passes.

**Use `votes_valid_best` rather than `votes_valid`.** It is anchored on the
word-validated candidate sum for 1,089 of 1,715 constituencies (63%) and falls back
to the OCR'd digits otherwise, with `votes_valid_source` recording which.

Coverage: 248 delegation decisions. The first round spans 15 of the 27
constituencies, so this is a substantial sample of the 2023 local elections, not
the complete national result.

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
2,378 PDF); this is the index. Their contents are dataset 9.

---

## 9. `data/pv_presidential_2024.csv` — polling-station results, 2024 presidential

9,448 rows, one per polling bureau — every presidential PV in the index. The
station-level count, read off the handwritten scans offline with no model API:
grid detection, a digit classifier trained on labels the forms produced
themselves, and maximum-likelihood decoding under the form's own arithmetic.
Method and validation in [`PV_OFFLINE_READING.md`](PV_OFFLINE_READING.md).

One caveat on completeness: the file has 9,448 rows, one per presidential bureau,
but ISIE filed 14 further PVs under an Arabic school name carrying no bureau code.
Those cannot be joined to a polling station and are not in the dataset.

**Filter before use.** Every row is present, including the ones that could not be
read, so that missingness is visible rather than silent. A cell is empty when the
form's own arithmetic did not vouch for it — never because a value was guessed and
withheld.

Which filter you want depends on what you need.

| you want | filter | rows |
|---|---|---|
| candidate votes | `votes_certified == 1` | **8,970 (94.9%)** |
| the paper count | `papers_certified == 1` | 8,769 (92.8%) |
| ballot accounting | `ballots_certified == 1` | 8,725 (92.3%) |
| every field on the form | `reading == "decoded"` | 8,056 (85.3%) |
| candidate votes, split backed by the words | `split_corroborated == 1` | 7,083 (75.0%) |

`reading == "decoded"` means the form passed the joint gate whole (`fields_read >=
18`, `cells_corrected <= 3` and `logp_conceded <= 12`) and every column is filled. `reading == "blocks"`
means only the accounts the identities closed were published and the other columns
are empty. `reading == "none"` means nothing on the form could be vouched for.
`reading == "vision"` means the form was read off the scan by eye — see below.

**One filter has two provenances behind it.** Most certified rows come from the
offline pipeline and can be re-derived by anyone who runs `tools/decode_all.py`.
A minority were read directly off the scans, because the classifier cannot see
them: the form draws candidate cells 56×38 in reference coordinates and every
other field about 23×24, so on the 560px scans ISIE published for much of
Medenine the candidates land near 20px wide and `valid` and `q_declared` near
8px. Measured against forms read by eye, the classifier gets the candidates
61–78% right and `valid` 1 time in 17 — and since the votes identity is
`q == valid == the three candidates summed`, two unreadable fields veto a form
however well its candidates are read.

Those rows are admitted on the same evidence as every other row: the candidates
must sum to `valid`, and to `q_declared` where the form fills it in, which is the
test `certify_cells` applies and which a misread digit almost always breaks. What
differs is that **they cannot be reproduced from the code** — nobody can re-run a
pair of eyes. So:

- `votes_certified == 1` gives every row the form's arithmetic vouches for, of
  either provenance.
- `votes_certified == 1 and reading != "vision"` gives the reproducible subset.

**The identities constrain the candidate total, not the split.** `valid == zammel +
maghzaoui + saied` is one equation in three unknowns, so a misreading that moves
votes between candidates while preserving their sum satisfies it exactly as well as
the truth does, and is certified. Bureau 01080310102 was previously published as
Saied 329 / Zammel 85 and reads Saied 389 / Zammel 25 — both sum to 414, both
closed every identity, and the scan says the second is right. Treat `saied`,
`zammel` and `maghzaoui` as classifier output constrained to a certified total,
and `valid` / `q_declared` / `candidate_sum` as identity-certified.

`split_corroborated` is what can be offered instead of an identity. The form
writes each score a second time in Arabic words beside the digits, and this column
is 1 when a separate reader of that column agrees with all three published
figures, 0 when it does not, and empty when the words could not be read. It
overrules nothing — the word reader is the weaker of the two and no value is taken
from it — but the errors concentrate where the two disagree. Of the pilot's 90
hand-verified scores, the 73 the two channels agree on are all correct, and both
of the cell reader's two errors fall among the 17 they differ on.

Read the column for what it is. Two errors is a thin basis: zero wrong in 73 puts
the agreed set under about 4%, which is not yet distinguishable from the 2.2% base
rate, so this shows the errors concentrating rather than proving the agreed rows
cleaner. `split_corroborated == 0` also does not mean the row is wrong — on the
pilot the digits were right in 15 of the 17 disagreements. It means the split is
worth checking against the scan if the analysis turns on it. Corpus-wide, 7,083 of
the 8,970 certified rows are corroborated, 1,776 contradicted and 111 unreadable;
restricting to the corroborated rows moves the aggregate by about 0.1pp.

On the hand-verified pilot the decoded rows are exactly right on all 18
constrained fields, and certified field values were right in 255 of 255 cases.

Rows published as blocks and rows decoded whole now agree closely on Saied — 90.87%
against 90.85% — and within the 249 delegations carrying both, the paired median
difference is +0.06pp. They still cover different polling stations, so mixing them
changes the weighting on the smaller candidates.

One calibration note, and a correction to an earlier version of this file. When
coverage first reached 83% of bureaux the aggregate had drifted on the smaller
candidates — Zammel 6.90% against a reported 7.35% — and this file recorded that as
unexplained. It was classifier error on the degraded scans that had just become
readable, which the training set did not yet cover. Harvesting labels from those
forms and retraining moved Zammel to 7.17% and Maghzaoui from 2.24% to 1.99%
against a reported 1.97%, with no change to the reader. The remaining gap on Zammel
is 0.18pp.

Note that the national figures are the widely reported ones rather than numbers
sourced from ISIE, whose own results pages are empty, so this is a sanity check
rather than a reconciliation. The smaller candidates' shares remain the figures
most sensitive to any residual reading error.

| column | meaning |
|---|---|
| `bureau_code` | 11-digit polling-bureau identifier; joins to `pv_index.csv` |
| `governorate`, `delegation`, `sector`, `polling_centre` | from the index (presidential collection only) |
| `a_registered` | registered voters (أ) — **see the caveat below** |
| `b_delivered` | ballot papers delivered (ب) |
| `c_signed` | voters who signed the register (ج) |
| `d_damaged`, `r_remaining` | damaged (د) and unused (ر) ballots |
| `s_extracted` | ballots extracted from the urn (س) |
| `valid`, `blank`, `spoilt` | valid (ص), blank (ع) and spoilt (ف) papers |
| `w_voted` | voters who voted (و) |
| `q_declared` | declared valid votes (ق) |
| `zammel`, `maghzaoui`, `saied` | votes for each candidate |
| `candidate_sum` | the three candidate counts added up |
| `turnout_pct` | `w_voted / a_registered`, blank where `a_registered_ok` is 0 |
| `saied_share_pct` | `saied / candidate_sum` |
| `a_registered_ok` | 1 when `a_registered >= w_voted`; 0 flags a reading known to be wrong |
| `reading` | `decoded` (whole form passed the joint gate), `blocks` (only the accounts its identities closed), `none` |
| `votes_certified`, `papers_certified`, `ballots_certified` | 1 when the form's arithmetic vouches for that account's columns — either because the independent cell-by-cell reading closed its identity, or because the decoder closed it while overruling at most one cell in that block |
| `identities_ok` | how many of the eight identities the **independent** cell-by-cell reading satisfied, before any correction (0–8) |
| `cells_corrected` | cells the arithmetic had to overrule to reach a consistent reading |
| `logp_conceded` | log-likelihood given up to reach consistency |
| `margin` | log-likelihood gap to the next reading the identities also admit |
| `fields_read`, `fields_published`, `fields_located` | fields the decoder resolved; fields actually written to this row; fields in the layout used (detected, or placed from the template where detection came up short) |
| `status` | `read` (something was published), `unverified` (read but nothing the form vouches for), `no_grid`, `unreadable` |

**`a_registered` is the weak column.** It appears in none of the form's identities,
so nothing on the paper checks it and the decoder cannot correct it — it is the one
field read by classifier alone. `a_registered_ok` flags the 0.3% of published rows
where it reads lower than the turnout it is supposed to exceed; the rest are
plausible but uncertified. Every other column is either certified by an identity,
determined by columns that are, or — for the three candidate columns specifically —
constrained only in its total, as described above.

**Coverage is not random.** The forms that fail are the low-resolution scans —
median width 1130px against 1600px for the ones that read — so any station-level
analysis should treat the published subset as a sample skewed toward better-scanned
stations, not as a random one. Aggregates over the published rows come to Saied
91.39% against a widely reported 90.69%. That gap is not a reconciliation and
should not be read as one: these are counting records from *inside the republic*
(محضر عملية الفرز داخل الجمهورية) while the reported total includes out-of-country
voting, and the stations still missing lean measurably one way — the 717 added in
the most recent run break 93.70% for Saied against 91.15% for those already held.
An earlier version of this file cited a closer agreement as evidence of accuracy;
that agreement narrowed as the reader got *worse*, so it was not measuring what it
appeared to.

---

## Not built

**Electoral register statistics.** `/statistiques-dinscription/` is still live but
its content is now empty (97 characters via the WordPress REST API), and the
figures were rendered client-side. Neither the archive nor the live site has them.
