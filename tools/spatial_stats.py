"""Global and local spatial autocorrelation, with permutation inference.

What these answer that no map in `maps/` answers yet
----------------------------------------------------
Every other figure in this repo shows *where* a value is. None of them says
whether the pattern is more clustered than chance would produce. A choropleth of
a random variable still looks patchy, and the eye will find regions in it, so
"Saied is strong in the centre" is not a finding until it survives a null.

That is the whole job here: attach a null model to the pattern.

Conventions, chosen so the pieces agree
---------------------------------------
`z` is standardised with the population standard deviation, so `z'z = n` and
Moran's I under a row-standardised `W` reduces to `z'Wz / n`. The pay-off is
that **the mean of the local statistics is exactly the global one**, which is a
free arithmetic check on the local computation and is asserted in `local_moran`.

Local Moran's I (Anselin 1995) is `I_i = z_i * (Wz)_i`, and the four-way
classification reads off the two signs: a unit above the mean whose neighbours
are above it too is `HH`, and so on. The signs do not depend on the scaling, so
the labels are convention-independent even though the magnitudes are not.

Getis-Ord Gi* includes the unit itself, which is what makes it a hot/cold-spot
statistic rather than an association statistic: it asks whether the local
*total* is unusual, so it has no outlier categories and is the more legible of
the two on a map. Both are published because they answer different questions.

Inference, and why permutation rather than the analytical z
-----------------------------------------------------------
The analytical variance of Moran's I assumes normality. These shares are
severely skewed -- Saied's delegation median is 93.8% against a 59.7% floor --
so the normal approximation is not credible here, and conditional permutation
costs little. `local_moran` and `getis_ord` hold unit `i`'s own value fixed and
draw its neighbours' values at random from the remaining `n-1`, without
replacement, `perms` times.

Each unit's draw is an exact uniform `k_i`-subset of the other values: one
random permutation of the others is generated per replication and each unit
reads a random offset into it. Units within a replication are therefore
correlated with each other, as they are in the reference implementations; that
does not bias any single unit's null distribution, and Benjamini-Hochberg
remains valid under this kind of positive dependence.

Multiple testing is not optional at this scale
----------------------------------------------
The imada level runs **2,042 simultaneous tests**. At a nominal 0.05 that
expects about 102 false positives, which is more than the number of units many
candidates' genuine clusters occupy -- so an uncorrected LISA map at this level
is mostly an artefact of its own multiplicity. Every p-value here goes through
Benjamini-Hochberg, and `fdr()` returns the adjusted threshold so a figure can
say what it actually used.

Rate instability, and the Empirical Bayes correction
----------------------------------------------------
A share is a ratio, and a ratio computed from few votes is noisy. An imada with
300 valid votes has a standard error on Maghzaoui's share several times that of
one with 5,000, so a raw-rate LISA systematically flags *small* units as spatial
outliers -- a statement about sampling variance dressed up as geography.

`eb_standardise` applies the Assuncao-Reis (1999) Empirical Bayes correction,
which divides each deviation by that unit's own expected variance
`s^2 + b/P_i` rather than by one national constant. Both versions are computed
and the figures publish the raw one with the EB disagreement counted, so the
correction's effect is visible rather than assumed.
"""

import numpy as np


def standardise(x):
    """z with population sd, so z'z = n exactly."""
    x = np.asarray(x, dtype=float)
    sd = x.std()
    if sd == 0:
        raise ValueError("zero variance; a spatial statistic is undefined")
    return (x - x.mean()) / sd


def eb_standardise(events, population):
    """Assuncao-Reis Empirical Bayes standardised rate.

    Returns (z, s2, negative_s2). `s2` is the estimated between-unit variance of
    the true rates; when the observed variance is smaller than the Poisson noise
    alone it comes out negative, which means "no signal beyond sampling noise"
    and is clamped to zero -- reported rather than hidden, because a clamp is a
    statement about the data.
    """
    o = np.asarray(events, dtype=float)
    p = np.asarray(population, dtype=float)
    b = o.sum() / p.sum()
    rate = o / p
    pbar = p.mean()
    s2 = (p * (rate - b) ** 2).sum() / p.sum() - b / pbar
    negative = bool(s2 < 0)
    s2 = max(s2, 0.0)
    v = s2 + b / p
    return (rate - b) / np.sqrt(v), float(s2), negative


def global_moran(z, W, perms=999, seed=0):
    """Moran's I with a full-map permutation null.

    `z` must already be standardised, so I = z'Wz / n. Returns a dict; the
    pseudo p-value is two-sided and cannot go below 1/(perms+1), which is why
    that floor is reported alongside it rather than printed as "p < 0.001".
    """
    z = np.asarray(z, dtype=float)
    n = z.size
    obs = float(z @ (W @ z) / n)
    rng = np.random.default_rng(seed)
    sim = np.empty(perms)
    for r in range(perms):
        zp = rng.permutation(z)
        sim[r] = zp @ (W @ zp) / n
    # two-sided, counting the observed value in its own reference distribution
    extreme = int(np.sum(np.abs(sim - sim.mean()) >= abs(obs - sim.mean())))
    return {
        "I": obs,
        "expected": -1.0 / (n - 1),
        "sim_mean": float(sim.mean()),
        "sim_sd": float(sim.std()),
        "z_sim": float((obs - sim.mean()) / sim.std()),
        "p_sim": (extreme + 1) / (perms + 1),
        "p_floor": 1.0 / (perms + 1),
        "perms": perms,
        "n": n,
    }


