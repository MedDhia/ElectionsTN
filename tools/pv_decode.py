"""Read a whole PV form by maximum-likelihood decoding under its own identities.

A per-digit classifier good enough to read this corpus cell by cell is not
reachable from the labels available: at ~94% per digit a four-cell field is
right about 78% of the time and a whole form of twenty fields essentially never.
But the form is not twenty independent numbers. It is an error-correcting code.

The turnout count is written **five times** — ballots extracted from the urn,
voters who signed the register, voters who voted, the sum of valid, blank and
spoilt papers, and again through the reconciliation rows that tie those together.
Decoding pivots on that shared count: every candidate value is scored by all
five readings at once, so a misread digit in one of them is outvoted rather than
believed. The valid-vote total is likewise written twice, and the three
candidate scores must sum to it.

The identities used (verified against all 30 hand-checked pilot forms, where
each held without exception unless noted):

    c_signed == w_voted            voters who signed are voters who voted
    match1 == c_signed - s_extracted
    match3 == w_voted - n_total
    n_total == valid + blank + spoilt
    m_total == s_extracted + d_damaged + r_remaining
    match2 == b_delivered - m_total
    q_declared == valid == zammel + maghzaoui + saied

The four `match` rows are reconciliation *differences*, zero on all 30 pilot
forms, but they stay free variables rather than being pinned to zero: one pilot
form has a genuine discrepancy in the ballot count, and forcing it to reconcile
would turn a truthful record into a wrong reading.

Fields absent from the grid detection contribute nothing rather than failing the
form — the remaining identities often still pin the answer, and the fields that
could not be located come back as None instead of a guess. `a_registered` takes
part in no identity at all, so it is read cell by cell and is never certified.

The margin between the best and second-best consistent reading is what makes a
decode trustworthy: a form whose runner-up is far behind has essentially one
reading its own arithmetic admits.
"""
import itertools
import numpy as np

TOPK = 6           # candidate values kept per free field
TOPD = 3           # digit alternatives considered per cell
PIVOT_K = 12       # candidate values for the shared turnout count
MATCH_K = 3        # the reconciliation rows are near-always zero, so a wide
                   # search over them buys nothing and costs a lot: they
                   # multiply the size of every subproblem downstream
NEG = -1e9

BALLOT = ["s_extracted", "d_damaged", "r_remaining", "m_total",
          "b_delivered", "c_signed", "match1", "match2"]
VOTES = ["valid", "blank", "spoilt", "n_total", "match3", "w_voted",
         "q_declared", "zammel", "maghzaoui", "saied"]
FREE = ["a_registered", "match4"]
ALL = BALLOT + VOTES + FREE


class FieldProbs:
    """log P(field = value), for any value, from the cell probability vectors."""

    known = True

    def __init__(self, logp):
        self.logp = logp
        self.n = len(logp)
        self.max = 10 ** self.n - 1

    @classmethod
    def from_probs(cls, probs):
        return cls(np.log(np.maximum(probs, 1e-6)))

    def score(self, value):
        if value is None or value < 0 or value > self.max:
            return NEG
        s = 0.0
        for i in range(self.n - 1, -1, -1):
            s += self.logp[i, value % 10]
            value //= 10
        return s

    def best(self):
        return int("".join(str(d) for d in self.logp.argmax(1)))

    def candidates(self, k=TOPK):
        """Top-k values, built from the few likeliest digits in each cell."""
        out = []
        for combo in itertools.product(*(np.argsort(-r)[:TOPD] for r in self.logp)):
            v, s = 0, 0.0
            for i, d in enumerate(combo):
                v = v * 10 + int(d)
                s += self.logp[i, d]
            out.append((s, v))
        out.sort(reverse=True)
        return [v for _, v in out[:k]]


class Unknown:
    """A field the grid detector could not locate: no evidence either way."""

    known = False
    n = 0

    def score(self, value):
        return 0.0

    def best(self):
        return None

    def candidates(self, k=TOPK):
        return []


UNKNOWN = Unknown()


