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
that is **7,083 corroborated, 1,776 contradicted, 111 unreadable** of the 8,977
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
individual blocks for a further 978. A further **447 stations were read off the
scans by eye**, because the form draws `valid` and `q_declared` at about 23x24
against 56x38 for a candidate cell — on the 560px scans ISIE published for much of
Medenine that is roughly 8px against 20px, and two unreadable fields veto a form
however well its candidates are read. **Candidate votes are vouched for at 9,417 of
the 9,448 polling stations — 99.7%**, of which 8,977 (95.0%) come from the
reproducible pipeline; the codebook says how to filter the two apart. Reading those
447 hardest stations moved the national Saied figure by 0.05pp, which is itself
worth knowing: the missing stations were not where the aggregate was going to
change.

## The blank cell the reader read as a seven

Every identity in this project asks whether a set of numbers is consistent. None
of them asks whether a number is *possible*. That gap held a systematic error for
the life of the corpus.

Across the published dataset, 120 values exceeded 1,500 — and every single one
began with a 7. Twenty-one extracted-ballot counts, twenty signed-voter counts,
eleven Saied figures. Meanwhile the largest `valid` among the readings the pattern
spared, across 9,392 stations, is 662, and the largest `saied` is 628.

The scans say what happened. The four-digit fields are four separate cells, and a
clerk who counts 403 valid ballots writes `403` and leaves the leftmost cell
**empty** rather than writing `0403`. The classifier has no class for an empty
cell, so it emits its nearest guess, and its nearest guess for blank paper is a 7.
A wholly blank field comes back as `7777`, which is how five of them read.

**The votes gate passed all of it.** Bureau 02090610103 was published as Saied
7357 against a valid of 7403, and 41 + 5 + 7357 = 7403 exactly. The form says 41 /
5 / 357 against 403. Eleven certified rows carried an inflated Saied figure this
way — 77,000 votes, 3.2% of his certified total — because the artefact lands on a
candidate and on the total together and the identity that gates the row cannot
tell the difference.

`tools/fix_leading_seven.py` repairs it, and the repair is not a guess. Stripping
the spurious digit is accepted only where doing so makes the form's identities
close and leaving it does not, or where the published value is beyond anything the
column reaches anywhere else in the corpus — a station with 7,403 valid ballots is
not a competing hypothesis but an impossible one. The ceilings are measured per
column from the readings the artefact spared, so `a_registered` and `b_delivered`,
which legitimately reach 2,137 and 2,100, keep their large values. All 56 affected
bureaux were repaired on one of those two grounds, and five were checked against
the scans by eye first.

| | before | after |
|---|---|---|
| certified votes | 2,603,057 | **2,526,057** |
| Saied | 2,377,380 (91.33%) | **2,300,380 (91.07%)** |
| Zammel | 6.78% | **6.99%** |
| Maghzaoui | 1.89% | **1.94%** |

The corrected share is 0.38pp from the reported national figure where the
uncorrected one was 0.64pp away. That is not proof, but it is the direction an
error correction should move it.

`tools/cross_check.py` now carries the guard as a standing check rather than a
one-off: it warns on any published value a polling station could not have
produced. And it publishes `valid_corroborated`, which checks `valid` against the
ballots column — the second identity that could have caught this from the start.

## The corrections the archive already made

The counting record is not always ISIE's last word on a station. 388 bureaux are
filed with a *قرار تصحيح محضر فرز*: a three-column table of **الخانة / الخطأ /
الإصلاح** — the field, the value recorded in error, the value replacing it — with
a tick-box per field and a section for the three candidates by name. Where one
exists, publishing the counting record unchanged publishes the figure the
commission struck out.

This project read the counting record and ignored the decision beside it for most
of its life. All 388 have now been read, and the 328 whose table carries anything
are in `data/verification/corrections.jsonl`, field by field.

**A decision that changes a candidate cannot be caught by the arithmetic gate.**
The counting record closed before the correction and closes again after it, so
such a row passes every check and is wrong anyway. 29 decisions touch a candidate
figure. 08090510101 is the plain example: the record says Saied 265, the decision
says 263, and nothing in the form's own arithmetic objects.

