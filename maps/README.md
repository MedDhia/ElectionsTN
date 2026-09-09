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
panels sit side by side.

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

**These rest on 99.52% of the certified vote**, not all of it: the imada table
omits the 41 stations whose sector never matched an imada, worth 12,182 votes.
The delegation choropleth has no such gap.

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
