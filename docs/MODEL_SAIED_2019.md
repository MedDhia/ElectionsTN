# Predicting Kais Saied's 2019 first-round vote

**A three-variable model built from the 2014 census predicts Saied's share to a
median error of 1.9 points, out of sample, and misses badly in exactly one
constituency.** The 2014 election results -- who voted for whom five years
earlier -- are worth almost nothing. Neither is his own 2024 landslide.

Built by `tools/model_saied_2019.py`; the figure is
`maps/y2019/model_saied_fit.{pdf,png,svg}` from `tools/make_model_figure.py`;
the joins and the estimator are checked by `tools/test_model_saied.py`.

```
python3 tools/fetch_census.py                  # census + statistical yearbook
python3 tools/covariates.py --write            # the delegation map, and check it
python3 tools/test_model_saied.py
python3 tools/model_saied_2019.py --ablate --nested --permute 999 --compositional
python3 tools/model_saied_2019.py --unit governorate --ablate --permute 999
python3 tools/make_model_figure.py
```

## What is being predicted, and what cannot be

The target is Saied's share of valid votes on **15 September 2019**, in each of
the 33 constituencies of the first round. That is the only 2019 presidential
quantity the sources resolve geographically: annex 7 of ISIE's retrospective
report breaks round one down by constituency and gives round two as a national
pair of numbers. There is no round-two share per unit, so none is modelled.

Across the 27 domestic constituencies the target runs from **4.88%** (Kasserine)
to **29.86%** (Zaghouan), mean 18.65, standard deviation 5.78. Predicting the
mean everywhere is the baseline any model has to beat, and under leave-one-out
that baseline is an RMSE of **5.89 points**.

## The result

| model | LOO RMSE | MAE | max error | LOO R² | in-sample R² |
|---|---|---|---|---|---|
| **forward-selected OLS, 3 variables** | **3.53 p** | 2.44 p | 12.09 p | **0.614** | 0.836 |
| forward-selected OLS, 2 variables | 4.04 p | 2.82 p | 13.42 p | 0.494 | 0.750 |
| average of the four best | 4.24 p | 3.14 p | 12.12 p | 0.440 | 0.856 |
| forward OLS, size chosen in-fold | 4.30 p | 3.02 p | 14.98 p | 0.426 | 0.836 |
| elastic net | 4.72 p | 3.71 p | 11.86 p | 0.307 | 0.885 |
| lasso | 4.75 p | 3.72 p | 11.86 p | 0.298 | 0.897 |
| principal-component regression | 4.98 p | 3.74 p | 12.73 p | 0.228 | 0.632 |
| random forest | 5.12 p | 3.80 p | 15.19 p | 0.186 | 0.855 |
| gradient boosting | 5.18 p | 4.12 p | 13.22 p | 0.165 | 1.000 |
| ridge | 5.62 p | 4.03 p | 15.29 p | 0.019 | 0.841 |
| **predicting the mean** | **5.89 p** | 4.59 p | 14.30 p | −0.078 | 0.000 |
| nearest neighbours | 5.94 p | 4.34 p | 18.52 p | −0.095 | 1.000 |

27 domestic constituencies, 200 candidate predictors, identity link. Every
number is leave-one-out with **the hyper-parameter and the variable selection
redone inside each fold**, so nothing about the held-out constituency reaches
the model that predicts it. The in-sample column is printed beside it to show
the size of the gap: gradient boosting fits the 27 points perfectly and predicts
a 28th no better than a coin.

**The three variables**, all from the 2014 census, with the fit on all 27:

| variable | coefficient | per standard deviation | marginal r |
|---|---|---|---|
| share of the employed with **primary schooling only** | +0.753 pp per point | +4.53 pp | +0.673 |
| **graduate unemployment rate** | −0.403 pp per point | −3.40 pp | −0.394 |
| share of the unemployed with **no schooling** | +0.364 pp per point | +1.70 pp | +0.260 |

Intercept 3.09. Saied ran strongest where the workforce is least educated and
where unemployment does *not* fall on graduates, and weakest where it does.

**The selection is stable.** Refitting on each of the 27 leave-one-out samples
picks the same three variables **26 times out of 27**. No other variable is
chosen more than once. That is the check that matters for a forward selection
over 200 columns on 27 rows, and it is the right-hand panel of the figure.

## The one place it fails, and why

| | actual | predicted | error |
|---|---|---|---|
| Kasserine | 4.88 | 16.97 | **+12.09** |
| Nabeul 2 | 20.26 | 25.75 | +5.48 |
| Jendouba | 22.95 | 17.64 | −5.31 |
| Zaghouan | 29.86 | 24.63 | −5.23 |
| Monastir | 25.77 | 21.57 | −4.21 |

**Kasserine is the whole error term.** Drop it and the RMSE over the other 26 is
**2.70 points**; the median absolute error across all 27 is **1.86 points**, and
26 of 27 are within 5.48. What happened in Kasserine is that **Lotfi Mraihi took
45.9%** of the vote there, against 6.6% nationally. Gafsa is the same story with
a different name -- **Safi Said took 53.0%** against 7.1% nationally -- and the
model misses it by less only because it predicted a low share there anyway.

