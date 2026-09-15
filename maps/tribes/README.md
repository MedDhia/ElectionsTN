# From the tribe's ground to the family name: `tribes/`

`tools/make_tribal_mobility.py`, 49 figures in 100 files: one per tribe
(`<latin>_mobility.{pdf,png}`, 43 of them), four composite sheets of eleven
panels, and two overviews (`overview_displacement`, `overview_retention`, also
in SVG). The numbers on every figure are in `data/tribal_mobility.csv`, and the
governorate breakdown behind the arrows in `data/tribal_mobility_destinations.csv`.

## What is being joined

Two sources that were never meant to meet.

**The sheets.** The 1853 Pellissier and 1881 Lasailly maps of the Regency, and
André Martel's 1965 sketch of 1881, print tribe names in letterspaced capitals
across the ground each tribe held. The sibling repository
[MapsTN](https://github.com/MedDhia/MapsTN) read every label, placed it on the
ground by an affine fitted to towns, and gave each tribe the largest ellipse
that holds all of its own labels and no other tribe's. Those tables are copied
verbatim under `data/sources/mapstn/` and the ellipse is what these figures
call the tribe's **historical ground**. No sheet draws a tribal boundary, so the
ellipse is a reading of the names and nothing more.

**The register.** The 2024 ISIE voter register counts every registered voter's
family name by imada (`data/voter_surnames_2024/`). A Tunisian family name is
very often a *nisba*, the adjective of belonging formed from a tribe, a fraction
or an eponym: the Hammama's member is a همامي (Hammami), the Zlass's a جلاصي
(Jlassi), the Ouled Ayar's a عياري (Ayari), the Souassi's a سويسي (Souissi).

**The crosswalk.** `data/tribal_surname_crosswalk.csv` pairs each of the 92
tribes MapsTN places with the nisba the register carries, says how the one
derives from the other, and grades the link: `high` where the name is unusual
and the derivation transparent, `medium` where the name could also come from a
given name or a town, `low` where it almost certainly does. 43 pairs are
drawn. The rest are listed with the reason: generic patronymics (Saidi,
Khelifi, Yaacoubi, Marzouki), names the register puts somewhere the tribe never
was (Adhari is 84% Sousse, Mtiri 70% Kairouan, Mekni a Sahel name), names below
1,000 holders, and 19 tribes with no nisba in the register at all.

## What a figure shows

The ground as a filled ellipse in the 1853 sheet's ink, the label centres each
cartographer printed (square 1853, triangle 1881, diamond Martel), every
registered voter bearing the nisba as a dot inside the imada that holds them,
and arrows from the ground's centre to the largest concentrations of the name
more than 25 km away, sized by voters. The gutter states:

- how much of the name is registered inside the ground, within 25 km of it,
  and beyond;
- how heavily the name sits on its own ground (one voter in so many), and in
  how many imadas inside and outside it reaches 5% of the electorate;
- how far the name's centre of gravity lies from the ground's centre, and in
  which direction;
- the median holder's distance from the ground;
- the governorates the arrows point at, with counts.

`overview_displacement` draws all 43 at once, an arrow from each ground's
centre to the name's centre of gravity, coloured by the share still inside.
`overview_retention` is the same table as stacked bars, sorted by that share.

## What the figures say

**The nisba of a tribe is mostly borne away from the tribe's ground.** Across
the 43 pairs, 728,919 registered voters, the median share registered inside the
historical ground is 1.5%, and 32 of the 43 are under 5%. Add the 25 km ring
and the median is still under 12%. Greater Tunis (Tunis, Ariana, Ben Arous,
Manouba) holds 42.7% of everyone bearing one of these names, and Tunis is the
largest concentration beyond the ring for 24 of the 43. The median centre of
gravity sits 122 km from the ground's centre, and the direction is north or
north-east for nearly every steppe and southern tribe.

**The great confederations are the extreme case.** Hammami (53,065 voters)
is 0.7% inside the Hammama's ground on the Sidi Bou Zid steppe, and one voter
in 288 there; its holders are in Manouba, Tunis and Béja. Jlassi is 4.8% inside
the Zlass ground around Kairouan and 19.6% in Tunis alone. Mejri is 0.3% inside
the Mejers arc, Methlouthi 0.2% inside the M'Talith Sahel, Ferchichi 1.9%
inside the Frechiche ground at Kasserine, Hamrouni 0.9% inside the Hamarna's
ground by Gabès. On its own ground the confederation's name is rare: the
people there carry the names of fractions, lineages and douars, which is what
the 1:50 000 sheets print where the 1:800 000 sheets print the tribe. A nisba
is what a person is called by outsiders, so it is the name a family keeps when
it leaves.

**The small north-western tribes keep their names at home.** Sdiri is 41%
inside the Ouled Sdira ground and one voter in 65 there; Riahi 27% inside and
one in 31; Hkimi 18%; Ghezouani, Zouaghi, Boussalmi and Zghalmi 10 to 12%. Add
the ring and Charni reaches 46%, Ghezouani 51%, Riahi 53%, Trabelsi 47%. These
are tribes whose ground is small because it is hemmed in by neighbouring names,
and whose nisba is the local family name.

**The frontier tribes are visible only on the Tunisian side.** Merdassi,
Mezlini and Abidi have 0% inside, because the 1881 sheet prints Merdès, Beni
Mezzeline and Ouled Sidi Abid west of the border, where the register cannot
see. Their figures say how much of the ground lies outside Tunisia. Abidi, the
commonest family name in the country, has its home in Jendouba, across the
frontier from the tribe, and 17.6% of it there.

**Where the sheets disagree, the ground is a splinter.** Ouled Sdira (211 km
between placements), Ouled Khiar (287 km), Souassi (126 km) and Riah (119 km)
have grounds that join two placements, drawn dashed. Sdiri's 41% is inside a
splinter that runs from Ghardimaou into the Constantine province, so it is a
generous reading.

## Three readings the figures do not support

**A nisba is a name, not a membership.** Not every Hammami descends from the
Hammama and the register cannot say which do. A holder outside the ground may
be a migrant, a migrant's descendant, or someone whose name has another origin:
Trabelsi means Tripolitan, Aouni and Soltani can come from given names,
Jendoubi from the town. The crosswalk grades each pair and every figure prints
the grade.

**The ground is the largest reading of the sheets, not a territory.** It is
bounded by neighbouring names, so a tribe alone in its quarter gets a huge
ellipse (the Ouerghemma, the Nefzaoua) and a tribe hemmed in gets a small one
(Djendouba, Meressen). A large ground makes a name look settled and a small one
makes it look dispersed, before anybody moved. Read `inside` beside
`ground_area_sqkm`.

**A concentration is where a name is registered in 2024, not a route.** The
arrows join a nineteenth-century centre to a twenty-first-century one and say
nothing about when anyone moved, or whether the movement was one family's or a
century's. The twentieth century pulled people towards Tunis, the Sahel and
Sfax, and every figure shows that pull; none shows its mechanism.

## Files

| file | rows | what |
|---|---|---|
| `data/tribal_surname_crosswalk.csv` | 87 | tribe, nisba, Latin spelling, how the one derives from the other, the grade, drawn or not, and why |
| `data/tribal_mobility.csv` | 43 | one row per drawn pair: the ground, the counts, the shares inside, near and beyond, the displacement, the top destination, the figure |
| `data/tribal_mobility_destinations.csv` | 989 | one row per pair and governorate: voters, share, voters beyond the 25 km ring, and whether an arrow was drawn |
| `data/sources/mapstn/` | | the four MapsTN tables, with `SOURCE.md` naming the commit |

## Rebuilding

```bash
python3 tools/fetch_boundaries.py          # once; caches the OCHA COD-AB archive
python3 tools/make_tribal_mobility.py      # ~90 s; the 100 files and the two tables
python3 tools/make_tribal_mobility.py --only Hammama Zlass   # a subset, tables untouched
```

The Arabic labels need `fonts-hosny-amiri`, as the surname maps do. Dots are
seeded from the surname, so the same name draws the same dots here as in
`maps/surnames/`.
