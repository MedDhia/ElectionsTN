"""Does training on manufactured low-resolution strips help, and where?

`tools/harvest_degraded.py` makes 19,379 strips by shrinking whole pages to the
resolution that fails and re-cropping through the normal pipeline. `strip_model`
already folds them in by default — but the production reader,
`.cache/strip_cnn_holdout.pt`, was fitted before they existed, so nothing has
ever measured whether they help.

Measuring it through `strip_model.cv` would not answer the question, for two
reasons that both flatter the result:

- **the test set changes.** `cv` concatenates the degraded strips and *then*
  splits, so turning them on adds manufactured strips to the test set. Scoring a
  reader trained on downsampled forms against more downsampled forms is
  circular, and `harvest_degraded`'s own notes say so: forms shrunk to 868px
  still locate a mean of 14.9 fields where real 868px scans yield about 3.
- **the split moves.** A different set of forms lands in test, so the two arms
  are not compared on the same thing.

So this holds the test set fixed and varies only the training data. Both arms are
scored on **real strips from held-out forms**, never on a manufactured one, and
the degraded strips of a test form are dropped rather than used — a form's real
and shrunk copies straddling the split would hand the net the answer.

Then the part that decides it: the test set is broken out by the **published
resolution of the form the strip came from**. Manufactured data is supposed to
buy accuracy on small scans specifically. If it helps at 560px and does nothing
at 1600px, that is the result. If it helps everywhere equally, something is
leaking. If it helps nowhere, the manufactured domain is too easy to be worth
carrying, which is a real answer too.

The pilot is withheld from both arms, as everywhere else in this project: it is
the only independent ground truth and a model that has seen it cannot be scored
against it.

Usage: python3 tools/eval_degraded_training.py [--holdout 0.12] [--seed 0]
"""
import argparse, json, os, sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

STRIPS = ".cache/digit_strips.npz"
DEGRADED = ".cache/digit_strips_degraded.npz"
UPRIGHT = ".cache/pv_upright"
PILOT = ".cache/pv_pilot/readings.jsonl"
OUT = "data/verification/degraded_training.json"

# Buckets over the long edge of the published page, in pixels. The failing forms
# sit around 560; the top bucket is where the reader was already fine.
BUCKETS = ((0, 700, "under 700px"), (700, 1100, "700-1100px"),
           (1100, 1600, "1100-1600px"), (1600, 10 ** 9, "1600px and over"))


def long_edge(code):
    import cv2
    p = os.path.join(UPRIGHT, f"{code}.jpg")
    im = cv2.imread(p, cv2.IMREAD_REDUCED_COLOR_8)
    return None if im is None else max(im.shape[:2]) * 8


def bucket(px):
    if px is None:
        return "unknown"
    for lo, hi, name in BUCKETS:
        if lo <= px < hi:
            return name
    return "unknown"


