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
cropped at a guess.

## How the rows are read

Handwriting, three lines per station, drawn from a set of three names. No model
in this repository reads it. It is read by eye off contact sheets
(`tools/reps_sheets.py`) that pack 36 stations to a sheet, each tile carrying the
candidate column and the representative's name beside it — the second column is
what settles an ambiguous hand, and it catches the stations where a clerk filled
the columns the other way round.

**A classifier was considered and rejected on the shape of the problem, not its
difficulty.** The attributed rows are about 96% Kais Saied. A model trained on
this corpus would learn that prior and be right almost always, and it would be
useless for precisely the rows that carry the information — the rare
representative for someone else. Those rows are the finding; a method whose
errors concentrate there cannot produce it.

The reading order (`tools/reps_reading_plan.py`) is driven by **deficit**: the
next station is drawn from the governorate whose own share read is lowest. Any
prefix of the pass is therefore close to proportional across the country, so an
incomplete pass is a national sample rather than a list of the places whose scans
happened to be cached first.

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
| table located on the scan | **9,241 (97.8%)** |
| rows read | **3,823 (40.5%)** |
| no table recovered from the scan | 207 (2.2%) |

The 207 unlocated break down as 125 where the placement found no column rule and
was refused, 55 where the six-rule pattern would not fit at any rotation, and 27
where the band falls past the edge of the page the form was scanned on.

**The reading pass was run until its coverage was even.** The deficit order was
carried to the point where every governorate sits between **40.0% and 40.9%** of
its own polling stations — a 0.9-point spread, which is as flat as integer
station counts allow at this sample size. National figures therefore need no
weighting: post-stratifying by governorate moves the headline rate by less than
0.05 points, and `tools/reps_geography.py` prints both so the reader can see
that rather than take it on trust.

Getting there took one correction worth recording. The plan is ordered greedily
by deficit *at the moment it is built*, so its stored sequence is only optimal
against the readings that existed then. Two thousand stations later the actual
coverage had drifted from what that sequence assumed — one governorate sat three
points below the rest and the sequence was no longer closing the gap. Rebuilding
the plan against the readings as they then stood closed the spread from 5.1
points to 0.9 in three sheets. The lesson is that a greedy order is a snapshot,
not an invariant: rebuild it when the state it was computed from has moved.

### Who was in the room

Of the 3,823 stations read:

| | stations | share of stations read |
|---|---|---|
| at least one representative recorded | 2,170 | **56.8%** |
| one representative | 1,822 | 47.7% |
| two | 300 | 7.8% |
| three | 48 | 1.3% |

2,566 representatives in all, and they are almost all for one candidate:

| candidate | representative rows | stations | share of stations read |
|---|---|---|---|
| Kais Saied | 2,422 | 2,104 | **55.0%** |
| Zouhair Maghzaoui | 144 | 143 | 3.7% |
| Ayachi Zammel | **0** | 0 | 0.0% |
| written but unattributable | 74 rows | | |

**Ayachi Zammel's campaign put no representative in any of the 3,823 stations
read.** He took 7.0% of the vote. Zero in two fifths of the corpus bounds his
presence at under about 0.08% of stations at 95% confidence — roughly eight
stations nationwide, against Saied's several thousand. It is the sharpest fact in
the dataset, and it is what the record of a candidate who spent the campaign in
prison looks like at the counting table.

### Where

Presence is not uniform, and the spread is far wider than sampling noise: 83.0%
of stations read in Le Kef against 39.6% in Nabeul, on samples of 112 and 260,
whose Wilson intervals (75.0–88.9 and 33.9–45.7) are nowhere near each other.

| governorate | read | any representative | Saied | Maghzaoui stations |
|---|---|---|---|---|
| Le Kef | 112 | 83.0% | 82.1% | 4 |
| Monastir | 179 | 77.1% | 76.5% | 4 |
| Gabès | 137 | 71.5% | 65.0% | 27 |
| Zaghouan | 69 | 71.0% | 71.0% | 1 |
| Tozeur | 41 | 68.3% | 63.4% | 2 |
| … | | | | |
| **Kebili** | 62 | 59.7% | **33.9%** | **23** |
| … | | | | |
| Bizerte | 200 | 47.0% | 47.0% | 1 |
| Tunis | 318 | 46.9% | 44.0% | 17 |
| Kasserine | 184 | 46.7% | 46.7% | 0 |
| Ben Arous | 196 | 41.8% | 37.8% | 12 |
| Tataouine | 76 | 40.8% | 40.8% | 0 |
| Nabeul | 260 | 39.6% | 39.6% | 0 |

