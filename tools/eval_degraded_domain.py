"""Did the reader learn the low-resolution domain at all?

`tools/eval_degraded_training.py` scores both arms on real strips from held-out
forms, which is the right generalisation test — and it exposes a limit of the
strip corpus while doing it: only **9** of its 10,757 held-out strips come from a
page under 700px. That is not a sampling accident, it is the bootstrapping bias
this whole task exists to attack. Strip labels come from forms the identities
vouch for, and low-resolution forms almost never certify, so the training corpus
barely contains the domain the reader needs to learn.

So that harness can answer "does manufactured data hurt the forms the reader
already handles" and cannot answer "does it help the ones it does not". This
answers a narrower question that is still worth having: on **manufactured strips
from forms neither arm trained on**, does the arm that saw manufactured data read
better?

That is a domain-fit check, not a generalisation claim, and the difference is the
point. A yes here means the manufactured domain is learnable and the reader
picked it up; it does **not** mean real 560px scans get easier, because
`harvest_degraded`'s own notes measure the gap — forms shrunk to 868px still
locate a mean of 14.9 fields where real 868px scans yield about 3. Only
`tools/eval_lowres.py`, on forms that are genuinely small, can speak to that.

The split is reproduced from the same seed and the same rule as the training
harness, so the held-out forms are the same ones, and both saved arms are scored
without retraining.

Usage: python3 tools/eval_degraded_domain.py [--seed 0] [--holdout 0.12]
"""
import argparse, json, os, sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

STRIPS = ".cache/digit_strips.npz"
DEGRADED = ".cache/digit_strips_degraded.npz"
PILOT = ".cache/pv_pilot/readings.jsonl"
ARMS = {"real only": ".cache/strip_arm_real_only.pt",
        "real + manufactured": ".cache/strip_arm_real_plus_manufactured.pt"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--holdout", type=float, default=0.12)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()

    import torch
    from strip_model import StripNet, predict

    real = np.load(STRIPS, allow_pickle=True)
    deg = np.load(DEGRADED, allow_pickle=True)
    cr = real["code"]
    Xd, yd, cd = deg["X"], deg["y"].astype(np.int64), deg["code"]

    pilot = {json.loads(l)["bureau_code"] for l in open(PILOT, encoding="utf-8")}
    cr = cr[~np.isin(cr, list(pilot))]
    kd = ~np.isin(cd, list(pilot))
    Xd, yd, cd = Xd[kd], yd[kd], cd[kd]

    forms = np.random.default_rng(a.seed).permutation(
        np.unique(np.concatenate([cr, cd])))
    nte = max(1, int(len(forms) * a.holdout))
    test_forms = set(forms[:nte].tolist())
    te = np.array([c in test_forms for c in cd])
    Xte, yte = Xd[te], yd[te]
    print(f"{int(te.sum()):,} manufactured strips from held-out forms "
          f"(neither arm trained on these)\n")

    for name, path in ARMS.items():
        if not os.path.exists(path):
            print(f"{name}: {path} not found — run "
                  "tools/eval_degraded_training.py first")
            continue
        net = StripNet()
        net.load_state_dict(torch.load(path, map_location="cpu"))
        net.eval()
        p = predict(net, Xte).argmax(2)
        print(f"{name:24s} per-cell {(p == yte).mean():.4f}   "
              f"per-field {(p == yte).all(1).mean():.4f}")

    print("\nA gap here says the manufactured domain is learnable and was learnt.")
    print("It does not say real low-resolution scans got easier — for that, see")
    print("tools/eval_lowres.py, which scores on forms that are genuinely small.")


if __name__ == "__main__":
    main()
