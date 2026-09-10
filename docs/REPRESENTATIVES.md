# Who was in the room: candidate representatives at the 2024 count

The 2024 presidential counting record (`محضر عملية الفرز`) ends with a table this
project read past for its whole life:

> **أسماء وإمضاءات ممثلي المترشحين**
> إسم ولقب ممثل المترشح | المترشح | الإمضاء

Three rows: the representative's name and surname, the candidate they act for,
and their signature. It sits in the bottom band of the form, to the right of the
polling staff's own signatures, and it is filled in by hand at the close of the
count.

Read across the corpus it answers a question the vote totals cannot. A campaign's
vote share says how many people marked its name. This table says whether the
campaign could put a person in the room while those marks were counted — an
organisational fact rather than an electoral one, recorded station by station.

## What the table is, and is not

It records **candidate representatives** (`ممثلي المترشحين`) — campaign agents,
the *mandataires* of the French tradition. It is not the accreditation register
for **election observers** (`الملاحظين`), who are accredited centrally by ISIE and
belong to civil-society organisations and foreign missions. The archive holds
ISIE's observer code of conduct but no observer roster, so the two cannot be
joined.

The distinction leaks in one direction: a handful of stations enter an
organisation rather than a candidate in the `المترشح` column — bureau
`01030110107` writes `ممثل عن مرصد شاهد` (a representative of the Chahed
observatory) on its first row. Rows like that are coded as present but
unattributed rather than assigned to a candidate.

## How the table is found

`tools/pv_reps_geom.py`. The digit-grid registration the rest of this project
uses anchors on the form's four-cell number boxes, and the bottom band has none,
so localisation starts from the printed rules instead.

The form carries six full-width rules. Measured as ratios of the span between the
two that bracket the three-stage block, they sit at **-0.500, 0, 1.0, 1.438,
1.568, 1.993**, and those ratios hold to a thousandth across clean scans of every
size in the corpus. So every pair of detected rules proposes a scale, and the
right pair is the one under which the remaining rules land on template lines.

That fit replaced a positional window, which fails in a way worth recording: on a
form that does not fill its page, the results-table foot at ratio 1.438 drifts
into the window where the stage rule is looked for and wins, because it is the
longer line. The window has no way to notice. The pattern fit does, because under
the wrong pair nothing else lines up.

The placement is then snapped onto the table's **own** rules — columns at 0.20
and 0.60 of its width, rows at fixed fractions of the band — and a box that has
no interior column rule is refused. That is the check the page-level fit cannot
make for itself, and it is what catches a fit that landed in the turnout block.
The page's structure is printed red and the bottom band's interior is ruled in
grey, so the two searches run on different masks; using the red plate for both is
why the first version of the refinement rejected two thirds of the corpus.

Where the fit fails at every rotation the form is reported unlocated rather than
cropped at a guess. That is not the end of the road for those pages: the
representatives table is the last thing on the counting record, so
`tools/reps_rescue.py` crops the bottom of the page and the row is read by eye
from there, with no localisation involved. 207 stations came back unlocated and
193 of them were read that way; localisation is a convenience for the contact
sheets, not a precondition for the dataset.

## How the rows are read

Handwriting, three lines per station, drawn from a set of three names. No model
in this repository reads it. It is read by eye off contact sheets
(`tools/reps_sheets.py`) that pack 36 stations to a sheet, each tile carrying the
candidate column and the representative's name beside it — the second column is
what settles an ambiguous hand, and it catches the stations where a clerk filled
the columns the other way round.

**A classifier was considered and rejected on the shape of the problem, not its
difficulty.** The attributed rows are 94.8% Kais Saied. A model trained on
this corpus would learn that prior and be right almost always, and it would be
useless for precisely the rows that carry the information — the rare
representative for someone else. Those rows are the finding; a method whose
errors concentrate there cannot produce it.