`tools/apply_corrections.py` applies a correction only where the error value the
decision names is what the dataset already holds. That middle column is what ties
a decision to a row, and the check earns its place: bureau 120611101's bundle
holds a decision whose own header codes the station 12-06-11-1-01-01 while the
archive files it under a nine-digit code, and the row under that code holds a
valid of 318 against the decision's 418. Every error value fails to match and
nothing is written. 93 fields are *already* at the corrected value — the clerk
struck the wrong figure out on the record as well as issuing the decision, and the
reader picked up the amended number, which is the pairing check confirming itself.

A decision is also applied whole or not at all, and never if applying it would
stop a row balancing. Six fail that test, moving a candidate or a total without
moving the other; none of the six is applied, and the `correction` column marks
those rows `held` so that anyone using their figures can see the commission
superseded them.

Two of the corrections caught reading errors of ours rather than the clerk's.
01170110302 was published as 36/16/299 against a valid of 351, which closes — but
on the extracted-ballots figure, not the valid one; re-reading its heavily
overwritten form against the decision gives 36/16/288 against 340. 04080310104 was
one too high on both the third candidate and the total. Neither would have been
found without the decision.

The decisions also gave back stations the scans could not. 14030610201's candidate
table is blank on a complete scan — there was nothing to read — and its decision
fills all three rows, 1 / 1 / 211, against the 213 the form states as valid.
08040710203, read as 11/2/135 with no words column to check it against on the
reasoning that the writer draws 1 as a caret, has all three rows ticked in its
decision and written out as 11 / 2 / 135. And 04080410201 settles a judgment the
other way: it was published as 30/9/355, choosing the digit reading of thirty over
the Arabic word thirty-one because thirty was what closed against a valid of 394,
and its decision puts the declared total at 395.

## The ballots column, read for every station it could be read for

`valid_corroborated` only means anything where the ballots column is published, and
after the corrections pass 727 rows still rested on the votes identity alone. All of
them are stations read by eye, where the earlier passes had transcribed the candidate
rows and stopped. So the ballots column was read for them too.

`tools/papers_sheets.py` lays six of those blocks to a sheet, cropped to the four
rows (س) / (ص) / (ع) / (ف) and nothing else, and a recorder refuses any reading that
does not satisfy `س == ص + ع + ف` **and** whose (ص) does not match the `valid`
already published from the candidate pass. A reading has to agree with two things it
was not derived from before it is written down; where it could not, the station was
left alone rather than guessed at. That happened on about a sixth of them — a faint
photocopy, a cell overwritten twice, a 3 and a 9 that no crop could separate.

**281 stations gained a papers block.** Coverage of `papers_certified` went from
8,826 to **9,107**, and the rows whose total is backed by both identities from 8,666
to **8,946** — 94.7% of the dataset, leaving 447 rows on the votes identity alone.

Two of those readings did more than corroborate. Bureaux 21110210301 and 23061210101
were both non-balancers: the form's (ص) cell states a number the candidates do not
sum to (388 against 361, and 265 against 244), and a correction decision had already
been applied to each. The ballots column settles them independently and in the same
direction:

```
21110210301   388 extracted = 361 valid + 13 blank + 14 spoilt
23061210101   265 extracted = 244 valid +  5 blank + 16 spoilt
```

In both, the number in the (ص) cell is the *extracted* count written a second time,
and the candidate sum is the valid count. That is a clerical slip a person makes and
an arithmetic check cannot see — the votes identity has nothing to say about it —
and it is exactly what the second identity is for.

## The identity that certifies a blank page

Every gate in this pipeline is the form's own arithmetic, and one of those
identities has a solution that is not a reading at all.

`zammel + maghzaoui + saied == valid` closes when all four are zero. A page with
no candidate table on it — the **polling** record (محضر عملية الاقتراع) rather
than the **counting** record (محضر عملية الفرز) — presents four empty fields, the
reader emits 0 for each, and `0 + 0 + 0 == 0` closes exactly. The gate cannot tell
that from a station where every voter chose the same candidate; it sees an
identity satisfied and certifies.

