# Reading the presidential PVs with no model API

The 2024 presidential count exists in public only as 9,448 scanned *procès-verbaux*
— one per polling station, filled in by hand. ISIE publishes no machine-readable
results, so the scans are the only source. This documents the pipeline that reads
them offline, on CPU, with no paid API and no hand-labelling beyond the 30 forms
already read for the pilot.

## What does not work

**Reading the results off the website.** ISIE's results pages are still served —
`/resultats-finaux-<governorate>/`, `/ar/presidentielle-2024-resultat-preliminaire/`
— but they are navigation shells of ~70 KB: no tables, no canvas, no iframes, no
data links. The theme's `custom.js` contains no call that would fetch results, and
the only endpoints in the page are WordPress and analytics boilerplate. The content
was rendered client-side and is gone.

**Reading each cell and believing it.** Every number on the form is written one
digit per cell in a printed grid, so segmentation is a line-detection problem
rather than a handwriting one, and it works (see *Segmentation* below). But a form
carries 88 digits. Even at 98% per cell — better than anything the 30 pilot forms
alone can train — the expected form has two misread digits in it, and a
cell-by-cell reading of the whole corpus would be wrong somewhere on most forms.

**Reading the forms in-session.** The pilot's 30 readings were made by the model
driving the session. Token cost is not the constraint; turns are. Even at six forms
per message, 9,448 forms is on the order of 1,500 messages.

## What works: the form is an error-correcting code

The PV is not twenty independent numbers. The turnout count is written **five
times** — ballots extracted from the urn, voters who signed the register, voters
who voted, the sum of valid, blank and spoilt papers, and again through the
reconciliation rows tying those together. The valid-vote total is written twice,
and the three candidate scores must sum to it. Twelve of the twenty fields are
determined by the other eight.

That redundancy does two jobs.

### 1. It lets the corpus label itself

`tools/certify_cells.py` reads a form cell by cell, then checks the identities on
that raw reading. Where an identity holds, the cells that produced it are almost
certainly right — a three-term sum does not come out even if a digit was misread,
unless a second error compensates exactly.

The move that makes this work is certifying **parts** of a form rather than whole
forms. At 94% per cell a whole form is right about 1% of the time, so whole-form
certification yields almost nothing; a single identity involves about sixteen
cells and holds far more often. Harvesting per identity instead of per form turns
a 1% yield into 42%.

Measured against the pilot's hand-checked labels, by a classifier that never saw
the form it was scoring:

| | cells | correct |
|---|---|---|
| all cells, uncertified | 1,490 | 93.7% |
| cells the form's own arithmetic vouches for | 624 (41.9%) | **99.5%** |

Run over the corpus that produced **245,748 labelled cells from 5,359 forms** —
165× the pilot's 1,490, and 7,200–20,000 examples of every digit where the pilot
had 47–140 of some. Retraining on them, and scoring against the pilot's verified
cells with a net that saw **no human label at all**:

| training set | per-cell accuracy on verified cells |
|---|---|
| 1,490 hand-checked cells | 93.7% |
| 185k self-certified cells | **97.9%** |
| 245k self-certified cells (round 2) | 97.7% |

One round of bootstrapping cuts the error rate by two thirds. A second round adds
labels but not accuracy — the difference is three cells in 1,490 — so the loop is
run once and stopped.

### 2. It corrects what is left

`tools/pv_decode.py` decodes the form jointly rather than cell by cell: it pivots
on the count written five times, so every candidate value is scored by all five
readings at once and a misread digit is outvoted rather than believed. The four
reconciliation rows stay free variables rather than being pinned to zero — they
are zero on all 30 pilot forms, but one form records a genuine discrepancy, and
forcing it to reconcile would turn a truthful record into a wrong reading.

Each published row carries what the form said about it: how many identities the
independent reading already satisfied, how many cells the arithmetic had to
overrule (`cells_corrected` — the syndrome weight), and the likelihood conceded to
reach consistency.

Against the 28 pilot forms whose grid could be read, scored on all 18 constrained
fields, exact match required:

| | forms | exactly right |
|---|---|---|
| cell-by-cell reading | 28 | 35.7% |
| joint decoding | 21 decoded | 76.2% |
| joint decoding, `fields_read >= 18` and `cells_corrected <= 3` | 16 kept | **100%** |

Both gate terms earn their place. `cells_corrected` catches the form where the
grid detector split a four-cell box: the decoder had to overrule six cells and
concede 26 nats to make the arithmetic close, far outside the range of any correct
form. `fields_read` catches the opposite failure — a form so incompletely detected
that few identities applied, where a small correction count means only that there
was little to contradict.

## Publishing per block, not per form

The PV is three self-contained accounts, each closed by its own identity: the
ballots delivered and returned, the papers found in the urn, and the votes cast
for each candidate. Requiring the whole form before publishing any of it throws
away the accounts that *are* vouched for on a form whose others are not — which,
on this corpus, is about 1,900 polling stations' candidate votes.

