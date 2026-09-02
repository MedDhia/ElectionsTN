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

### 3. Reading a whole field, not four cells

Every field on the form is four digit cells, and the cell classifier read them
one at a time. That throws away two things: a digit's neighbours constrain it
(leading zeros pad a four-cell field, so the shapes are not independent), and a
cell crop can clip a digit that a field crop would contain whole.

`tools/strip_model.py` reads the field in one pass — a single conv trunk over the
whole 4-cell strip with four digit heads, emitting exactly the `(n, 10)`
probability array the decoder already consumed, so it drops in behind
`FieldProbs` with a per-cell fallback for the fields that are not four cells.

Trained on **89,757 strips from 8,697 forms**, all self-certified by the
identities, withholding every strip from a pilot form: **98.91% per cell and
97.06% per field.** The cell reader is 97.58% per cell, which would be 90.67% per
field if its errors were independent — they are not quite, but the gap is the
point.

One caveat on that figure: the split is random over strips within the non-pilot
forms, so two strips from the same scan can land on both sides of it. It is
therefore optimistic as a per-cell number, and the honest test of the reader is
the pilot block check below, where the forms are withheld entirely.

Where it earns its place is the forms that were failing. On 70 stations with no
certified votes, the strip reader certified **114 accounts against 41** and
completed **21 forms against 2**.

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

### Does the gate keep its promise?

The claim a published block makes is that the form's own arithmetic vouches for
it. `tools/eval_blocks.py` tests that against the 30 forms read and verified by
hand, which are the only independent ground truth there is, using a reader that
never saw a pilot form — scoring a reader against forms it trained on is how an
early cell-classifier number came out 25 points too generous.

Of the **86 blocks** the reader publishes across those 30 forms, **86 are
correct**: 75 of 75 by the identity route and 11 of 11 by the decoder route. No
error was observed by either route.

That is not the same as no error. Thirty forms are a small sample, and zero
mistakes in 86 blocks puts the per-block error rate somewhere under about 3.5% at
95% confidence. What it does rule out is a gate that is quietly wrong at the
percent level, which is the failure that would matter.

### What the identities do not protect

The seven identities constrain the candidate **total**. They do not constrain the
**split**. `q == valid == zammel + maghzaoui + saied` is one equation in three
unknowns, so any redistribution among the three candidates that preserves the sum
satisfies it exactly as well as the truth does.

This is not hypothetical. Bureau 01080310102 was published as Saied 329, Zammel 85;
rereading it gives Saied 389, Zammel 25. Both sum to 414, both close every identity
on the form, and both were certified. Reading the scan by hand settles it — the
form says 389 and 25, in digits and again in words — but *the arithmetic cannot*,
because a 2/8 confusion in the tens column of two fields cancels in the total.

So the guarantee a published row carries is narrower than "the form vouches for
these numbers". It is:

- **turnout, papers and ballot accounts**: vouched for by the identities, which
  over-determine them.
- **the candidate total**: vouched for the same way.
- **the split between the three candidates**: vouched for only by the classifier.

The gate still helps here — a station whose candidate cells are illegible usually
fails to close the total either — but it is a weaker guarantee, and the codebook
now says so. Of 8,238 stations certified by both the previous build and this one,
66 changed a candidate value while keeping the same total.

There is a second channel on the page that ought to close this, and it was tried.
The form writes each candidate's score **twice**: once in digit cells and once
spelled out in Arabic words in the adjacent column (`ثلاثمائة و تسعة و ثمانين`
beside `0389`). The words are a redundant encoding of precisely the quantity the
identities leave unprotected.

`tools/harvest_words.py` and `tools/word_model.py` crop that column and read it
with the same architecture the digit strips use.

**The first attempt looked like a dead end, and it was a data limit.** Trained on
8,001 strips it read 89.6% of whole numbers, and this document said it did not
work. The label filter was the problem, not the idea: it demanded both that the
reading overruled no cell *and* that it conceded no likelihood, when the first
condition alone already guarantees the published values are what the classifier
read. Dropping the redundant half took the training set to 14,733 strips — 1.84x
— and whole-number accuracy from **89.6% to 96.4%**, per-digit from 96.7% to
98.8%.

