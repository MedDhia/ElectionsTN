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

**One arm per process, because a container restart already ate a run.** The first
attempt trained both arms in one process and was killed 90 minutes in, having
written nothing: `strip_model.train` only returns a model after all 30 epochs, so
there was no partial result to keep. Each arm now runs on its own and writes its
metrics and its `.pt` the moment it finishes, and `--compare` prints the table
from whatever arms exist on disk. A restart costs at most one arm. The split is
rebuilt from `--seed` and `--holdout` rather than passed between processes, so
the arms stay comparable across separate invocations.

Usage:
  python3 tools/eval_degraded_training.py --arm real          # baseline
  python3 tools/eval_degraded_training.py --arm both          # + manufactured
  python3 tools/eval_degraded_training.py --compare           # the table
"""
import argparse, json, os, sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

STRIPS = ".cache/digit_strips.npz"
DEGRADED = ".cache/digit_strips_degraded.npz"
UPRIGHT = ".cache/pv_upright"
PILOT = ".cache/pv_pilot/readings.jsonl"
OUT = "data/verification/degraded_training.json"
# arm key -> (human name, whether manufactured strips are in the training set)
ARMS = {"real": ("real only", False),
        "both": ("real + manufactured", True)}


def arm_paths(key):
    name = ARMS[key][0].replace(" ", "_").replace("+", "plus")
    return (f"data/verification/degraded_training_{key}.json",
            f".cache/strip_arm_{name}.pt")

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


def build_split(seed, holdout):
    """Everything both arms share: the arrays, the pilot cut, and the split.

    Rebuilt from the seed rather than cached, so two arms trained in two
    processes are still scored on exactly the same held-out strips.
    """
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
    forms = np.random.default_rng(seed).permutation(
        np.unique(np.concatenate([cr, cd])))
    nte = max(1, int(len(forms) * holdout))
    test_forms = set(forms[:nte].tolist())
    te = np.array([c in test_forms for c in cr])
    trd = np.array([c not in test_forms for c in cd])
    print(f"\ntest: {int(te.sum()):,} real strips from {nte:,} forms "
          "(no manufactured strip is ever tested on)")

    Xte, yte, cte = Xr[te], yr[te], cr[te]
    px = {c: long_edge(c) for c in sorted(set(cte.tolist()))}
    bk = np.array([bucket(px[c]) for c in cte])
    print("test strips by published page resolution")
    for _, _, name in BUCKETS:
        print(f"   {name:18s} {int((bk == name).sum()):6,}")
    if (bk == "unknown").any():
        print(f"   {'unknown':18s} {int((bk == 'unknown').sum()):6,}")
    return dict(Xr=Xr, yr=yr, Xd=Xd, yd=yd, te=te, trd=trd,
                Xte=Xte, yte=yte, bk=bk, test_forms=nte)


def run_arm(key, seed, holdout):
    import torch
    from strip_model import train, predict, MAX_STEPS

    name, use_deg = ARMS[key]
    sp = build_split(seed, holdout)
    trr = ~sp["te"]
    if use_deg:
        Xt = np.concatenate([sp["Xr"][trr], sp["Xd"][sp["trd"]]])
        yt = np.concatenate([sp["yr"][trr], sp["yd"][sp["trd"]]])
    else:
        Xt, yt = sp["Xr"][trr], sp["yr"][trr]

    print(f"\n=== {name}: {len(yt):,} training strips, "
          f"{MAX_STEPS} steps/epoch ===", flush=True)
    net = train(Xt, yt, seed=seed, log=True)
    pred = predict(net, sp["Xte"]).argmax(2)
    cell, field = score(pred, sp["yte"])
    per = {}
    for _, _, b in BUCKETS:
        m = sp["bk"] == b
        if m.any():
            per[b] = score(pred[m], sp["yte"][m]) + (int(m.sum()),)
    res = {"arm": name, "per_cell": cell, "per_field": field, "by_bucket": per,
           "train_strips": int(len(yt)), "steps_per_epoch": MAX_STEPS,
           "seed": seed, "holdout": holdout, "test_forms": sp["test_forms"]}
    print(f"  per-cell {cell:.4f}   per-field {field:.4f}")
    for b, (c, f, n) in per.items():
        print(f"    {b:18s} n={n:5,}  cell {c:.4f}  field {f:.4f}")

    jp, mp = arm_paths(key)
    torch.save(net.state_dict(), mp)
    with open(jp, "w", encoding="utf-8") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=2)
    print(f"\n-> {mp}\n-> {jp}")


def compare():
    got = {}
    for key in ARMS:
        jp, _ = arm_paths(key)
        if os.path.exists(jp):
            got[key] = json.load(open(jp, encoding="utf-8"))
        else:
            print(f"{ARMS[key][0]}: not run yet ({jp} missing)")
    if len(got) < 2:
        return
    a_, b_ = got["real"], got["both"]
    if a_["seed"] != b_["seed"] or a_["holdout"] != b_["holdout"]:
        sys.exit("the two arms used different splits — not comparable")
    if a_["steps_per_epoch"] != b_["steps_per_epoch"]:
        sys.exit("the two arms used different step budgets — not comparable")
    print(f"both arms: seed {a_['seed']}, holdout {a_['holdout']}, "
          f"{a_['steps_per_epoch']} steps/epoch, "
          f"{a_['test_forms']:,} held-out forms")
    print(f"training strips: {a_['train_strips']:,} real only, "
          f"{b_['train_strips']:,} with manufactured\n")
    print("=" * 74)
    print(f"{'resolution':22s} {'real only':>22s} {'real + manufactured':>24s}")
    print(f"{'':22s} {'cell':>10s} {'field':>11s} {'cell':>11s} {'field':>12s}")
    print(f"{'ALL':22s} {a_['per_cell']:10.4f} {a_['per_field']:11.4f} "
          f"{b_['per_cell']:11.4f} {b_['per_field']:12.4f}")
    for _, _, name in BUCKETS:
        if name in a_["by_bucket"] and name in b_["by_bucket"]:
            ac, af, n = a_["by_bucket"][name]
            bc, bf, _ = b_["by_bucket"][name]
            print(f"{name + f' (n={n:,})':22s} {ac:10.4f} {af:11.4f} "
                  f"{bc:11.4f} {bf:12.4f}")
    print("=" * 74)
    d_cell = b_["per_cell"] - a_["per_cell"]
    d_field = b_["per_field"] - a_["per_field"]
    print(f"manufactured strips move per-cell {d_cell:+.4f} and per-field "
          f"{d_field:+.4f} overall")
    print("\nThe row that licenses adoption is the *high*-resolution one: it has")
    print("to show no material regression, because that is most of the corpus.")
    print("The low-resolution row here is too thin to decide anything — see")
    print("tools/eval_lowres.py, which scores on forms that are genuinely small")
    print("rather than shrunk, and tools/eval_degraded_domain.py for domain fit.")
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(got, fh, ensure_ascii=False, indent=2)
    print(f"\n-> {OUT}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", choices=sorted(ARMS),
                    help="train and score one arm, then write its metrics")
    ap.add_argument("--compare", action="store_true",
                    help="print the table from the arms already on disk")
    ap.add_argument("--holdout", type=float, default=0.12)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    if a.compare:
        compare()
    elif a.arm:
        run_arm(a.arm, a.seed, a.holdout)
    else:
        ap.error("give --arm real, --arm both, or --compare")


if __name__ == "__main__":
    main()