def _pad_neighbours(adj):
    """(idx, mask, k) as dense (n, kmax) arrays, for vectorised permutation."""
    n = len(adj)
    kmax = max(len(a) for a in adj)
    idx = np.zeros((n, kmax), dtype=np.int64)
    mask = np.zeros((n, kmax), dtype=bool)
    for i, nbs in enumerate(adj):
        nb = sorted(nbs)
        idx[i, :len(nb)] = nb
        mask[i, :len(nb)] = True
    return idx, mask, mask.sum(1)


def _conditional_lags(z, adj, perms, seed):
    """(perms, n) simulated neighbour means under conditional permutation.

    Unit i's own value is held out of its own draw: indices are sampled from
    0..n-2 and any index at or above i is shifted up by one, which is the
    standard way to draw from "everything except me" without building n
    separate pools.
    """
    z = np.asarray(z, dtype=float)
    n = z.size
    idx, mask, k = _pad_neighbours(adj)
    kmax = idx.shape[1]
    rng = np.random.default_rng(seed)
    out = np.empty((perms, n))
    steps = np.arange(kmax)
    for r in range(perms):
        order = rng.permutation(n - 1)              # a permutation of "the others"
        off = rng.integers(0, n - 1, size=n)        # each unit reads a random window
        take = order[(off[:, None] + steps[None, :]) % (n - 1)]
        take = take + (take >= np.arange(n)[:, None])   # skip i itself
        vals = np.where(mask, z[take], 0.0)
        out[r] = vals.sum(1) / k
    return out


def fdr(p, q=0.05):
    """Benjamini-Hochberg. Returns (significant mask, cut-off actually used).

    The cut-off is the largest p that passed, so a figure can print the
    threshold it applied rather than the nominal q -- at the imada level those
    differ by more than an order of magnitude.
    """
    p = np.asarray(p, dtype=float)
    m = p.size
    order = np.argsort(p)
    ranked = p[order]
    passing = ranked <= (np.arange(1, m + 1) / m) * q
    if not passing.any():
        return np.zeros(m, dtype=bool), 0.0
    cut = ranked[np.max(np.flatnonzero(passing))]
    return p <= cut, float(cut)


#: LISA quadrant labels. Index 0 is reserved for "not significant".
QUADRANTS = {0: "ns", 1: "HH", 2: "LH", 3: "LL", 4: "HL"}


def local_moran(z, W, adj, perms=999, seed=0, q=0.05):
    """Local Moran's I, conditional permutation p-values, BH-corrected.

    Returns a dict with `I` (local statistics), `lag`, `p`, `sig`, `quadrant`
    (0 where not significant), and the FDR cut-off.
    """
    z = np.asarray(z, dtype=float)
    n = z.size
    lag = np.asarray(W @ z).ravel()
    Ii = z * lag
    # The scaling convention pays off here: the local statistics average to the
    # global one, so a mismatch means the weights and the values disagree.
    assert abs(Ii.mean() - float(z @ (W @ z) / n)) < 1e-9, "local/global mismatch"

    sim_lag = _conditional_lags(z, adj, perms, seed)
    sim_I = z[None, :] * sim_lag
    # two-sided about each unit's own simulated mean
    centre = sim_I.mean(0)
    extreme = np.sum(np.abs(sim_I - centre) >= np.abs(Ii - centre), axis=0)
    p = (extreme + 1) / (perms + 1)

    sig, cut = fdr(p, q)
    quad = np.where(z > 0, np.where(lag > 0, 1, 4), np.where(lag > 0, 2, 3))
    return {
        "I": Ii, "lag": lag, "p": p, "sig": sig, "cut": cut,
        "quadrant": np.where(sig, quad, 0), "perms": perms, "q": q,
    }


def getis_ord(x, adj, perms=999, seed=0, q=0.05):
    """Getis-Ord Gi* (self included), conditional permutation, BH-corrected.

    Reported as a signed z-score against each unit's own simulated null, so the
    sign is the hot/cold direction and the magnitude is comparable across units
    despite their different neighbour counts.
    """
    x = np.asarray(x, dtype=float)
    n = x.size
    star = [sorted(set(a) | {i}) for i, a in enumerate(adj)]
    k = np.array([len(s) for s in star], dtype=float)
    obs = np.array([x[s].mean() for s in star])

    # The star lag includes x_i, so unit i's own value is fixed and k_i - 1
    # neighbours are drawn -- the conditional null for Gi*.
    sim_nb = _conditional_lags(x, adj, perms, seed)
    sim = (sim_nb * (k - 1)[None, :] + x[None, :]) / k[None, :]
    centre = sim.mean(0)
    sd = sim.std(0)
    zsc = np.where(sd > 0, (obs - centre) / np.where(sd > 0, sd, 1.0), 0.0)
    extreme = np.sum(np.abs(sim - centre) >= np.abs(obs - centre), axis=0)
    p = (extreme + 1) / (perms + 1)
    sig, cut = fdr(p, q)
    return {
        "G": obs, "z": zsc, "p": p, "sig": sig, "cut": cut,
        "hot": sig & (zsc > 0), "cold": sig & (zsc < 0),
        "perms": perms, "q": q,
    }
