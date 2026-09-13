# Covering all 2024 presidential PVs

The pilot (`docs/PV_PILOT.md`) established that the forms are readable and that
the results verify against seven internal checks. This document covers the
scale-up to all of them.

## Status

| Stage | State |
|---|---|
| Index of every presidential PV | **done** — 10,523 files, 9,448 bureaux (`data/pv_index.csv`) |
| Scans downloaded | **done** — 10,518 of 10,523 (5 fetch failures), 3.1 GB |
| Orientation + page selection | **done** — 9,448 upright pages, one per bureau, 2.8 GB |
| Extraction pipeline | **written and ready** (`tools/extract_pvs.py`) |
| Extraction run | **not run** — needs an API key this session does not have |

**The one thing that could not be done here is the extraction itself.** The
pilot's readings were made by the model driving this session, one image at a
time; that does not scale to 9,448 bureaux in a session, and this container has
no programmatic model access to substitute for it — no `ANTHROPIC_API_KEY`, no
`ant` credential profile (the CLI is not installed), and the AWS credentials
present are not valid for Bedrock (`UnrecognizedClientException`). So the
pipeline is built, the inputs are prepared, and the run is one command away for
anyone with a key.

## Two problems solved on the way

### Orientation — the pilot's headline blocker

The pilot found Tesseract's OSD wrong on 7 of 30 scans. OSD infers page
orientation from glyph shapes across the whole page, and this form's printed
Arabic is legible enough at every angle to fool it.

`tools/pv_orient.py` inverts the approach: the form has a fixed printed masthead
that appears **only along the top edge**, so it tries all four rotations, OCRs
just the top sixth of each, and keeps the one where the masthead words appear.
Handwriting — the part Tesseract cannot read — is never involved.

| | correct on the pilot's 30 |
|---|---|
| Tesseract OSD | 21 / 30 |
| **Masthead detector** | **30 / 30** |

Regression test: `tools/test_pv_orient.py`. Roughly 0.7 s per image.

Run over the whole collection it produced **9,448 upright pages — exactly one per
bureau in the index**. The rotations it applied show why the step matters:

| rotation applied | scans |
|---|---|
| 0° (already upright) | 5,733 |
| 270° | 2,201 |
| 90° | 1,490 |
| 180° | 24 |

**39% of the collection arrives not upright.** 754 pages (8.0%) scored below the
confidence threshold; they are still oriented, but flagged in the per-image
metadata so a run can route them for review rather than trust them silently.

### The 741 PDFs are bundles, not pages

741 of the presidential files are PDFs of 4–6 pages — the counting record plus
other paperwork — and 195 bureaux hold several separate images, so a naive
"render page 1" would have extracted the wrong document for 7% of the collection.

**The masthead was the wrong test, and sampling did not show it.** In sampling
the counting record scored 6–9 on the header words and the other pages 0–2, so
the top scorer won. What the sample missed is that the record's own masthead is
the part most often lost to a bad scan: measured across the bureaux this got
wrong, the record page OCRs to *nothing* and scores 0 while the correction
decision beside it — same ISIE masthead, down to "الانتخابات الرئاسية لسنة 2024"
— scores 2, so any legible other page wins. A score compared *between* pages is
only as good as the OCR on the page you want, which is exactly the page that is
hardest to read. It chose wrongly for 126 bureaux, found years later by asking a
different question of the same files: which page carries the representatives
table.

The stage now decides by **registering each page against the reference layout**
and keeping the one that fits it — the counting record fits at 0.91–0.96 and
every other page in its bundle at 0.49 or below. That is an absolute test on the
document being sought rather than a comparison between pages, so an early exit on
a good fit is safe where the old exit on a good masthead was not. Where no
reference is cached the fallback is still structural, not textual: the red plate
the form is printed in, then the six-rule fit of its bottom band. The masthead
survives only as a last tie-break, and every choice is recorded in the page's
`.json` note (`chosen_on`, `fit`, `pages_available`) so a bad pick is auditable
instead of silent. `tools/test_pv_pagepick.py` pins the 126 against the page each
was eventually read from.

The same rule now runs in one place. `tools/pick_page.py` had the good test from
the start but only visited bureaux whose votes were not yet certified, so it
could never reach one whose votes had already been read off the wrong page — a
weak rule in the stage and a strong one in an optional repair is how this
survived.

### What the wrong pick cost the results

Fixing the picker raised a question the representatives work had only asked of
one table: how many bureaux had their *votes* read off the wrong page too.
`tools/audit_page_pick.py` answers it by re-running the picker over all 949
bureaux whose archive holds more than one page and registering the page already
cached against the reference layout.

| | bureaux | certified | read by eye | identities holding, of 8 |
|---|---|---|---|---|
| cached page **is** the counting record | 760 | 99.6% | 11.4% | 5.96 |
| cached page **is not** — a better page exists | **125** | 98.5% | 40.6% | 3.78 |
| neither page registers | 55 | 78.2% | 5.5% | 5.04 |
| single-page bureaux, no choice to make | 8,500 | 99.9% | 3.8% | 6.81 |

**125 bureaux read their results off a page that is not the counting record**,
and 123 of them are certified. Certification rests on the form's internal
arithmetic, and those identities close on whatever digits the page carries, so a
certified row is not evidence the page was right. That is the whole lesson: the
check that was supposed to catch a bad read cannot see a bad *page*.

