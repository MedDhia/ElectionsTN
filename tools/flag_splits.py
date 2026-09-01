"""Flag the rows where the written-out words back up the digits.

The identities constrain the candidate total but not the split between the three
candidates, so those three columns rest on the classifier in a way no other
published field does. The words column beside the digits is the only independent
evidence on the page about that split.

It is not good enough to overrule the digits — read on its own it gets 75 of the
pilot's 90 scores against the cell reader's 88, and where the two disagree it is
right twice out of seventeen. Mixing it into the decoder at any weight that fixed
those two would introduce more errors than it removed. That is measured in
`docs/PV_OFFLINE_READING.md` and it is why nothing here overwrites a value.

What it is good at is noticing. The cell reader makes exactly two errors on the
pilot and the words catch both, so the disagreements are where the errors live:
of the 73 pilot scores where the two channels agree, 73 are correct. Publishing
that as a column costs nothing, changes no value, and lets anyone who needs the
split to be right filter on it.

The caveat travels with the column, in the codebook: two errors is a thin sample.
Zero wrong in 73 bounds the agreed set near 4%, which is not yet distinguishable
from the 2.2% base rate. What the pilot shows is that the errors concentrate in
the flagged group, not that the unflagged group is proven cleaner.

Usage: python3 tools/flag_splits.py [--workers 4]
"""
import argparse, csv, os, shutil, sys, tempfile
from concurrent.futures import ProcessPoolExecutor

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

RESULTS = "data/pv_presidential_2024.csv"
UPRIGHT = ".cache/pv_upright"
# The pilot-free model, for the same reason the field reader uses one: the 30
# verified forms stay usable as ground truth for as long as the corpus is reread.
MODEL = os.environ.get("PV_WORD_MODEL", ".cache/word_cnn_holdout.pt")
COLUMN = "split_corroborated"

_net = None


def _work(args):
    code, path, published = args
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
            return code, ""
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
            return code, ""
        pred = predict(_net, np.array(strips)).argmax(2)
        for n, p in zip(names, pred):
            if int("".join(str(d) for d in p)) != published[n]:
                return code, "0"
        return code, "1"
    except Exception:
        return code, ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 4)
    a = ap.parse_args()

    rows = list(csv.DictReader(open(RESULTS, encoding="utf-8")))
    jobs = []
    for r in rows:
        if r["votes_certified"] != "1":
            continue
        try:
            pub = {n: int(r[n]) for n in ("zammel", "maghzaoui", "saied")}
        except (ValueError, KeyError):
            continue
        p = os.path.join(UPRIGHT, f"{r['bureau_code']}.jpg")
        if os.path.exists(p):
            jobs.append((r["bureau_code"], p, pub))
    print(f"{len(jobs)} bureaux with certified votes to corroborate", flush=True)

    flag = {}
    with ProcessPoolExecutor(a.workers) as ex:
        for i, (code, v) in enumerate(ex.map(_work, jobs, chunksize=8), 1):
            flag[code] = v
            if i % 500 == 0:
                n1 = sum(1 for x in flag.values() if x == "1")
                print(f"  {i}/{len(jobs)}  {n1} corroborated", flush=True)

    fields = list(rows[0].keys())
    if COLUMN not in fields:
        fields.append(COLUMN)
    for r in rows:
        r[COLUMN] = flag.get(r["bureau_code"], "")

    # Write aside and check the shape before replacing the published file; a
    # short dataset has been committed from this directory once already.
    fd, tmp = tempfile.mkstemp(dir="data", suffix=".csv")
    with os.fdopen(fd, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    if sum(1 for _ in open(tmp, encoding="utf-8")) != len(rows) + 1:
        os.unlink(tmp)
        sys.exit("refusing to install a dataset of the wrong length")
    shutil.move(tmp, RESULTS)
    os.chmod(RESULTS, 0o644)

    n1 = sum(1 for v in flag.values() if v == "1")
    n0 = sum(1 for v in flag.values() if v == "0")
    nb = sum(1 for v in flag.values() if v == "")
    print(f"\ncorroborated {n1}, contradicted {n0}, no words readable {nb}")
    print(f"-> {RESULTS} (+{COLUMN})")


if __name__ == "__main__":
    main()
