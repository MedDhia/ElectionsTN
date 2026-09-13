"""Predict Kais Saied's 2019 first-round share, one unit at a time.

The target is his share of valid votes on 15 September 2019. It is the only 2019
presidential quantity the sources resolve geographically at all: annex 7 of
ISIE's report breaks round one down by constituency and gives round two as a
national pair of numbers, so there is no round-two share to model per unit and
none is invented here.

**What makes this a real problem rather than a curve fit.** Across the 27
domestic constituencies Saied's share runs from 4.9% (Kasserine) to 29.9%
(Zaghouan), mean 18.7%, standard deviation 5.8. That is a lot of variance for a
candidate with no party, no machine and almost no campaign, and the question is
whether anything measurable accounts for it.

**What makes it hard.** N is 27, or 24 at governorate level. Every predictor is
a share from an earlier election and they are collinear with each other by
construction. Thirty-odd columns on 27 rows fit the training data perfectly and
mean nothing, so every performance number here comes out of **leave-one-out
cross-validation with the hyper-parameter chosen inside each fold** -- nested,
not the usual shortcut of tuning on the full sample and reporting the
cross-validated error of the winner, which leaks the answer. The in-sample
R-squared is printed beside the honest one so the gap is visible.

Even that is not enough on a sample this size, because the table's winner is the
best of 22 model-and-link combinations and the best of 22 noisy numbers is
biased upward. Three flags exist to test whether a winner is real:

    --nested    leave-one-out over the whole procedure, selection included
    --permute N the same procedure against N shuffles of the target
    --seeds N   the stochastic learners refitted under other seeds

**Two units.** `--unit constituency` uses the 33 constituencies as published, of
which 27 are domestic; the three governorates split in two for elections get one
row per half, and both halves take the governorate's centroid and half its area,
which is honest because nothing in the boundary layer says where the line
between them runs. `--unit governorate` sums the halves back -- exact arithmetic
on vote counts, not an average of shares -- for 24 rows with clean geography.

**Three information sets**, and which one is in force changes what a result
means:

* `--block forecast` (default) -- only what was known before polling day: the
  2014 presidential first round (the 12 candidates above 0.5% nationally), 2014
  round two, the 2014 legislative lists (the 12 above 0.6%), participation
  proxies from 2014, and geography. A result here is a forecast.
* `--block concurrent` -- adds the October 2019 legislative vote and the change
  in ballots cast since 2014. Those votes were cast three weeks **after** the
  first round, so this forecasts nothing; it asks how much of Saied's geography
  is recoverable from the party vote of the same season.
* `--block retro` -- adds the 2024 presidential result read off the counting
  records in this repo, aggregated to governorate. Available at governorate
  level only, and retrodictive by five years: it asks whether the places that
  went hardest for Saied in 2024 are the ones that went for him first.

**The out-of-country test.** The six out-of-country constituencies have
electoral history but no polygon. At constituency level the model is trained on
the 27 domestic units and then asked to predict all six cold, on electoral
columns alone. That is the strictest test in here and it is reported separately,
because transferring to a population never seen is a different claim from
interpolating inside one.

Usage:
    python3 tools/model_saied_2019.py
    python3 tools/model_saied_2019.py --unit governorate --block retro
    python3 tools/model_saied_2019.py --nested --permute 199 --seeds 9
"""
import argparse, collections, csv, gzip, json, os, re, sys, unicodedata

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_census
from covariates import (census, damerau, geography, latin_fold, pair_names,
                        poverty, yearbook)
from make_maps import load_layer
from make_2019_maps import CANDIDATE_LABEL, PARTY_KEYS, fold, gov_of

PRES19 = "data/presidential_2019_r1_constituency.csv"
PRES14 = "data/presidential_2014_constituency.csv"
TURN14 = "data/presidential_2014_centre_turnout.csv"
LEG14 = "data/legislative_2014_list_results.csv"
LEG14C = "data/legislative_2014_constituency_results.csv"
LEG19 = "data/legislative_2019_list_results.csv"
PV24 = "data/station_margins.csv"

# One pair of outputs per unit, so the constituency and governorate runs do not
# overwrite each other and a reader can compare them.
OUT_CSV = "data/model_saied_2019_{unit}.csv"
OUT_JSON = "data/verification/model_saied_2019_{unit}.json"

SAIED = fold("قيس سعيد")

# Romanised so a coefficient table and a CSV header stay readable. Keyed on the
# folded Arabic, which is what the loaders produce.
LABEL = dict(CANDIDATE_LABEL)
LABEL.update({
    "محمد الباجي قايد السبسي": "Beji Caid Essebsi",
    "سليم الرياحي": "Slim Riahi",
    "كمال مرجان": "Kamel Morjane",
    "احمد نجيب الشابي": "Nejib Chebbi",
    "محمد المنذر الزنايدي": "Mondher Zenaidi",
    "مصطفي بن جعفر": "Mustapha Ben Jaafar",
    "كلثوم كنو": "Kalthoum Kannou",
    "محمد الفريخه": "Mohamed Frikha",
    "قايمه حزب حركه نداء تونس": "Nidaa Tounes",
    "قايمه حزب حركه النهضه": "Ennahda",
    "قايمه حزب الاتحاد الوطني الحر": "UPL",
    "قايمه الجبهه الشعبيه": "Front Populaire",
    "قايمه حزب افاق تونس": "Afek Tounes",
    "قايمه حزب الموتمر من اجل الجمهوريه": "CPR",
    "قايمه حزب التيار الديمقراطي": "Tayar",
    "قايمه الحزب الجمهوري": "Al Joumhouri",
    "قايمه حزب حركه الشعب": "Chaab",
    "قايمه حزب التحالف الديمقراطي": "Alliance Democratique",
    "قايمه حزب المبادره": "Al Moubadara",
    "قايمه تيار المحبه": "Tayar Al Mahabba",
    "قايمه الاتحاد من اجل تونس": "Union pour la Tunisie",
    "قايمه حزب التكتل": "Ettakatol",
    "قايمه حركه وفاء": "Wafa",
})


