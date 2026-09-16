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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pv_decode import (FieldProbs, UNKNOWN, combine, _top2, _ballot_tail,
                       MATCH_K, NO_SPLIT, PIVOT_K, TOPK, NEG)
import pv_fields_local_2023 as F

BALLOT = ["s_extracted", "d_damaged", "r_remaining", "m_total",
          "b_delivered", "c_signed", "match1", "match2"]
VOTES = ["valid", "blank", "spoilt", "n_total", "match3", "w_voted",
         "q_declared"] + F.SLOTS
FREE = ["a_registered", "match4"]
ALL = BALLOT + VOTES + FREE


def _slot_split(P, valid, slots, memo):
    """Best slot values summing to `valid`, by dynamic program over the sum.

    Returns (score, values, gap). `gap` is the log-likelihood between the best
    assignment and the next best, which is what says whether the arithmetic had
    a real choice to make; a wide gap means the votes were essentially read
    rather than inferred.
    """
    key = (valid, len(slots))
    if key in memo:
        return memo[key]
    if not slots or any(not P[s].known for s in slots):
        # Nothing to say either way: the boxes were never located.
        memo[key] = (0.0, None, float("inf"))
        return memo[key]
    if valid is None or valid < 0:
        memo[key] = (NO_SPLIT, None, float("inf"))
        return memo[key]

    # Two best assignments per partial sum, so the runner-up survives to the end.
    reach = {0: [(0.0, ())]}
    for name in slots:
        values = P[name].candidates(TOPK)
        nxt = {}
        for total, best in reach.items():
            for v in values:
                t = total + v
                if t > valid:
                    continue
                s = P[name].score(v)
                if s <= NEG:
                    continue
                row = nxt.setdefault(t, [])
                for score, path in best:
                    row.append((score + s, path + (v,)))
        reach = {t: sorted(rows, reverse=True)[:2] for t, rows in nxt.items()}
        if not reach:
            break
    got = reach.get(valid)
    if not got:
        memo[key] = (NO_SPLIT, None, float("inf"))
    else:
        gap = got[0][0] - got[1][0] if len(got) > 1 else float("inf")
        memo[key] = (got[0][0], got[0][1], gap)
    return memo[key]


def _vote_tail(P, V, n, slots, memo):
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
                cs, values, _ = _slot_split(P, valid, slots, memo)
                out = dict(blank=b, spoilt=sp, valid=valid, q_declared=valid,
                           n_total=n)
                if values:
                    out.update(dict(zip(slots, values)))
                yield sb + P["spoilt"].score(sp) + V.score(valid) + cs, out

    sc, vals, gap = _top2(options())
    return sc, ({"n_total": n} if vals is None else vals), gap


def _side(c, matches, cache, P, ballot, valid_v=None, slots=(), memo=None):
    for m in matches:
        x = c - m
        if x < 0:
            continue
        if x not in cache:
            cache[x] = (_ballot_tail(P, x) if ballot
                        else _vote_tail(P, valid_v, x, slots, memo))
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
    tail_b, tail_v, slot_memo = {}, {}, {}

    def per_pivot(c):
        sb, vb, _ = _top2(_side(c, m1s, tail_b, P, ballot=True))
        sv, vv, _ = _top2(_side(c, m3s, tail_v, P, ballot=False,
                                valid_v=valid_v, slots=slots, memo=slot_memo))
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
