"""Decode a 2023 local PV under its own identities, with a variable slate.

The 2023 local form is the same error-correcting code as the 2024 presidential
one — the turnout count is written five times, the valid-vote total twice — so
the pivot search, the ballot half and the reconciliation offsets are imported
from `pv_decode` unchanged rather than restated here.

What has to change is the vote half. A presidential form splits its valid votes
between three known candidates, which is a small enough search to enumerate. A
local form splits them between anything from one to nine, and a constituency's
slate is not written on the form: the nine slots are pre-printed and the unused
ones are left blank or struck through. Enumerating even six values per slot over
nine slots is 10 million combinations per candidate total, which is not a search
worth running.

So the split is solved rather than searched. Maximising the summed
log-likelihood of the slots subject to their total being the valid-vote count is
a knapsack, and a polling bureau's valid votes number in the hundreds, so the
dynamic program over partial sums is a few thousand steps. It is also exact over
the values considered, where an enumeration would have had to be truncated.

How many slots are in play is decided per constituency before decoding, by which
boxes carry ink (`decode_local_2023.slate`), not here: it is a property of the
constituency's slate, the same on all of its bureaux, and reading it off one
form would make it a per-form guess. This function is told the number and
believes it.
"""
import sys, os

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pv_decode import (FieldProbs, UNKNOWN, combine, _top2, _ballot_tail,
                       MATCH_K, NO_SPLIT, PIVOT_K, NEG)
import pv_fields_local_2023 as F

# How many values per slot the split may consider. `pv_decode` keeps six per
# field, built from the three likeliest digits per cell, which is right for a
# presidential form: three candidates, and the valid total pins them hard. Here
# it was the binding constraint. A slot whose leading cell is faint reads as
# 2038 where the form says 38, and with three digits per cell the true value is
# not in the field's top six at all, so no assignment can reach the valid total
# and the whole vote block comes back empty however well the other slots read.
#
# Widening is affordable because the search below is a dynamic program over
# every reachable total at once rather than an enumeration: the cost is a few
# dozen vector operations per slot, not a combinatorial explosion. The
# candidates are also taken over the field's whole scored range rather than
# from a per-cell shortlist, so no digit is ruled out before the arithmetic
# has had its say.
SLOT_K = 32

BALLOT = ["s_extracted", "d_damaged", "r_remaining", "m_total",
          "b_delivered", "c_signed", "match1", "match2"]
VOTES = ["valid", "blank", "spoilt", "n_total", "match3", "w_voted",
         "q_declared"] + F.SLOTS
FREE = ["a_registered", "match4"]
ALL = BALLOT + VOTES + FREE


def _score_table(P, vmax):
    """log P(field = v) for every v from 0 to `vmax`, as one array.

    Scoring the whole range rather than a shortlist is what lets the split
    consider a value the classifier ranked nowhere. It costs one pass per cell
    over an array the length of the biggest plausible vote total.
    """
    rem = np.arange(vmax + 1)
    out = np.zeros(vmax + 1)
    for i in range(P.n - 1, -1, -1):
        out += P.logp[i][rem % 10]
        rem //= 10
    if vmax > P.max:
        out[P.max + 1:] = NEG
    return out


class SlotSplit:
    """Every way the slots could sum, solved once for the whole form.

    Maximising the slots' summed log-likelihood subject to their total being a
    given number is a knapsack, and the useful thing about a knapsack is that
    solving it for one capacity solves it for all of them. So the table is built
    once, over every total up to the largest the form could plausibly state, and
    each candidate valid-vote count the decoder tries is then a lookup rather
    than another search — which is what makes a wide per-slot candidate set
    affordable.

    Each step is a max-plus convolution of the running best-score-per-total
    against one slot's scored values, with a backpointer array so the values can
    be recovered afterwards.
    """

    def __init__(self, P, slots, vmax):
        self.slots = list(slots)
        self.vmax = int(max(0, vmax))
        self.ok = bool(self.slots) and all(P[s].known for s in self.slots)
        if not self.ok:
            return
        best = np.full(self.vmax + 1, NEG)
        best[0] = 0.0
        self.args = []
        for name in self.slots:
            table = _score_table(P[name], self.vmax)
            new = np.full(self.vmax + 1, NEG)
            arg = np.full(self.vmax + 1, -1, np.int32)
            for v in np.argsort(-table)[:SLOT_K]:
                v = int(v)
                if table[v] <= NEG:
                    continue
                moved = best[:self.vmax + 1 - v] + table[v]
                tail = new[v:]
                better = moved > tail
                tail[better] = moved[better]
                arg[v:][better] = v
            best = new
            self.args.append(arg)
        self.best = best

    def score(self, valid):
        """The best summed log-likelihood for slots totalling `valid`."""
        if not self.ok:
            return 0.0
        if valid is None or not (0 <= valid <= self.vmax):
            return NO_SPLIT
        s = float(self.best[valid])
        return NO_SPLIT if s <= NEG else s

    def values(self, valid):
        """The slot values behind that score, or None if the total is unreachable."""
        if not self.ok or valid is None or not (0 <= valid <= self.vmax):
            return None
        out, t = [], int(valid)
        for arg in reversed(self.args):
            v = int(arg[t])
            if v < 0:
                return None
            out.append(v)
            t -= v
        return list(reversed(out)) if t == 0 else None