**Ten stations were published that way**, with all three candidates on zero. The
bug is not in the reader, which did what it could with the page it was handed; it
is in trusting an equation that a blank page satisfies as well as a real one.
Reading the ten by eye:

| | what the archive holds |
|---|---|
| 6 | only the polling record — the candidate counts are not in the bundle |
| 3 | a counting record the pipeline had missed: one scanned mirror-image, one landscape, one simply misread |
| 1 | a counting record whose candidate table falls outside the scanned area |

`tools/fix_zero_rows.py` restores the four recoverable rows from the scan —
03020510204 as 7/2/319 of 328, 07050510101 as 3/1/104 of 108, 04050210207 as
7/4/330 of 341, and 11040610202's papers and ballots without its votes — and
withdraws the six that have no counting record, recording each in
`data/verification/unreadable_scans.jsonl`. Every restored row is checked against
all three identities before it is written; the tool refuses to write one that does
not close.

`tools/decode_all.py` now refuses to certify any block whose fields all read zero,
so the degenerate solution cannot certify a station again. No polling station casts
zero valid votes *and* is delivered zero ballots; withholding such a reading costs
nothing real and stops the pipeline blessing a page it never read.

Candidate votes go from 9,424 to **9,417** — six withdrawn, one de-certified for
its votes and kept for its papers — and the national shares do not move at two
decimal places: **91.07% / 6.99% / 1.94%** before and after. That is the point
worth keeping. Ten rows of zeros were invisible in the aggregate and wrong in the
dataset, and only reading the scans found them.

## The split the identity was never watching

`zammel + maghzaoui + saied == valid` is one equation in four unknowns, and it
catches a misread candidate only when nothing else in the same equation moves to
match it. Two shapes of matching error survive it whole:

- **the candidate rows transposed.** Rows 2 and 3 of the table are Maghzaoui and
  Saied. Read in the wrong order the total is untouched, so the identity closes
  exactly and the row certifies.
- **the same leading-digit slip in two fields.** Drop the leading 3 from `saied`
  and from `valid` and 29 + 6 + 19 == 54 closes — three hundred votes short.

The words column beside the digits is the only channel on the page that is
independent of the digit cells, and `split_corroborated == 0` flags 1,768 rows
where the two disagree. That is too many to read and mostly single-digit noise,
so `tools/screen_split_errors.py` narrows it with three tests, any one of which
puts a row in front of the eye: the ballots column contradicting `valid` by 50 or
more, an implausible winner's share, or a `valid` far off its own polling
centre's median. **49 rows.** Reading all 49 found eleven wrong and cleared 38 —
including every 100%-for-Saied station on the list, which are simply small and
real.

| | station | published | the form and its words |
|---|---|---|---|
| rows 2/3 transposed | 03070410202 | 11 / 178 / 2 | 11 / 2 / **178** |
| | 03070510201 | 19 / 359 / 5 | 19 / 5 / **359** |
| | 06090610201 | 4 / 184 / 4 | 4 / 4 / **184** |
| | 11010510101 | 7 / 468 / 5 | 7 / 5 / **468** |
| a hundred traded | 13030310101 | 111 / 6 / 70 | **11** / 6 / **170** |
| split simply wrong | 23010310102 | 13 / 80 / 15 | 13 / **2** / **93** |
| slip in candidate *and* total | 05080810101 | 206 of 207 | **207** of **208** |
| | 23040510301 | 19 of 54 | **319** of **354** |
| | 23090710308 | 0 of 9 | **70** of **79** |
| | 24051110101 | 139 of 140 | **39** of **40** |
| (س) contradicted by three fields | 07070710102 | extracted 31 | extracted **231** |

`tools/fix_split_errors.py` applies them, taking the Arabic words as the
authority and refusing to write any row that then fails an identity. Net across
the eleven: **Saied +1,622, Maghzaoui −1,251, Zammel −100**. National shares move
from 91.07 / 6.99 / 1.94 to **91.12 / 6.98 / 1.89**.

Four transpositions in a screen of 49 is the finding that matters, because the
screen only sees rows the words already flagged and only the extreme end of
those. The transposition is invisible to every identity on the form, and the
codebook says plainly that the split rests on the classifier alone. This is what
that sentence costs.