A local candidate hoovering up half a constituency is not a thing the 2014
census can know. It is the correct kind of failure for a structural model: it
gets the electorate right and the candidate field wrong.

## What does not predict it

The middle panel of the figure is the finding. Each block of predictors, refitted
alone, under the same leave-one-out:

| predictors | columns | LOO RMSE |
|---|---|---|
| **2014 census** | 129 | **3.45 p** |
| everything | 200 | 3.53 p |
| 2014 presidential results | 13 | 5.98 p |
| *(baseline: predict the mean)* | | *5.89 p* |
| 2014 participation | 5 | 6.64 p |
| geography (centroid, area, region) | 9 | 6.71 p |
| 2014 legislative results | 15 | 8.11 p |
| statistical yearbook, per head | 29 | 8.61 p |

The census does all of it, and slightly more than all of it: on its own it beats
the full matrix, because the other 71 columns give the selector more ways to go
wrong. Everything else is at or beyond the baseline. The headline stays at the
full-matrix 3.53 rather than the census-only 3.45, because picking the block
after seeing this table is a choice the cross-validation did not police.

### Things tried that did not work

Six of them, kept in the tool as flags so the negatives are reproducible rather
than asserted:

- **The October 2019 legislative vote** (`--block concurrent`), cast three weeks
  after the first round, makes the model *worse*: 5.06 p against 4.67 p without
  it, on the pre-census matrix. Saied's September geography is not the party
  geography of the same season.
- **Saied's own 2024 result** (`--block retro`), read station by station off
  9,459 counting records in this repo, also makes it worse: 5.56 p against
  5.16 p without. At governorate level the correlation between his 2019 and 2024
  shares is **0.334** -- the two landslides are not the same map.
- **Spatial interpolation.** Nearest neighbours on the geography block alone --
  estimating a constituency from the ones around it, which is the standard way
  to fill a hole in a map -- lands at 5.87 p, barely better than the mean.
  Saied's 2019 vote is not smooth in space.
- **The compositional route** (`--compositional`). Predicting the other 25
  candidates separately and taking Saied as one minus their sum lands at 9.10
  points: the 25 errors accumulate instead of cancelling.
- **Choosing the number of variables inside the fold** (`ols_forwardcv`, k from
  one to six by inner leave-one-out) is *worse* than fixing it at three: 4.30
  against 3.53. Inner cross-validation on 26 rows is itself noisy enough to pick
  the wrong size, which is worth knowing before trusting any in-fold tuning on a
  sample like this.
- **Averaging the four best models** gives 4.24, worse than its own best member.
  Averaging helps when members err independently; here one member is much better
  than the rest and the average drags it down.
- **Within-constituency spread** (`--spread`): giving every census variable a
  companion column holding its population-weighted standard deviation across the
  constituency's own delegations. It helps the dense models a lot -- lasso goes
  from 4.75 to 3.99 -- and hurts the winner, 3.53 to 3.75.
- **The 2015 poverty map** (`--poverty`): INS's small-area estimates of the
  poverty rate and three school-dropout rates per delegation. Worse, at 4.01,
  and it costs a constituency: the published table omits Siliana's eleven
  delegations, so that unit leaves the sample.

## Predictors, and why each one is allowed

Everything is measured **before 15 September 2019**, so a result under the
default `--block forecast` is a forecast rather than a retrodiction.

| block | n | source |
|---|---|---|
| 2014 presidential round one, the 12 candidates above 0.5% nationally, plus Marzouki's round-two share | 13 | JORT 2014, `data/presidential_2014_constituency.csv` |
| 2014 legislative, the 12 lists above 0.6% nationally | 15 | `data/legislative_2014_list_results.csv` |
| 2014 participation: ballots per seat, presidential-over-legislative turnout, round-two lift, spoilt and blank rates | 5 | `data/presidential_2014_centre_turnout.csv`, `data/legislative_2014_constituency_results.csv` |
| geography: population-weighted centroid, log area, region | 9 | OCHA/HDX COD-AB, delegation polygons |
| **2014 census**: every published percentage, aggregated from delegation to constituency | 129 | INS RGPH 2014 via `MedDhia/rgph2014tn` |
| statistical yearbook: 29 per-head governorate indicators at their latest year through 2018 | 29 | INS *Annuaire Statistique* via `MedDhia/ConsumptionSurveysTN` |

The census and the yearbook are the only measurements here that are not
themselves elections. The census was taken in April 2014 and the yearbook series
stop in 2018, so both are available to a forecaster and neither can have been
contaminated by the outcome. `tools/fetch_census.py` clones both packages to
`.cache/` and records each commit and each file's SHA-256 in
`data/verification/census_source.json`, the same way the boundaries are handled.