Scored on the pilot, whose hand-verification pass happens to have transcribed the
words column as well as the digits, it now gets **82 of 90 exact against the cell
reader's 88 of 90**, up from 75.

The decisive figure is not either accuracy but what happens when they disagree,
since arbitrating disagreements is the entire purpose. They differ on 10 of the 90
scores — down from 17 — and **the words are right on 2**.

Those 2 are the whole reason to keep the idea alive rather than discard it. The
cell reader makes exactly two errors on the pilot — bureau 13010610202 reads
zammel as 207 against a true 7, and 05020810401 reads maghzaoui as 6 against a
true 5 — and the words channel catches **both**, before and after the retrain. So
it has perfect recall on real cell errors and 20% precision: it sees every error
and cries wolf eight times besides. Better data moved the precision from 12% to
20% and did not change the shape. There is still no weight at which it can be
mixed into the decoder that fixes the two without breaking more of the eight.

The lesson worth keeping is the one about the first verdict. "It does not work"
was recorded here on a model fitted to half the labels that were available,
because a redundant condition in the filter was silently discarding them. The
words are plainly legible by eye, which was the reason to suspect the model
rather than the idea — and the suspicion was right.

**So the channel is published as a flag rather than mixed into the decoder.**
Perfect recall with 12% precision is the wrong shape for overruling a value and
the right shape for marking one. `tools/flag_splits.py` writes
`split_corroborated`: 1 where the word reader agrees with all three published
scores, 0 where it does not, empty where the words could not be read. Corpus-wide
that is **7,083 corroborated, 1,776 contradicted, 111 unreadable** of the 8,970
rows with certified votes. Nothing is overwritten, so a weaker reader cannot
damage the dataset; a user who needs the split to be right gets a filter, and
restricting to the corroborated rows moves the aggregate by about 0.1pp.

The corpus figures are also a check on the pilot's. Words and digits disagree on
20% of stations here against 19% of the pilot's scores, so the pilot was not an
unusually easy or hard sample of the disagreement rate.

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

`tools/decode_all.py` publishes the whole form for 8,056 bureaux (85.3%) and
individual blocks for a further 978. A further **340 stations were read off the
scans by eye**, because the form draws `valid` and `q_declared` at about 23x24
against 56x38 for a candidate cell — on the 560px scans ISIE published for much of
Medenine that is roughly 8px against 20px, and two unreadable fields veto a form
however well its candidates are read. **Candidate votes are vouched for at 9,310 of
the 9,448 polling stations — 98.5%**, of which 8,970 (94.9%) come from the
reproducible pipeline; the codebook says how to filter the two apart. Reading those
340 hardest stations moved the national Saied figure by 0.04pp, which is itself
worth knowing: the missing stations were not where the aggregate was going to
change.

Of the 138 stations still missing, 27 were looked at by eye and left unread, and
the reasons separate into three kinds. Most have the information **physically
destroyed** — an ink blot over the total, a red validation stamp overprinting it,
pixelation that makes 3 and 4 inseparable. Two **never recorded it**, leaving the
candidate rows blank with only a total written; a blank box is not a zero, and
filling one in from the identity would make the check circular. And six **do not
balance**: 02020310202 has candidates summing to 320 against a `valid` of 319, and
08090510101 sums to 267 against 265 — on that one the offline pipeline had
independently certified the papers block at `valid = 265`, corroborating the
reading of the total. Digits and words agree with each other on every candidate on
those forms. They look like arithmetic errors in the original records rather than
reading failures.

The published rows span all 24 governorates and all 277
delegations that appear in the corpus. Only 20 scans yield no field map at all,
against 1,389 before the form could be registered on colour and 73 before the page
chooser was fixed.