The quality gradient was in the published dataset the entire time and nothing was
reading it. By-eye reading runs 3.8% → 11.4% → 40.6% and identities holding run
6.81 → 5.96 → 3.78, moving from single-page bureaux to right-page to wrong-page.

**Rotation is a confound here and has to be controlled.** These are exactly the
pages whose masthead scored 0, so their cached orientation is suspect too, and a
sideways counting record registers near zero for a reason that has nothing to do
with which page it is. Measured upright-only the list came to 133; measured at
every rotation, 8 of those turn out to be the right page badly turned. The audit
uses the rotated measure.

Ten of the 125 were found by this audit alone, and they share a signature worth
naming: **all ten had a black-and-white page cached while the counting record in
the same archive is a colour scan** — zero red plate on the kept page, 0.006 to
0.042 on the page that fits. The representatives pass missed them because their
kept page carries something table-like enough that nothing went looking, and the
red-plate shortcut described in `docs/REPRESENTATIVES.md` would have read that
same zero as evidence there was no record to find. Two heuristics, the same blind
spot, and only the registration test sees past it.

The list is `data/verification/results_wrong_page.csv`, with the fit of both
pages and the published row's quality flags. It is a list to re-read, not a
correction: re-reading needs the Batch API or the offline digit model, and this
audit was run where neither was available.

759 of the oriented pages came from PDF bundles. One caveat found while checking
this: in a sampled bundle the code written on the
form (`02010810202`) did not match the filename (`02010110102`). Filenames matched
the form on 30/30 JPG scans in the pilot, but they cannot be assumed for PDFs, so
the pipeline treats **the code on the form as authoritative**, keeps the filename
alongside it, and sets `code_mismatch` when they disagree.

## The pipeline

`tools/extract_pvs.py`, four resumable stages:

```bash
python3 tools/extract_pvs.py estimate    # cost and sizing, no API key needed
python3 tools/extract_pvs.py orient 4    # masthead orientation + PDF page pick
python3 tools/extract_pvs.py montage 4   # digit montages where the grid is clean
python3 tools/extract_pvs.py submit      # Batch API, chunks of 2,000
python3 tools/extract_pvs.py collect     # poll, stream results, cache per bureau
python3 tools/extract_pvs.py validate    # seven checks -> data/pv_results_2024.csv
```

Design notes:

- **Batch API** — 50% of standard price, most batches finish within an hour.
- **Structured output** — a JSON schema over the 22 numeric fields plus the three
  spelled-out vote counts, so responses parse without post-hoc repair.
- **The prompt tells the model not to self-correct.** It reads digits as written
  and reports uncertainty; inferring a value from neighbouring boxes would
  destroy the independence the seven checks depend on. That is the single most
  important line in the instructions.
- **Prompt caching** on the shared instruction block, which is identical across
  every request.
- **Resumable at every stage** — oriented images, batch ids and per-bureau results
  are all cached, so an interrupted run picks up where it stopped.
- **The seven checks are applied to the output, not the input.** Rows passing all
  seven are marked `verified=true`; the rest carry `checks_failed` for review.

## Cost and time for the full run

At 1600 px long edge (images bill at roughly width × height / 750 tokens):

| | value |
|---|---|
| Bureaux | 9,448 |
| Input tokens | ~29 M |
| Output tokens | ~3 M |
| **Cost, Batch API** | **~$93** |
| Cost, standard rates | ~$185 |

That is with digit montages sent for the 3,827 bureaux (40.5%) whose printed grid
is fully recoverable and the full page for the rest — 17% cheaper than sending
every page. See [`PV_OFFLINE_ATTEMPT.md`](PV_OFFLINE_ATTEMPT.md).
| Wall clock | a few hours, dominated by batch turnaround |

Prompt caching on the instruction block reduces the input figure further. Three
knobs trade cost against accuracy, all environment variables:

- `PV_LONG_EDGE` (default 1600) — the dominant cost term, and the one most likely
  to affect digit legibility. Spot-checked: two pilot bureaux (`09010810101`,
  `02010210103`) were re-read from the pipeline's own 1600 px output and every
  field matched the pilot reading made at 2000 px, bureau code included. Worth
  re-checking on a wider sample before a full run, but the setting looks safe.
- `PV_EFFORT` (default `medium`) — this is perception, not reasoning.
- `MODEL` (default `claude-opus-5`) — a cheaper model would cut the bill
  substantially, but the pilot's accuracy figures were measured on Opus-class
  reading and would need re-establishing.

**Recommended sequence:** re-run the pilot's 30 bureaux through the pipeline at
the intended settings and compare against `data/pv_pilot_2024.csv` — those rows
are hand-verified, so they are a ready-made accuracy harness. Confirm the seven
checks pass at the pilot's rate, then launch the full run. That costs cents and
protects a $93 job.

## What the output looks like

`data/pv_results_2024.csv`, one row per bureau: geography joined from
`pv_index.csv`, the 22 form fields, `candidate_sum`, the per-row check results,
`legibility`, `fields_uncertain`, and `verified`. Same shape as
`data/pv_pilot_2024.csv`, which is 30 rows of exactly this produced by hand — use
it as the reference for what a good row looks like.
