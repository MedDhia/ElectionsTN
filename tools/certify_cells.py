"""Label digit cells from any PV, using the form's identities as the annotator.

The pilot forms give ~1.5k labelled digits, which trains a classifier to about
94% per cell — not enough to read a form of 88 cells. More labels are the only
way forward, and the corpus can label itself.

The trick is to certify *parts* of a form rather than whole forms. A whole form
read independently is right about 1% of the time at 94% per cell, so certifying
whole forms yields almost nothing. But a single identity — say that the three
candidate scores add up to the valid-vote total — involves only sixteen cells,
and holds by accident only if a misread happens to be compensated exactly. When
it holds, those sixteen cells are almost certainly right, whatever the rest of
the form does. Harvesting per identity instead of per form turns a 1% yield into
a large one.

Sum identities are the strong ones: an equality between two readings of the same
number can be satisfied by the same misreading twice, since it is the same hand
on the same scan, but a three-term sum cannot absorb an error without a
compensating one elsewhere. Cells are therefore certified by sum identities, or
by agreeing equalities backed by a second identity.

Usage:
  python3 tools/certify_cells.py --eval           # purity/yield on pilot truth
  python3 tools/certify_cells.py --run [--limit N]  # harvest the whole corpus
"""
import argparse, json, os, sys
from concurrent.futures import ProcessPoolExecutor

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

OUT = ".cache/digit_certified.npz"
UPRIGHT = ".cache/pv_upright"

# (name, fields involved, predicate, is_sum). The predicate reads the raw
# per-cell values; `is_sum` marks the identities strong enough to certify alone.
IDENTITIES = [
    ("c_eq_w", ["c_signed", "w_voted"],
     lambda v: v["c_signed"] == v["w_voted"], False),
    ("q_eq_valid", ["valid", "q_declared"],
     lambda v: v["valid"] == v["q_declared"], False),
    ("cands_sum", ["zammel", "maghzaoui", "saied", "valid"],
     lambda v: v["zammel"] + v["maghzaoui"] + v["saied"] == v["valid"], True),
    ("papers_sum", ["valid", "blank", "spoilt", "n_total"],
     lambda v: v["valid"] + v["blank"] + v["spoilt"] == v["n_total"], True),
    ("ballots_sum", ["s_extracted", "d_damaged", "r_remaining", "m_total"],
     lambda v: v["s_extracted"] + v["d_damaged"] + v["r_remaining"] == v["m_total"], True),
    ("match1", ["c_signed", "s_extracted", "match1"],
     lambda v: v["c_signed"] - v["s_extracted"] == v["match1"], True),
    ("match2", ["b_delivered", "m_total", "match2"],
     lambda v: v["b_delivered"] - v["m_total"] == v["match2"], True),
    ("match3", ["w_voted", "n_total", "match3"],
     lambda v: v["w_voted"] - v["n_total"] == v["match3"], True),
]


def certified_fields(raw):
    """Fields whose raw reading the form's own arithmetic vouches for."""
    strong, weak = set(), {}
    for name, fields, pred, is_sum in IDENTITIES:
        if not all(f in raw for f in fields):
            continue
        try:
            if not pred(raw):
                continue
        except TypeError:
            continue
        for f in fields:
            if is_sum:
                strong.add(f)
            else:
                weak[f] = weak.get(f, 0) + 1
    # A sum vouches for a field on its own; an equality only alongside another.
    return strong | {f for f, n in weak.items() if n >= 2 or f in strong}


def read_form(img, net):
    """Independent per-cell reading of a form: {field: value}, {field: cells}.

    This goes through the production reader rather than plain grid detection, so
    it harvests from the scans that only register — which is the point. The cells
    the classifier already reads easily are the ones it was trained on; the
    labels worth adding come from the forms it currently cannot read.
    """
    from decode_all import read_image
    from digit_model import predict_proba
    got = read_image(img, lambda X: predict_proba(net, X))
    if not got:
        return {}, {}
    return got["raw"], got["cells"]


