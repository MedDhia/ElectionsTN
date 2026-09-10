# Candidate maps, 2024 Tunisian presidential election

743 figures in ten folders, grouped by family — one folder per producing
tool, so a rebuild lands in exactly one directory. Filenames are unique across
the whole set, so a figure stays identifiable detached from its folder.

**Two scales, published as a pair.** Every percentage figure outside `fitted/`
runs on a fixed 0–100% bar, so a shade means the same number everywhere and
nothing can be read wrong across figures — at the price that most maps look
flat. `fitted/` holds the same maps with the ramp spanning only the values each
one contains, which is where the geography becomes legible — at the price that a
shade means nothing anywhere else. Neither is the honest one on its own, so both
exist and each figure names what it gave up.

| folder | n | what is in it | built by |
|---|---|---|---|
| `national/` | 30 | the four choropleths at delegation and imada level, plus a four-panel composite of each | `tools/make_maps.py` |
| `cartograms/` | 12 | the same four as vote-weighted Dorling cartograms, delegation level | `tools/make_cartograms.py` |
| `surfaces/` | 33 | kernel-smoothed surfaces: the four fields, vote density, the local bandwidth, and a fixed 10 km comparison set | `tools/make_kde.py` |
| `comparative/` | 27 | the three bases built for reading colours *across* candidates, at governorate, delegation and imada level | `tools/make_comparative.py` |
| `levels/` | 36 | per-candidate margin and rank, aggregated to governorate and to region | `tools/make_levels.py` |
| `zoom/` | 150 | four-panel and shared-ratio sheets for 25 governorate-scale extents, on national breaks | `tools/make_zooms.py` |
| `micro/` | 186 | one map per candidate per extent, 31 extents, on **local** breaks | `tools/make_zooms.py --basis micro` |
| `clusters/` | 54 | where the pattern beats chance (LISA, Getis-Ord Gi*) and the electoral regions | `tools/make_clusters.py` |
| `turnout/` | 179 | turnout at every level, the electorate behind it, the coverage it rests on, plus zoom and per-extent sheets | `tools/make_turnout.py` |
| `fitted/` | 36 | the four candidate quantities and turnout with the ramp **fitted to each map's own range** rather than to 0–100 | `tools/make_maps.py --scale fitted`, `tools/make_turnout.py --scale fitted` |

Three asymmetries are deliberate rather than gaps, and each is explained in its
own section below: `micro/` covers **31** extents where `zoom/` covers 25 (the
six regions take the micro basis only) and is **PDF+PNG only**; `surfaces/` has
33 files rather than 36 because a fixed bandwidth makes the local-bandwidth map
a constant, so there is no `local_bandwidth_kde_10km`; and `cartograms/` exists
at delegation level only, because 2,084 imada circles would be a smear.

Everything is in PDF (vector, for LaTeX) and PNG (300 dpi); everything except
`micro/` is also in SVG (editable).

Every `fitted/` figure names its fixed-scale counterpart in its own caption, and
vice versa, so the pair is navigable from either side.

`clusters/` is the only family that attaches a **null model**. Every other
figure here shows where a value is; those say whether the pattern is more
clustered than chance would produce.

## The fitted scale: `fitted/`

The fixed 0–100% scale buys comparability and spends contrast. This family makes
the opposite trade on the same maps, so the two can be read together: the ramp
runs from a map's own minimum to its own maximum, and those two numbers are
printed as the end ticks because on a fitted scale they *are* the scale.

**Measured, because the gain is not uniform.** Contrast gain is 100 divided by
the observed span:

| figure | observed range | gain over the fixed scale |
|---|---|---|
| `maghzaoui_delegation` | 0.51 – 15.28% | **6.8×** |
| `turnout_delegation` | 13.82 – 44.78% | 3.2× |
| `zammel_delegation` | 1.34 – 35.13% | 3.0× |
| `saied_delegation` | 59.73 – 97.69% | 2.6× |
| `maghzaoui_imada` | 0.00 – 40.72% | 2.5× |
| `saied_imada` | 44.00 – 100.00% | 1.8× |
| `turnout_imada` | 5.42 – 84.13% | 1.3× |
| `margin_imada` | −10.83 – 100.00 pp | **0.9× — none** |

**The fitted scale barely helps at imada level, and that is a finding about the
data rather than about the scale.** At 2,042 units someone hits 0% and someone
hits 100%, so the extremes pin the ramp and there is almost nothing left to
recover; `margin_imada` spans 111 points, which is *wider* than the fixed scale,
so its fitted version has less contrast, not more. Fitting pays at delegation
level, where 264 units aggregate the outliers away. Both levels are published so
this is visible instead of asserted.

