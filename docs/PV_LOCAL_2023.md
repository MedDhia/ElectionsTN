# Reading the 2023 local PVs at ballot-box level

The 2023 local-council election is the most granular thing in ISIE's archive and
the least published. Two files in this repository already carry what ISIE decided
— `data/local_2023_candidate_results.csv`, an OCR reading of the results
decisions, and `data/local_2023_constituency_turnout.csv` — and between them they
cover **938** and **1,120** of round one's local constituencies. The scan archive
indexed in `data/pv_index.csv` covers **2,127**, in **8,137** polling bureaux
across **12,195** files. Everything below that line — which bureau, which centre,
which box — exists only as handwriting on a scanned form.

This documents reading those forms offline, on CPU, with no paid API. It is the
same method as [the 2024 presidential read](PV_OFFLINE_READING.md), ported to a
different form, and the port is most of the interest: what carried over
unchanged, what had to be rebuilt, and what the new form makes possible that the
old one did not.

## What is different about this form

The presidential form splits its valid votes between three named candidates. The
local form splits them between **one to nine pre-printed ballot slots**, and how
many of them a constituency filled is not written anywhere on the form: the
unused ones are left blank or struck through with a pen. That single difference
propagates through the whole pipeline — the decoder cannot enumerate the split,
the slate has to be inferred before decoding, and the published file has to say
which slots mean anything.

Three things it makes *easier*. The form is landscape, which halves the
orientation question. It is a denser grid, which line detection likes. And it
carries **one more identity than the presidential form**: the slot votes sum to
the valid total, which is the single most useful statement on the page, because
it vouches for exactly the boxes that are hardest to read.

## The eight identities

Every number on the form is written one digit per cell in a printed grid, and the
grid is redundant. Writing the fields by the letters printed beside them:

| | identity | what it ties together |
|---|---|---|
| 1 | `c_signed == w_voted` | voters who signed the register = voters who voted |
| 2 | `match1 == c_signed − s_extracted` | signatures against papers drawn from the urn |
| 3 | `n_total == valid + blank + spoilt` | the papers counted, by kind |
| 4 | `match3 == w_voted − n_total` | voters against papers counted |
| 5 | `m_total == s_extracted + d_damaged + r_remaining` | the ballot account closes |
| 6 | `match2 == b_delivered − m_total` | papers delivered against papers accounted for |
| 7 | `q_declared == valid` | the declared result restates the valid total |
| 8 | `Σ slots == valid` | the candidate votes sum to the valid total |

The turnout count is therefore written five times and the valid total twice. That
is what makes the corpus able to label itself (§*Bootstrapping*) and what makes a
published row mean something more than a model's guess (§*Publishing per block*).

`tools/pilot_local_2023.py check` holds the hand-read labels to exactly these
eight, because a transcription that fails an identity the printed form has to
satisfy is a reading slip, not a discovery about the election.

## Which file, and which page, is the counting record

A bureau's bundle is one file for 7,073 of the 8,109, and several for the other
1,036 — and the extras are not extra pages of the counting record. They are the
pages of a *قرار تصحيح محضر فرز*, a decision naming a field of the record, the
value written in error and the value replacing it, filed under the same bureau.
The 2024 presidential corpus has the same thing for 388 of its bureaux.

Taking the first file was wrong for every one of those 1,036, and silently:
plain ASCII order puts the suffixed names first, because both `-` and a space
sort below `.`. One bureau in eight was handed a decision instead of a record,
the grid of a wholly different form was not found, and the only trace was a
`no_grid` count of 12%.

Nor does the name settle it. One bureau's `-C01-5.pdf` is a five-page record
bundle whose form is page one; another's `-C02-4.pdf` is a four-page correction
decision with no record in it at all. So the file and the page are chosen the
same way the rotation is: over every page of every file for the bureau, the
candidate whose field map is fullest wins, stopping at the first complete map —
which is the first page of the first file for the great majority. That took
`no_grid` from 12.1% to 4.0%.

Sixty bureaux hold a decision and nothing else. There is no counting record to
read for them, and they are published unread rather than guessed at.

## Standing the scan upright, without OCR

