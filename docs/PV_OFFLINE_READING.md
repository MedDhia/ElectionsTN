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
| 245k, trained through a resolution round trip | 97.5% |
| 471k, harvested through the full reader | 97.6% |

The last two rows barely move that number, and the number is the wrong place to
look: it is measured on the pilot, which is 28 well-scanned forms, so it cannot see
the thing being fixed. Both changes target the degraded domain instead.

The resolution round trip puts half of each batch through a lower resolution and
back. The larger harvest is the same bootstrap loop run once more, but with the
harvest routed through the full reader rather than plain grid detection — which
matters only because registration now reaches forms with no recoverable grid, so
for the first time the training set contains cells from the scans the classifier
was worst on. It went from 245k cells over 5,359 forms to **471k over 8,799**.

What that fixed is visible in the aggregate rather than the accuracy. See below.

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

So each block is published on its own evidence, by either of two routes. A field
is published when the form's identities vouch for it on the **independent**
cell-by-cell reading — the same test `certify_cells` uses to label training data,
which is 99.5% correct at cell level. It is also published when the *decoder*
closes that block's identity having barely argued with the classifier there: at
most one cell overruled and under four nats conceded, counted over that block
alone. That is the standard whole forms are held to, applied to one account and
tightened, because a single account has far less redundancy behind it.

### Escalating to the right thing

The reader tries its passes in order and stops when the reading is good enough,
which makes the stopping condition load-bearing. Two versions of it were wrong in
opposite directions, and both cost coverage quietly.

Stopping once fourteen fields were certified leaves a form whose paper and ballot
accounts clear the bar while its votes stay unread — it never reaches the pass that
would have read them. That was the shape of most of what was missing: **1,342 of
1,506 unread stations had all twenty fields located**, cells found and a digit or
two read wrongly.

Stopping once all three accounts were certified is wrong the other way. Pass 1
often reaches that alone, so passes 2 and 3 never run — and on 191 forms one of
them would have produced a reading the identities accept *whole*. Those forms fell
back to block publication and lost every field outside the three accounts.

The condition is both: the form reads whole **and** all three accounts are in hand.
Readings are also ranked on how many accounts they would publish before how many
fields they touch, since a layout vouching for the votes is worth more than one
vouching for more fields of the accounts already held. Together these took whole
forms from 5,725 to 6,026 and certified votes from 8,154 to 8,264, with **no form
losing a reading it previously had**.

The second failure is worth recording because of how it hid: the number being
optimised — votes coverage — went *up* in the same run that lost the 191 forms. It
was visible only in a figure that was not the target, and only by diffing against
the previous dataset rather than reading the run's summary.

The second route matters because localisation stopped being the constraint. Of the
stations that were still unread before it, **1,342 of 1,506 had all twenty fields
located** — the cells were found and a digit or two was read wrongly, which is
precisely what the arithmetic exists to repair. On 372 of them the ballot account
was already certified and on 286 the paper account was, so the form was
demonstrably readable and only the votes block was failing. Where the whole form passes the joint gate it is published whole;
otherwise only the certified fields are filled and the rest are left empty.

Field values certified this way were correct in **255 of 255** cases on the pilot
forms, scored by a net that never saw them. Counting whole blocks rather than
fields, and including the decoder-backed route, every block the pilot publishes is
right: **66 of 66** backed by the raw reading and **11 of 11** backed by the
decoder. The decoder-backed sample is small, which is why its bound is the tight
one. Per block: votes certified on 15
pilot forms and right on 15, papers 16 of 16, ballots 10 of 10.

## The corpus

`tools/decode_all.py` publishes the whole form for 6,026 bureaux (63.8%) and
individual blocks for a further 2,239. **Candidate votes are vouched for at 8,265
of the 9,448 polling stations — 87.5%, and 82.1% of the national vote**, spanning
all 24 governorates and 277 of 279 delegations. Only 73 scans yield no field map at
all, against 1,389 before the form could be registered on colour.

Nothing in the pipeline knows the national result, so that result is an
out-of-sample test of the whole chain, on 100× more forms than the pilot:

| | Saied | Zammel | Maghzaoui | votes |
|---|---|---|---|---|
| official (ISIE) | 90.69% | 7.35% | 1.97% | 2,802,258 |
| **all rows with certified votes (n=8,265)** | **90.66%** | **7.11%** | **2.23%** | 2,300,265 |
| whole form decoded (n=6,026) | 90.92% | 7.07% | 2.01% | 1,641,011 |
| votes block only (n=2,238) | 90.00% | 7.22% | 2.78% | 659,079 |

Publication is gated rather than open because the ungated alternative was
measured: an earlier build that published every row it could read, without asking
the identities to vouch for it, put Saied at 83.20% and Maghzaoui at 6.03% over
7,606 rows — seven points out and triple, respectively.