def combine(*fields):
    """Fuse independent readings of the same quantity into one distribution."""
    known = [f for f in fields if f.known]
    if not known:
        return UNKNOWN
    n = max(f.n for f in known)
    total = np.zeros((n, 10))
    for f in known:
        total[n - f.n:] += f.logp     # right-align: units digit last
    return FieldProbs(total)


def _top2(options):
    """(best score, best value, gap to the runner-up) over scored options.

    The gap is the point: a maximisation with a clear winner is a decision the
    form's arithmetic made, and one with a near-tie is a coin flip dressed up as
    a reading. The decoder's confidence is the smallest of these gaps, so a form
    is only trusted when every choice inside it was clear.
    """
    best = (NEG, None)
    second = NEG
    for sc, val in options:
        if sc > best[0]:
            best, second = (sc, val), best[0]
        elif sc > second:
            second = sc
    if best[1] is None:
        return 0.0, None, float("inf")
    return best[0], best[1], best[0] - second if second > NEG else float("inf")


def _ballot_tail(P, s):
    """Best (d, r, m, match2, b) given the ballots extracted."""
    ds, rs = P["d_damaged"].candidates(), P["r_remaining"].candidates()
    if not ds or not rs:
        # Nothing to search, but the rest of the form is still readable: hand
        # back an empty result rather than None, so one undetected box does not
        # cost the whole record.
        return 0.0, {}, float("inf")
    m2s = P["match2"].candidates(MATCH_K) or [0]

    def options():
        for d in ds:
            sd = P["d_damaged"].score(d)
            for r in rs:
                m = s + d + r
                head = sd + P["r_remaining"].score(r) + P["m_total"].score(m)
                bs, m2, _ = _top2((P["match2"].score(k) + P["b_delivered"].score(m + k), k)
                                  for k in m2s)
                if m2 is None:        # no delivery total this m can reconcile with
                    continue
                yield head + bs, dict(d_damaged=d, r_remaining=r, m_total=m,
                                      match2=m2, b_delivered=m + m2)

    sc, vals, gap = _top2(options())
    return sc, ({} if vals is None else vals), gap


def _cand_split(P, valid, memo):
    """Best (zammel, maghzaoui, saied) summing to the valid-vote total."""
    if valid in memo:
        return memo[valid]
    zs, mgs = P["zammel"].candidates(), P["maghzaoui"].candidates()
    if not zs or not mgs or valid < 0:
        memo[valid] = (0.0, None, float("inf"))
    else:
        memo[valid] = _top2(
            (P["zammel"].score(z) + P["maghzaoui"].score(mg)
             + P["saied"].score(valid - z - mg), (z, mg, valid - z - mg))
            for z in zs for mg in mgs)
    return memo[valid]


def _vote_tail(P, V, n, memo):
    """Best (valid, blank, spoilt, q, candidate votes) given the papers counted.

    The candidate votes are scored inside the search over the blank/spoilt split
    rather than after it. Choosing the split first and the candidates second
    throws away the strongest evidence there is about the valid-vote total —
    that three numbers elsewhere on the form have to add up to it.
    """
    bs, sps = P["blank"].candidates(), P["spoilt"].candidates()
    if not bs or not sps:
        return 0.0, {"n_total": n}, float("inf")

    def options():
        for b in bs:
            sb = P["blank"].score(b)
            for sp in sps:
                valid = n - b - sp
                if valid < 0:
                    continue
                cs, cand, _ = _cand_split(P, valid, memo)
                out = dict(blank=b, spoilt=sp, valid=valid, q_declared=valid,
                           n_total=n)
                if cand:
                    out.update(zammel=cand[0], maghzaoui=cand[1], saied=cand[2])
                yield sb + P["spoilt"].score(sp) + V.score(valid) + cs, out

    sc, vals, gap = _top2(options())
    return sc, ({"n_total": n} if vals is None else vals), gap


