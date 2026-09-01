"""Score every block the reader would publish against the hand-verified pilot.

The gate's promise is that a published account is one the form's own arithmetic
vouches for. This checks that promise the only way it can be checked — against
the 30 forms read and verified by hand — and reports it per block and per route,
because the two routes carry different evidence: an identity closing on the
independent reading, or the decoder closing it having barely argued.

Point `PV_STRIP_MODEL` at a model that never saw a pilot form. Scoring a reader
against forms it trained on is how an early cell-classifier number came out 25
points too generous.

Usage: PV_STRIP_MODEL=.cache/strip_cnn_holdout.pt python3 tools/eval_blocks.py
"""
import collections, json, os, sys
import cv2
import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from decode_all import read_image, BLOCKS, BLOCK_CORRECTED, BLOCK_DROP
from digit_model import holdout_net, predict_proba
from harvest_digits import source_image

READINGS = ".cache/pv_pilot/readings.jsonl"


def main():
    torch.set_num_threads(os.cpu_count() or 4)
    net = holdout_net()
    truth = {r["bureau_code"]: r for r in
             (json.loads(l) for l in open(READINGS, encoding="utf-8"))}
    tally = collections.Counter()
    wrong = []
    for code, t in truth.items():
        path = source_image(code)
        img = cv2.imread(path) if path else None
        if img is None:
            continue
        got = read_image(img, lambda X: predict_proba(net, X))
        if not got:
            continue
        info, vals, cert = got["info"], got["values"], got["certified"]
        per_field = (info or {}).get("per_field", {})
        for name, fields in BLOCKS.items():
            by_raw = set(fields) <= cert
            have = bool(info) and all(vals.get(f) is not None for f in fields)
            c = sum(per_field.get(f, (99, 99.0))[0] for f in fields) if have else 99
            d = sum(per_field.get(f, (99, 99.0))[1] for f in fields) if have else 99.0
            by_dec = have and c <= BLOCK_CORRECTED and d <= BLOCK_DROP
            if not (by_raw or by_dec):
                continue
            route = "raw" if by_raw else "decoder"
            read = {f: (got["raw"][f] if by_raw else vals[f]) for f in fields}
            ok = all(t.get(f) is None or read[f] == t[f] for f in fields)
            tally[f"{route}_{name}"] += 1
            tally[f"{route}_{name}_ok"] += ok
            tally[route] += 1
            tally[route + "_ok"] += ok
            tally["all"] += 1
            tally["all_ok"] += ok
            if not ok:
                bad = {f: (read[f], t.get(f)) for f in fields if t.get(f) != read[f]}
                wrong.append((code, name, route, bad))

    print(f"strip model: {os.environ.get('PV_STRIP_MODEL', '(production)')}\n")
    for route in ("raw", "decoder"):
        if tally[route]:
            print(f"  {route:8s} {tally[route+'_ok']:3d}/{tally[route]:3d} "
                  f"= {tally[route+'_ok']/tally[route]:.4f}")
            for name in BLOCKS:
                if tally[f"{route}_{name}"]:
                    print(f"     {name:8s} {tally[f'{route}_{name}_ok']:3d}"
                          f"/{tally[f'{route}_{name}']:3d}")
    print(f"\n  {'total':8s} {tally['all_ok']:3d}/{tally['all']:3d} "
          f"= {tally['all_ok']/max(tally['all'],1):.4f} correct")
    for code, name, route, bad in wrong:
        print(f"    WRONG {code} {name} via {route}: "
              + ", ".join(f"{f} read {r} truth {tt}" for f, (r, tt) in bad.items()))


if __name__ == "__main__":
    main()
