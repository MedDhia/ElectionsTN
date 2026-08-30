# Reading the PVs without model access — what was tried

The full presidential run (`docs/PV_FULL_RUN.md`) needs a Claude API key this
container does not have. This documents the attempt to find a route that does
not need one, so the ground already covered is not re-covered.

**Conclusion: there isn't one at usable quality.** Three routes were tried. One
produced a real cost saving for the eventual API run; none replaces it.

## 1. Are the results already published in machine-readable form?

No. ISIE's results pages are still served — `/resultats-finaux-<governorate>/`,
`/ar/presidentielle-2024-resultat-preliminaire/` — but they are navigation shells
of ~70 KB with no tables, no canvas, no iframes, and no data links. The theme's
`custom.js` contains no AJAX call that would fetch results, and the only endpoints
in the page are WordPress and analytics boilerplate. This matches the earlier
finding for the registration-statistics page: the content was rendered
client-side and is gone. The PV scans really are the only source.

## 2. Offline digit recognition

The forms are unusually favourable for this: every number is written one digit per
cell in a printed grid, so it is a segmentation problem before it is a
handwriting problem.

**Segmentation works.** Contour detection fails — it finds ink strokes, not rules —
but extracting long horizontal and vertical runs morphologically recovers the
printed grid, and the enclosed regions are the cells (`tools/pv_grid.py`). On a
good scan this yields all 20 fields with the correct cell counts, and
`tools/pv_fields.py` maps them by normalised position: the three data blocks are
columns read right-to-left as Arabic is, stage 1 on the right, stage 3 on the left.

**Classification does not.** `tools/harvest_digits.py` labels cells for free from
the 30 hand-verified pilot forms — their field values are known, so mapping
fields to cells labels each digit — giving 1,234 labelled digits in this corpus's
own handwriting. Best classifier on that set:

| | per-digit accuracy |
|---|---|
| SVM (RBF) | 83.8% |
| MLP | 82.9% |

A form carries 88 digits. At 84% per digit, a single field of four is right ~49%
of the time and a whole form essentially never is, so the seven consistency
checks would reject nearly everything. Reaching the ~99.5% per-digit accuracy this
needs would take thousands of labelled examples per class; the pilot yields 38–114
for each non-zero digit, and more labels cannot be bootstrapped without a
classifier that already works.

**Coverage is also uneven.** Over 400 random forms, grid detection recovered the
complete field set on only 31.2% (median 5 of 20 fields). The parameters that work
on a clean scan do not transfer across the corpus's range of contrast, skew and
resolution.

## 3. Reading in-session

The pilot's 30 readings were made by the model driving this session. Token cost is
not the binding constraint — the montage below brings a form to ~460 image tokens,
so 9,448 forms is a few million tokens. **Turn count is.** Even reading six forms
per message, full coverage is on the order of 1,500 messages. It is not reachable
in a session regardless of efficiency.

## What did come out of it

`tools/pv_montage.py` crops the located cells and tiles them one field per row.
The result carries the same 20 fields at **462 image tokens instead of ~2,410 for
the full page — a 5.2× reduction.**

Validated by reading two montages for bureaux with known values
(`09010810101`, `02010210103`): **40 of 40 fields correct**, including all three
candidate vote counts. The crops look distorted — thin digits get square-padded —
but nothing is lost.

For the API run that means roughly **$25 instead of $111**, on the ~31% of forms
where the field map is complete, falling back to the full page otherwise. Blending
those gives about **$85**. Making it pay across the whole corpus means generalising
the grid detection: scale the morphological line lengths to the detected cell
pitch rather than fixing them in pixels, deskew before detection, and retry with
relaxed thresholds when a column comes up short.

## Files

| file | what |
|---|---|
| `tools/pv_grid.py` | morphological grid detection and cell cropping |
| `tools/pv_fields.py` | maps cell runs to the 20 named fields by normalised position |
| `tools/pv_montage.py` | compact per-form digit montage (5.2× fewer tokens) |
| `tools/harvest_digits.py` | labels digits from the verified pilot forms |
| `tools/check_montage_coverage.py` | measures how often the field map completes |