The two kinds of row now agree closely on Saied — 90.85% decoded against 90.87%
from blocks — and within the 249 delegations carrying both, the paired median
difference is +0.06pp for Saied, -0.05pp for Zammel and -0.01pp for Maghzaoui.

### The drift, and what caused it

An earlier round of this work recorded an unexplained problem: as coverage rose
from 47% to 83% of bureaux, the aggregate moved *away* from the published national
result on the smaller candidates — Zammel from 7.21% to 6.90% against a reported
7.35%, Maghzaoui up to 2.24% against 1.97%. Three explanations were tested and none
held. The registration pass reproduced detection's readings exactly (121 of 121
forms, six key fields, zero disagreements); scan quality did not predict vote share
within delegations (a coin flip, 34 of 76); and coverage did not correlate with
Zammel's share across governorates (-0.05).

Retraining on the larger harvest closed most of it without touching the reader:

| | Zammel | Maghzaoui |
|---|---|---|
| reported nationally | 7.35% | 1.97% |
| before the larger harvest | 6.90% | 2.24% |
| **after** | **7.17%** | **1.99%** |

So the residual was classifier error on degraded crops after all — a small
systematic misreading of exactly the scans that registration had just made
readable, which the three tests could not see because all of them compared reading
*paths* against each other rather than asking whether the classifier had ever been
trained on that kind of image. It had not. The bias was in the training
distribution, and feeding the newly-readable forms back into it is what removed it.

The lesson generalises past this dataset: a self-certifying loop will happily
certify what it is already good at, and the labels worth harvesting are the ones it
currently cannot get. Two rounds of bootstrapping on easy cells bought nothing
(97.9% then 97.7%); one round that reached the hard ones fixed a bias worth 0.4
points of national vote share.

A caveat that belongs with all of the above: the national figures compared against
are the widely reported ones, not numbers sourced from ISIE — the Instance's own
results pages are the empty shells described at the top of this document. The
comparison is a sanity check of the right order, not a reconciliation to an
authoritative total.

## Is there a better scan to be had?

Two questions, with different answers.

**Does ISIE serve anything better than what was downloaded?** No. Fetching the
failing bureaux back from their published URLs returns files byte-identical to the
copies already held, and the PVs sit in a custom upload directory, so WordPress
generates none of its usual resized variants. The low-resolution scans are what
ISIE published; there is no higher-resolution original to go and get.

**Did ISIE publish more than one scan of the same form?** Yes, for 629 presidential
bureaux, filed under two polling-centre paths. Some of those are the same file
linked twice; others are genuinely different scans. The downloader kept one copy
per bureau — same basename, so the second was overwritten or skipped as cached —
and the reader had only ever seen whichever arrived.

`tools/retry_alternates.py` re-reads every bureau whose votes are not yet vouched
for and which has an alternative, keeping whichever scan the form's identities like
better. It replaced the cached scan for **174 of 364**, which is a high hit rate,
and yet moved coverage only from 6,260 bureaux to 6,320. The alternatives are
mostly better without being good enough to cross the bar — worth having, but not
the lever it first looked like.

It also surfaced a data bug. **14 presidential PVs are filed by ISIE under an
Arabic school name carrying no bureau code at all.** All 14 collapse onto one or
two cache keys, so at most two survive as files, and neither can be joined to a
polling station — the metadata lookup was attaching *some other station's*
geography to a real reading. They are now excluded rather than published wrong.

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
- **Training the classifier harder.** At 250 steps per epoch the net sees about
  two passes over the 473k self-certified cells, which looked like the schedule
  capping the labels rather than the labels running out. It is not: 800 steps —
  3.2x the compute — moves per-cell accuracy from 97.58% to 97.65%, one cell in
  1,490, and on 90 stations still without certified votes the two models certify
  the same votes and papers blocks and the longer one certifies two fewer ballot
  blocks. The net has converged; the ceiling is the crops and the labels.
- **Test-time augmentation.** Averaging predictions over five shifts moves
  per-cell accuracy from 97.58% to 97.72% — two cells — and recovers no stations.
- **Certifying a field because two layouts agree on it.** The reader produces
  several field maps per scan and classifies them separately, so agreement looks
  like independent corroboration. It is not: the layouts crop nearly the same
  pixels and repeat each other's mistakes. Fields not vouched for by an identity
  but agreed on by two layouts are **52% correct**, against 98% for
  identity-certified fields on the same forms.
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
| `tools/pv_template.py` | reference geometry, and registering a scan onto it by colour |
| `tools/pv_fields.py` | maps cell runs to the 20 named fields by normalised position |
| `tools/certify_cells.py` | labels cells using the form's identities as the annotator |
| `tools/digit_model.py` | the cell classifier: training, and holdout scoring against verified cells |
| `tools/pv_decode.py` | joint maximum-likelihood decoding under the identities |
| `tools/retry_alternates.py` | re-reads failing bureaux from the other scan ISIE published |
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
