"""Sheet one 2023 local PV per image, for a person to read and transcribe.

The offline reader needs labels to start from, and the only labels available are
read by eye. This makes that cheap and self-checking: rather than showing the
scan and asking for twenty-six numbers off it, it crops each field's cells from
the geometry the pipeline actually placed and lays them out enlarged, one field
per row, named. Reading the sheet therefore does two jobs at once — it produces
the labels, and it shows whether the placement is on the right boxes, which a
transcription from the raw scan would hide.

The sample is drawn with a fixed seed over the whole cached corpus, so it is
representative of scan quality rather than of what happens to read well, and the
same forms come back on a re-run. These forms are also the honest test set:
`harvest_local_2023 certify` skips them, so `digit_model cv` can train on
self-certified cells alone and score against cells no form in its training set
shares a writer with. The shipped model does get them, which understates its
measured accuracy — the right direction for a number used to decide whether to
trust the output.

Two kinds of form are wanted, and the difference matters. Cells to *train* on
have to come from forms whose grid detection found the fields itself: where the
boxes were placed by registering against the template instead, a crop can sit
half a cell out, and a label read off the sheet would then be attached to the
wrong image. Forms to *test* on should be drawn without that filter, because the
corpus is mostly forms like that. `min_detected` picks between the two.

A transcription is worth exactly as much as its own consistency, so `check`
audits the finished file against the form's eight identities before anything is
trained on it. A hand-read form is not a fact; it is a reading, and a reading
that fails an identity the printed form has to satisfy is a transcription slip,
not a discovery about the election. Every one of these labels has to clear the
same bar the pipeline's own output is held to.

Usage:
  python3 tools/pilot_local_2023.py sample [n] [min_detected] [tag]
  python3 tools/pilot_local_2023.py blank [tag]
  python3 tools/pilot_local_2023.py check
"""
import csv, os, random, sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pv_local_2023 as L
import pv_fields_local_2023 as F
from pv_grid import find_cells, group_runs, LADDER
from pv_register import load_template

OUT = ".cache/pilot_2023"
LABELS = "data/verification/pv_local_2023_pilot.csv"
SEED = 11
CELL = 64          # each cell is drawn this big on the sheet
PAD = 8


def place(img, template):
    """(fields, detected) for one upright, canonicalised image."""
    H, W = img.shape[:2]
    best = ({}, -1)
    for cfg in LADDER:
        rows = group_runs(find_cells(img, settings=cfg))
        fields, detected, _ = L.placed(rows, W, H, template)
        if detected > best[1]:
            best = (fields, detected)
        if len(fields) == F.WANT and detected >= F.WANT - 2:
            break
    return best


def sheet(img, fields):
    """One image: every field's cells, enlarged, one field per labelled row."""
    names = [n for n in F.ORDER if n in fields]
    width = PAD + 260 + 4 * (CELL + PAD)
    height = PAD + len(names) * (CELL + PAD)
    canvas = np.full((height, width, 3), 255, np.uint8)
    for i, name in enumerate(names):
        y = PAD + i * (CELL + PAD)
        cv2.putText(canvas, name, (PAD, y + CELL - 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.85, (0, 0, 0), 2)
        for j, cell in enumerate(fields[name][:4]):
            x, y0, w, h = cell
            crop = img[max(0, y0):y0 + h, max(0, x):x + w]
            if crop.size == 0:
                continue
            crop = cv2.resize(crop, (CELL, CELL), interpolation=cv2.INTER_CUBIC)
            x0 = PAD + 260 + j * (CELL + PAD)
            canvas[y:y + CELL, x0:x0 + CELL] = crop
            cv2.rectangle(canvas, (x0, y), (x0 + CELL, y + CELL), (200, 200, 200), 1)
    return canvas


def sample(n=20, min_detected=0, tag=""):
    out_dir = f"{OUT}{tag}"
    os.makedirs(out_dir, exist_ok=True)
    template = load_template(L.TEMPLATE)
    files = L.cached_files()
    codes = sorted(files)
    random.Random(SEED).shuffle(codes)
    picked = []
    for code in codes:
        if len(picked) >= n:
            break
        img = L.load(files[code][0])
        if img is None:
            continue
        work = L.canon(L.upright(img)[0])
        fields, detected = place(work, template)
        if len(fields) != F.WANT or detected < min_detected:
            continue
        cv2.imwrite(f"{out_dir}/{code}.png", sheet(work, fields))
        picked.append((code, detected, work.shape[1], work.shape[0]))
        print(f"  {code}  detected={detected}/{F.WANT}", flush=True)
    with open(f"{out_dir}/sample.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["bureau_code", "fields_detected", "width", "height"])
        w.writerows(picked)
    print(f"{len(picked)} sheets -> {out_dir}")


def blank(tag=""):
    """A CSV with a row per sampled form and a column per field, to fill in."""
    codes = [r["bureau_code"] for r in
             csv.DictReader(open(f"{OUT}{tag}/sample.csv", encoding="utf-8"))]
    os.makedirs(os.path.dirname(LABELS), exist_ok=True)
    with open(LABELS, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["bureau_code"] + F.ORDER)
        for code in codes:
            w.writerow([code] + [""] * len(F.ORDER))
    print(f"wrote {LABELS} ({len(codes)} rows to fill in)")


def check(path=LABELS):
    """Audit the hand-read labels against the identities printed on the form.

    A form whose vote block was not legible on the sheet has no slots recorded,
    and the two slot tests are then skipped rather than failed: nothing was
    claimed about them, so there is nothing to check. Every other identity is
    required of every row.
    """
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    bad = with_slots = 0
    for r in rows:
        def g(k):
            v = r.get(k, "")
            return None if v in ("", None) else int(v)
        slots = [g(s) for s in F.SLOTS]
        tests = {
            "signed_voted": g("c_signed") == g("w_voted"),
            "match1": g("match1") == g("c_signed") - g("s_extracted"),
            "papers": g("n_total") == g("valid") + g("blank") + g("spoilt"),
            "match3": g("match3") == g("w_voted") - g("n_total"),
            "ballots": g("m_total") == (g("s_extracted") + g("d_damaged")
                                        + g("r_remaining")),
            "match2": g("match2") == g("b_delivered") - g("m_total"),
            "declared": g("q_declared") == g("valid"),
        }
        if any(s is not None for s in slots):
            with_slots += 1
            read = [s for s in slots if s is not None]
            tests["slots"] = sum(read) == g("valid")
            tests["slate"] = len(read) == g("n_candidates")
        failed = [k for k, ok in tests.items() if not ok]
        if failed:
            bad += 1
            print(f"  ! {r['bureau_code']}: {', '.join(failed)}")
    print(f"{len(rows)} hand-read forms ({with_slots} with a legible vote "
          f"block), {bad} with a failing identity")
    return bad


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "sample"
    if what == "check":
        raise SystemExit(1 if check() else 0)
    elif what == "blank":
        blank(sys.argv[2] if len(sys.argv) > 2 else "")
    else:
        sample(int(sys.argv[2]) if len(sys.argv) > 2 else 20,
               int(sys.argv[3]) if len(sys.argv) > 3 else 0,
               sys.argv[4] if len(sys.argv) > 4 else "")
