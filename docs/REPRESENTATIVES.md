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
| rows read | **1,914 (20.3%)** |
| no table recovered from the scan | 207 (2.2%) |

The 207 unlocated break down as 125 where the placement found no column rule and
was refused, 55 where the six-rule pattern would not fit at any rotation, and 27
where the band falls past the edge of the page the form was scanned on.

The reading pass is a fifth of the corpus, drawn by the deficit order, so its
governorate coverage runs from 11.1% (Sidi Bouzid) to 36.9% (Ariana) rather than
being uniform. National figures below are therefore given **post-stratified by
governorate** — each governorate weighted to its true share of polling stations —
with the unweighted figure printed beside them. The two differ by 1.3 points,
which is the useful thing to know about the imbalance: it is not doing the work.

### Who was in the room

Of the 1,914 stations read:

| | stations | share of stations read |
|---|---|---|
| at least one representative recorded | 1,086 | **56.7%** (post-stratified **58.0%**) |
| one representative | 921 | 48.1% |
| two | 144 | 7.5% |
| three | 21 | 1.1% |

1,272 representatives in all, and they are almost all for one candidate:

| candidate | representative rows | stations | share of stations read |
|---|---|---|---|
| Kais Saied | 1,218 | 1,076 | **56.2%** post-stratified |
| Zouhair Maghzaoui | 54 | 53 | 3.3% post-stratified |
| Ayachi Zammel | **0** | 0 | 0.0% |
| written but unattributable | 39 rows | | |

**Ayachi Zammel's campaign put no representative in any of the 1,914 stations
read.** He took 7.0% of the vote. Zero in a fifth of the corpus is not proof of
zero nationally — it bounds his presence at under about 0.2% of stations at 95%
confidence — but it is the sharpest fact in the dataset, and it is what the
record of a candidate who spent the campaign in prison looks like at the counting
table.

### Where

Presence is not uniform, and the spread is far wider than sampling noise: 84.2%
of stations read in Le Kef against 38.1% in Nabeul, on samples of 57 and 134,
whose Wilson intervals (72.6–91.5 and 30.3–46.5) do not come near each other.

| governorate | read | any representative | Saied | Maghzaoui stations |
|---|---|---|---|---|
| Le Kef | 57 | 84.2% | 84.2% | 0 |
| Sidi Bouzid | 58 | 77.6% | 77.6% | 4 |
| Monastir | 92 | 77.2% | 76.1% | 3 |
| Gabès | 48 | 72.9% | 68.8% | 7 |
| Gafsa | 44 | 72.7% | 63.6% | 5 |
| **Kebili** | 22 | 72.7% | **31.8%** | **11** |
| … | | | | |
| Tunis | 164 | 45.1% | 43.3% | 6 |
| Kasserine | 147 | 44.9% | 44.9% | 0 |
| Ben Arous | 148 | 42.6% | 39.2% | 8 |
| Nabeul | 134 | 38.1% | 38.1% | 0 |

Full table in `data/representatives_by_governorate.csv`, with delegations and
imadas beside it and a Wilson interval on every rate.

**Kebili is the exception worth naming.** It is the one governorate where Saied's
campaign was not the one in the room: 11 of its 22 read stations recorded a
Maghzaoui representative against 7 recording one for Saied. Maghzaoui took 1.9%
of the national vote and his 53 stations are concentrated — Kebili 11, Ben Arous
8, Gabès 7, Tunis 6, Gafsa 5 — which is what a campaign with cadres in a few
places and none elsewhere looks like from the counting table.

At delegation level, among the 91 delegations with at least eight stations read,
the range runs from Nefza, Monastir and Teboulba at 100% to Mejez El Bab at 0%,
Bardo at 8.3% and Sakiet Eddaier at 9.1%. Neighbouring delegations differ sharply
enough that this is organisational rather than regional.

### It is not a proxy for the vote

Whether a station recorded a representative barely moves with what the station
did. Across the 1,914 read stations the correlation between Saied's vote share
and any representative being present is **0.107**; his mean share is 92.3% where
one signed and 90.6% where none did. Against turnout the correlation is 0.055.

That near-independence is the finding, not a null result. A campaign's ability to
staff a polling station is a different quantity from its vote there, and on this
corpus the two are close to orthogonal — so the map of representatives is a map
of organisation, and reading it as a map of support would be reading it wrong.

(Six stations carry an impossible `turnout_pct` in `data/station_margins.csv`,
up to 6771%, inherited from the turnout fields of the results build. They are
excluded from the turnout figure here. Including them moves the correlation to
-0.022 and the mean turnout gap to 8 points in the opposite direction, which is
an artefact of six rows and not a finding.)

## Maps

`tools/make_reps_maps.py` draws three panels at governorate and at delegation,
into `maps/levels/`: stations with any representative, stations with a Saied
representative, and representatives per 100 stations read. Units under a floor of
stations read (5 at governorate, 8 at delegation) are drawn in the no-data grey
and counted in the legend, so the sampling pattern cannot be misread as
geography — at delegation that leaves 91 of 264 shaded.

Figure text carries no Arabic. Matplotlib does no bidirectional reordering or
glyph shaping, so the form's own heading renders as reversed isolated letters;
it is named in this file instead.

## What the dataset will not tell you

- **It is a fifth of the corpus.** Every rate is over stations read. The
  remaining 7,326 located tables are unread, and `reading` says which is which.
- **The reading is by eye and single-pass.** No second reader, so there is no
  measured error rate. 39 rows carried writing that could not be attributed and
  are coded `?` rather than guessed; 30 stations were dropped because the crop
  landed somewhere other than the table, which is 1.5% of what was rendered and
  is the localisation's residual error showing up where it can be seen.
- **A blank row and a struck row are the same value.** See the protocol above.
- **Two representatives for the same candidate at one station** happen (144
  stations have two rows, 21 have three), so representative rows and stations
  with a representative are different counts. The tables carry both.
- **It says who signed, not who watched.** A campaign may have had someone
  present who did not sign, and the accredited civil-society observers are not
  in this table at all except where a bureau wrote one into it by mistake.
