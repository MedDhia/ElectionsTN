# Candidate maps, 2024 Tunisian presidential election

Four maps at each of two granularities, in PDF (vector, for LaTeX), PNG (300 dpi)
and SVG (editable), plus a four-panel composite as a single figure.

| file | shows |
|---|---|
| `saied_{delegation,imada}.*` | Kais Saied's share of valid votes |
| `zammel_{delegation,imada}.*` | Ayachi Zammel's share |
| `maghzaoui_{delegation,imada}.*` | Zouhair Maghzaoui's share |
| `margin_{delegation,imada}.*` | Saied's share minus his strongest rival's, in points |
| `composite_{delegation,imada}.*` | all four as one figure |
| `{saied,zammel,maghzaoui,margin}_cartogram.*` | the same four, as vote-weighted cartograms |
| `{saied,zammel,maghzaoui,margin}_kde.*` | the same four, as kernel-smoothed surfaces |
| `vote_density_kde.*` | certified valid votes per km² |

Built by `tools/make_maps.py` from `data/delegation_margins.csv` and
`data/imada_margins.csv`. The joined spatial data is in
`data/maps/{delegation,imada}_results.geojson` if you would rather restyle it in
QGIS, R (`sf`) or a web map.

- **delegation**: 264 units, all with a result. The join is by code —
  `adm3_pcode` is `TN` + the INS `id_delegation` — so nothing here rests on name
  matching.
- **imada**: 2,084 units, 2,042 with a result. This join is by Arabic name,
  scoped inside each delegation; the 42 without a result are drawn in grey and
  named in every legend.

## Read this before reading the maps

**Area is not votes — which is why the cartograms exist.** The choropleths are
equal-area projections, right for weighing colour but they let the desert
dominate: the ten largest delegations cover **40.6% of the map and cast 2.29% of
the votes**, Remada alone is 17.6% of the map against 0.08% of the vote, and the
ten largest by votes are 0.59% of the map and 11.0% of the vote. So the pale
south in Saied's choropleth is visually dominant and electorally almost
weightless.

The `*_cartogram.*` files fix that. Each delegation becomes a circle whose
**area is its certified valid votes**, nudged apart until nothing overlaps but
still near where it belongs — a Dorling cartogram, built by
`tools/make_cartograms.py`. Colour is the same seven quantile classes from the
same ramp, so a cartogram and its choropleth differ only in how much of the page
each delegation may claim. Read them together: the cartogram answers "where are
the voters, and how did they vote", the choropleth answers "what does the
territory look like".

Packing is measured, not eyeballed. `--report` prints it: **zero remaining
overlap**, with the median delegation displaced 1.6% of the map diagonal (p90
7.8%, max 14.8%). Circle areas sum to 36% of the bounding box — at 30% / 36% /
42% the median displacement is 1.5% / 1.6% / 2.8%, all overlap-free, and 36%
keeps circles legible without rearranging the country. **Positions are therefore
approximate**: the faint outline is orientation, not a claim about where any
circle now sits. Cartograms are delegation-level only; 2,084 imada circles would
be a smear.

**Classes are quantiles, computed per panel.** The shares are severely skewed —
Saied's delegation median is 93.8% against a floor of 59.7% — so equal-interval
classes would drop almost every unit into one bin and show nothing. Seven
quantile classes are used instead, and every legend prints the real range of each
class. The consequence: **a shade in one panel does not mean the same value in
another.** Read each legend. This matters most in the composite, where the four
panels sit side by side. If what you want is to read colours *across*
candidates, use the `compare_*` figures below, which are built for exactly that.

**Sequential, not diverging, on the margin map.** Saied's margin is positive in
all 264 delegations (24.6 to 96.4 points), so there is no polarity for a
diverging scale to encode, and centring one at zero would spend half its range on
empty territory. Only 2 of 2,042 imadas go the other way, and they are outlined
in red rather than left to the pale end of a ramp where 2 in 2,042 would be
invisible.