Full table in `data/representatives_by_governorate.csv`, with delegations and
imadas beside it and a Wilson interval on every rate.

**Kebili is the exception worth naming.** It is the one governorate where Saied's
campaign was not the one in the room: 23 of its 62 read stations recorded a
Maghzaoui representative against 21 recording one for Saied. Maghzaoui took 1.9%
of the national vote, and his 143 stations are concentrated — Kebili 23, Gabès 27,
Médenine 19, Tunis 17, Ben Arous 12 — while seven governorates — Nabeul, Sfax,
Kasserine, Kairouan, Mahdia, Siliana and Tataouine — record him at none. That is what a campaign with cadres in a few places and none elsewhere
looks like from the counting table, and the concentration in the south is the
shape of it.

At delegation level, among the 218 delegations with at least eight stations read,
the range runs from Nefza, Amdoun, Oued Mliz and Borj El Amri at 100% to Bab Bhar
at 8.3%, Bou Argoub at 9.1% and Menzel Bourguiba at 9.5%. Neighbouring
delegations differ sharply enough that this is organisational rather than
regional: Bab Bhar and El Menzah, both in Tunis, sit at 8.3% and 11.8% while the
governorate around them averages 46.9%.

### It is not a proxy for the vote

Whether a station recorded a representative barely moves with what the station
did. Across the 3,821 read stations with a published result, the correlation
between Saied's vote share and any representative being present is **0.106**; his
mean share is 92.3% where one signed and 90.8% where none did. Against turnout
the correlation is 0.082, on the 3,440 stations whose turnout figure is possible.

That near-independence is the finding, not a null result. A campaign's ability to
staff a polling station is a different quantity from its vote there, and on this
corpus the two are close to orthogonal — so the map of representatives is a map
of organisation, and reading it as a map of support would be reading it wrong.

(383 of the read stations are dropped from the turnout figure: 369 have no
turnout in `data/station_margins.csv` and 14 carry an impossible one, up to
6771%, inherited from the turnout fields of the results build. 44 such values
exist corpus-wide.)

## Maps

`tools/make_reps_maps.py` draws three panels at governorate and at delegation,
into `maps/levels/`: stations with any representative, stations with a Saied
representative, and representatives per 100 stations read. Units under a floor of
stations read (5 at governorate, 8 at delegation) are drawn in the no-data grey
and counted in the legend, so the sampling pattern cannot be misread as
geography — at delegation that leaves 218 of 264 shaded, and all 24 governorates.

Figure text carries no Arabic. Matplotlib does no bidirectional reordering or
glyph shaping, so the form's own heading renders as reversed isolated letters;
it is named in this file instead.

## What the dataset will not tell you

- **It is two fifths of the corpus.** Every rate is over stations read, and the
  coverage behind them is flat across governorates but not within them: a
  delegation can still be thin, which is what the Wilson intervals and the map
  floors are for. The remaining 5,417 located tables are unread, and `reading`
  says which is which.
- **The reading is by eye and single-pass.** No second reader, so there is no
  measured error rate. 74 rows carried writing that could not be attributed and
  are coded `?` rather than guessed; 65 stations were dropped because the crop
  landed somewhere other than the table, which is 1.7% of what was rendered and
  is the localisation's residual error showing up where it can be seen.
- **A blank row and a struck row are the same value.** See the protocol above.
- **Two representatives for the same candidate at one station** happen (300
  stations have two rows, 48 have three), so representative rows and stations
  with a representative are different counts. The tables carry both.
- **It says who signed, not who watched.** A campaign may have had someone
  present who did not sign, and the accredited civil-society observers are not
  in this table at all except where a bureau wrote one into it by mistake —
  `مرصد شاهد` and `ملاحظ محلي` appear on a handful of forms and are coded `?`.