The scans arrive as PDFs and as JPEGs, from 600 to 2,500 pixels wide, and a third
of them are a quarter turn out. The 2024 pipeline settles orientation by OCR-ing
the printed masthead (`tools/pv_orient.py`). Here the form itself is the better
witness: it is landscape at 1.40:1, so the aspect ratio narrows the question to
one pair of rotations, and between those two the right one is simply **the one
where the field template maps more fields**. That uses the printed grid rather
than Tesseract, needs no language data, and scores exactly the quantity the rest
of the pipeline depends on. A tie means the grid was not found at all, and the
caller sees a field count of zero rather than a confident wrong answer.

`pv_local_2023.upright` hands its winning rotation's cell runs back to the
caller, because the next act is to map fields on precisely that image with
precisely those settings, and `pv_grid.find_cells` — two morphological passes
over a 1,600-pixel resample — is most of the cost of reading a form.

## Placing twenty-six fields when detection finds twenty

Grid detection alone maps all twenty-six fields on about a third of the corpus.
Registering the form against a template built from one cleanly-detected scan
(`pv_register.register`, an affine fit over the fields that *were* found) lifts
that to about nine in ten. Two form-specific corrections sit on top of it, both
in `pv_local_2023.placed`:

**Over-long runs are trimmed by alignment.** A vote box's detected run carries
the neighbouring group's printed slot number as a fifth cell. Left in, that
printed digit is read as part of the number. Which end to trim comes from the
template's own specs, because the vote columns are right-aligned — a three-digit
number fills the rightmost three cells and leaves the left one blank — while the
header fields are left-aligned.

**Short runs defer to the template entirely.** A run shorter than the printed
field means detection lost a cell, and reading the field off what is left drops a
digit: `0128` becomes `012`. The template knows where the missing cell is, so the
field is placed wholly from the template rather than padded, which would mix two
coordinate systems inside one field.

Afterwards, each field the registration *had to place* is nudged one step over a
3×3 neighbourhood to wherever the classifier reads it most surely
(`decode_local_2023.nudge`). Only those: a global transform leaves individual
blocks a few pixels out, which is enough to clip a digit, while a field the
detector found is already on its own printed box and moving it can only make it
worse. Confidence is a fair objective here precisely because it decides nothing
— whether the reading is published is settled afterwards by the form's
arithmetic, which a sharper crop can only help satisfy honestly.

Restricting the nudge was also the largest single speed-up in the pipeline.
Nudging all twenty-six fields was 79% of the cost of preparing a form; nudging
the one or two that needed it cut the corpus pass from hours to about twenty
minutes, and raised the share of bureaux with a certified vote block on the same
slice from 10.8% to 28.3% — because moving a correctly-detected field off its
box was doing harm as well as costing time.

## The slate is a property of the constituency, not of the form

How many of the nine slots are in play has to be inferred, and the temptation is
to infer it per form — which would make it a guess, and a different guess on
different bureaux of the same constituency. It is not a per-form quantity. A
constituency's slate is fixed; every one of its bureaux prints the same nine boxes
and fills the same prefix of them. So `decode_local_2023 slate` reads it off the
ink across **all** of a constituency's bureaux at once.

Ink is measured, not classified. How much of a normalised cell crop is dark is a
number no model is asked about, and over this corpus it comes out sharply
bimodal:

| per-field ink fraction | what it is |
|---|---|
| 0.03 – 0.09 | an unused box — never empty, because the crop still catches the printed rule and whatever the officer struck the box out with |
| 0.20 – 0.48 | a box carrying a number |

Under a tenth of the values fall between 0.10 and 0.20, so the threshold sits in
a valley rather than on a judgement call. A slot counts as filled when it carries
ink on most of its constituency's forms, so one faint strike-through or one stray
mark cannot move the slate.

"Across the constituency" is thinner than it sounds for a lot of them: of the
2,127 local constituencies in the index, 340 have a single polling bureau and 509
have two, so for two in five the vote is over one or two forms. The ink signal
carries it anyway — 0.05 against 0.35 is a seven-fold separation, not a close
call — and where it does not, the form says so rather than hiding it: a slot
wrongly dropped from the slate leaves the slot sum short of the valid total, the
vote identity fails, and the block is not certified. The failure mode of this
inference is a missing row, not a wrong one.

Nine is a hard ceiling, and the form imposes it rather than the code: three of
the 938 constituencies in the published candidate results fielded ten
candidates, and there is no tenth box to read. Their vote blocks cannot close
and are not certified.