The reading order (`tools/reps_reading_plan.py`) is driven by **deficit**: the
next station is drawn from the governorate whose own share read is lowest. Any
prefix of the pass is therefore close to proportional across the country, so an
incomplete pass is a national sample rather than a list of the places whose scans
happened to be cached first. The pass was carried to completion, which makes the
property moot for this dataset and load-bearing for anyone rerunning the tools.

Where the contact-sheet tile is not the table — the fit landed a block out, the
page is turned, or nothing was located at all — `tools/reps_rescue.py` renders a
window anchored on the *page* rather than on the box, tall enough to hold the
band wherever it sits. Anchoring the rescue on the bad box inherits the mistake:
the first version did, and ten of its first twelve windows framed the results
table again, because that is where the bad fit had put them. The window is run
twice, once as the page sits and once at the stored rotation, and the two are
complementary: a station unreadable under one is often plain under the other.

Transcribing the bureau code beside each reading was the first protocol and it
put a typo class into the data: three codes in the first eighty sheets were
mistyped by one digit, and two of them were *valid codes for other stations*, so
nothing downstream could notice. `reps_readings.py pair` removes the hazard by
taking only the row codes, in tile order, and pairing them with the codes the
plan already holds for that sheet; `rescue` does the same against the rescue
sheet's own order, and `verify` is the retrospective form of the check.

Row codes are `s` / `z` / `m` for the three candidates, `.` for no representative
recorded, `?` for a row that carries writing which cannot be attributed.

**`.` collapses three visibly different things** — a row left blank, a row filled
with a dash, and a row struck through with a diagonal — and an early draft of the
protocol kept them apart. It was collapsed after a sheet of trial reading: the
distinction costs most of the reading effort, the three are not reliably
separable at contact-sheet scale, and all three say the same thing about the
question the dataset is for. What is lost is the ability to ask whether a bureau
that struck the table out differs from one that left it blank. Some bureaux are
emphatic about it — `13080510202` writes `لا يوجد` in all six cells, `03040710101`
lists the three candidates and writes `لا أحد` across them — and the dataset
cannot distinguish that from silence.

## What the dataset says

### Coverage

| | stations |
|---|---|
| polling stations in the 2024 presidential corpus | 9,448 |
| **rows read** | **9,310 (98.5%)** |
| scan carries no representatives table | 137 |
| no readable scan | 1 |

**Every representatives table in the corpus has been read.** What is left is not
a reading backlog: each of the 138 was looked at by eye, on a window anchored to
the page rather than to the located box, and at the stored rotation as well as
none, and none of them has a table on the page.
`data/verification/representatives_no_table.txt` lists them one per line with the
reason:

| why it cannot be read | stations |
|---|---|
| the file ISIE published under that bureau code is a **different form** — a decision correcting a counting record (`قرار تصحيح محضر فرز`), a register page, or a signature block | 114 |
| a sideways scan of the recap block, the band not on the page | 13 |
| the scan is cut off above the band | 9 |
| a hand-drawn substitute form with no representatives table | 1 |
| the JPEG is truncated: only the top of the file decodes | 1 |

The largest category is a property of what the archive contains, not of this
pipeline. Coverage by governorate now runs from 90.5% (Médenine) to 100%
(Tataouine), so national figures need no weighting: post-stratifying by
governorate moves the headline rate by less than 0.05 points, and
`tools/reps_geography.py` prints both so the reader can see that rather than
take it on trust.

Three corrections along the way are worth recording. Each is the same mistake in
different clothes: **a fallback fired, and everything downstream trusted it.**

The first is about **ordering**. The reading plan is built greedily by deficit
*at the moment it is built*, so its stored sequence is only optimal against the
readings that existed then. Two thousand stations in, actual coverage had
drifted from what the sequence assumed — one governorate sat three points below
the rest and the sequence was no longer closing the gap. Rebuilding the plan
against the readings as they then stood closed the spread from 5.1 points to 0.9
in three sheets. A greedy order is a snapshot, not an invariant.