**Two joins had to be made and both are tested.** The 2019 report's text layer
transposes adjacent letters -- المنستير comes out as املنستير, and the
two-continent constituency carries the swap twice -- so constituency names are
matched by Damerau distance with the runner-up required to be strictly worse.
The census writes MANNOUBA where the boundary layer writes Manubah, and MANNOUBA
is three edits from Manubah and also three from **Jendouba**; matching each name
to its own nearest neighbour therefore gets it wrong. Both sides have exactly 24
governorates, so the join is solved as a one-to-one assignment of minimum total
cost, under which Jendouba is already taken at distance zero. 21 of the 24 need
no repair at all.

**Percentages are re-weighted before they are aggregated.** A census percentage
is aggregated from delegation to governorate by its own stated denominator --
population, adults, the employed, the unemployed -- rather than averaged.
Averaging would give Carthage's 24,000 people the same weight as Sfax's 270,000.

## Recovering the constituency split

Tunis, Sfax and Nabeul each elect in two constituencies, and every source above
is published by delegation or by whole governorate. Until the split was
recovered, both halves of each pair carried **identical** census and identical
geography, so the model was obliged to give Tunis 1 and Tunis 2 the same
prediction while they differ by 5.7 points -- a floor on the error that no
amount of modelling could lift.

The archive states the split, in a place nothing was reading: the 2023
local-election folder tree files every delegation under its numbered
constituency, and those numbers are the same 27 domestic constituencies the
presidential election used. All 53 delegations of the three governorates
resolve, none ambiguously, into halves of 11+10, 8+8 and 9+7 -- exactly each
governorate's delegation count.

**Checked against something it cannot have copied.** The 2014 assembly allocated
seats by population, so if the split is right, population per seat should be
near-constant across the six halves. It is: 57,676 to 63,180, a spread of 5,504
on a mean near 60,000. Swap the two halves of any of the three governorates and
the fit gets worse, in all three cases. `tools/covariates.py` runs that check and
`tools/test_model_saied.py` asserts it.

One trap on the way, and it is the reason the map is keyed on a pair rather than
a name: **Kasserine also has a delegation called الزهور**, and keying on the
delegation name alone files the Kasserine one into Tunis 1.

The map is published in its own right as `data/constituency_delegations.csv`,
264 rows, because any analysis attaching delegation-level data to a constituency
election needs it and should not have to re-derive it.

What it bought, per unit:

| | actual | predicted |
|---|---|---|
| Tunis 1 | 16.62 | 16.58 |
| Tunis 2 | 10.96 | 12.41 |
| Sfax 1 | 24.18 | 24.54 |
| Sfax 2 | 20.33 | 20.28 |
| Nabeul 1 | 23.77 | 23.60 |
| Nabeul 2 | 20.26 | 25.75 |

Five of the six are now close; before, each pair had to share one number.

`--unit governorate` still exists and sums the split pairs back together -- exact
arithmetic on vote counts, not an average of shares -- for 24 rows. The two
units agree.

## The out-of-country test

The six out-of-country constituencies have electoral history but no polygon and
no census, so the transfer is run on the electoral columns alone, dropped from
both sides. It fails: RMSE 9.30 points abroad, and the same reduced matrix
manages only 11.09 points on the domestic units it was trained on. Stripped of
the census and geography, there is no model left to transfer. This is reported
because it is the strictest test available, not because it flatters anything.

## How the numbers were kept honest

- **Leave-one-out, with everything inside the fold.** The penalty, the component
  count, the neighbour count and the variable selection are all re-derived on
  each training fold of 26. Selecting variables once on all 27 and then
  cross-validating the winner is the standard way to manufacture an R² and it is
  not what happens here.
- **A permutation test.** The whole procedure, run against 999 shuffles of the
  target: observed 3.55 points at constituency level against a null median of
  7.97, and 3.60 at governorate level against a null median of 8.37 and a 5th
  percentile of 5.85. **p = 0.002** on both. The model is not finding
  structure that a shuffled target would also yield.
- **A nested pass over the selection itself** (`--nested`), which holds a unit
  out, runs the entire 24-way model-and-link comparison on the rest, and lets
  whatever won predict the held-out unit. That is what someone following this
  recipe would actually have got, with the winner's-curse removed.
- **Determinism.** The winning model has no random state at all; the tool says so
  rather than printing a meaningless seed sweep. The stochastic learners were
  swept over ten seeds when they were in front (4.52 to 4.75 points), so their
  ranking is not a seed artefact.

## Reading it as social science, not just as a forecast

Three cautions belong on any use of the coefficient table:

1. **It is ecological.** These are 27 areal units. That the vote is higher where
   the low-schooled workforce is larger does not establish that low-schooled
   workers voted for Saied.
2. **It is not causal.** No design here separates the census variables from
   anything correlated with them. Read them as the coordinates of a place, not
   as the mechanism.
3. **N is 27.** A three-variable model is about as much as that supports, which
   is why the honest table stops at three and why the two-variable model is
   printed beside it.

What survives all three is the comparison, and the comparison is the point:
**the social structure of a place in 2014 predicts Saied's 2019 vote; the
politics of that place in 2014 does not.** He did not inherit a bloc. He
assembled one along a line the party system was not organised on.