**Every figure carries a reference strip.** Beside the fitted bar is a narrow
grey strip spanning the full 0–100 with this map's window marked on it in blue —
the inverse of the bracket the fixed-scale figures carry. Without it a fitted
scale silently exaggerates: Maghzaoui's map would look as varied as Saied's when
his darkest delegation is 15% against Saied's 98%. The composite is the sharpest
case, since its four panels each have their own scale, and its caption says so
in as many words.

Built from `data/delegation_margins.csv` and `data/imada_margins.csv`. The joined spatial data is in
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

The `cartograms/*_cartogram.*` files fix that. Each delegation becomes a circle whose
**area is its certified valid votes**, nudged apart until nothing overlaps but
still near where it belongs — a Dorling cartogram, built by
`tools/make_cartograms.py`. Colour is the same fixed 0–100% scale as the
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

**Every percentage runs on one fixed scale, 0 to 100%.** Instead of seven class
swatches, each figure carries a continuous colourbar ticked every 10: 0% at the
pale end of the ramp, 100% at the dark end. A signed margin is a difference of
two shares, so it runs the full −100 to +100 points. The consequence is the one
worth having: **a shade means the same number on every figure in this
directory** — across candidates, across levels, across all nine families. No
legend needs reading twice.

The price is paid in contrast, and it is stated on each figure rather than
buried. Against the range a percentage can take, most of these quantities are
flat. Measured over the 264 delegations, if you divide 0–100 into sevenths:

| quantity | observed range | share of units in one seventh |
|---|---|---|
| Maghzaoui's share | 0.51 – 15.28% | 99.6% (100.0% of imadas) |
| Zammel's share | 1.34 – 35.13% | 96.6% |
| Saied's share | 59.73 – 97.69% | 89.0% |
| turnout | 13.82 – 44.78% | 70.5% |

So Maghzaoui's map is nearly a single wash where the quantile version showed
structure. Two things keep that from being a loss of information. A continuous
ramp resolves gradations that seven classes collapsed, so an outlier such as Bou
Abdellah still reads inside a pale field. And **every bar carries a bracket
giving the range its own units occupy, and a rule at the national figure**, so
how much of the scale is in use is visible rather than implied — which is what a
fitted scale gave away for free and a fixed one has to say out loud.