So each block is published on its own evidence. A field is published when the
form's identities vouch for it on the **independent** cell-by-cell reading — the
same test `certify_cells` uses to label training data, which is 99.5% correct at
cell level. Where the whole form passes the joint gate it is published whole;
otherwise only the certified fields are filled and the rest are left empty.

Field values certified this way were correct in **255 of 255** cases on the pilot
forms, scored by a net that never saw them. Per block: votes certified on 15
pilot forms and right on 15, papers 16 of 16, ballots 10 of 10.

## The corpus

`tools/decode_all.py` publishes the whole form for 4,426 bureaux (46.8%) and
individual blocks for a further 2,752 (29.1%). **Candidate votes are vouched for
at 6,260 of the 9,448 polling stations — 66.3%, and 63.1% of the national vote**,
spanning all 24 governorates and 273 of 279 delegations.

Nothing in the pipeline knows the national result, so that result is an
out-of-sample test of the whole chain, on 100× more forms than the pilot:

| | Saied | Zammel | Maghzaoui | votes |
|---|---|---|---|---|
| official (ISIE) | 90.69% | 7.35% | 1.97% | 2,802,258 |
| **all rows with certified votes (n=6,260)** | **90.41%** | **7.19%** | **2.39%** | 1,767,829 |
| whole form decoded (n=4,426) | 90.70% | 7.22% | 2.09% | 1,197,247 |
| votes block only (n=1,834) | 89.82% | 7.15% | 3.03% | 570,582 |

Publication is gated rather than open because the ungated alternative was
measured: an earlier build that published every row it could read, without asking
the identities to vouch for it, put Saied at 83.20% and Maghzaoui at 6.03% over
7,606 rows — seven points out and triple, respectively.

The block-only rows sit 0.9pp below the whole-form rows on Saied's share and half
a point above on Maghzaoui's. That is composition rather than drift: the two sets
are different polling stations, and compared *within* the 217 delegations that
carry both, the paired median difference is -0.08pp for Saied, -0.03pp for Zammel
and -0.01pp for Maghzaoui. Pooled national shares should be read with that in
mind — the subsets are not interchangeable, even though neither is biased against
the other.

### Placing the fields that detection missed

`pv_fields.map_fields` accepts a column of the form only when every field in it is
detected. On a clean scan that costs nothing. On a degraded one it throws away most
of what was recovered — one failing form yielded seven runs at exactly the right
normalised positions and kept three, because no column was complete.

`tools/pv_register.py` treats the runs that *were* found as landmarks: it matches
them against their known positions in a reference form, fits a transform, and
places the fields that were missed. Registering on detected cells is what makes
this work. Aligning two scans by image correlation instead scores well — 0.87 on
grayscale — while missing the cells by several pixels, which is enough to crop the
wrong ink; of 40 forms registered that way, 35 decoded and 1 passed the gate.

Where both a detected and a placed layout exist, the form chooses: a reading its
own identities accept beats one they do not, and among those, the one that needed
least correcting. Offering the placed layout unconditionally is worse than not
offering it at all — it cost 7 of 120 already-published forms while gaining 8 of
100 near-misses, a net wash that trades verified rows for unverified ones.

Selected this way it is a clear gain and costs nothing already held: **120 of 120**
published forms survive it, the pilot gate goes from 15 forms to 16 at 100% exact,
and the corpus goes from 3,293 published rows to 3,884.

Two further passes run only when the one before leaves something unresolved, so
their cost falls on the scans that need them.

**Refining each placement locally.** One transform fitted over the whole form
leaves individual blocks a few pixels out — enough that a crop clips its digit or
catches the neighbouring one. Each field is nudged over a one-step neighbourhood
and the offset the classifier reads most surely is kept. Confidence is a fair
objective here because it decides nothing: whether the row is published is still
settled afterwards by the identities, which a sharper crop can only help satisfy
honestly. On forms that published nothing, this takes certified votes from 0 in
100 to 12 in 100, and on the pilot it takes certified field values from 255 of 255
correct to **274 of 274**. Widening the search to two steps is worse, not better:
it finds offsets that are confidently wrong and certifies fewer blocks.

**Retrying the other three rotations**, for scans the orientation detector called
wrong. Worth about 2% of what is otherwise unreadable.

One bug was found along the way and is worth recording, because its failure mode
was silence. `digit_image` sliced the image without clamping, so a cell placed
partly off the page did not raise — numpy wrapped the negative index and returned
a crop of the *opposite edge*. Seven forms crashed outright, which is the only
reason it surfaced; how many others were read from the wrong pixels cannot be
recovered from the output.

## The pilot had an error, and the pipeline found it