def decode(cell_probs):
    """cell_probs: {field: (n_cells, 10) array} -> (values, info), or None.

    `info["margin"]` is the log-likelihood gap between the best reading and the
    nearest alternative the identities also admit. It is the confidence signal,
    not the absolute likelihood, and is what a caller should threshold on before
    trusting a row or training on it.
    """
    P = {f: (FieldProbs.from_probs(cell_probs[f]) if f in cell_probs else UNKNOWN)
         for f in ALL}
    turnout = combine(P["c_signed"], P["w_voted"])
    if not turnout.known:
        return None
    valid_v = combine(P["valid"], P["q_declared"])
    m1s = P["match1"].candidates(MATCH_K) or [0]
    m3s = P["match3"].candidates(MATCH_K) or [0]
    tail_b, tail_v, cand_memo = {}, {}, {}

    def per_pivot(c):
        """Score of the best reading with this turnout count."""
        gaps = []
        sb, vb, _ = _top2(_side(c, m1s, tail_b, P, gaps, ballot=True))
        sv, vv, _ = _top2(_side(c, m3s, tail_v, P, gaps, ballot=False,
                                valid_v=valid_v, memo=cand_memo))
        if vb is None or vv is None:
            return None
        return (turnout.score(c) + sb + sv,
                dict(c_signed=c, w_voted=c, **vb, **vv))

    scored = [r for r in (per_pivot(c) for c in turnout.candidates(PIVOT_K))
              if r is not None]
    if not scored:
        return None
    scored.sort(key=lambda t: -t[0])
    best = scored[0]
    # A single surviving reading is not certainty — there was nothing to compare
    # it against — so it gets no credit for the pivot being unambiguous.
    margin = best[0] - scored[1][0] if len(scored) > 1 else 0.0
    vals = best[1]

    # a_registered is in no identity; read it alone, preferring a value that at
    # least does not imply more voters than registered.
    if P["a_registered"].known:
        cands = P["a_registered"].candidates()
        ok = [v for v in cands if v >= vals["c_signed"]]
        vals["a_registered"] = (ok or cands)[0] if cands else None
    if P["match4"].known:
        vals["match4"] = P["match4"].best()

    # How hard the arithmetic had to argue with the classifier. This is the
    # syndrome weight of the code: a reading the cells already almost agreed
    # with is trustworthy, one that required overruling six cells is a solution
    # the constraints found rather than one the ballot paper contains.
    changed = drop = 0
    per_field = {}
    for f in BALLOT + VOTES:
        if not P[f].known or vals.get(f) is None:
            continue
        raw = P[f].logp.argmax(1)
        got = str(vals[f]).zfill(P[f].n)
        if len(got) != P[f].n:
            changed += P[f].n
            per_field[f] = (P[f].n, 99.0)
            continue
        c = sum(int(a) != int(b) for a, b in zip(raw, got))
        d = float(P[f].logp.max(1).sum()) - P[f].score(vals[f])
        per_field[f] = (c, d)
        changed += c
        drop += d
    return vals, {"margin": round(float(min(margin, 999.0)), 2),
                  "changed": changed, "drop": round(drop, 2),
                  "per_field": per_field,
                  "fields_read": sum(1 for f in ALL if vals.get(f) is not None),
                  "fields_located": sum(1 for f in ALL if P[f].known)}


def _side(c, matches, cache, P, gaps, ballot, valid_v=None, memo=None):
    """Score each reconciliation offset for one half of the form."""
    for m in matches:
        x = c - m
        if x < 0:
            continue
        if x not in cache:
            cache[x] = (_ballot_tail(P, x) if ballot
                        else _vote_tail(P, valid_v, x, memo))
        sc, vals, gap = cache[x]
        if vals is None:
            continue
        gaps.append(gap)
        if ballot:
            yield (P["match1"].score(m) + P["s_extracted"].score(x) + sc,
                   dict(match1=m, s_extracted=x, **vals))
        else:
            yield P["match3"].score(m) + sc, dict(match3=m, **vals)


def read_raw(cell_probs):
    """Unconstrained cell-by-cell reading, for comparison."""
    return {f: FieldProbs.from_probs(p).best() for f, p in cell_probs.items()}