def label(folded):
    return LABEL.get(folded, folded)


# ---- joining the constituency names across five files ---------------------
# `damerau` and `pair_names` live in covariates.py, which needs them too. The
# report's text layer transposes adjacent letters: المنستير comes out as
# املنستير, مدنين as مدنني, and the two-continent constituency carries the swap
# twice, past any single-swap repair. Matching on distance covers all of them
# under one rule, and `align` refuses the join unless every best match beats its
# runner-up outright.
def align(names, canon, whole=True):
    """{name as written: canonical key}. Both sides folded before the distance."""
    out = {}
    for name in names:
        f = fold(name)
        scored = sorted((damerau(f, c), c) for c in canon)
        best, runner = scored[0], scored[1]
        if best[0] and best[0] >= runner[0]:
            raise SystemExit(f"ambiguous name {name!r} -> {best[1]!r} / "
                             f"{runner[1]!r}, both at distance {best[0]}")
        if best[0] > 4:
            raise SystemExit(f"nothing matches {name!r} "
                             f"(nearest {best[1]!r} at {best[0]})")
        out[name] = best[1]
    if whole and len(set(out.values())) != len(canon):
        raise SystemExit(f"unmatched: {sorted(set(canon) - set(out.values()))}")
    return out


def read(path):
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def num(x):
    return float(x) if (x or "").strip() else 0.0


# ---- counts, then units, then shares --------------------------------------
# Everything below returns vote *counts* keyed by constituency. Shares are taken
# only after those counts are summed into whatever unit is in force, because a
# governorate's share is its votes over its valid votes, not the mean of two
# constituency shares weighted by nothing.
def pres_counts(path, canon, key, den, rnd=None):
    rows = [r for r in read(path) if rnd is None or r["round"] == rnd]
    m = align({r[key] for r in rows}, canon)
    votes = collections.defaultdict(collections.Counter)
    total = collections.Counter()
    for r in rows:
        votes[m[r[key]]][fold(r["candidate"])] += num(r["votes"])
        total[m[r[key]]] = num(r[den])          # one denominator per unit row
    return votes, total


def leg_counts(path, canon, key, name, party_keys=None):
    rows = read(path)
    m = align({r[key] for r in rows}, canon)
    votes = collections.defaultdict(collections.Counter)
    total = collections.Counter()
    for r in rows:
        c, v = m[r[key]], num(r["votes"])
        total[c] += v
        if party_keys is None:
            votes[c][fold(r[name])] += v
            continue
        f = fold(r[name])
        for party, stems in party_keys.items():
            if any(s in f for s in stems):
                votes[c][party] += v
                break
    return votes, total


def to_shares(votes, total, units, top):
    """Sum counts into units, then divide. Keeps names over `top` nationally."""
    v = collections.defaultdict(collections.Counter)
    t = collections.Counter()
    for c, counter in votes.items():
        if units[c] is not None:
            v[units[c]].update(counter)
    for c, n in total.items():
        if units[c] is not None:
            t[units[c]] += n
    national = collections.Counter()
    for u in v:
        national.update(v[u])
    grand = sum(t.values())
    keep = [n for n, s in national.most_common() if s / grand >= top]
    return {u: {n: v[u][n] / t[u] for n in keep} for u in t}, keep, t


def participation(canon, units):
    """2014 participation, from counts summed into units before any ratio.

    Registered voters are published per constituency in neither 2014 source, so
    turnout itself cannot be formed. What can: ballots cast per seat, and seats
    are allocated on population, so this is turnout up to the registration rate;
    the presidential-to-legislative ratio of ballots; the round-two lift; and the
    spoilt and blank rates, the closest the archive comes to a measure of protest
    and of difficulty with the ballot paper.
    """
    turn = collections.defaultdict(dict)
    rows = read(TURN14)
    m = align({r["centre"] for r in rows}, canon)
    for r in rows:
        turn[m[r["centre"]]][r["round"]] = r
    legc = read(LEG14C)
    ml = align({r["constituency"] for r in legc}, canon)
    acc = collections.defaultdict(collections.Counter)
    for c in canon:
        if units[c] is None:
            continue
        r1, r2 = turn[c]["r1"], turn[c]["r2"]
        a = acc[units[c]]
        a["r1_voters"] += num(r1["voters"])
        a["r2_voters"] += num(r2["voters"])
        a["spoilt"] += num(r1["spoilt_ballots"])
        a["blank"] += num(r1["blank_ballots"])
    for r in legc:
        u = units[ml[r["constituency"]]]
        if u is None:
            continue
        acc[u]["leg_voters"] += num(r["voters"])
        acc[u]["seats"] += num(r["seats"])
    return {u: {"log_ballots_per_seat": np.log(a["leg_voters"] / a["seats"]),
                "pres_over_leg": a["r1_voters"] / a["leg_voters"],
                "r2_lift": a["r2_voters"] / a["r1_voters"],
                "spoilt_14": a["spoilt"] / a["r1_voters"],
                "blank_14": a["blank"] / a["r1_voters"]}
            for u, a in acc.items()}