def _eval():
    """Purity and yield of the rule, scored against the verified pilot forms."""
    from digit_model import train, load, predict_proba
    from pv_decode import FieldProbs
    from harvest_digits import source_image
    from decode_all import cells_of
    from pv_fields import digits_of

    X, y, code, _ = load()
    truth = {r["bureau_code"]: r for r in
             (json.loads(l) for l in open(".cache/pv_pilot/readings.jsonl",
                                          encoding="utf-8"))}
    forms = [c for c in np.unique(code) if c in truth]
    cells = {}
    for c in forms:
        img = cv2.imread(source_image(c))
        cells[c] = cells_of(img) if img is not None else {}
    forms = [c for c in forms if cells[c]]

    rng = np.random.default_rng(0)
    order = np.array(forms); rng.shuffle(order)
    tot = ok = allcells = allok = 0
    for i, held in enumerate(np.array_split(order, 7)):
        net = train(X[~np.isin(code, held)], y[~np.isin(code, held)], seed=i)
        for c in held:
            P = predict_proba(net, np.concatenate([cells[c][f] for f in cells[c]]))
            raw, at = {}, 0
            for f in cells[c]:
                raw[f] = FieldProbs.from_probs(P[at:at + len(cells[c][f])]).best()
                at += len(cells[c][f])
            good = certified_fields(raw)
            for f, arr in cells[c].items():
                labs = digits_of(truth[c].get(f), len(arr))
                if labs is None:
                    continue
                got = [int(d) for d in str(raw[f]).zfill(len(arr))]
                allcells += len(arr); allok += sum(a == b for a, b in zip(got, labs))
                if f in good:
                    tot += len(arr); ok += sum(a == b for a, b in zip(got, labs))
        print(f"  fold {i+1}/7  certified {tot} cells, {ok/max(tot,1):.4f} correct",
              flush=True)
    print(f"\n  uncertified baseline: {allok}/{allcells} = {allok/allcells:.4f}")
    print(f"  certified:            {ok}/{tot} = {ok/max(tot,1):.4f}")
    print(f"  yield:                {tot}/{allcells} = {tot/allcells:.1%} of cells")


_net = None


def _work(args):
    code, path, model = args
    global _net
    try:
        if _net is None:
            import torch
            from digit_model import Net
            torch.set_num_threads(1)
            _net = Net(); _net.load_state_dict(torch.load(model, map_location="cpu"))
            _net.eval()
        img = cv2.imread(path)
        if img is None:
            return None
        raw, cells = read_form(img, _net)
        good = certified_fields(raw)
        out = []
        for f in good:
            arr = cells[f]
            s = str(raw[f]).zfill(len(arr))
            if len(s) == len(arr):
                out.append((arr, [int(d) for d in s]))
        return code, out
    except Exception:
        return None


def _run(limit, model, workers):
    codes = sorted(f[:-4] for f in os.listdir(UPRIGHT) if f.endswith(".jpg"))
    if limit:
        codes = list(np.random.default_rng(0).permutation(codes)[:limit])
    jobs = [(c, os.path.join(UPRIGHT, f"{c}.jpg"), model) for c in codes]
    print(f"{len(jobs)} forms, {workers} workers", flush=True)
    X, y, src, forms = [], [], [], 0
    with ProcessPoolExecutor(workers) as ex:
        for i, res in enumerate(ex.map(_work, jobs, chunksize=8), 1):
            if res and res[1]:
                code, blocks = res
                forms += 1
                for arr, labs in blocks:
                    X.append(arr); y += labs; src += [code] * len(labs)
            if i % 500 == 0:
                print(f"  {i}/{len(jobs)}  {forms} forms contributed, "
                      f"{len(y)} cells", flush=True)
    Xa = np.concatenate(X)
    np.savez_compressed(OUT, X=Xa, y=np.array(y, np.int8), code=np.array(src))
    print(f"\ncertified {len(y)} cells from {forms} forms -> {OUT}")
    print("class counts:", np.bincount(np.array(y), minlength=10).tolist())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--model", default=".cache/digit_cnn.pt")
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 4)
    a = ap.parse_args()
    if a.eval:
        _eval()
    else:
        _run(a.limit, a.model, a.workers)


if __name__ == "__main__":
    main()
