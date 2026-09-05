"""Score a reader on genuinely low-resolution forms, not simulated ones.

Everything measured in this project until now rests on the 30-form pilot, and
every one of those is a sharp scan. That sample cannot say whether the reader or
the gate behaves on the forms that actually fail: 478 stations without certified
votes, 195 of them in Medenine, where ISIE published at a median 560px.

So the failing forms were read directly off the scans, magnified, with the score
each candidate got also written out in Arabic beside the digits as a second
check. The readings live in `.cache/vision_lowres/readings.jsonl`.

They are not asserted on authority. Of the 17 with a legible total, 17 close the
form's own identity exactly — the same test every published row must pass, and
one a misread digit would almost always break. That is what makes them usable as
truth here.

This matters most for judging `harvest_degraded`. Manufactured low-resolution
strips are known to be easier than real ones, so a reader trained on them must be
scored on real degraded forms or the measurement is circular.

Usage: python3 tools/eval_lowres.py [--model .cache/digit_cnn.pt]
"""
import argparse, collections, json, os, sys

import cv2
import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

READINGS = "data/verification/lowres_readings.jsonl"
UPRIGHT = ".cache/pv_upright"
FIELDS = ("zammel", "maghzaoui", "saied", "valid", "q_declared")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=".cache/digit_cnn.pt")
    a = ap.parse_args()

    from digit_model import Net, predict_proba
    from decode_all import read_image, BLOCKS
    torch.set_num_threads(os.cpu_count() or 4)
    net = Net()
    net.load_state_dict(torch.load(a.model, map_location="cpu"))
    net.eval()
    predict = lambda X: predict_proba(net, X)

    truth = [json.loads(l) for l in open(READINGS, encoding="utf-8")]
    t = collections.Counter()
    wrong = []
    for r in truth:
        code = r["bureau_code"]
        p = os.path.join(UPRIGHT, f"{code}.jpg")
        img = cv2.imread(p) if os.path.exists(p) else None
        if img is None:
            t["no_image"] += 1
            continue
        got = read_image(img, predict)
        if not got:
            t["no_reading"] += 1
            continue
        t["read"] += 1
        raw, vals, cert = got["raw"], got["values"], set(got["certified"])
        for f in FIELDS:
            want = r.get(f)
            if want is None:
                continue
            t[f"{f}_seen"] += 1
            t[f"{f}_raw_ok"] += (raw.get(f) == want)
            t[f"{f}_final_ok"] += (vals.get(f) == want)
            if raw.get(f) != want:
                wrong.append((code, f, want, raw.get(f)))
        if set(BLOCKS["votes"]) <= cert:
            t["votes_certified"] += 1
            ok = all(r.get(f) is None or raw.get(f) == r[f]
                     for f in ("zammel", "maghzaoui", "saied"))
            t["votes_certified_correct"] += ok

    print(f"model: {a.model}\n")
    print(f"  forms read {t['read']} of {len(truth)}"
          + (f", {t['no_reading']} unreadable" if t["no_reading"] else ""))
    print("\n  per field, independent cell reading vs the scan:")
    for f in FIELDS:
        n = t[f"{f}_seen"]
        if n:
            print(f"    {f:12s} raw {t[f'{f}_raw_ok']:3d}/{n:3d}"
                  f"   after decoding {t[f'{f}_final_ok']:3d}/{n:3d}")
    print(f"\n  votes block certified on {t['votes_certified']} of {t['read']}"
          f", correct on {t['votes_certified_correct']}")
    if wrong:
        print("\n  fields the raw reading gets wrong:")
        for code, f, want, got in wrong[:40]:
            print(f"    {code} {f:12s} scan says {want:5d}   reader says {got}")


if __name__ == "__main__":
    main()