def presidential_2024(units):
    """The 2024 result this repo read off the counting records, by governorate.

    Five years the wrong side of the target, so it is retrodiction and the tool
    says so wherever it is used. It earns its place because it is the only
    measure here that is not an ISIE summary table: it is 9,459 counting records
    read station by station, the finest-grained thing the archive holds.
    """
    acc = collections.defaultdict(collections.Counter)
    govs = {u for u in units.values() if u is not None}
    cache = {}
    for r in read(PV24):
        g = fold(r["governorate_ar"])
        if g not in cache:
            scored = sorted((damerau(g, u), u) for u in govs)
            if scored[0][0] > 4 or scored[0][0] >= scored[1][0]:
                raise SystemExit(f"2024 governorate {g!r} matches no unit")
            cache[g] = scored[0][1]
        for k in ("registered", "voters", "valid", "blank", "spoilt", "saied"):
            acc[cache[g]][k] += num(r.get(k))
    return {u: {"saied_2024": a["saied"] / a["valid"],
                "turnout_2024": a["voters"] / a["registered"],
                "blank_2024": a["blank"] / a["voters"],
                "spoilt_2024": a["spoilt"] / a["voters"]}
            for u, a in acc.items()}


def census_governorates(census_names, layer_names):
    """Kept as a name because the test asks for it; `pair_names` does the work."""
    return pair_names(census_names, layer_names)[0]


def design(block, unit, with_census=True, with_poverty=False,
           spread=False):
    """(names, X, y, columns, weights, domestic mask, regions)."""
    canon = sorted({fold(r["centre"]) for r in read(PRES14)})
    if len(canon) != 33:
        raise SystemExit(f"expected 33 constituencies, found {len(canon)}")
    units = ({c: c for c in canon} if unit == "constituency"
             else {c: gov_of(c) for c in canon})     # None abroad, dropped
    if block == "retro" and unit != "governorate":
        raise SystemExit("--block retro needs --unit governorate: the 2024 "
                         "record cannot be split between constituency halves")

    v19, t19 = pres_counts(PRES19, canon, "constituency",
                           "constituency_valid_votes")
    y19, keys19, valid19 = to_shares(v19, t19, units, top=0.0)
    if SAIED not in keys19:
        raise SystemExit("Saied not found in the 2019 table")

    v14, t14 = pres_counts(PRES14, canon, "centre", "centre_valid_votes",
                           rnd="r1")
    p14r1, cand14, valid14 = to_shares(v14, t14, units, top=0.005)
    w14, u14 = pres_counts(PRES14, canon, "centre", "centre_valid_votes",
                           rnd="r2")
    p14r2, r2names, _ = to_shares(w14, u14, units, top=0.005)
    marz = [n for n in r2names if fold("المرزوقي") in n]
    if len(marz) != 1:
        raise SystemExit(f"round two: {len(marz)} names look like Marzouki")

    vl, tl = leg_counts(LEG14, canon, "constituency", "list_name")
    l14, list14, _ = to_shares(vl, tl, units, top=0.006)
    part = participation(canon, units)
    geo, regions = geography({u for u in units.values() if u is not None}, unit)

    l19 = party19 = None
    if block in ("concurrent", "retro"):
        v19l, t19l = leg_counts(LEG19, canon, "constituency", "list_name",
                                PARTY_KEYS)
        l19, _, _ = to_shares(v19l, t19l, units, top=0.0)
        party19 = sorted(PARTY_KEYS)
    pv24 = presidential_2024(units) if block == "retro" else None
    keyset = {u for u in units.values() if u is not None}
    cen, cen_cols = (census(keyset, unit, spread) if with_census
                     else (None, []))
    yb, yb_cols = yearbook(keyset, unit) if with_census else (None, [])
    pov, pov_cols = poverty(keyset, unit) if with_poverty else (None, [])

    cols = [f"p14r1_{label(n)}" for n in cand14]
    cols += ["p14r2_marzouki"]
    cols += [f"l14_{label(n)}" for n in list14]
    cols += ["log_ballots_per_seat", "pres_over_leg", "r2_lift",
             "spoilt_14", "blank_14"]
    cols += ["lat", "lon", "log_area"]
    cols += [f"region_{r.replace(' ', '_')}" for r in regions]
    if l19 is not None:
        cols += [f"l19_{p}" for p in party19] + ["ballots_2019_over_2014"]
    if pv24 is not None:
        cols += ["saied_2024", "turnout_2024", "blank_2024", "spoilt_2024"]
    if cen is not None:
        cols += [f"census_{v}" for v in cen_cols]
        cols += [f"yb_{v}" for v in yb_cols]
    if pov is not None:
        cols += [f"poverty_{v}" for v in pov_cols]

    names = sorted({u for u in units.values() if u is not None},
                   key=lambda u: -valid19[u])
    X, y, w, dom = [], [], [], []
    for u in names:
        g = geo.get(u)
        row = [p14r1[u][n] for n in cand14]
        row += [p14r2[u][marz[0]]]
        row += [l14[u][n] for n in list14]
        row += [part[u][k] for k in ("log_ballots_per_seat", "pres_over_leg",
                                     "r2_lift", "spoilt_14", "blank_14")]
        row += ([g["lat"], g["lon"], g["log_area"]] if g else [np.nan] * 3)
        row += [1.0 if g and g["region"] == r else 0.0 for r in regions]
        if l19 is not None:
            row += [l19[u].get(p, 0.0) for p in party19]
            row += [valid19[u] / valid14[u]]
        if pv24 is not None:
            row += [pv24[u][k] for k in ("saied_2024", "turnout_2024",
                                         "blank_2024", "spoilt_2024")]
        if cen is not None:
            row += [cen[u][v] if u in cen else np.nan for v in cen_cols]
            row += [yb[u][v] if u in yb else np.nan for v in yb_cols]
        if pov is not None:
            row += [pov[u][v] if u in pov and v in pov[u] else np.nan
                    for v in pov_cols]
        X.append(row)
        y.append(y19[u][SAIED])
        w.append(valid19[u])
        dom.append(g is not None)
    return (names, np.asarray(X, float), np.asarray(y, float), cols,
            np.asarray(w, float), np.asarray(dom), regions)


