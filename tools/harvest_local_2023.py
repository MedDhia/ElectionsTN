"""Label digit cells for the 2023 local reader — by hand once, then by arithmetic.

Two sources of labels, in that order.

`pilot` takes the eighteen forms read by eye
(`data/verification/pv_local_2023_pilot.csv`) and cuts out their cells, from the
crops `decode_local_2023 prepare` already cached. That is about 1,450 labelled
digits, and it exists only to get a first classifier off the ground.

`certify` then lets the corpus label itself. A form's identities are checked
against the *raw*, cell-by-cell reading; where one holds, the cells that
produced it are almost certainly right, because a three-term sum does not come
out even when a digit has been misread unless a second error compensates for it
exactly. The unit of certification is the identity rather than the form: at 94%
per cell a whole form is right about a percent of the time, so certifying whole
forms yields almost nothing, while any one identity involves a dozen cells and
holds far more often.

The 2023 form has one identity the presidential form does not — the slot votes
sum to the valid total — and it is the most useful of them all, because it
vouches for the vote boxes, which is where the corpus is hardest to read and
where the published constituency results can check the answer afterwards.

Pilot forms are excluded from `certify` so they stay a genuine holdout.

Both read the cached crops, so `decode_local_2023 prepare` has to have run, and
`slate` before `certify`.

Usage:
  python3 tools/harvest_local_2023.py pilot
  python3 tools/harvest_local_2023.py certify [limit] [workers]
"""
import csv, json, os, sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pv_local_2023 as L
import pv_fields_local_2023 as F
from pv_fields import digits_of

PILOT = "data/verification/pv_local_2023_pilot.csv"
TRAIN = ".cache/digit_train_local_2023.npz"
CERTIFIED = ".cache/digit_certified_local_2023.npz"
# Written by `decode_local_2023 slate`, from ink alone.
SLATE = f".cache/pv_{L.ELECTION}_slate.json"

# Each identity, as the fields it involves and a test on a reading of them. A
# reading that satisfies one vouches for every cell of every field named.
IDENTITIES = [
    ("signed_voted", ["c_signed", "w_voted", "match1", "s_extracted"],
     lambda v: v["c_signed"] == v["w_voted"]
     and v["match1"] == v["c_signed"] - v["s_extracted"]),
    ("papers", ["valid", "blank", "spoilt", "n_total"],
     lambda v: v["n_total"] == v["valid"] + v["blank"] + v["spoilt"]),
    ("voted_papers", ["w_voted", "n_total", "match3"],
     lambda v: v["match3"] == v["w_voted"] - v["n_total"]),
    ("ballots", ["s_extracted", "d_damaged", "r_remaining", "m_total"],
     lambda v: v["m_total"] == v["s_extracted"] + v["d_damaged"] + v["r_remaining"]),
    ("delivered", ["b_delivered", "m_total", "match2"],
     lambda v: v["match2"] == v["b_delivered"] - v["m_total"]),
    ("declared", ["valid", "q_declared", "match4"],
     lambda v: v["q_declared"] == v["valid"] and v["match4"] == 0),
]


def raw_read(net, crops):
    """Cell-by-cell reading of each field, from its cached crops."""
    from digit_model import predict_proba
    names = [n for n in crops if len(crops[n])]
    if not names:
        return {}
    flat = predict_proba(net, np.concatenate([crops[n] for n in names]))
    values, at = {}, 0
    for name in names:
        k = len(crops[name])
        values[name] = int("".join(str(int(d)) for d in flat[at:at + k].argmax(1)))
        at += k
    return values


def slot_identity(values, n_slots=None):
    """The vote-block identity, and the fields it vouches for.

    Where the constituency's slate is known — `decode_local_2023 slate` reads it
    off the ink across all of its bureaux, which needs no model and so is
    available before any of this — the identity is the real one: those slots sum
    to the valid total, or they do not.

    Without it the count has to be inferred, by taking the number of leading
    slots that makes the sum come out. A coincidence is possible and cheap to
    bound — it needs the read votes of a prefix of slots to hit the read valid
    total exactly — and any it produces is a set of cells that already agree
    with the rest of the form. It is still the weaker test, which is why the
    slate is passed in when there is one.
    """
    valid = values.get("valid")
    if valid is None:
        return None
    if n_slots:
        slots = F.SLOTS[:n_slots]
        if any(s not in values for s in slots):
            return None
        return (["valid"] + slots
                if sum(values[s] for s in slots) == valid else None)
    running = 0
    for k, name in enumerate(F.SLOTS, 1):
        if name not in values:
            break
        running += values[name]
        if running == valid:
            return ["valid"] + F.SLOTS[:k]
    return None