Three things keep classes on purpose, because they are not percentages and have
no 0–100 to be fixed to: the rank maps in `levels/` and `comparative/`
(ordinal), the ratio basis (multiples of a candidate's national share), and
everything in `clusters/` (z-score bands and named categories). Vote density,
the electorate as a head count, and the kernel bandwidth in km are not
percentages either and keep their own scales.

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

## Comparing the candidates against each other: `comparative/`

`tools/make_comparative.py`, files
`comparative/compare_{rank,ratio,opposition}_{governorate,delegation,imada}.*`.

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

## Per-candidate margin and rank, by governorate and by region: `levels/`

`tools/make_levels.py`, files
`levels/{saied,zammel,maghzaoui}_{margin,rank}_{governorate,region}.*` — twelve
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

Two things needed fixing here. Six regions could not carry seven quantile
classes, so with as many classes as units the legend printed interpolated class
bounds instead of the regions' own values — it labelled the top class 2.84% where
South West actually polled 3.37%. The fixed scale removes that failure mode
entirely, there being no class bounds left to interpolate; the value is printed
on each unit instead. And the four Greater Tunis governorates put
their labels on top of one another, so labels are nudged apart in display space
with a decaying spring back to the true centroid, and carry a halo in case a
nudged label lands over a neighbour of the opposite lightness. Measured, not
eyeballed: **zero remaining overlap at both levels, with the furthest label moved
2.4 px.**

## The kernel-smoothed surfaces: `surfaces/`

`tools/make_kde.py`. The choropleths and cartograms give one value per
administrative unit, so every boundary is a hard edge the vote does not actually
have. These drop the units: each of the 2,042 imada centroids is a sample, and
the value anywhere is a distance-weighted average of nearby samples — a
Nadaraya–Watson estimator whose weights are kernel × votes, so a large imada
pulls the local estimate more than a small one and the result is a share rather
than a count. Contoured on the **same fixed 0–100% scale as the choropleths**,
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

## Zoomed sheets: Greater Tunis and each governorate: `zoom/`

`tools/make_zooms.py`, files `zoom/zoom_{grand_tunis,tunis,ariana,…}.*` — 25 sheets,
four panels each (the three candidates and Saied's margin), at imada level.

The national imada map carries 2,084 units on one page. It shows the country and
hides every city: **Greater Tunis is 334 imadas in about 1% of the page**, and
those four governorates cast 614,219 certified valid votes — a fifth of the
national total. These sheets give each extent the whole page. `--list` prints the
25 slugs; `--only <slug>` builds one.

**The scale is the fixed 0–100% one, identical on every sheet.**
This is the choice that makes the set worth having rather than 25 pretty,
mutually unintelligible pictures. Local breaks would maximise contrast inside
each governorate, but then no sheet could be compared with another or with the
national maps. On a fixed scale a shade means the same share everywhere, so
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

### Comparable on both axes at once: `zoom/zoom_ratio_*`

The shares sheets above are now comparable across governorates **and** across
candidates, the scale being the same fixed 0–100% for all of them. What they
cannot show is how a candidate did relative to *his own* national level, which
is a different question: at a 91.12% national share Saied cannot exceed 1.10×
himself, while Maghzaoui's 1.89% leaves room for 20×. So each extent also gets a
`zoom_ratio_*` sheet on the same shared-ratio basis as
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

### One map per candidate per extent, showing the detail: `micro/`

`micro/micro_<extent>_<candidate>.{pdf,png}` — **93 maps**: three candidates across 31
extents, which is Greater Tunis, the 24 governorates and now the **6 regions**
(155 to 585 imadas each, selected by `adm1_pcode`). `--list` prints the slugs.

These were built on **local** breaks — quantiles of that candidate's share
among the imadas of that extent alone — which spent the whole ramp on the
variation inside one map at the price that a shade meant nothing outside it.
That is exactly the trade the fixed scale rules out, so the local classing is
gone and these now read on the same 0–100% scale as everything else.

**What that leaves is size, not a different reading.** One candidate, one
extent, at full page size instead of a quarter panel; the bracket on the bar and
the subtitle give the extent's own range, which is what stretching the ramp used
to convey. The family therefore no longer offers a view `zoom_*` does not — it
offers the same view larger. If you want the detail the local breaks bought,
that trade is not available on a fixed scale.

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
three formats would add about 80 MB to a `maps/` directory already at 300 MB, and
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

## Spatial clusters: what beats chance, and where the regions are: `clusters/`

`tools/make_clusters.py`, files `clusters/{lisa,hotspot}_<candidate>_<level>.*`,
`clusters/lisa_composite_<level>.*`, `clusters/regions_<level>.*` and
`clusters/region_ladder_<level>.*` — 18 figures at delegation and imada level.

**This is the only family with a null model, and that is the point.** Every
other map in this directory shows where a value is. A choropleth of pure noise
still looks patchy, and the eye finds regions in anything, so "Saied is strong
in the centre" has been a description here, never a finding. These test it.

Global Moran's I says there is structure to localise, at both levels and for all
three candidates — Saied +0.556/+0.599, Zammel +0.552/+0.591, Maghzaoui
+0.375/+0.399, every pseudo p at the 1/10,000 floor. Each figure prints its own.

**Only a handful of units are individually significant, and that is not a
failure of the method.** Local Moran's conditional null is wide when a unit has
five or six neighbours, so strong global clustering coexists with few
individually extreme neighbourhoods. At delegation level the *only* significant
cluster in the country is the Tunis metropolitan core, and the candidates' maps
nest rather than standing apart: Saied's eight `LL` delegations — Ariana Médina,
Bab Bhar, Cité El Khadra, El Menzah, Le Kram, Omrane, Radès, Soukra — are a
strict **subset** of Zammel's nine `HH`, which adds Omrane Supérieur. That is
the arithmetic of a 91% result, where Saied's weakness is mechanically his
rival's strength. Maghzaoui's cluster is a genuinely different one: five
delegations in the Kebili and Gafsa oases, plus Guetar as a spatial outlier.

**Multiple testing is corrected, and it changes the answer.** The imada level
runs 2,042 simultaneous tests, which at a nominal 0.05 expects about 102 false
positives — more units than any candidate's real cluster occupies. Every p-value
goes through Benjamini-Hochberg and each figure prints the threshold it actually
applied. For Saied at imada level, 445 units reach raw p ≤ 0.05 and **64**
survive. An uncorrected LISA map — which is what most published ones are —
would shade the 445.

**`hotspot_*` is the same test, drawn differently — not a second one.** Under
conditional permutation, Getis-Ord Gi* and local Moran's I both hold the unit's
own value fixed, so both reduce to asking whether its neighbourhood mean is
extreme; measured on the same seed, their p-values differ by at most one
permutation and they select identical sets. What Gi* adds is the continuous
z-surface and the hot/cold direction that the categorical quadrant map discards.
It is classed on **absolute** z bands (±1.65 / 1.96 / 2.58) rather than
quantiles. A z-score is not a percentage, so this family keeps classes rather
than taking the fixed 0–100% bar — but the bands are absolute, so a shade still
means the same thing on every map in the family, across candidates and levels.

**Insets appear only where the cluster is too small to see.** Eight delegations
of inner Tunis are a speck at national scale. Each figure frames its own
significant units — Maghzaoui's are in Kebili, not Tunis — and only when they
cover 5% or less of the country's bounding box; above that the national map
already shows them and an inset would just duplicate it.

### The electoral regions: `regions_*` and `region_ladder_*`

Ward agglomeration on the three-candidate share vector under the same
contiguity constraint, so every region is a connected piece of the country. This
is the only figure in the repo that draws a boundary the state did not draw.

**Six electoral regions explain more of the vote than all twenty-four
governorates.**

| variance explained (R²) | delegation | imada |
|---|---|---|
| the 6 official regions | 0.209 | 0.157 |
| all 24 governorates | 0.457 | 0.302 |
| **6 electoral regions** | **0.670** | **0.482** |

Ward maximises this criterion by construction, so the clustering is expected to
win and the sign of the gap proves nothing; its size is the informative part,
and six clusters overtaking twenty-four governorates is not something the
construction guarantees. `region_ladder_*` plots the whole ladder from k = 2 to
24 against both administrative baselines — the clustering passes all 24
governorates at k = 4.

The regions are substantively legible, and two of them independently recover
anomalies documented elsewhere in this repo without being told about them: a
30-imada belt averaging **6.4% for Maghzaoui** against his 1.89% nationally, 26
of the 30 in Kebili, and Bou Abdellah alone at 40.7%. Ward isolating a
single-unit region is a real outlier, not a failure of the clustering.

Shaded by mean Saied share with the **palest at the top**, which inverts this
directory's usual "darker is more": the 94%-Saied cluster covers two thirds of
the vote, and shading it darkest would bury the four distinctive regions under
the homogeneous majority. Every legend row prints its own three means.

### Islands, and the one ordering that matters

Contiguity is derived from shared boundary vertices — the COD-AB rings are
topologically clean, so no GIS stack is needed. The check that this is sound is
the degree distribution, since a planar partition has mean degree near 6 and
nothing else does: 5.26 at delegation level, 5.85 at imada.

Tunisia has real islands, and a spatial statistic cannot ignore them the way a
share map can. Djerba and Kerkennah are disconnected **components**, not lone
units — they border each other perfectly well, just not the mainland. Each is
bridged to the mainland by its single shortest link, and every bridge is named
in `data/verification/clusters.jsonl` with its distance; the links land on the
real crossings (Ajim–El Jourf 10.1 km, Kerkennah–Sfax 26.7 km). Units at a
bridge endpoint carry `island_bridged` in the published CSV, because their
"neighbourhood" is an imposed edge across water rather than an observed border.

The order is load-bearing and was got wrong once: restricting to units that have
a result **before** bridging makes an island look like a stranded unit and drops
it, which silently removed Kerkennah from a national map. Subset first, bridge
second, and then nothing needs dropping — all 264 and all 2,042 units are kept.

Per-unit output is published as `data/{delegation,imada}_clusters.csv` and
checked by `tools/audit_clusters.py`, whose invariants include that every
electoral region really is contiguous in the same graph the figures used.

## Turnout, and the basis that had to be repaired first: `turnout/`

`tools/make_turnout.py` — 70 figures. National choropleths of turnout, the
registered electorate and coverage at delegation and imada level; governorate
and region rollups; LISA clusters; turnout against Saied's share; a
kernel-smoothed surface; a Dorling cartogram sized by electorate; 25 zoomed
sheets pairing turnout with the coverage behind it; and 31 per-extent maps on
local breaks.

**The published turnout column could not carry a map, and three defects had to
be fixed before one was drawn.** A quality gate had been dropped, so 40 stations
published impossible turnout — the worst at 13,133%, three registered voters
against 394 who voted. Numerator and denominator were summed over *different*
stations, so in 167 of 264 delegations the ratio was nobody's turnout: Houmt
Souk read 1.1%, `registered` from 47 stations over `voters` from 3, against
17.3% on the matched subset. And four rows carried a flag their own columns
refuted. Mapping the column as it stood would have drawn a turnout collapse
across the south that does not exist. After the repair, stations over 100% go
from 44 to zero and delegation turnout runs **13.8% to 44.8%** around a national
**30.38%**.

`docs/figures/pv_turnout_fields.*` annotates a real procès-verbal with the
cells the calculation reads, if you want to see where these numbers come
from before trusting a map of them.

**Turnout is weaker evidence than anything else in this directory, and every
figure says so.** The registered count is the only field in the dataset that no
identity on the form checks — the one field read by classifier alone. So turnout
is a *certified numerator over an uncertified denominator*. Nothing else mapped
here has that asymmetry.

**The national rate is a rule across the bar, not a class boundary.** Turnout
genuinely straddles its mean in both directions — 105 delegations below, 154
above, a spread of −16.6/+14.4pp — which is exactly the polarity the margin maps
lacked and the reason they are sequential. That used to be encoded by placing
30.38% on a class boundary, the palette documenting one hue and a diverging
scale needing two. On the fixed 0–100% scale there are no class boundaries to
place it on, so the rate is ruled across the colourbar and labelled instead. The
two-sided reading survives; what is lost is contrast, since 13.8–44.8% is about
a third of the bar.

**`coverage_*` is published as a map of its own.** A unit's turnout rests only
on the stations where both figures survived, and those gaps are structured
rather than random — the forms that fail are the low-resolution scans, and
missingness runs from 8.1% of Nabeul's stations to 18.1% of Médenine's. Units
whose turnout would rest on under 50% of their stations are drawn in the no-data
grey and named in the legend: five delegations, all in Médenine, at 5–6%
coverage, with every other delegation at 60% or above. Read the turnout map
against the coverage map.

### Two findings worth stating

**Turnout and Saied's share are essentially uncorrelated.** Pearson r is
**+0.058** across the 8,403 stations on this basis and **+0.185** across
delegations. The intuition that Saied did better where turnout collapsed is not
in this data. The scatter also shows the shape a correlation hides: below the
national rate his share is tightly held between 85% and 95%, and every
delegation where he underperformed badly is *above* the national rate — the
Tunis metropolitan core, which is also the only significant cluster in
`clusters/`.

**Participation is less spatially organised than vote choice.** Turnout's global
Moran's I is +0.451 at delegation level and +0.254 at imada, against
+0.556/+0.552/+0.375 and +0.599/+0.591/+0.399 for the three candidates — and the
gap widens at the finer level. Whom people voted for clusters more strongly than
whether they voted at all.


### The rest of the family

**`zoom_turnout_*` — 25 sheets, two panels each.** Turnout on the national
imada breaks beside *the coverage behind it*, for the same extent. The pairing
is the point: at national scale a thin unit is a grey speck, but at governorate
scale you can see which neighbourhoods the figure actually rests on. Breaks are
national, so a shade means the same thing on every sheet and against the
national maps.

**`micro_turnout_*` — 31 extents on local breaks.** Quantiles of turnout among
the imadas of that extent alone, so the whole ramp goes on the variation inside
it and a shade means nothing outside its own map. The six regions take this
basis only, as in the candidate families.

**`turnout_kde`** smooths turnout over the imada centroids on the same adaptive
bandwidth the candidate surfaces use — each sample smoothed over its own
nearest-neighbour distance — but weighted by the **registered electorate**
rather than by votes cast, since turnout is a rate over the electorate. Cells
more than 30 km from any sample are left blank rather than extrapolated, and
imadas below the coverage floor contribute no sample at all.

**`turnout_cartogram`** sizes each delegation by its registered electorate. This
is the figure that corrects the choropleth's worst distortion: the ten largest
delegations cover 40.6% of the map, so a pale southern desert reads as a
national collapse in participation when it is a handful of voters. On the
cartogram the south nearly disappears and the north-east and Sahel carry the
ink.

Per-unit columns are in `data/{delegation,imada}_margins.csv`
(`turnout_registered`, `turnout_voters`, `turnout_stations`,
`turnout_coverage_pct`) and checked by `tools/audit_turnout.py`.

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