The second is about **rotation**. `locate_any` retries the other rotations when
the six-rule fit fails at zero, and on a page that is already upright a
180-degree retry can still satisfy the pattern, because the form is nearly
symmetric top to bottom once the band and the results block are both in play.
Eighty-seven of the hundred stations unread at that point carried
`rotation = 180` for that reason, and honouring it put every rescue window on the
masthead. No false reading came of it — an upside-down row does not read as a
name — but five stations had been read as *empty*, which an upside-down crop of
the wrong block also looks like. Those five were dropped and re-read.

The third is about **triage by colour**, and it is the one that nearly cost real
data. The counting record's bottom band is printed red and the correction
decision is not, so measuring red ink in the bottom third of the page looked
like a free way to skip the 114 forms that carry no table. It separates
perfectly on the colour scans — and 114 of the remaining scans are *greyscale*,
where a counting record has no red either. The test would have discarded two
readable tables (`11020110401`, `13100610401`) on a signal that says nothing
about them. They were found because the whole set was looked at anyway. A
classifier validated only where it works is not validated.

### Who was in the room

Of the 9,310 stations read:

| | stations | share of stations read |
|---|---|---|
| at least one representative recorded | 5,289 | **56.8%** |
| one representative | 4,434 | 47.6% |
| two | 726 | 7.8% |
| three | 129 | 1.4% |

6,273 representatives in all, and they are almost all for one candidate:

| candidate | representative rows | stations | share of stations read |
|---|---|---|---|
| Kais Saied | 5,947 | 5,152 | **55.3%** |
| Zouhair Maghzaoui | 326 | 321 | 3.4% |
| Ayachi Zammel | **0** | 0 | 0.0% |
| written but unattributable | 194 rows | | |

**Ayachi Zammel's campaign put no representative in any of the 9,310 stations
read.** He took 7.0% of the vote. Zero across 98.5% of the corpus bounds his
presence under 0.041% of stations at 95% confidence — about four stations
nationwide, against Saied's five thousand. It is the sharpest fact in the
dataset, and it is what the record of a candidate who spent the campaign in
prison looks like at the counting table.

One form comes closest to an exception and is not one. Bureau `22010610201` wrote
all three candidate names into the column by hand; the Maghzaoui and Saied rows
carry a representative and the Zammel row is blank.

### Where

Presence is not uniform, and the spread is far wider than sampling noise: 78.2%
of stations in Le Kef against 34.9% in Tataouine, on 271 and 186 stations, whose
Wilson intervals (72.9–82.7 and 28.5–42.0) are nowhere near each other.

| governorate | read | any representative (95% CI) | Saied | Maghzaoui stations |
|---|---|---|---|---|
| Le Kef | 271 | **78.2%** (72.9–82.7) | 77.9% | 6 |
| Monastir | 441 | 76.0% (71.8–79.7) | 75.7% | 6 |
| Zaghouan | 161 | 74.5% (67.3–80.6) | 74.5% | 3 |
| Tozeur | 100 | 74.0% (64.6–81.6) | 71.0% | 3 |
| Béja | 283 | 71.7% (66.2–76.7) | 71.0% | 14 |
| … | | | | |
| **Kebili** | 152 | 59.9% (51.9–67.3) | **41.4%** | **55** |
| … | | | | |
| Sfax | 804 | 47.9% (44.5–51.3) | 47.9% | 0 |
| Kasserine | 449 | 44.3% (39.8–48.9) | 44.3% | 0 |
| Ben Arous | 481 | 43.2% (38.9–47.7) | 39.9% | 23 |
| Bizerte | 480 | 42.3% (38.0–46.8) | 41.7% | 7 |
| Nabeul | 642 | 42.1% (38.3–45.9) | 42.1% | 0 |
| Tataouine | 186 | **34.9%** (28.5–42.0) | 34.9% | 0 |

Full table in `data/representatives_by_governorate.csv`, with delegations and
imadas beside it and a Wilson interval on every rate.