Bureau `04010310201` was recorded in the pilot with `b_delivered = 1189`. That
reading failed the form's own `match2` check — `b - m = 0` requires `b = s+d+r =
1199` — which is exactly what the check is for. The offline reading of that box
also gives 1199. The pilot record is corrected in `data/pv_pilot_2024.csv`, which
now passes 29/30 with no failures (one form has two boxes left blank on the paper,
so two of its checks are untestable).

## What limits coverage

Not the classifier, and not the decoder — grid detection. The decoder needs the
printed rules recovered well enough to locate the fields.

Failure tracks resolution: among forms where 18 or more fields are located the
median scan is 1600px wide and the 10th percentile 1200px; among failures the
median is 1130px and the 10th percentile 768px.

**But resolution alone is not the cause, and an earlier version of this document
was wrong to say it was.** Taking forms that read perfectly at 1600px and
downsampling them still locates a mean of 14.9 fields at 868px, and 20 of 27 still
decode — where *real* 868px scans yield about 3. Something other than pixel count
separates them. Re-encoding the downsampled image as JPEG at that size accounts for
part of it (13.4 fields at quality 88, 9.1 at quality 60 — the printed rules are
red, which is what chroma subsampling degrades most), but not all of the gap.
Sharpness and contrast, measured at a common width, are indistinguishable between
the two groups. The residual is uncharacterised; it is not explained by anything
measured here.

What that changed is where the effort went. Since the scans were not the whole
story, the field *locator* was worth attacking, and that is where the gain came
from — see *Placing the fields that detection missed* above.

Things tried against it that did not work, recorded so they are not tried again:

- **Detecting at a fixed working width** and mapping cells back. This one worked —
  only 48.5% of the corpus is 1600px and a fifth is under 900px, where cells fall
  below the size thresholds outright. It took the median from 5 fields to 11.
- **A four-setting retry ladder** on the threshold and kernel sizes. Also worked:
  31.2% complete field maps to 40.2%.
- **A parameter sweep aimed squarely at the low-resolution failures** — two working
  widths, three opening-kernel sizes, three block sizes, two offsets, with and
  without unsharp masking, 72 combinations over 45 failing scans. The best
  combination located a mean of **1.6 fields out of 20**.
- **Extracting the rules from a colour channel rather than luminance.** The printed
  rules are red, so grayscale conversion should be throwing contrast away. It does,
  but not usefully: blue gave 3.6 mean fields against grayscale's 3.0, and 8% of
  failures reaching 14 fields against 0%. Saturation collapsed entirely.
- **Deskewing.** Skew here has a median of 0.00° and a maximum of 1.14°; a
  Hough-based correction improved three forms and worsened three.

One real loss was recoverable. The upright cache was built for the API route with
a 1,600px long-edge cap, chosen to control image-token cost — which threw away
resolution on scans that had more, and is pure loss for an offline pipeline that is
compute-bound rather than token-bound. Rebuilding the 743 affected failures at
native size, and re-rendering PDF sources at 350 dpi instead of 200, recovered
123 more readable forms.

Normalising field positions to the form's own bounding box rather than the page was
also tried, on the theory that scans where the form does not fill the frame would
misplace every field. It changed the completion rate by under one point: the forms
that fail do not fail for that reason.

## Files

| file | what |
|---|---|
| `tools/pv_orient.py` | masthead-based orientation detection (30/30 vs tesseract OSD's 21/30) |
| `tools/pv_grid.py` | morphological grid detection and cell cropping |
| `tools/pv_register.py` | places missed fields by matching detected runs to the template |
| `tools/pv_template.py` | builds the reference geometry; also the failed pixel-registration route |
| `tools/pv_fields.py` | maps cell runs to the 20 named fields by normalised position |
| `tools/certify_cells.py` | labels cells using the form's identities as the annotator |
| `tools/digit_model.py` | the cell classifier: training, and holdout scoring against verified cells |
| `tools/pv_decode.py` | joint maximum-likelihood decoding under the identities |
| `tools/decode_all.py` | runs the corpus, writes the dataset with per-row provenance |
| `tools/eval_decode.py` | scores decoding against the hand-verified pilot |

Reproducing from scratch, on four CPU cores:

```
python3 tools/harvest_digits.py                    # pilot labels, ~1.5k cells
python3 tools/digit_model.py fit                   # seed classifier
python3 tools/certify_cells.py --run               # ~245k self-certified cells
python3 tools/digit_model.py cv                    # honest holdout accuracy
python3 tools/digit_model.py fit                   # production classifier
python3 tools/pv_template.py build                 # reference form geometry
python3 tools/decode_all.py                        # the dataset
```

## The API route, kept for reference

`tools/extract_pvs.py` and `tools/pv_montage.py` implement the same extraction
through the Claude Batch API, costing about $93 for the corpus. They are no longer
on the critical path. The montage trick they use — cropping the located cells and
tiling them one field per row, 462 image tokens instead of ~2,410 for the full page
— was validated at 40 of 40 fields correct on two forms with known values.
