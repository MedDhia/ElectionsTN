"""Score the word reader against the only ground truth that can judge it.

The word reader is trained on labels taken from the digit cells, so scoring it
against those labels cannot answer the question it exists for: whether the words
are right when the cells are wrong. That comparison is circular by construction.

The pilot is not. Thirty forms were read and verified by hand, and — usefully —
that pass transcribed the words column as well as the digits
(`saied_words: "مائة وثلاثون"` beside `saied: 130`). Those 90 transcriptions were
never training data, and the model scored here withheld every pilot form, so this
is an honest read of what the words channel can contribute.

Reported two ways. Overall accuracy says whether the channel works at all. The
disagreement cases say whether it is *useful*: the whole point is arbitrating
where cells and words differ, so the number that matters is how often the words
are right when they disagree with the cells.

Usage: python3 tools/eval_words.py [--model .cache/word_cnn_holdout.pt]
"""
import argparse, collections, json, os, sys

import cv2
import numpy as np
import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harvest_words import word_image, CANDIDATES, NDIG
from harvest_digits import source_image

READINGS = ".cache/pv_pilot/readings.jsonl"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=".cache/word_cnn_holdout.pt")
    ap.add_argument("--cells", default=".cache/digit_cnn.pt")
    a = ap.parse_args()

    from word_model import WordNet, predict
    from digit_model import Net, predict_proba
    from decode_all import read_image, layouts
    from pv_template import placed_layouts
    torch.set_num_threads(os.cpu_count() or 4)

    wnet = WordNet()
    wnet.load_state_dict(torch.load(a.model, map_location="cpu"))
    wnet.eval()
    cnet = Net()
    cnet.load_state_dict(torch.load(a.cells, map_location="cpu"))
    cnet.eval()

    truth = [json.loads(l) for l in open(READINGS, encoding="utf-8")]
    tally = collections.Counter()
    rows = []
    for t in truth:
        path = source_image(t["bureau_code"])
        img = cv2.imread(path) if path else None
        if img is None:
            continue
        got = read_image(img, lambda X: predict_proba(cnet, X))
        cells = got["raw"] if got else {}
        strips, names = [], []
        for fields in list(layouts(img)) + list(placed_layouts(img)):
            if any(len(fields.get(n, ())) != NDIG for n in CANDIDATES):
                continue
            for n in CANDIDATES:
                im = word_image(img, fields[n])
                if im is not None:
                    strips.append(im); names.append(n)
            if strips:
                break
        if not strips:
            tally["no_strip"] += 1
            continue
        pred = predict(wnet, np.array(strips)).argmax(2)
        for n, p in zip(names, pred):
            want = t.get(n)
            if want is None:
                continue
            got_w = int("".join(str(d) for d in p))
            got_c = cells.get(n)
            tally["n"] += 1
            tally["words_ok"] += (got_w == want)
            if got_c is not None:
                tally["cells_seen"] += 1
                tally["cells_ok"] += (got_c == want)
                if got_c != got_w:
                    tally["disagree"] += 1
                    tally["words_right_on_disagree"] += (got_w == want)
                    tally["cells_right_on_disagree"] += (got_c == want)
                    rows.append((t["bureau_code"], n, want, got_c, got_w))

    n = max(tally["n"], 1)
    print(f"model: {a.model}\n")
    print(f"  word reader   {tally['words_ok']:3d}/{tally['n']:3d} "
          f"= {tally['words_ok']/n:.3f} exact")
    if tally["cells_seen"]:
        c = tally["cells_seen"]
        print(f"  cell reader   {tally['cells_ok']:3d}/{c:3d} "
              f"= {tally['cells_ok']/c:.3f} exact  (same scores, for reference)")
    d = tally["disagree"]
    print(f"\n  they disagree on {d} of {tally['cells_seen']} scores")
    if d:
        print(f"    words right {tally['words_right_on_disagree']:3d}/{d}"
              f"    cells right {tally['cells_right_on_disagree']:3d}/{d}")
        for code, name, want, gc, gw in rows:
            mark = "words" if gw == want else ("cells" if gc == want else "neither")
            print(f"      {code} {name:10s} truth {want:5d}  cells {gc:5d}  "
                  f"words {gw:5d}  -> {mark}")
    if tally["no_strip"]:
        print(f"\n  {tally['no_strip']} pilot forms yielded no word strip")


if __name__ == "__main__":
    main()