| | Saied | Zammel | Maghzaoui | votes |
|---|---|---|---|---|
| widely reported national | 90.69% | 7.35% | 1.97% | 2,802,258 |
| **all rows with certified votes (n=9,310)** | **91.34%** | **6.77%** | **1.89%** | 2,567,356 |
| reproducible pipeline only (n=8,970) | 91.38% | 6.74% | 1.87% | 2,490,902 |
| whole form decoded (n=8,056) | 91.20% | 6.87% | 1.93% | 2,171,145 |
| votes block only (n=914) | 92.60% | 5.89% | 1.51% | 319,757 |
| read off the scans by eye (n=340) | 90.05% | 7.60% | 2.35% | 76,454 |

The last row is worth a second look. The 340 stations read by eye are the ones the
pipeline could not reach, and they break **90.05%** for Saied against 91.38% for
the stations it could — closer to the reported national figure, not further. That
is a small piece of evidence that the uncertified stations were leaning the way the
gap suggested, though 340 stations move the total by only 0.04pp.

**This table is a weaker check than an earlier version of this document claimed,
and the direction of travel says so.** A previous build agreed with the reported
national share to 0.03pp on Saied; this one, which is demonstrably the more
accurate reader, is 0.70pp away. Agreement got worse as the reading got better, so
the agreement was not measuring what it appeared to.

Two reasons, both structural. These forms are *محضر عملية الفرز داخل الجمهورية* —
counting records **from inside the republic**. The reported national total includes
out-of-country voting, which this corpus does not contain at all, so the two
quantities are not the same quantity. And the 493 stations still uncertified are
not a random sample: the 717 stations this run newly certified break 93.70% for
Saied against 91.15% for the ones already held, so the stations that are hard to
read lean measurably more one way than the corpus as a whole.

The comparison is retained because a gross failure would still show up in it — the
ungated build below is caught by exactly this test. It is not evidence that the
published rows reproduce the national result, and it should not be read as such.

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

Three questions, with different answers.

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

Run again after `pick_page`, on the 200 bureaux still uncertified that had a
second scan, it replaced **109** and moved certified votes from 8,955 to 8,970.
The same shape holds, and the two tools turn out not to be redundant: `pick_page`
had already registered every one of those 109 pages and preferred the one it kept,
so they are precisely the cases where the better-*fitting* page reads *worse*.
Geometry and legibility are different questions, and only the second one is the
one that matters.

It also surfaced a data bug. **14 presidential PVs are filed by ISIE under an
Arabic school name carrying no bureau code at all.** All 14 collapse onto one or
two cache keys, so at most two survive as files, and neither can be joined to a
polling station — the metadata lookup was attaching *some other station's*
geography to a real reading. They are now excluded rather than published wrong.

**Is the page being read even the counting record?** Not always — and this turned
out to be the single largest remaining cause of total failure.

741 of the presidential files are multi-page PDF bundles, and the page chooser
picked among them by masthead: the counting record scores 6-9 on the header words
while the accompanying paperwork scores 0-2, so the top scorer wins. Two shapes of
file defeat that rule.

A **correction decision** (قرار تصحيح محضر فرز) carries the same ISIE masthead as
the counting record, so it scores just as well. And some scans **inset the
landscape counting record in a portrait A4 page**, where the masthead is small
enough that the detector scores it 0 and the paperwork beside it wins on 2. Every
one of the 60 bureaux whose cached page had no recoverable grid and no second scan
came out of a bundle this way. The counting record was in the file the whole time.

Registration tells the two apart where the masthead cannot. Cropping a rendered
page to its ink and fitting it to the reference layout scores the counting record
at **0.93-0.96** and every other page in the bundle at **0.31 or below**; for
comparison, a page that already reads fits at 0.92-0.97. The crop is also the fix
and not merely the test, because an inset form sits outside the warp search's
capture range until the white margin is gone — these pages score 0.00
unregistered and 0.93 cropped. Rotation is decided by the same correlation, since
an inset form gives the masthead nothing to score.

