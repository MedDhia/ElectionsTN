# PV extraction pilot — 2024 presidential

**Question:** can polling-station results be read off the 23,509 procès-verbaux
indexed in `data/pv_index.csv`, at an accuracy that would make a station-level
dataset worth building?

**Answer: yes, but not with conventional OCR.** On a 30-bureau stratified sample,
a vision model read every candidate vote count correctly — verified against the
form's own internal arithmetic — while Tesseract recovered nothing usable.

## The document is better than expected

The PVs are not free-form handwriting. Each is a **pre-printed form**
(`محضر عملية الفرز`, the counting-operation record) on which:

- the field labels and the three candidate names are **printed**;
- every number is handwritten **one digit per box** — a constrained field, not cursive;
- each vote count appears **twice**, in digits and spelled out in Arabic words;
- the form carries **four printed reconciliation rows** (`المطابقة 1–4`) that the
  polling staff must compute and that must come to zero.

That last property is what makes the pilot rigorous. Seven constraints can be
checked with no external ground truth at all:

| # | Constraint | What it catches |
|---|---|---|
| 1 | bureau code in the form == code in the file path | misfiled or misread scans |
| 2 | `مطابقة 1`: signed voters − ballots extracted == 0 | stage-1/stage-2 mismatch |
| 3 | `م = س + د + ر` | ballots delivered not accounted for |
| 4 | `مطابقة 2`: delivered − م == 0 | |
| 5 | `ن = ص + ع + ف` | ballots extracted not accounted for |
| 6 | `مطابقة 3`: voters − ن == 0 | |
| 7 | sum(candidate votes) == `ق` == valid ballots | **any error in the results themselves** |

A reading that satisfies all seven is almost certainly right: a misread digit
would have to be compensated by matching misreads in three other boxes.

## Sample

30 bureaux drawn by `tools/sample_pv_pilot.py` from the 7,444 single-image
bureaux with unambiguous 11-digit filenames, round-robin across governorates so
each is represented before any is sampled twice. **23 of 24 governorates** are in
the sample. Scans range from 828×585 to 2386×3307 px.

## Result 1 — Tesseract cannot read these forms

`tools/pv_tesseract_baseline.py`, with orientation detection, upscaling and a
digits-only whitelist:

- **bureau code recovered: 0 of 30**
- median 704 characters of printed Arabic read per page — the *printed* text is fine
- median 49 digit tokens emitted per page, none of which reconstruct the known code

Conventional OCR reads the form and fails on the handwriting. That is the whole
difficulty in one number.

## Result 2 — vision reading passes the form's own checks

`tools/validate_pv_pilot.py` over the 30 readings:

| | count |
|---|---|
| Fully consistent (7/7 checks pass) | **28 / 30** |
| Consistent, some checks untestable | 1 |
| At least one check failed | 1 |

Per constraint:

| Constraint | pass | fail | untestable |
|---|---|---|---|
| bureau code matches path | **30** | 0 | 0 |
| `مطابقة 1` | 30 | 0 | 0 |
| `م = س + د + ر` | 29 | 0 | 1 |
| `مطابقة 2` | 28 | **1** | 1 |
| `ن = ص + ع + ف` | 30 | 0 | 0 |
| `مطابقة 3` | 30 | 0 | 0 |
| **candidate sum == ق == valid** | **30** | **0** | **0** |

**The results themselves — the candidate vote counts — verified in all 30 cases.**
The single failure is in the ballot-stock accounting: on bureau `04010310201`,
ballots delivered reads 1189 while `م` reads 1199 and the form's own `مطابقة 2`
says the difference is zero, so one of the three boxes is misread. It does not
touch the vote counts.

Fields not confidently read: **7 of 480 (1.5%)**, concentrated in the one
faint scan (`23030110202`) where the turnout block is unreadable but the
candidate votes are legible and internally consistent.

## Result 3 — an external sanity check

Pooling the 30 bureaux (not a representative sample — stratified by governorate,
not weighted by size):

| | pilot | official 2024 |
|---|---|---|
| Saied | 91.0% | ~90.7% |
| Zammel | 7.0% | ~7.4% |
| Maghzaoui | 2.0% | ~1.9% |
| Turnout | 31.8% | ~28.8% |

Vote shares land within a point of the published national result. Turnout is
higher, as expected when small bureaux are over-weighted by an unweighted draw.

## What a production run needs

1. **Orientation is the main engineering problem, not recognition.** Scans arrive
   at all four rotations, and Tesseract's OSD got it wrong on **7 of 30** — it
   reads the printed Arabic, which appears at every angle on this form. A
   template-based detector keyed on the red header block would be more reliable
   and is worth building before scaling.
2. **Resolution varies by ~8× in linear dimension.** The smallest scans are at the
   edge of legibility; expect a few percent of bureaux where some fields cannot
   be recovered at any cost.
3. **Keep the seven checks as the acceptance gate.** Rows that pass all seven can
   be published unreviewed; rows that fail should be queued for a human. On this
   sample that queue would be 2 rows in 30 (~7%).
4. **Scope.** 9,448 bureaux have a PV in the index, 8,820 with exactly one image.
   The locales collections are heterogeneous (correction pages, multi-page
   documents) and need separate handling — this pilot deliberately covers only
   the uniform 2024 presidential template.

## Files

| file | what |
|---|---|
| `data/pv_pilot_2024.csv` | the 30 verified bureaux, with per-row check results |
| `tools/sample_pv_pilot.py` | stratified sampler and downloader |
| `tools/pv_tesseract_baseline.py` | the conventional-OCR baseline |
| `tools/validate_pv_pilot.py` | the seven-constraint validator |

`data/pv_pilot_2024.csv` carries `checks_passed`, `checks_testable`,
`checks_failed`, `legibility` and `fields_uncertain` per row, so nothing is
presented as verified that isn't.