The first cut of this used a threshold of 0.02 — the level at which
`pv_grid.digit_image` refuses to return a crop at all — and called 65 of 71
constituencies nine-candidate races. The measured distribution is what corrected
it, and the corrected answer looks like the election: mostly one to three
candidates, with a long thin tail.

## Solving the candidate split instead of searching it

`pv_decode.py` decodes a presidential form by enumerating the ways three
candidates can split a valid total. Nine slots at six plausible values each is
ten million combinations per candidate total, which is not a search worth
running.

So `pv_decode_local_2023._slot_split` solves it. Maximising the summed
log-likelihood of the slots subject to their total being the valid-vote count is
a knapsack, and a polling bureau's valid votes number in the hundreds, so a
dynamic program over partial sums is a few thousand steps. It keeps the **two**
best assignments per partial sum, so the runner-up survives to the end and the
log-likelihood gap between them can be reported: a wide gap means the votes were
essentially read rather than inferred.

It is also exact over the values considered, where the enumeration would have had
to be truncated.

Everything else in the decoder is imported from `pv_decode` unchanged — the pivot
search over the five-times-written turnout count, the ballot half, the
reconciliation offsets — because those parts of the form are the same instrument.

## Publishing per block, not per form

The form is three accounts that close separately, and they are published
separately:

- **ballots** — papers delivered, extracted, damaged, remaining (identities 5–6)
- **papers** — valid, blank, spoilt against the papers counted (identity 3)
- **votes** — the filled slots against the valid total (identity 8)

A form whose ballot accounting is unreadable can still have vouched-for votes,
and requiring the whole form before publishing any of it would throw those away.
Each block is certified only when its identity holds on the decoded reading *and*
the decoder did not have to overrule a cell inside it to get there.

One column sits across two blocks. `valid` is the one number the form states
twice, once as a total of paper kinds and once as a total of candidate votes, and
the vote identity has a blind spot the paper identity does not share: a
misreading that moves a candidate and the total together satisfies the slot sum
exactly, and nothing inside the vote block could ever say so. `valid_corroborated`
is 1 where both blocks certify — where `valid` survived two independent
statements of itself — and says so rather than leaving it to be assumed. This is
the same move `tools/cross_check.py` makes on the 2024 presidential file.

Every published row also carries what the form said about itself before any
correction: how many identities the raw cell-by-cell reading already satisfied
(`identities_ok`), how many cells the arithmetic had to overrule to reach a
consistent reading (`cells_corrected`), the likelihood given up doing so
(`logp_conceded`), and the gap to the next reading the identities also admit
(`margin`).

## Bootstrapping: hand-read once, then let the corpus label itself

Nothing here is trained on data anyone had. The sequence is:

1. `pilot_local_2023.py sample` draws a fixed-seed sample over the whole cached
   corpus and, for each form, lays out **the cells the pipeline actually placed**
   — enlarged, one field per labelled row. Reading the sheet therefore does two
   jobs: it produces labels, and it shows whether placement is on the right
   boxes, which a transcription from the raw scan would hide.
2. Eighteen forms read by eye, 1,434 cells, every one of them clearing the eight
   identities (`pilot_local_2023.py check`).
3. A cold-start CNN on those cells (`digit_model.py fit` with
   `DIGIT_SET=_local_2023`; the 2023 form is the same instrument photographed
   differently, so it wants the same architecture and its own weights).
4. `harvest_local_2023.py certify` reads every form in the corpus cell by cell
   with that net and checks the identities on the **raw** reading. Where one
   holds, the cells that produced it are almost certainly right: a three-term sum
   does not come out even when a digit has been misread, unless a second error
   compensates for it exactly. Pilot forms are excluded, so they stay a genuine
   holdout.
5. Retrain on the certified cells, and score honestly: `digit_model.py cv` trains
   on self-certified cells from forms **outside** the pilot and tests on the
   hand-read cells, so no form's handwriting appears on both sides of the split.

The unit of certification is the identity, not the form. At the per-cell accuracy
a cold-start net reaches, a whole form is right a percent of the time, so
certifying whole forms yields almost nothing, while any one identity involves a
dozen cells and holds far more often.

## Why the image work happens exactly once

Placement is the expensive half of reading a form — up to four passes of line
detection at 1,600 pixels, a registration fit, then the nudge — and three later
steps need the identical result: the slate inference, the certification loop, and
the decode. `decode_local_2023 prepare` does it once and stores each form's
normalised cell crops (`pv_local_2023.save_cells`), and the rest read those
arrays.