# ---- models ---------------------------------------------------------------
def logit(p):
    return np.log(p / (1 - p))


def expit(z):
    return 1 / (1 + np.exp(-z))


class Mean:
    """The baseline every other model has to beat."""

    def fit(self, X, y):
        self.m = float(np.mean(y))
        return self

    def predict(self, X):
        return np.full(len(X), self.m)


class Forward:
    """Forward-selected OLS on `k` columns, selection redone on every fit.

    Doing the selection inside the fold is the point. Choose the columns once on
    all the rows and the cross-validated error of the result is not an
    out-of-sample number at all: the held-out row helped pick the variables.
    """

    def __init__(self, k):
        self.k = k

    def fit(self, X, y):
        # Exact forward selection, but by partial correlation rather than by
        # refitting every candidate. Adding a column to an OLS fit reduces the
        # residual sum of squares in proportion to the squared partial
        # correlation of y with that column given the ones already in, so
        # residualising the whole candidate matrix at once picks the same column
        # as 170 separate regressions would, at a fraction of the cost. That
        # matters because the permutation test refits this hundreds of times.
        from sklearn.linear_model import LinearRegression
        idx = np.flatnonzero(~np.isnan(X).any(axis=0))
        A = np.ones((len(y), 1))
        r = y - y.mean()
        chosen = []
        for _ in range(min(self.k, len(idx))):
            coef, *_ = np.linalg.lstsq(A, X[:, idx], rcond=None)
            R = X[:, idx] - A @ coef
            norm = np.sqrt((R ** 2).sum(axis=0))
            score = np.abs(R.T @ r) / np.where(norm > 1e-12, norm, np.inf)
            j = int(np.argmax(score))
            chosen.append(int(idx[j]))
            A = np.column_stack([A, X[:, chosen[-1]]])
            b, *_ = np.linalg.lstsq(A, y, rcond=None)
            r = y - A @ b
            idx = np.delete(idx, j)
        self.cols = chosen
        self.model = LinearRegression().fit(X[:, chosen], y)
        return self

    def predict(self, X):
        return self.model.predict(X[:, self.cols])


class ForwardCV(Forward):
    """Forward selection with the number of variables chosen inside the fold.

    Fixing k at three is a decision taken by looking at the answer. This makes it
    a hyper-parameter like any other: each training fold runs its own
    leave-one-out over k from one to six and keeps whichever wins there, so the
    held-out unit has no say in how many variables its predictor gets.
    """

    def __init__(self, kmax=6):
        self.kmax = kmax

    def fit(self, X, y):
        best, self.k = np.inf, 1
        for k in range(1, min(self.kmax, len(y) - 2) + 1):
            err = 0.0
            for i in range(len(y)):
                m = np.arange(len(y)) != i
                f = Forward(k).fit(X[m], y[m])
                err += (float(f.predict(X[i:i + 1])[0]) - y[i]) ** 2
            if err < best:
                best, self.k = err, k
        f = Forward(self.k).fit(X, y)
        self.cols, self.model = f.cols, f.model
        return self


class Average:
    """The unweighted mean of several fitted models.

    Averaging predictors that err in different directions is the cheapest
    variance reduction there is, and on 27 rows variance is most of the error.
    It earns its place only if it beats its own members out of sample, which the
    table is there to say.
    """

    def __init__(self, members):
        self.members = members

    def fit(self, X, y):
        self.fitted = [m().fit(X, y) for m in self.members]
        return self

    def predict(self, X):
        return np.mean([np.asarray(m.predict(X)).ravel()
                        for m in self.fitted], axis=0)


class PCRCV:
    """Principal-component regression, component count by inner 5-fold CV."""

    def __init__(self, grid, seed):
        self.grid, self.seed = grid, seed

    def build(self, k):
        from sklearn.decomposition import PCA
        from sklearn.linear_model import LinearRegression
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
        return make_pipeline(StandardScaler(), PCA(n_components=k),
                             LinearRegression())

    def fit(self, X, y):
        from sklearn.model_selection import KFold, cross_val_score
        cv = KFold(5, shuffle=True, random_state=self.seed)
        best = -np.inf
        for k in self.grid:
            if k >= len(y):
                break
            p = self.build(k)
            s = cross_val_score(p, X, y, cv=cv,
                                scoring="neg_mean_squared_error").mean()
            if s > best:
                best, self.model, self.k = s, p, k
        self.model.fit(X, y)
        return self

    def predict(self, X):
        return np.asarray(self.model.predict(X)).ravel()