def _vote_tail(P, V, n, split):
    """Best (valid, blank, spoilt, q, slot votes) given the papers counted.

    The slot votes are scored inside the search over the blank/spoilt split
    rather than after it, because what the slots have to add up to is the
    strongest evidence on the form about the valid-vote total.
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
                out = dict(blank=b, spoilt=sp, valid=valid, q_declared=valid,
                           n_total=n)
                values = split.values(valid)
                if values:
                    out.update(dict(zip(split.slots, values)))
                yield (sb + P["spoilt"].score(sp) + V.score(valid)
                       + split.score(valid)), out

    sc, vals, gap = _top2(options())
    return sc, ({"n_total": n} if vals is None else vals), gap


def _side(c, matches, cache, P, ballot, valid_v=None, split=None):
    for m in matches:
        x = c - m
        if x < 0:
            continue
        if x not in cache:
            cache[x] = (_ballot_tail(P, x) if ballot
                        else _vote_tail(P, valid_v, x, split))
        sc, vals, _ = cache[x]
        if vals is None:
            continue
        if ballot:
            yield (P["match1"].score(m) + P["s_extracted"].score(x) + sc,
                   dict(match1=m, s_extracted=x, **vals))
        else:
            yield P["match3"].score(m) + sc, dict(match3=m, **vals)


def decode(cell_probs, n_slots):
    """cell_probs: {field: (n_cells, 10)} -> (values, info), or None.

    `n_slots` is how many of the nine vote boxes the constituency's slate fills.
    """
    slots = F.SLOTS[:max(0, min(9, int(n_slots or 0)))]
    P = {f: (FieldProbs.from_probs(cell_probs[f]) if f in cell_probs else UNKNOWN)
         for f in ALL}
    turnout = combine(P["c_signed"], P["w_voted"])
    if not turnout.known:
        return None
    valid_v = combine(P["valid"], P["q_declared"])
    m1s = P["match1"].candidates(MATCH_K) or [0]
    m3s = P["match3"].candidates(MATCH_K) or [0]
    # No slot total can exceed the papers counted, which cannot exceed the
    # turnout; so the largest pivot the decoder will try bounds the table.
    pivots = turnout.candidates(PIVOT_K)
    split = SlotSplit(P, slots, max(pivots or [0]))
    tail_b, tail_v = {}, {}

    def per_pivot(c):
        sb, vb, _ = _top2(_side(c, m1s, tail_b, P, ballot=True))
        sv, vv, _ = _top2(_side(c, m3s, tail_v, P, ballot=False,
                                valid_v=valid_v, split=split))
        if vb is None or vv is None:
            return None
        return (turnout.score(c) + sb + sv,
                dict(c_signed=c, w_voted=c, **vb, **vv))

    scored = [r for r in (per_pivot(c) for c in pivots) if r is not None]
    if not scored:
        return None
    scored.sort(key=lambda t: -t[0])
    best = scored[0]
    margin = best[0] - scored[1][0] if len(scored) > 1 else 0.0
    vals = best[1]

    # Neither of these takes part in an identity, so each is read on its own.
    if P["a_registered"].known:
        cands = P["a_registered"].candidates()
        ok = [v for v in cands if v >= (vals.get("c_signed") or 0)]
        vals["a_registered"] = (ok or cands)[0] if cands else None
    if P["match4"].known:
        vals["match4"] = P["match4"].best()

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
                  "n_slots": len(slots),
                  "fields_read": sum(1 for f in ALL if vals.get(f) is not None),
                  "fields_located": sum(1 for f in ALL if P[f].known)}
