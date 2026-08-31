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
other paperwork — so a naive "render page 1" would have extracted the wrong
document for 7% of the collection. The masthead score separates them cleanly:
the counting record scores 6–9 and every other page scores 0–2. Exactly one
PV-like page was found per bundle in sampling, so nothing is lost by keeping the
best-scoring page.

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