def cells_of(code, net, n_slots=None):
    """(28x28 cells, labels, field names) the identities vouch for on one form.

    Works from the cached crops that `decode_local_2023 prepare` wrote, so the
    loop can be run again after retraining without touching a scan.
    """
    got = L.load_cells(code)
    if got is None:
        return None
    crops, detected = got[0], got[1]
    values = raw_read(net, crops)
    if not values:
        return None
    fields = {n: crops[n] for n in values}
    cell_imgs = crops
    vouched = set()
    for _, names, test in IDENTITIES:
        if all(n in values for n in names):
            try:
                if test(values):
                    vouched.update(names)
            except (TypeError, KeyError):
                pass
    slots = slot_identity(values, n_slots)
    if slots:
        vouched.update(slots)
    X, y, names = [], [], []
    for name in vouched:
        labels = digits_of(values[name], len(fields[name]))
        if labels is None:
            continue
        for crop, label in zip(cell_imgs[name], labels):
            X.append(crop)
            y.append(label)
            names.append(name)
    if not X:
        return None
    return np.array(X, np.uint8), np.array(y, np.int64), names, detected


def harvest_pilot():
    """Cut the hand-read forms' cells out of the cached crops.

    Reading them from the cache rather than replacing the placement is the whole
    point: the labels then sit on exactly the crops the reader will be shown, so
    a placement that drifts drifts on both sides at once. Re-deriving placement
    here would let the training crops and the inference crops come from two
    different code paths, which is how a label ends up half a cell from the digit
    it names.
    """
    X, y, codes, names = [], [], [], []
    for row in csv.DictReader(open(PILOT, encoding="utf-8")):
        code = row["bureau_code"]
        got = L.load_cells(code)
        if got is None:
            print(f"  {code}: no cached cells — run `prepare` first", flush=True)
            continue
        crops = got[0]
        kept = 0
        for name, cells in crops.items():
            raw = row.get(name, "")
            if raw == "" or not len(cells):
                continue
            labels = digits_of(int(raw), len(cells))
            if labels is None:
                continue
            for crop, label in zip(cells, labels):
                X.append(crop)
                y.append(label)
                codes.append(code)
                names.append(name)
                kept += 1
        print(f"  {code}: {kept} cells", flush=True)
    X, y = np.array(X, np.uint8), np.array(y, np.int64)
    os.makedirs(".cache", exist_ok=True)
    np.savez_compressed(TRAIN, X=X, y=y, code=np.array(codes),
                        field=np.array(names))
    counts = np.bincount(y, minlength=10)
    print(f"{len(y)} cells from {len(set(codes))} forms -> {TRAIN}")
    print("per digit:", dict(enumerate(counts.tolist())))


def _one(args):
    code, n_slots = args
    try:
        return code, cells_of(code, _NET, n_slots)
    except Exception:
        return code, None


def load_net(path=None):
    """The trained cell classifier, ready to predict."""
    import torch, digit_model
    net = digit_model.Net()
    net.load_state_dict(torch.load(path or digit_model.OUT, map_location="cpu"))
    net.eval()
    return net


def _init():
    global _NET
    import torch
    torch.set_num_threads(1)
    _NET = load_net()


def harvest_certified(limit=None, workers=4):
    pilot = {r["bureau_code"] for r in csv.DictReader(open(PILOT, encoding="utf-8"))}
    slates = (json.load(open(SLATE)) if os.path.exists(SLATE) else {})
    jobs = [(c, (slates.get(L.constituency_of(c)) or {}).get("n_candidates"))
            for c in L.cached_codes() if c not in pilot]
    if limit:
        jobs = jobs[:limit]
    print(f"{len(jobs)} forms with cached cells, "
          f"{sum(1 for _, n in jobs if n)} with a known slate", flush=True)
    X, y, codes = [], [], []
    with ProcessPoolExecutor(max_workers=workers, initializer=_init) as pool:
        for i, (code, got) in enumerate(pool.map(_one, jobs, chunksize=8), 1):
            if got:
                cx, cy, _, _ = got
                X.append(cx)
                y.append(cy)
                codes.extend([code] * len(cy))
            if i % 500 == 0:
                n = sum(len(a) for a in y)
                print(f"  {i}/{len(jobs)}  {n} cells from "
                      f"{len(set(codes))} forms", flush=True)
    if not X:
        raise SystemExit("nothing certified")
    X, y = np.concatenate(X), np.concatenate(y)
    np.savez_compressed(CERTIFIED, X=X, y=y, code=np.array(codes))
    print(f"{len(y)} certified cells from {len(set(codes))} forms -> {CERTIFIED}")
    print("per digit:", dict(enumerate(np.bincount(y, minlength=10).tolist())))


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "pilot"
    if what == "pilot":
        harvest_pilot()
    else:
        harvest_certified(int(sys.argv[2]) if len(sys.argv) > 2 else None,
                          int(sys.argv[3]) if len(sys.argv) > 3 else 4)