**Shares are of valid votes at certified stations.** 9,419 of 9,448 stations.
The excluded 29 are stations whose candidate figures do not close against the
form's own published total, so a digit in them is known to be wrong; they are
listed in `data/verification/margins.jsonl`. Summing the station table reproduces
the published national figures exactly: 2,303,043 / 176,525 / 47,847 =
2,527,415, shares 91.12 / 6.98 / 1.89.

## Comparing the candidates against each other

`tools/make_comparative.py`, files `compare_{rank,ratio,opposition}_{delegation,imada}.*`.

The per-candidate maps cannot be read across, for the reason above. But the fix
is not simply "share one scale", and the obstacle is arithmetic rather than
styling. **Saied's share is pinned against the ceiling.** At a 91.12% national
share, a unit that gave him 100% is only **1.10× his national average**; the
observed range is 0.48–1.10×. Zammel and Maghzaoui, at 6.98% and 1.89%, have
room to multiply — observed 0.00–7.85× and 0.00–21.51×. One scale wide enough
for the challengers makes Saied a flat wash; one narrow enough for Saied puts
both challengers off the top end.

So there are three comparative figures, each comparable in a different and
stated sense, and none pretending to be the others. Each is built at **three
levels** — `governorate` (24 units), `delegation` (264) and `imada` (2,042).
The governorate level is the one to reach for when the question is which
*governorate* differs from which: 24 units on one page can be compared to each
other at a glance, where 2,042 cannot. Its totals are summed from the delegation
table, `adm2_pcode` being the first four characters of `adm3_pcode`, and the sum
is exact — 2,303,043 / 176,525 / 47,847 = 2,527,415, the published figures.

**`compare_rank_*` — the same shade means the same standing in that candidate's
own distribution.** Seven equal-count classes per candidate, so the darkest
seventh of each panel covers the same number of units. This compares *geography*
and deliberately sets level aside: it is the figure for "do the two challengers
draw from the same places?" Each legend still prints the values behind its
classes, so the level is set aside rather than hidden. Read this way the three
maps are close to mirror images — Saied darkest across the north and palest in
the south, both challengers the reverse — and the two challengers separate from
each other in the north, Zammel on the north-east coast and Maghzaoui inland.

**`compare_ratio_*` — the same shade means the same multiple of that candidate's
own national average.** One shared scale, in half-powers of two either side of
1.00×, so a class boundary falls exactly at the national average and "darker
than the middle" means "better here than nationally" for all three. This
compares *levels*. Saied's near-uniformity on it is the finding, not a defect:
his ceiling is 1.10×, and the panel subtitle prints each candidate's observed
range so the compression is visible rather than implied.

Because this scale is national rather than derived from whatever is on the page,
it is the basis that stays comparable when the page changes — which is why the
zoomed sheets use it too. At governorate level the ranges are Saied 0.93–1.05×,
Zammel 0.38–1.86×, Maghzaoui 0.49–3.44×, and the most distinctive governorate in
the country is **Kebili**: Maghzaoui at 3.44× his own national share while Zammel
sits at 0.94× of his. It is the one place the third candidate outruns the
runner-up relative to their own averages, and in level they finish a tenth of a
point apart (6.52% to 6.59%). This figure carries one legend for the whole sheet
rather than one per panel.

**`compare_opposition_*` — the two challengers as a field.** The left panel is
the combined non-Saied share, which is where the incumbent was weakest (2.3% to
40.3% by delegation, concentrated in the south-east and along the Sfax coast).
The right panel is Zammel's share of that non-Saied vote, with a class boundary
at exactly **50%** — the runner-up line — so it reads as who came second and by
how much. Neither panel needs a shared-scale caveat, because both are ordinary
shares. Zammel is ahead in 257 of 264 delegations and 1,729 of 2,037 imadas; the
7 delegations where Maghzaoui led are outlined in red.