class PLSCV(PCRCV):
    """Partial least squares, component count by the same inner CV."""

    def build(self, k):
        from sklearn.cross_decomposition import PLSRegression
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
        return make_pipeline(StandardScaler(), PLSRegression(n_components=k))


def zoo(n_features, seed=0):
    """The candidate models, each a (name, factory) the CV loop can refit.

    Nothing exotic. With 27 rows the question is not which learner is cleverest
    but how few effective parameters the sample supports, so the set runs from
    the mean up through one- and two-variable OLS, penalised regression, and two
    tree ensembles that are here to be beaten.
    """
    from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
    from sklearn.linear_model import ElasticNetCV, LassoCV, RidgeCV
    from sklearn.model_selection import GridSearchCV, KFold
    from sklearn.neighbors import KNeighborsRegressor
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    # Shuffled, because the rows arrive sorted by size: an unshuffled 5-fold
    # would put the largest units in one fold and make the penalty depend on the
    # order the design matrix happens to be built in.
    inner = KFold(5, shuffle=True, random_state=seed)
    alphas = np.logspace(-3, 4, 60)
    grid = list(range(1, min(8, n_features) + 1))

    def scaled(est):
        return make_pipeline(StandardScaler(), est)

    return [
        ("mean", lambda: Mean()),
        ("ols_forward1", lambda: Forward(1)),
        ("ols_forward2", lambda: Forward(2)),
        ("ols_forward3", lambda: Forward(3)),
        ("ridge", lambda: scaled(RidgeCV(alphas=alphas))),
        ("lasso", lambda: scaled(LassoCV(alphas=alphas, cv=inner,
                                         max_iter=200000, random_state=seed))),
        ("elasticnet", lambda: scaled(ElasticNetCV(
            l1_ratio=[0.1, 0.5, 0.7, 0.9, 0.95, 1.0], alphas=alphas, cv=inner,
            max_iter=200000, random_state=seed))),
        ("ols_forwardcv", lambda: ForwardCV()),
        ("pcr", lambda: PCRCV(grid, seed)),
        ("pls", lambda: PLSCV(grid, seed)),
        # Nearest neighbours earns its place for one reason: run it on the
        # geography block alone and it is spatial interpolation, an estimate of
        # a unit from the units around it. That is the standard way to fill a
        # hole in a map, and the ablation table is where it gets tested.
        ("knn", lambda: GridSearchCV(
            make_pipeline(StandardScaler(), KNeighborsRegressor()),
            {"kneighborsregressor__n_neighbors": [1, 2, 3, 4, 5, 6, 8],
             "kneighborsregressor__weights": ["uniform", "distance"]},
            cv=inner, scoring="neg_mean_squared_error")),
        ("random_forest", lambda: RandomForestRegressor(
            n_estimators=500, min_samples_leaf=2, random_state=seed)),
        ("gbm", lambda: GradientBoostingRegressor(
            n_estimators=300, max_depth=2, learning_rate=0.05,
            random_state=seed)),
        ("average", lambda: Average([
            lambda: Forward(3),
            lambda: scaled(LassoCV(alphas=alphas, cv=inner, max_iter=200000,
                                   random_state=seed)),
            lambda: scaled(ElasticNetCV(
                l1_ratio=[0.1, 0.5, 0.7, 0.9, 0.95, 1.0], alphas=alphas,
                cv=inner, max_iter=200000, random_state=seed)),
            lambda: PCRCV(grid, seed)])),
    ]


# ---- evaluation ------------------------------------------------------------
def loo(factory, X, y, link):
    """Leave-one-out predictions, the model refitted from scratch each time."""
    pred = np.empty(len(y))
    for i in range(len(y)):
        keep = np.arange(len(y)) != i
        m = factory().fit(X[keep], link[0](y[keep]))
        pred[i] = link[1](float(np.asarray(m.predict(X[i:i + 1])).ravel()[0]))
    return pred


def scores(y, pred, w):
    err = pred - y
    ss = float(np.sum((y - y.mean()) ** 2))
    return {"rmse_pp": 100 * float(np.sqrt(np.mean(err ** 2))),
            "mae_pp": 100 * float(np.mean(np.abs(err))),
            "max_pp": 100 * float(np.max(np.abs(err))),
            "wrmse_pp": 100 * float(np.sqrt(np.sum(w * err ** 2) / np.sum(w))),
            "r2": 1 - float(np.sum(err ** 2)) / ss}


def nested_recipe(X, y, links, want, seed=0):
    """Leave-one-out over the *whole procedure*, model choice included.

    The table picks a winner by comparing 22 model-and-link combinations on the
    same leave-one-out predictions. That winner's score is the maximum of 22
    noisy numbers on one small sample, and the maximum of a set of noisy numbers
    is biased upward however honest each one is. This removes the bias the only
    way it can be removed: hold a unit out, run the entire selection on the rest,
    and let the procedure predict the held-out unit with whatever it chose. What
    comes back is what someone following this recipe would actually have got.
    """
    picks, pred = [], np.empty(len(y))
    for i in range(len(y)):
        keep = np.arange(len(y)) != i
        Xi, yi = X[keep], y[keep]
        best = None
        for lk in want:
            for name, factory in zoo(Xi.shape[1], seed):
                inner = loo(factory, Xi, yi, links[lk])
                rmse = float(np.sqrt(np.mean((inner - yi) ** 2)))
                if best is None or rmse < best[0]:
                    best = (rmse, name, lk, factory)
        _, name, lk, factory = best
        m = factory().fit(Xi, links[lk][0](yi))
        pred[i] = links[lk][1](float(np.asarray(
            m.predict(X[i:i + 1])).ravel()[0]))
        picks.append(f"{name}/{lk}")
    return pred, collections.Counter(picks)