## Widening the screen: are there more transpositions?

Four transposed candidate rows came out of a 49-row shortlist, which is no way to
search 9,417 stations and no basis for saying whether more exist. The honest
version of the question is: read the words for **every** station, keep the values
rather than the agreement bit, and see whether any station's three numbers are
right but assigned to the wrong candidates.

`tools/harvest_word_values.py` does that — the same reader `flag_splits.py` uses,
writing what it read to `data/verification/word_readings.jsonl`. **9,279 of the
9,417 certified stations** have a words column both readable and complete.
`tools/screen_transpositions.py` then compares the two channels per candidate.

A transposition has an unmistakable signature: the **multiset** of three values is
correct and the assignment is not. That is not a mistake a 3.6% whole-number error
rate makes by accident — it would need two specific compensating errors on one
form.

```
PERMUTATION — the three values are right, the order is not   0
PAIR SWAP   — two candidates hold each other's value          0
```

**Zero, across 9,279 stations.** The four already found were all there were.

A screen that reports nothing is worth exactly what its sensitivity is worth, so
`--control` re-runs the test against the six rows already known to have been
wrong, using the digits as they stood before they were corrected:

| station | was | words | verdict |
|---|---|---|---|
| 03070410202 | 11/178/2 | 11/2/178 | **PERMUTATION** |
| 03070510201 | 19/359/5 | 19/5/359 | **PERMUTATION** |
| 06090610201 | 4/184/4 | 4/4/184 | **PERMUTATION** |
| 11010510101 | 7/468/5 | 7/5/468 | **PERMUTATION** |
| 13030310101 | 111/6/70 | 11/6/170 | large disagreement, off by 100 |
| 23010310102 | 13/80/15 | 13/2/93 | large disagreement, off by 78 |

Every transposition is caught as a permutation and the other two are caught by the
size of the gap. The screen finds the class it claims to find.

### The test that does not use the words

138 stations had no readable words column, and a transposition could in principle
hide behind a word reader that also erred. So the screen carries a third test that
never consults the words at all: **a candidate whose share is far above the median
of the other stations in his own polling centre.** A transposition hands one
candidate another's votes, which in a centre of three or more stations is
conspicuous.

One station is flagged, and it is real: 02080310101 in حمام الشط gives Maghzaoui
70 of 396 against a centre median of 2.9%. Its words agree exactly (9/70/317),
every identity closes, and both corroboration flags are set. Some places simply
voted differently.

### What the disagreements actually are

452 stations disagree by 25 votes or more on some candidate, which sounds alarming
until you look at them. 81 are the **words** reader dropping leading digits
(`518` read as `8`, `509` as `5`). Six more were drawn from the rest and read by
eye: 01100110101, 01130810102, 01151110105, 01210610203, 05070810401 and
10130310201 — in all six the published digits are right and the word reader is
wrong, misreading أربعمائة وسبعة as 107, مائتان as 6, خمسمائة وثمانية عشرة as 8.

That matches what the earlier shortlist showed: of the 49 rows read there, 38 were
fine. So `split_corroborated == 0` should be read as *these two readers disagree*,
not as *this row is suspect* — the digit channel is the stronger of the two, which
is why nothing here overwrites a value. The flag earns its place by concentrating
the errors, not by predicting them.

## What is left

**Every published scan has now been opened.** The 31 stations still without
certified votes are a closed list, not a backlog: each is recorded in
`data/verification/unreadable_scans.jsonl` with a reason and with whatever the
scan does show.

Fifteen have **no counting record in the bundle at all**. Every page of every file
held for those bureaux was rendered and registered against the counting-record
layout; the best fit is 0.13-0.53 where a real counting record scores 0.93-0.98.
What ISIE published for them is the polling record, a correction decision, or a
box-reopening record. Two of those decisions give something: 23080410201's names
the third candidate at 87, and 23040510303's a declared total of 262 — but with no
counting record there is no split to put either against.

Eight are **truncated**: the scan stops part-way down the candidate table, so the
digits column and the later candidates are simply not on the page. Their papers
blocks are complete and close, and the register carries the candidate words that
are visible, but a third candidate derived from the identity would make the check
circular and is not published.