**Do not treat the imada runner-up as a solid fact.** 72 imadas are *exact* ties
between the two challengers, on counts from 1 vote to 38, mostly under 10 —
which is why the imada panel leaves the flip to its two palest classes instead
of outlining 236 units in red and burying the ramp underneath. The shade, which
gives the margin, is the part to trust at that level.

Colour is the same documented blue ramp as everywhere else here. The ratio and
composition panels have a meaningful midpoint and would ordinarily ask for a
diverging ramp, but the palette documents a full ramp for blue only and its rule
is that every step is a documented hex — so rather than invent a second hue, the
midpoint is placed on a class boundary and named in the legend.

## Per-candidate margin and rank, by governorate and by region

`tools/make_levels.py`, files
`{saied,zammel,maghzaoui}_{margin,rank}_{governorate,region}.*` — twelve
figures, each a full page of its own rather than a panel in a triptych.

**margin** is that candidate's own share minus his strongest rival's, in
percentage points, recomputed from the aggregated votes rather than averaged
from the level below (averaging would weight a 3,000-vote delegation like a
60,000-vote one). It is positive for the local winner and negative for everyone
else, so a challenger's margin map reads as how far behind he finished.

**rank** is that candidate's share in equal-count classes — seven over the 24
governorates, six over the 6 regions, which makes each region its own class. At
region level "rank" is therefore a literal ordering, and the legend prints the
share behind each place.

On all twelve, **darker means better for the named candidate.** For rank that is
automatic; for margin it follows from classing the signed value, so a
challenger's darkest units are where he came closest. Each unit carries its own
number on the map — the margin in points, or the rank with 1 as strongest —
because at 24 and 6 units there is room, and a coarse choropleth without numbers
is a worse table than the one it came from.

### What these levels collapse

Saied leads and Zammel is runner-up in **all 24 governorates and all 6
regions**. Three consequences, measured rather than assumed:

- **Zammel's margin is exactly minus Saied's**, everywhere, at both levels. The
  two margin maps carry identical information with the ramp reversed. Both are
  published, because "how far behind Zammel finished" is what a reader of a
  Zammel map wants and should not have to negate in their head — but each figure
  names whose mirror it is.
- Their **rank** maps are near-mirrors for the same reason: Spearman correlation
  between the two candidates' shares is **−0.965** across governorates and
  **−1.000** across regions, where the ordering is exactly reversed.
- **Maghzaoui is redundant with neither.** His margin is his share minus
  Saied's, a different field, and his ordering is his own: −0.82 against Saied
  and +0.72 against Zammel by governorate, −0.60 and +0.60 by region. His best
  region is the South West at 3.37%, his worst the Centre West at 1.26%.

Both levels are summed from `data/delegation_margins.csv`, since the pcodes nest
exactly — `adm2_pcode` is the first four characters of `adm3_pcode`, `adm1_pcode`
the first three — and the sums reproduce the published certified figures,
2,303,043 / 176,525 / 47,847 = 2,527,415, which `--report` prints.

Two things needed fixing here. Six regions cannot carry seven quantile classes,
so with as many classes as units the legend was printing interpolated class
bounds instead of the regions' own values — it labelled the top class 2.84% where
South West actually polled 3.37%. And the four Greater Tunis governorates put
their labels on top of one another, so labels are nudged apart in display space
with a decaying spring back to the true centroid, and carry a halo in case a
nudged label lands over a neighbour of the opposite lightness. Measured, not
eyeballed: **zero remaining overlap at both levels, with the furthest label moved
2.4 px.**

## The kernel-smoothed surfaces

`tools/make_kde.py`. The choropleths and cartograms give one value per
administrative unit, so every boundary is a hard edge the vote does not actually
have. These drop the units: each of the 2,042 imada centroids is a sample, and
the value anywhere is a distance-weighted average of nearby samples — a
Nadaraya–Watson estimator whose weights are kernel × votes, so a large imada
pulls the local estimate more than a small one and the result is a share rather
than a count. Contoured at the **same seven quantile breaks as the choropleths**,
so surface and tiles can be read against each other.