def permutation(factory, X, y, link, n, seed=0):
    """How often does a shuffled target do as well, under the same procedure?

    A learner flexible enough to help on 27 rows is flexible enough to find
    structure in noise, so the question is not whether the model beats the mean
    but whether it beats it by more than it would on a target with the geography
    shuffled out. The p-value counts the observed value in both numerator and
    denominator, which is the conservative convention.
    """
    rng = np.random.default_rng(seed)
    obs = float(np.sqrt(np.mean((loo(factory, X, y, link) - y) ** 2)))
    null = np.empty(n)
    for k in range(n):
        yp = rng.permutation(y)
        null[k] = float(np.sqrt(np.mean((loo(factory, X, yp, link) - yp) ** 2)))
    return obs, null, (1 + int(np.sum(null <= obs))) / (n + 1)


def seed_sweep(name, X, y, link, seeds):
    """The stochastic learners refitted under other seeds, all else equal."""
    out = []
    for sd in seeds:
        pred = loo(dict(zoo(X.shape[1], sd))[name], X, y, link)
        out.append(float(np.sqrt(np.mean((pred - y) ** 2))))
    return np.array(out)


BLOCKS = {
    "pres_2014": lambda c: c.startswith("p14r1_") or c == "p14r2_marzouki",
    "leg_2014": lambda c: c.startswith("l14_"),
    "participation": lambda c: c in ("log_ballots_per_seat", "pres_over_leg",
                                     "r2_lift", "spoilt_14", "blank_14"),
    "geography": lambda c: c.startswith(("lat", "lon", "log_area", "region_")),
    "leg_2019": lambda c: (c.startswith("l19_") or
                           c == "ballots_2019_over_2014"),
    "pres_2024": lambda c: c in ("saied_2024", "turnout_2024", "blank_2024",
                                 "spoilt_2024"),
    "census_2014": lambda c: c.startswith("census_"),
    "yearbook_2018": lambda c: c.startswith("yb_"),
    "poverty_2015": lambda c: c.startswith("poverty_"),
}


def ablate(X, y, w, kept, link, models=("mean", "ridge", "random_forest",
                                        "gbm")):
    """Each block of predictors alone, and everything except each block.

    A cross-validated score for the whole matrix says how well the thing
    predicts; it does not say what is doing the predicting. Refitting on one
    block at a time answers that, and refitting on everything-but-one block
    answers the complementary question of what is not redundant. Both matter
    here, because the blocks are collinear: a variable can carry signal and
    still add nothing once the others are in.
    """
    present = {b: [i for i, c in enumerate(kept) if f(c)]
               for b, f in BLOCKS.items()}
    present = {b: idx for b, idx in present.items() if idx}
    out = []
    subsets = [("all", list(range(len(kept))))]
    subsets += [(f"{b} only", idx) for b, idx in present.items()]
    subsets += [(f"without {b}",
                 [i for i in range(len(kept)) if i not in set(idx)])
                for b, idx in present.items() if len(present) > 1]
    for tag, idx in subsets:
        row = {"subset": tag, "n_cols": len(idx)}
        for name in models:
            factory = dict(zoo(len(idx), 0))[name]
            row[name] = scores(y, loo(factory, X[:, idx], y, link),
                               w)["rmse_pp"]
        out.append(row)
    return out


def report_ablation(rows, models, header):
    print(f"\n{header}")
    print(f"  {'predictors':<22} {'cols':>5} " +
          " ".join(f"{m:>14}" for m in models))
    for r in rows:
        print(f"  {r['subset']:<22} {r['n_cols']:5d} " +
              " ".join(f"{r[m]:13.2f}p" for m in models))


def compositional(X, y, others, link, name="gbm"):
    """Saied as what is left after every other candidate is predicted.

    A share is one part of a composition that sums to one, and the other 25
    candidates in 2019 had things a model can hold on to that Saied did not:
    Mourou had Ennahda's 2014 vote behind him, Karoui had Nidaa's, Abir Moussi
    had the old regime's map. If those are the predictable parts, then the
    residual -- one minus their sum -- is a route to the unpredictable one.

    Leave-one-out here means holding a constituency out of all 25 fits at once,
    so nothing about the held-out unit reaches any of them.
    """
    pred = np.empty(len(y))
    for i in range(len(y)):
        keep = np.arange(len(y)) != i
        total = 0.0
        for j in range(others.shape[1]):
            m = dict(zoo(X.shape[1]))[name]().fit(X[keep],
                                                  link[0](others[keep, j]))
            total += link[1](float(np.asarray(
                m.predict(X[i:i + 1])).ravel()[0]))
        pred[i] = 1.0 - total
    return pred


def other_shares(unit, dom_names):
    """The 2019 shares of every candidate except Saied, for the given units."""
    canon = sorted({fold(r["centre"]) for r in read(PRES14)})
    units = ({c: c for c in canon} if unit == "constituency"
             else {c: gov_of(c) for c in canon})
    v19, t19 = pres_counts(PRES19, canon, "constituency",
                           "constituency_valid_votes")
    sh, keys, _ = to_shares(v19, t19, units, top=0.0)
    others = [k for k in keys if k != SAIED]
    return np.array([[sh[u][k] for k in others] for u in dom_names]), others


