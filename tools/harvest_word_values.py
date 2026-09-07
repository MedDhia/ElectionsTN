"""Keep what the words say, not just whether they agree.

`flag_splits.py` reads the Arabic words column beside each candidate's digits and
publishes one bit: do the two channels agree. That bit found four transposed
candidate rows once a screen narrowed it down, but the bit alone cannot say *how*
they disagree, and the disagreement is where the information is. If the words
beside Maghzaoui read what the digits put under Saied, the rows were read in the
wrong order — and that is visible only if the values are kept.

So this runs the same reader and writes the three numbers out. Nothing is
published from here and no value is overwritten; `screen_transpositions.py`
consumes the dump.

The reader is the pilot-free model, for the same reason the field reader uses
one: the 30 hand-verified forms stay usable as ground truth. It reads 96.4% of
whole numbers correctly, so a single disagreement is weak evidence — but a
disagreement that is *exactly another candidate's value* is not the kind of
mistake a 3.6% error rate makes.

Usage: python3 tools/harvest_word_values.py [--workers 4] [--out FILE]
"""
import argparse, csv, json, os, sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

RESULTS = "data/pv_presidential_2024.csv"
UPRIGHT = ".cache/pv_upright"
MODEL = os.environ.get("PV_WORD_MODEL", ".cache/word_cnn_holdout.pt")
OUT = "data/verification/word_readings.jsonl"

_net = None


def _work(args):
    code, path = args
    global _net
    try:
        import cv2
        import torch
        from harvest_words import word_image, CANDIDATES, NDIG
        from word_model import WordNet, predict
        from decode_all import layouts
        from pv_template import placed_layouts
        if _net is None:
            torch.set_num_threads(1)
            _net = WordNet()
            _net.load_state_dict(torch.load(MODEL, map_location="cpu"))
            _net.eval()
        img = cv2.imread(path)
        if img is None:
            return code, None
        strips, names = [], []
        for fields in list(layouts(img)) + list(placed_layouts(img)):
            if any(len(fields.get(n, ())) != NDIG for n in CANDIDATES):
                continue
            for n in CANDIDATES:
                im = word_image(img, fields[n])
                if im is not None:
                    strips.append(im); names.append(n)
            if len(strips) == len(CANDIDATES):
                break
            strips, names = [], []
        if len(strips) != len(CANDIDATES):
            return code, None
        pred = predict(_net, np.array(strips)).argmax(2)
        out = {}
        for n, p in zip(names, pred):
            out[n] = int("".join(str(d) for d in p))
        return code, out
    except Exception:
        return code, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 4)
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()

    rows = list(csv.DictReader(open(RESULTS, encoding="utf-8")))
    jobs = []
    for r in rows:
        if r["votes_certified"] != "1":
            continue
        p = os.path.join(UPRIGHT, f"{r['bureau_code']}.jpg")
        if os.path.exists(p):
            jobs.append((r["bureau_code"], p))
    print(f"{len(jobs)} bureaux to read the words for", flush=True)

    got = 0
    with open(a.out, "w", encoding="utf-8") as fh, \
            ProcessPoolExecutor(a.workers) as ex:
        for i, (code, vals) in enumerate(ex.map(_work, jobs, chunksize=8), 1):
            if vals:
                got += 1
                fh.write(json.dumps({"bureau_code": code, **vals}) + "\n")
            if i % 1000 == 0:
                print(f"  {i}/{len(jobs)}  {got} read", flush=True)

    print(f"\n{got} of {len(jobs)} had a readable words column\n-> {a.out}")


if __name__ == "__main__":
    main()