def score(pred, y):
    return float((pred == y).mean()), float((pred == y).all(1).mean())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--holdout", type=float, default=0.12)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()

    import torch
    from strip_model import train, predict

    real = np.load(STRIPS, allow_pickle=True)
    deg = np.load(DEGRADED, allow_pickle=True)
    Xr, yr, cr = real["X"], real["y"].astype(np.int64), real["code"]
    Xd, yd, cd = deg["X"], deg["y"].astype(np.int64), deg["code"]
    print(f"{len(yr):,} real strips from {len(set(cr.tolist())):,} forms")
    print(f"{len(yd):,} manufactured strips from {len(set(cd.tolist())):,} forms")

    pilot = {json.loads(l)["bureau_code"] for l in open(PILOT, encoding="utf-8")}
    kr, kd = ~np.isin(cr, list(pilot)), ~np.isin(cd, list(pilot))
    print(f"withholding {int((~kr).sum())} real and {int((~kd).sum())} "
          f"manufactured strips from {len(pilot)} pilot forms")
    Xr, yr, cr = Xr[kr], yr[kr], cr[kr]
    Xd, yd, cd = Xd[kd], yd[kd], cd[kd]

    # Split by form, over the union, so a form is wholly in train or wholly in
    # test no matter which array its strips live in.
    forms = np.random.default_rng(a.seed).permutation(
        np.unique(np.concatenate([cr, cd])))
    nte = max(1, int(len(forms) * a.holdout))
    test_forms = set(forms[:nte].tolist())
    te = np.array([c in test_forms for c in cr])
    trr = ~te
    trd = np.array([c not in test_forms for c in cd])
    print(f"\ntrain: {int(trr.sum()):,} real + {int(trd.sum()):,} manufactured")
    print(f"test:  {int(te.sum()):,} real strips from {nte:,} forms "
          "(no manufactured strip is ever tested on)")

    Xte, yte, cte = Xr[te], yr[te], cr[te]
    px = {c: long_edge(c) for c in sorted(set(cte.tolist()))}
    bk = np.array([bucket(px[c]) for c in cte])
    print("\ntest strips by published page resolution")
    for _, _, name in BUCKETS:
        print(f"   {name:18s} {int((bk == name).sum()):6,}")
    if (bk == "unknown").any():
        print(f"   {'unknown':18s} {int((bk == 'unknown').sum()):6,}")

    arms = {
        "real only": (Xr[trr], yr[trr]),
        "real + manufactured": (np.concatenate([Xr[trr], Xd[trd]]),
                                np.concatenate([yr[trr], yd[trd]])),
    }
    results = {}
    for name, (Xt, yt) in arms.items():
        print(f"\n=== {name}: {len(yt):,} training strips ===", flush=True)
        net = train(Xt, yt, seed=a.seed, log=True)
        pred = predict(net, Xte).argmax(2)
        cell, field = score(pred, yte)
        per = {}
        for _, _, b in BUCKETS:
            m = bk == b
            if m.any():
                per[b] = score(pred[m], yte[m]) + (int(m.sum()),)
        results[name] = {"per_cell": cell, "per_field": field, "by_bucket": per,
                         "train_strips": int(len(yt))}
        print(f"  per-cell {cell:.4f}   per-field {field:.4f}")
        torch.save(net.state_dict(),
                   f".cache/strip_arm_{name.replace(' ', '_').replace('+','plus')}.pt")

    print("\n" + "=" * 72)
    print(f"{'resolution':20s} {'real only':>22s} {'real + manufactured':>22s}")
    print(f"{'':20s} {'cell':>10s} {'field':>11s} {'cell':>10s} {'field':>11s}")
    a_, b_ = results["real only"], results["real + manufactured"]
    print(f"{'ALL':20s} {a_['per_cell']:10.4f} {a_['per_field']:11.4f} "
          f"{b_['per_cell']:10.4f} {b_['per_field']:11.4f}")
    for _, _, name in BUCKETS:
        if name in a_["by_bucket"] and name in b_["by_bucket"]:
            ac, af, n = a_["by_bucket"][name]
            bc, bf, _ = b_["by_bucket"][name]
            print(f"{name + f' (n={n})':20s} {ac:10.4f} {af:11.4f} "
                  f"{bc:10.4f} {bf:11.4f}")
    d_cell = b_["per_cell"] - a_["per_cell"]
    d_field = b_["per_field"] - a_["per_field"]
    print(f"\nmanufactured strips move per-cell {d_cell:+.4f} and per-field "
          f"{d_field:+.4f} overall")
    print("What decides adoption is the low-resolution row, not this one — and")
    print("then tools/eval_lowres.py, which scores on forms that are genuinely")
    print("small rather than shrunk.")

    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump({"holdout": a.holdout, "seed": a.seed,
                   "test_forms": nte, "results": results}, fh,
                  ensure_ascii=False, indent=2)
    print(f"\n-> {a.out}")


if __name__ == "__main__":
    main()
