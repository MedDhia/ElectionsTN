"""Does joint decoding under the form's identities beat reading cell by cell?

Grouped cross-validation over the hand-verified pilot forms: the classifier
never sees a digit from the form it is scored on, so the number here is what an
unseen form would get.

Usage: python3 tools/eval_decode.py
"""
import json, os, sys
import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from digit_model import predict_proba, load, holdout_net
from pv_decode import decode, read_raw, BALLOT, VOTES
from decode_all import cells_of
from harvest_digits import source_image

READINGS = ".cache/pv_pilot/readings.jsonl"
CHECKED = BALLOT + VOTES


def form_cells(code):
    path = source_image(code)
    img = cv2.imread(path) if path else None
    return cells_of(img) if img is not None else None


def main():
    X, y, code, _ = load()
    truth = {r["bureau_code"]: r for r in
             (json.loads(l) for l in open(READINGS, encoding="utf-8"))}
    forms = [c for c in np.unique(code) if c in truth]
    cells = {c: form_cells(c) for c in forms}
    forms = [c for c in forms if cells[c]]
    print(f"{len(forms)} pilot forms with a field map", flush=True)

    stats = dict(raw_field=[0, 0], dec_field=[0, 0],
                 raw_form=[0, 0], dec_form=[0, 0])
    margins = []
    net = holdout_net()      # trained only on other forms' self-certified cells
    for c in forms:
        probs = {f: predict_proba(net, cells[c][f]) for f in cells[c]}
        gt = truth[c]
        raw = read_raw(probs)
        res = decode(probs)
        dec = res[0] if res else {}
        marg = res[1]["margin"] if res else None
        rf = df = n = 0
        for f in CHECKED:
            if f not in probs or gt.get(f) is None:
                continue
            n += 1
            rf += raw.get(f) == gt[f]
            df += dec.get(f) == gt[f]
        stats["raw_field"][0] += rf; stats["raw_field"][1] += n
        stats["dec_field"][0] += df; stats["dec_field"][1] += n
        stats["raw_form"][0] += (rf == n and n > 0); stats["raw_form"][1] += 1
        ok = (df == n and n > 0)
        stats["dec_form"][0] += ok; stats["dec_form"][1] += 1
        if res:
            margins.append((marg, res[1]["changed"], res[1]["drop"],
                            res[1]["fields_read"], ok))
        print(f"  {c}  fields {n:2d}  raw {rf:2d}  decoded {df:2d}"
              + (f"  margin {marg:6.1f}  changed {res[1]['changed']:2d}"
                 f"  drop {res[1]['drop']:6.1f}" if res else "  no decode"),
              flush=True)

    print()
    for k, (a, b) in stats.items():
        print(f"  {k:10s} {a}/{b} = {a/b:.3f}" if b else f"  {k}: n/a")
    if margins:
        print("\n  cells the arithmetic overruled -> forms kept / of those, fully correct")
        for t in (0, 1, 2, 3, 4, 99):
            kept = [ok for _, ch, _, _, ok in margins if ch <= t]
            if kept:
                print(f"    <= {t:2d} changed: {len(kept):3d} kept, {sum(kept)/len(kept):.3f} correct")
        print("\n  log-likelihood the reading gave up -> forms kept / of those, fully correct")
        for t in (1, 3, 6, 12, 25, 1e9):
            kept = [ok for _, _, dr, _, ok in margins if dr <= t]
            if kept:
                print(f"    <= {t:6g} drop: {len(kept):3d} kept, {sum(kept)/len(kept):.3f} correct")
        print("\n  gate on both: cells overruled and how much of the form was read")
        for fr in (18, 19, 20):
            for t in (0, 1, 2, 3):
                kept = [ok for _, ch, _, n, ok in margins if ch <= t and n >= fr]
                if kept:
                    print(f"    fields_read >= {fr}, changed <= {t}: {len(kept):3d} kept, "
                          f"{sum(kept)/len(kept):.3f} correct")
        print("\n  per form: margin / changed / drop / fields read / correct")
        for m, ch, dr, n, ok in sorted(margins):
            print(f"    margin {m:7.2f}  changed {ch:2d}  drop {dr:7.2f}  read {n:2d}"
                  f"  {'ok' if ok else 'WRONG'}")


if __name__ == "__main__":
    main()