def report(rows, header):
    print(f"\n{header}")
    print(f"  {'model':<14} {'LOO RMSE':>9} {'MAE':>7} {'max':>7} "
          f"{'wRMSE':>7} {'LOO R2':>8} {'in-sample R2':>13}")
    for r in rows:
        print(f"  {r['model']:<14} {r['rmse_pp']:8.2f}p {r['mae_pp']:6.2f}p "
              f"{r['max_pp']:6.2f}p {r['wrmse_pp']:6.2f}p {r['r2']:8.3f} "
              f"{r['in_sample_r2']:13.3f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--unit", choices=["constituency", "governorate"],
                    default="constituency")
    ap.add_argument("--block", choices=["forecast", "concurrent", "retro"],
                    default="forecast")
    ap.add_argument("--link", choices=["identity", "logit", "both"],
                    default="both")
    ap.add_argument("--nested", action="store_true",
                    help="leave-one-out over the whole selection procedure")
    ap.add_argument("--permute", type=int, default=0, metavar="N",
                    help="permutation test for the winner, N shuffles")
    ap.add_argument("--seeds", type=int, default=0, metavar="N",
                    help="refit the stochastic learners under N other seeds")
    ap.add_argument("--no-census", dest="census", action="store_false",
                    help="drop the 2014 census block, leaving elections and "
                         "geography only")
    ap.add_argument("--spread", action="store_true",
                    help="give each census variable a companion column holding "
                         "its spread across the unit's own delegations")
    ap.add_argument("--poverty", action="store_true",
                    help="add the 2015 delegation poverty map, which costs "
                         "Siliana: the published table omits its delegations, "
                         "so that constituency leaves the sample")
    ap.add_argument("--compositional", action="store_true",
                    help="also estimate Saied as one minus the sum of the "
                         "other 25 candidates, each predicted separately")
    ap.add_argument("--ablate", action="store_true",
                    help="refit on each block of predictors alone, and on "
                         "everything except each block")
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args()

    names, X, y, cols, w, dom, regions = design(a.block, a.unit,
                                                a.census, a.poverty,
                                                a.spread)
    kind = {"forecast": "known before polling day",
            "concurrent": "same season, three weeks after the first round",
            "retro": "includes the 2024 result, five years after"}[a.block]
    print(f"unit: {a.unit}   information set: {a.block} ({kind})")
    print(f"{len(names)} units, {X.shape[1]} predictors "
          f"({dom.sum()} domestic, {(~dom).sum()} abroad)")
    print(f"target: Saied share, domestic mean {100 * y[dom].mean():.2f}%, "
          f"sd {100 * y[dom].std(ddof=1):.2f}, "
          f"range {100 * y[dom].min():.2f}-{100 * y[dom].max():.2f}")

    if a.poverty:
        pov = [i for i, c in enumerate(cols) if c.startswith("poverty_")]
        gone = dom & np.isnan(X[:, pov]).any(axis=1)
        if gone.any():
            print(f"dropped for want of a poverty figure: "
                  f"{', '.join(np.array(names)[gone])}")
            dom = dom & ~gone

    keep = ~np.isnan(X[dom]).any(axis=0)
    Xd, yd, wd = X[dom][:, keep], y[dom], w[dom]
    kept = [c for c, k in zip(cols, keep) if k]

    links = {"identity": (lambda v: v, lambda v: v), "logit": (logit, expit)}
    want = ["identity", "logit"] if a.link == "both" else [a.link]

    best, out_rows = None, []
    for lk in want:
        rows = []
        for name, factory in zoo(Xd.shape[1]):
            pred = loo(factory, Xd, yd, links[lk])
            m = factory().fit(Xd, links[lk][0](yd))
            ins = links[lk][1](np.asarray(m.predict(Xd)).ravel())
            s = scores(yd, pred, wd)
            s.update(model=name, link=lk, in_sample_r2=1 - float(
                np.sum((ins - yd) ** 2)) / float(np.sum((yd - yd.mean()) ** 2)))
            rows.append(s)
            if best is None or s["rmse_pp"] < best["rmse_pp"]:
                best = dict(s, factory=factory, pred=pred)
        rows.sort(key=lambda r: r["rmse_pp"])
        report(rows, f"link = {lk} -- leave-one-out over {dom.sum()} "
                     f"domestic units")
        out_rows += [dict(r) for r in rows]

    base = min(r["rmse_pp"] for r in out_rows if r["model"] == "mean")
    print(f"\nbest: {best['model']} ({best['link']} link), LOO RMSE "
          f"{best['rmse_pp']:.2f} points against a {base:.2f} baseline")

    # `mean` and the forward-selected fits use no random state at all: their
    # folds, their column order and their solution are fixed by the data.
    DETERMINISTIC = {"mean", "ols_forward1", "ols_forward2", "ols_forward3"}

    extra = {}
    if a.seeds and best["model"] in DETERMINISTIC:
        print(f"\nseed sweep: {best['model']} is deterministic -- no random "
              f"state to vary, so there is nothing to sweep")
    elif a.seeds:
        sw = seed_sweep(best["model"], Xd, yd, links[best["link"]],
                        range(1, a.seeds + 1))
        print(f"\nseed sweep: {best['model']} under {a.seeds} other seeds gives "
              f"LOO RMSE {100 * sw.min():.2f} to {100 * sw.max():.2f}, median "
              f"{100 * float(np.median(sw)):.2f} "
              f"(seed 0 gave {best['rmse_pp']:.2f})")
        extra["seed_sweep_pp"] = sorted(100 * sw)

    if a.permute:
        obs, null, p = permutation(best["factory"], Xd, yd,
                                   links[best["link"]], a.permute)
        print(f"\npermutation test, {a.permute} shuffles: observed LOO RMSE "
              f"{100 * obs:.2f}, null median {100 * float(np.median(null)):.2f},"
              f" null 5th percentile {100 * float(np.percentile(null, 5)):.2f}, "
              f"p = {p:.4f}")
        extra["permutation"] = {
            "n": a.permute, "observed_pp": 100 * obs,
            "null_median_pp": 100 * float(np.median(null)),
            "null_p05_pp": 100 * float(np.percentile(null, 5)), "p_value": p}

    if a.nested:
        npred, picks = nested_recipe(Xd, yd, links, want)
        ns = scores(yd, npred, wd)
        print(f"\nnested leave-one-out over the whole procedure, selection "
              f"redone on each fold of {dom.sum() - 1}")
        print(f"  RMSE {ns['rmse_pp']:.2f} points, MAE {ns['mae_pp']:.2f}, "
              f"R2 {ns['r2']:.3f}, against the {base:.2f} baseline")
        print("  picked, fold by fold: " +
              ", ".join(f"{k} x{v}" for k, v in picks.most_common()))
        extra["nested"] = dict(ns, picks=dict(picks))

    if a.compositional:
        others, _ = other_shares(a.unit, list(np.array(names)[dom]))
        cs = scores(yd, compositional(Xd, yd, others, links[best["link"]]), wd)
        print(f"\ncompositional alternative: Saied as one minus the sum of "
              f"{others.shape[1]} separately predicted candidates")
        print(f"  RMSE {cs['rmse_pp']:.2f} points, MAE {cs['mae_pp']:.2f}, "
              f"R2 {cs['r2']:.3f}, against the {base:.2f} baseline")
        extra["compositional"] = dict(cs, n_candidates=int(others.shape[1]))

    if a.ablate:
        models = ("mean", "ols_forward3", "ridge", "knn", "random_forest",
                  "gbm")
        rows = ablate(Xd, yd, wd, kept, links[best["link"]], models)
        report_ablation(rows, models, f"leave-one-out RMSE by block of "
                                      f"predictors, {best['link']} link")
        extra["ablation"] = rows

    ab_pred = None
    if (~dom).any():
        # Whatever the out-of-country units do not have, neither side may use:
        # geography (no polygon) and the census (published for the country, not
        # for its emigrants). Dropping those columns from the training rows too
        # is what makes this a transfer rather than a comparison of two models.
        finite = ~np.isnan(X[~dom][:, keep]).any(axis=0)
        elec = [i for i, c in enumerate(kept) if finite[i]
                and not c.startswith(("lat", "lon", "log_area", "region_"))]
        lk = links[best["link"]]
        Xe = X[:, keep][:, elec]
        m = best["factory"]().fit(Xe[dom], lk[0](y[dom]))
        ab_pred = lk[1](np.asarray(m.predict(Xe[~dom])).ravel())
        red = scores(y[dom], loo(best["factory"], Xe[dom], y[dom], lk), w[dom])
        s_ab = scores(y[~dom], ab_pred, w[~dom])
        print(f"\ncold transfer to the {(~dom).sum()} out-of-country units "
              f"({len(elec)} electoral columns, geography dropped from both "
              f"sides)")
        print(f"  domestic LOO RMSE on that reduced matrix: "
              f"{red['rmse_pp']:.2f} points")
        print(f"  abroad RMSE {s_ab['rmse_pp']:.2f}, MAE {s_ab['mae_pp']:.2f}, "
              f"max {s_ab['max_pp']:.2f}")
        for n, t, p in zip(np.array(names)[~dom], y[~dom], ab_pred):
            print(f"    {100 * t:6.2f} actual   {100 * p:6.2f} predicted   {n}")
        extra["abroad"] = s_ab
        extra["abroad_reduced_domestic"] = red

    if a.no_write:
        return

    pred_full = np.full(len(names), np.nan)
    pred_full[dom] = best["pred"]
    if ab_pred is not None:
        pred_full[~dom] = ab_pred
    out_csv = OUT_CSV.format(unit=a.unit)
    out_json = OUT_JSON.format(unit=a.unit)
    os.makedirs(os.path.dirname(out_json), exist_ok=True)
    with open(out_csv, "w", encoding="utf-8", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow(["unit", "unit_kind", "domestic", "valid_votes",
                     "saied_share_pct", "predicted_pct", "residual_pp",
                     "prediction_kind"])
        for i, n in enumerate(names):
            wr.writerow([n, a.unit, int(dom[i]), int(w[i]),
                         round(100 * y[i], 4), round(100 * pred_full[i], 4),
                         round(100 * (pred_full[i] - y[i]), 4),
                         "leave_one_out" if dom[i] else "cold_transfer"])
    with open(out_json, "w", encoding="utf-8") as fh:
        json.dump({"unit": a.unit, "block": a.block,
                   "n_domestic": int(dom.sum()),
                   "n_predictors": int(Xd.shape[1]), "predictors": kept,
                   "baseline_rmse_pp": base, "models": out_rows,
                   "best": {k: v for k, v in best.items()
                            if k not in ("factory", "pred")},
                   **extra}, fh, ensure_ascii=False, indent=2)
    print(f"\nwrote {out_csv} and {out_json}")


if __name__ == "__main__":
    main()