**Kebili is the exception worth naming.** It is the one governorate where Saied's
campaign was close to being matched in the room: 55 of its 152 stations recorded
a Maghzaoui representative against 63 recording one for Saied. Maghzaoui took
1.9% of the national vote, and his 321 stations are concentrated — Gabès 60,
Kebili 55, Tunis 46, Médenine 36, Ben Arous 23 — while seven governorates
(Mahdia, Siliana, Kairouan, Sfax, Kasserine, Nabeul and Tataouine) record him at
none at all. That is what a campaign with cadres in a few places and none
elsewhere looks like from the counting table, and the concentration in the south
is the shape of it.

At delegation level, among the 263 delegations with at least eight stations read,
the range runs from 100% (Oued Mliz, Sahline, Beni Hassen, Bekalta, Teboulba) to
Sidi El Béchir at 5.0%, Bou Argoub at 7.4% and Carthage at 8.0%.

**Within Tunis the range is nearly the whole national range.** Sidi El Béchir sits
at 5.0% and Carthage at 8.0% while Cité El Khadra sits at 92.3% and Omrane
Supérieur at 86.8% — four delegations of one city, one governorate, one
electoral administration. Whatever produces the pattern operates below the
governorate, which is what makes it organisational rather than regional.

### It is not a proxy for the vote

Whether a station recorded a representative barely moves with what the station
did. Across the 9,294 read stations with a published result, the correlation
between Saied's vote share and any representative being present is **0.100**; his
mean share is 92.3% where one signed and 90.9% where none did. Against turnout
the correlation is 0.098, on the 8,345 stations whose turnout figure is possible:
32.6% where a representative signed against 30.2% where none did.

That near-independence is the finding, not a null result. A campaign's ability to
staff a polling station is a different quantity from its vote there, and on this
corpus the two are close to orthogonal — so the map of representatives is a map
of organisation, and reading it as a map of support would be reading it wrong.

(965 of the read stations are dropped from the turnout figure: 921 have no
turnout in `data/station_margins.csv` and 44 carry an impossible one, up to
6771%, inherited from the turnout fields of the results build.)

## Maps

`tools/make_reps_maps.py` draws three panels at governorate and at delegation,
into `maps/levels/`: stations with any representative, stations with a Saied
representative, and representatives per 100 stations read. Units under a floor of
stations read (5 at governorate, 8 at delegation) are drawn in the no-data grey
and counted in the legend — at full coverage that leaves 263 of 264 delegations
shaded, and all 24 governorates.

Figure text carries no Arabic. Matplotlib does no bidirectional reordering or
glyph shaping, so the form's own heading renders as reversed isolated letters;
it is named in this file instead.

## What the dataset will not tell you

- **The reading is by eye and single-pass.** No second reader, so there is no
  measured error rate. 194 rows carried writing that could not be attributed and
  are coded `?` rather than guessed.
- **A blank row and a struck row are the same value.** See the protocol above.
- **Two representatives for the same candidate at one station** happen (726
  stations have two rows, 129 have three), so representative rows and stations
  with a representative are different counts. The tables carry both.
- **138 stations have no table to read**, listed with a reason in
  `data/verification/representatives_no_table.txt`. Every rate in the aggregates
  is over stations read.
- **A candidate identified only by ballot number is read as Saied.** Every form
  prints the candidates in the order 1 Zammel, 2 Maghzaoui, 3 Saied, and a
  handful of bureaux wrote `3` or `المترشح رقم 3` in the candidate column instead
  of a name. Two of them write it out — `09050110102` as
  `ممثل للمترشح عدد 3` and `15130610201` as a bare `3` beside a Saied row — which
  is what settles the mapping.
- **It says who signed, not who watched.** A campaign may have had someone
  present who did not sign, and the accredited civil-society observers are not
  in this table at all except where a bureau wrote one into it by mistake —
  `مرصد شاهد` and `ملاحظ محلي` appear on a handful of forms and are coded `?`.