Three are **below resolution** — the whole page published at 470-650px, which
leaves the four-digit boxes about eight pixels tall. On two of them the Arabic
words are still legible and are recorded, but with no readable total there is
nothing to check them against. One is a **faint photocopy** with the words column
blank.

Three **do not balance**, down from nine: six were resolved by their own
correction decisions. 10020210101 sums to 233 against a 333 that the papers block
independently corroborates (346 = 333 + 4 + 9), and its decision touches only the
signed-voter count. Digits and words agree with each other on every candidate on
these forms, so the discrepancy is the clerk's arithmetic rather than the reading
— exactly the case the gate exists to catch, and exactly the case it would be
wrong to round into agreement.

One earlier claim in this file was wrong and is corrected here: two stations were
described as having left the candidate rows blank. One of them, 120206101, leaves
the first two rows empty and writes 50 for the third, and its total is 50 — the
empty rows are zeros, and its decision writes صفر in both, confirming it. The
other, 14030610201, really does leave the whole table blank, and its decision
supplies it.

The published rows span all 24 governorates and all 277
delegations that appear in the corpus. Only 20 scans yield no field map at all,
against 1,389 before the form could be registered on colour and 73 before the page
chooser was fixed.

| | Saied | Zammel | Maghzaoui | votes |
|---|---|---|---|---|
| widely reported national | 90.69% | 7.35% | 1.97% | 2,802,258 |
| **all rows with certified votes (n=9,417)** | **91.12%** | **6.98%** | **1.89%** | 2,527,105 |
| reproducible pipeline only (n=8,977) | 91.11% | 6.96% | 1.93% | 2,415,898 |
| whole form decoded (n=8,056) | 91.18% | 6.89% | 1.93% | 2,164,145 |
| votes block only (n=920) | 90.56% | 7.52% | 1.93% | 251,509 |
| read off the scans by eye (n=447) | 90.07% | 7.73% | 2.20% | 110,159 |

The last row is worth a second look. The 447 stations read by eye are the ones the
pipeline could not reach, and they break **90.07%** for Saied against 91.11% for
the stations it could — closer to the reported national figure, not further. That
is a small piece of evidence that the uncertified stations were leaning the way the
gap suggested, though 447 stations move the total by only 0.05pp.

**This table is a weaker check than an earlier version of this document claimed,
and the direction of travel says so.** A previous build agreed with the reported
national share to 0.03pp on Saied; the build before the blank-cell repair was
0.64pp away, and this one is 0.38pp away. Agreement got worse as the reading got
better and then better again as a real error was removed, so the agreement is not
measuring accuracy directly — but it does move the way a correction should.

Two reasons, both structural. These forms are *محضر عملية الفرز داخل الجمهورية* —
counting records **from inside the republic**. The reported national total includes
out-of-country voting, which this corpus does not contain at all, so the two
quantities are not the same quantity. And the stations that were hard to read were
never a random sample: each wave of newly certified stations has leaned differently
from the ones already held, and the 447 read by eye lean 1.3pp less to Saied than
the pipeline's own rows. With 31 stations left, that selection effect is now almost
exhausted, and the gap that remains is the out-of-country one plus whatever those
30 would have added.

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
the counting record, so it scores just as well. Treating it purely as a nuisance
was itself a mistake, corrected in the section above: it is also a data source,
and the figure it names supersedes the one on the record. And some scans **inset the
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

The answer that held for most of this work, measured when 493 stations were
without certified votes: **436 of them located all 20 fields.** The geometry was
solved for seven failures in eight. What failed was the reading — which is why the
field reader above, and not another round of grid tuning, is where the gains came
from.

That question is now closed rather than answered, because every remaining scan has
been opened by eye. What limits coverage is no longer a property of the pipeline at
all: of the 31 stations left, 15 have no counting record in the published bundle, 9
are cut off mid-table by the scanner, 3 are below the resolution or contrast at
which any reader could work, 1 is a faint photocopy, and 3 are read but do not
balance. None of them is
waiting on a better classifier.

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