This is *not* the bounding-box normalisation recorded below as a dead lever. That
one repositioned fields within an already-chosen page; this changes which page is
read, and rescales the form before the fit is attempted.

`tools/pick_page.py` registers every page of every scan held for a bureau and
keeps the best-fitting one, touching only bureaux whose votes are not yet
certified so nothing already published can be traded down. It swapped the page for
**108 of 1,183**. Re-reading exactly those: **60 votes blocks gained and none
lost**, papers +41/-1, ballots +37/-6 — 69 bureaux improved and 7 regressed.

The regressions are the point of `tools/confirm_pages.py`. Registration fit is a
geometry signal, not a legibility one, and the two come apart: bureau
23030110103 has a page fitting at 0.94 that certifies nothing beside a page
fitting worse that certifies the whole votes block. So any bureau that ends up
certifying fewer blocks than before has its previous page rebuilt and re-read,
and whichever certifies more is kept.

## What limits coverage

This section has been rewritten twice, because the answer kept turning out to be
something other than what was being measured. Both earlier answers were wrong in
the same way: they named whatever the pipeline was worst at, rather than checking
what the failing stations actually had in common.

The current answer, on the 493 stations without certified votes: **436 of them
locate all 20 fields.** The geometry is solved for seven failures in eight. What
fails is the reading — which is why the field reader above, and not another round
of grid tuning, is where the recent gains came from. Of the remainder, 17 produce
no field map at all, down from 73 once the page chooser stopped handing the reader
a correction decision instead of the counting record.

Grid detection is still what limits the hard tail, and the rest of this section
records that work. But it is no longer what limits the corpus.

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
| `tools/harvest_strips.py` | cuts whole 4-cell fields, with the form code kept for grouping |
| `tools/strip_model.py` | the field reader: one trunk, four digit heads |
| `tools/pick_page.py` | picks the page that registers as a counting record |
| `tools/confirm_pages.py` | undoes a page swap that cost a bureau a published block |
| `tools/retry_alternates.py` | re-reads failing bureaux from the other scan ISIE published |
| `tools/decode_all.py` | runs the corpus, writes the dataset with per-row provenance |
| `tools/eval_decode.py` | scores decoding against the hand-verified pilot |
| `tools/eval_blocks.py` | scores every published block against the pilot, by route |
| `tools/harvest_words.py` | crops the score written out in words beside each candidate |
| `tools/word_model.py` | reads that column; a flag, not an arbiter |
| `tools/eval_words.py` | scores the words against the pilot's own transcriptions |
| `tools/flag_splits.py` | writes `split_corroborated` into the dataset |

Reproducing from scratch, on four CPU cores:

```
python3 tools/harvest_digits.py                    # pilot labels, ~1.5k cells
python3 tools/digit_model.py fit                   # seed classifier
python3 tools/certify_cells.py --run               # ~245k self-certified cells
python3 tools/digit_model.py cv                    # honest holdout accuracy
python3 tools/digit_model.py fit                   # production classifier
python3 tools/pv_template.py build                 # reference form geometry
python3 tools/harvest_strips.py                    # ~90k whole-field strips
python3 tools/strip_model.py cv                    # honest, pilot-free accuracy
python3 tools/strip_model.py fit                   # production field reader
python3 tools/pick_page.py                         # fix the page choice where wrong
python3 tools/decode_all.py                        # the dataset
python3 tools/confirm_pages.py                     # undo any swap that lost a block
python3 tools/eval_blocks.py                       # block purity against the pilot
python3 tools/harvest_words.py --from-dataset       # the words column
python3 tools/word_model.py cv                     # grouped by form, pilot withheld
python3 tools/flag_splits.py                       # + split_corroborated
```

## The API route, kept for reference

`tools/extract_pvs.py` and `tools/pv_montage.py` implement the same extraction
through the Claude Batch API, costing about $93 for the corpus. They are no longer
on the critical path. The montage trick they use — cropping the located cells and
tiling them one field per row, 462 image tokens instead of ~2,410 for the full page
— was validated at 40 of 40 fields correct on two forms with known values.