Caching the crops rather than the classifier's output is what makes the
bootstrapping loop affordable: retraining and re-decoding the whole corpus is
then one forward pass over arrays already on disk, not another pass over eight
thousand scans.

## What the pilot sheets showed about the placement

The sheets are a placement audit as much as a labelling tool, and three defects
showed up on them that no accuracy number would have named:

- **`q_declared` is a three-cell field, and on some forms its run is offset by
  one.** On bureau 11060710402 the crops read `003` against a valid total of 31.
  Identity 7 simply fails there and the reading falls back on the paper block;
  the failure is visible in `identities_ok` rather than silent.
- **A whole slot field can go unplaced.** On bureau 14091110101 the first three
  slots read 23, 3 and 69 against a valid total of 129, and slot 4 — which has to
  hold the missing 34 — came back as four blank crops. The slate is decided
  across the constituency, so one form like this cannot shrink the slate; the
  form's own vote block just does not certify.
- **The printed slot number bleeds into the leftmost cell of a neighbouring
  field.** Trimming handles the case where it arrives as a fifth cell, but a
  small printed digit sitting *inside* a legitimate cell is read as a digit. It
  would inflate a slot by thousands, which is exactly the kind of error identity
  8 rejects outright.

## What is on the form that this does not read

The candidate columns are printed three times over: the slot number, the
candidate's name written in by hand, the votes in Arabic words, and the votes in
digits. This reads the digits. Two things are therefore left on the table.

**The names.** They are handwritten Arabic in a narrow column, and resolving them
to candidates would need an Arabic handwriting model and a candidate register to
match against. Votes are published by ballot slot — "the order appearing on the
voting paper", which is all the form itself says about whose vote it was.

**The words.** Every vote total is also spelled out beside its digits, exactly as
on the presidential form, where `split_corroborated` uses the words to check the
split between candidates that the identities cannot constrain. The same check is
available here and is not yet made: the slot sum pins the total but not the split,
so the split still rests on the classifier. Reading the words would be the single
biggest improvement left.

## What this can and cannot be checked against

`data/local_2023_candidate_results.csv` and
`data/local_2023_constituency_turnout.csv` are OCR readings of ISIE's results
decisions, and their keys are Arabic governorate, delegation and constituency
names from those PDFs. A bureau is keyed by the eleven digits printed on its
form — subdivision, delegation, imada, constituency, centre, bureau — and the
only names the scans come with are folder names in the archive tree. There is no
crosswalk between the two, and inventing one out of two sets of OCR'd Arabic
names would be a worse measurement than the one it was checking.
`tools/audit_local_2023.py` therefore compares shape only: the number of
constituencies, the distribution of slate sizes, and the national totals.

It also quotes what the published extraction says about its own rows, which is
the one comparison a missing crosswalk does not block, because it needs no join.
Over its 1,202 round-one rows the ballot identity holds on 380 (32%) and the
candidate sum on 255 (21%); 694 rows carry at least one repaired or unpaired
figure, and 83 of the 969 rows that have both numbers report more voters than
registered. That is not a criticism of the extraction — those decisions are the
authoritative document, and a scanned PDF of a results table is a hard thing to
read — but it is the reason a bureau-level read from the primary paperwork is
worth the trouble: the forms carry eight identities that can be checked one row
at a time, and a results table carries one or two.

## Files

| | |
|---|---|
| `tools/pv_local_2023.py` | cached file → upright image; bureau-code arithmetic; the template; the cell cache |
| `tools/pv_fields_local_2023.py` | the 2023 geometry: 26 fields as normalised boxes, with alignment |
| `tools/pilot_local_2023.py` | field-crop sheets to read by eye, and the identity audit of what was read |
| `tools/harvest_local_2023.py` | pilot labels, then identity-certified labels from the corpus |
| `tools/pv_decode_local_2023.py` | joint decode under the eight identities, with the slot-split DP |
| `tools/decode_local_2023.py` | `prepare` → `slate` → `run`: the corpus pass and the published file |
| `tools/audit_local_2023.py` | per-form, per-constituency and against-published audits; the rollup |
| `data/verification/pv_local_2023_pilot.csv` | the eighteen hand-read forms |