`vote_density_kde.*` is a different quantity on its own scale: certified valid
votes per km². It answers what no share map can — where the voters actually are.

**The bandwidth is local, not a national constant.** This is the thing to
understand about these surfaces. The point pattern's spacing spans a factor of
650 — the median imada centroid has a neighbour 4.2 km away, the densest 0.16 km,
the sparsest 104.6 km — so no single kernel width can be right everywhere. Each
sample is therefore smoothed over **its own nearest-neighbour distance**, and
`local_bandwidth_kde.*` maps what that came to at every point: under 5 km across
the populated north, 25–88 km in the deep south.

Chosen by leave-one-out cross-validation, which estimates every imada's share
from all the others and weights the error by the votes at stake:

| bandwidth | weighted MAE |
|---|---|
| fixed 25 km — what these maps used to use | 4.003 pp |
| fixed 1 km — the best fixed width | 3.077 pp |
| **local, nearest neighbour** | **2.718 pp** |

A local bandwidth beats *every* fixed one, not just the one it replaced, and the
fixed family has a real interior optimum — below 1 km it gets worse again — so
this is a genuine minimum rather than cross-validation collapsing toward zero.
No floor is imposed, because every floor tested made the error worse. As
corroboration from a direction cross-validation cannot see: the nearest-neighbour
distance comes out at a median **1.32× the radius implied by the imada's own
area**, so the kernel lands at about the size of the unit it represents without
being told to.

**Where the estimate is not supported, nothing is drawn.** A local bandwidth
widens until it reaches data, which moves this problem rather than solving it: a
desert cell now gets an estimate from one imada 100 km away. So a cell is drawn
only if the nearest place that voted is **within 30 km** — about three times the
95th percentile of the spacing between samples — which covers 89.2% of the land
(20 km would keep 81.1%, 40 km 94.0%). An absolute threshold is right here even
though the bandwidth must not be fixed: the bandwidth is a smoothing scale and
has to follow the local density, while the mask is the claim that no observation
of this place exists, and "the nearest imada is 60 km away" is a fact about
geography rather than about kernels.

Kish's effective sample size was tried as that test first and measured wrong in
**both** directions: of the 9,243 land cells it withheld, 4,409 had a sample
within 30 km, while of the 16,773 cells with nothing inside 30 km it still drew
11,939. It conflates an empty desert with a cell sitting directly on a sample,
because a near-interpolating kernel makes one sample dominate in both. It is
reported by `--report` and no longer masks.

**The isolated circular patches in the south are not a rendering artifact.** They
are single desert imadas: one sample, radially symmetric, clipped where its
support runs out at 30 km. A circle there is the map saying that one observation
is all there is.

Grid is 1 km, fine enough to resolve the smallest bandwidths — checked by
integrating the density surface, which recovers 99.96% of the votes it was built
from. A local kernel concentrates each imada into roughly its own footprint, so
the density surface is far more peaked than a fixed 25 km one and its top class
is left open-ended rather than printed as a range no reader needs.

**A fixed 10 km comparison set is published alongside**, as `*_kde_10km.*` from
`tools/make_kde.py --fixed 10`. It is not a replacement and the figures say so
on their face: cross-validation prefers the local rule, 2.718 pp weighted MAE
against 3.548 pp at 10 km. It is worth having anyway, because 10 km is the
readable middle of the fixed family — coarse enough to show regional structure
without the near-interpolation of the local rule, and much better than the 25 km
these maps used to use. Two things it shows that the local set does not: a fixed
kernel pushes far more vote mass off the map (83.4% of the integral lands on
land, against 94.5% for the local rule), and it turns the sparse south into
hard-edged discs where a lone imada's kernel is the only thing present. There is
no `local_bandwidth_kde_10km`, because at a fixed bandwidth that field is a
constant.

