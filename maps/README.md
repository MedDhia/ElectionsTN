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

**Area is not votes.** These are equal-area projections, which is right for
weighing colour, but it means the desert dominates. The ten largest delegations
cover **40.6% of the map and cast 2.29% of the votes**. Remada alone is 17.6% of
the map and 0.08% of the vote. The ten largest by votes cover 0.59% of the map
and cast 11.0%. So the pale south in Saied's map is visually dominant and
electorally almost weightless. A cartogram or a population-proportional symbol
map would fix this and is not attempted here.

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