Every figure in this family renders at exactly the same size, so they can be
laid side by side without rescaling. That needed a fix: `bbox_inches="tight"`
expands the canvas around anything that overflows, so before the footnotes were
wrapped each figure came out as wide as its longest caption line.

**These rest on 99.52% of the certified vote**, not all of it: the imada table
omits the 41 stations whose sector never matched an imada, worth 12,182 votes.
The delegation choropleth has no such gap.

## Zoomed sheets: Greater Tunis and each governorate

`tools/make_zooms.py`, files `zoom_{grand_tunis,tunis,ariana,…}.*` — 25 sheets,
four panels each (the three candidates and Saied's margin), at imada level.

The national imada map carries 2,084 units on one page. It shows the country and
hides every city: **Greater Tunis is 334 imadas in about 1% of the page**, and
those four governorates cast 614,219 certified valid votes — a fifth of the
national total. These sheets give each extent the whole page. `--list` prints the
25 slugs; `--only <slug>` builds one.

**Class breaks are the national imada quantiles, identical on every sheet.**
This is the choice that makes the set worth having rather than 25 pretty,
mutually unintelligible pictures. Local breaks would maximise contrast inside
each governorate, but then no sheet could be compared with another or with the
national maps. With national breaks a shade means the same share everywhere, so
Tataouine's uniformly dark Zammel panel really is uniform national strength and
not merely local variation stretched to fill a ramp. The cost is that a
homogeneous governorate looks flat — which is true of it — and each panel's
subtitle prints that extent's own observed range so nothing is concealed.

Read across the set and the regional structure is plain: Zammel takes 10.7% in
Greater Tunis and 13.1% in Ariana against 6.98% nationally, and 10.1% in
Tataouine; **Maghzaoui takes 6.5% in Kebili against 1.89% nationally**, which is
within a tenth of a point of Zammel there — the one governorate where the two
challengers finish level. Saied's own range runs from 84.5% in Ariana to 96.0% in
Kairouan.

Neighbouring imadas are drawn in light grey for orientation and carry no value;
only those falling inside the visible rectangle are drawn, so a sheet carries its
surroundings rather than all 2,084 units. Geometry is simplified to 0.0015°,
finer than the national imada map, because at this scale there is room for it.

### Comparable on both axes at once: `zoom_ratio_*`

The shares sheets above are comparable **across** governorates but not across
candidates, because their breaks are each candidate's own national quantiles. So
each extent also gets a `zoom_ratio_*` sheet on the same shared-ratio basis as
`compare_ratio_*`: local share ÷ that candidate's national share, in half-powers
of two either side of 1.00×.

Because that scale is national, it does not depend on the extent — which makes
this the one basis comparable **on both axes simultaneously**. A shade means the
same thing between the three panels of one sheet *and* between any two of the 25
sheets. Ariana's Zammel panel and Kebili's Maghzaoui panel can be read against
each other directly.

Greater Tunis reads clearly on it: Saied uniform mid-blue at 0.50–1.09× (he
cannot exceed 1.10×), Zammel reaching 6.95× along the eastern coastal arc from
central Tunis out to La Marsa, and Maghzaoui up to 5.42× on a visibly different
footprint. Kebili is the opposite case: Maghzaoui to 21.51×, the highest ratio
anywhere in the country.

**One legend per sheet, not one per panel.** On a shared scale the per-panel
legends are three copies of one statement, and the gutter each occupies is dead
width — which was also why a row of three panels came out as a 17-by-3-inch
strip. Sharing the legend gives that width back to the maps: 3.6 inches of map
per panel against 2.8 with a gutter. `compare_ratio_*` gets the same treatment,
so the national and zoomed comparative sheets are laid out alike.

**The panel grid follows the extent's shape.** The governorates are not the same
shape, so no fixed grid works: three panels across wide, short Kébili was a
strip of postage stamps, while three across tall Tataouine is right. The column
count is chosen to bring the sheet closest to a landscape page — but restricted
to a single row or column on the comparative sheets, since three panels in a 2×2
grid with an empty quadrant asks the eye to turn a corner.

### One map per candidate per extent, showing the detail: `micro_*`

`micro_<extent>_<candidate>.{pdf,png}` — **93 maps**: three candidates across 31
extents, which is Greater Tunis, the 24 governorates and now the **6 regions**
(155 to 585 imadas each, selected by `adm1_pcode`). `--list` prints the slugs.

These are on **local** breaks: quantiles of that candidate's share among the
imadas of that extent alone. That is the whole point of the family, and it is
the exact opposite trade-off from the two sheet families above. National breaks
are what make a shade mean the same thing everywhere, and the price is that a
homogeneous governorate lands in one or two classes with everything inside it
flattened. Local breaks pay the opposite price — **a shade means nothing outside
its own map** — and buy the detail. Use `zoom_*` or `zoom_ratio_*` when you need
to compare extents; use these when you need to see inside one.

What the detail buys is not cosmetic. On national breaks Kebili's Maghzaoui
panel is a wash; on local breaks it runs 2.17% to **40.72%**. The top imada is
**Bou Abdellah**, where Maghzaoui took 542 of 1,331 votes across 7 stations and
**outpolled Saied in three of them** (159–127, 129–91, 98–89). Every one of those
stations matched its imada exactly, score 1.0000, so this is a real local
stronghold for a candidate who took 1.89% nationally — and it is invisible on
every national map in this directory.

It is not the only one. The strongest single imada for each challenger, none of
which reads as anything but pale on a national scale:

| | share | imada | extent |
|---|---|---|---|
| Zammel | **54.83%** | El Mansoura Sud | Siliana |
| Zammel | 48.51% | El Bouhaira | Tunis |
| Maghzaoui | **40.72%** | Bou Abdellah | Kebili |
| Zammel | 38.26% | Ennasr 2 | Ariana |
| Zammel | 34.30% | El Kantaoui | Sousse |
| Zammel | 27.50% | Ksar El Haddada | Tataouine |

Against national shares of 6.98% and 1.89%. A 91% national result is not
uniform at imada scale, and this is the family that shows it.

Two notes on the mechanics. These render to **PDF and PNG only**: 93 figures in
three formats would add about 80 MB to a `maps/` directory already at 210 MB, and
the PDF already carries the vector — `--formats pdf,png,svg` overrides it. And
the figure's chrome height is computed from the wrapped note rather than fixed: a
single-panel figure is a quarter the width of a sheet, so the same note wraps to
three times as many lines, and at the sheets' fixed height it printed straight
over the map.

**The samples are imada centroids, not stations.** That is the finest geography
the published record supports — `data/pv_presidential_2024.csv` carries no
coordinates and admin4 is the finest boundary set available. Note that moving to
stations *placed at their imada's centroid* would change nothing whatsoever: the
imada tables are exact sums of their stations, so every Nadaraya–Watson term
comes out identical. Station-level sampling needs real station coordinates from
outside this repo.

## Design notes

Colour is the documented blue sequential ramp (steps 100–700), used for all four
maps rather than inventing per-candidate ramps, because the palette instance
documents a full ramp for blue only and its rule is that every step is a
documented hex. Checked as a sequential ramp should be — lightness strictly
monotone, OKLCH L from 0.905 to 0.338 in even steps of 0.093–0.095.

Projection is Albers equal-area conic, standard parallels 32°N and 36°N.
Geometry is Douglas–Peucker simplified at 0.004° (delegation) and 0.002° (imada);
the raw admin4 layer is 42 MB and unusable in a document unsimplified.

Boundaries: OCHA/HDX Common Operational Dataset for Tunisia (COD-AB), licensed
CC BY-IGO. Provenance including the exact resource id and SHA-256 is in
`data/verification/boundaries_source.json`; `tools/fetch_boundaries.py` re-fetches
it. The archive is not committed — admin4 alone is 42 MB of geometry.
