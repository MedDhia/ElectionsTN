"""Read every presidential PV offline and publish the readings the form certifies.

For each scan: recover the printed grid (`pv_grid`), map the cells to the twenty
fields (`pv_fields`), classify each cell (`digit_model`), then decode the form
jointly under its own identities (`pv_decode`).

Nothing here is a bare model guess. Every published row carries what the form
itself says about it:

  `identities_ok`   how many of the eight identities the *independent* cell-by-cell
                    reading already satisfied, before any correction. This is the
                    same standard the 30 hand-checked pilot forms were held to.
  `cells_corrected` how many cells the arithmetic had to overrule to reach a
                    consistent reading — the syndrome weight of the code. Zero
                    means the classifier and the form agreed outright.
  `logp_conceded`   the likelihood given up to make it consistent.
  `margin`          the gap to the next reading the identities also admit.

A reader who wants only rows nobody has to take on trust can filter on
`cells_corrected == 0`; the looser rows are kept, labelled, rather than dropped,
because on a 9,448-form corpus what fails is not random — discarding it silently
would bias the result toward polling stations with tidy handwriting.

Usage:
  python3 tools/decode_all.py --limit 300
  python3 tools/decode_all.py
"""
import argparse, csv, os, sys
from concurrent.futures import ProcessPoolExecutor

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pv_grid import find_cells, group_runs, digit_image, LADDER
from pv_fields import map_fields, COLUMNS
from pv_decode import decode, read_raw
from pv_register import load_template, register

UPRIGHT = ".cache/pv_upright"
INDEX = "data/pv_index.csv"
OUT = "data/pv_presidential_2024.csv"
WANT = sum(len(c[4]) for c in COLUMNS)

VALUE_FIELDS = ["a_registered", "b_delivered", "c_signed", "d_damaged",
                "r_remaining", "s_extracted", "valid", "blank", "spoilt",
                "w_voted", "q_declared", "zammel", "maghzaoui", "saied"]

_net = None


GATE_FIELDS = 18       # fields a published row must have been able to read
GATE_CORRECTED = 3     # cells the arithmetic may overrule before the row is
                       # a solution the constraints found rather than a reading

_TEMPLATE = None


def _template():
    global _TEMPLATE
    if _TEMPLATE is None:
        try:
            _TEMPLATE = load_template()
        except (OSError, ValueError):
            _TEMPLATE = {}
    return _TEMPLATE


def _crops(img, fields):
    out = {}
    for name, run in fields.items():
        imgs = [digit_image(img, c) for c in run]
        if not any(d is None for d in imgs):
            out[name] = np.array(imgs, np.uint8)
    return out


def cells_of(img):
    """Best field map the detection ladder can reach, with the cell crops."""
    H, W = img.shape[:2]
    best, best_n = None, -1
    for cfg in LADDER:
        fields = map_fields(group_runs(find_cells(img, settings=cfg)), W, H)
        if len(fields) > best_n:
            best, best_n = fields, len(fields)
        if best_n == WANT:
            break
    return _crops(img, best or {})


def layouts(img):
    """Candidate field maps: what detection found, and what the template places.

    Registration is only offered when detection came up short — on a scan where
    every box was segmented there is nothing a template can add, and a placed
    cell is always a worse crop than a found one.
    """
    H, W = img.shape[:2]
    direct, best_n = {}, -1
    for cfg in LADDER:
        fields = map_fields(group_runs(find_cells(img, settings=cfg)), W, H)
        if len(fields) > best_n:
            direct, best_n = fields, len(fields)
        if best_n == WANT:
            break
    out = [direct] if direct else []
    tpl = _template()
    if tpl and best_n < WANT:
        reg = {}
        for cfg in LADDER:
            r, _ = register(group_runs(find_cells(img, settings=cfg)), W, H, tpl)
            if len(r) > len(reg):
                reg = r
            if len(reg) == WANT:
                break
        if reg:
            out.append(reg)
    return out


def read_image(img, predict):
    """Read one scan: (values, info, n_fields_located), or None.

    Where two field layouts are on offer, the form chooses between them. A
    reading its own identities accept is preferred to one they do not, and among
    those the one that needed least correcting — the same standard that decides
    whether the row is published at all, applied to pick which reading to publish.
    """
    best = None
    for fields in layouts(img):
        cells = _crops(img, fields)
        if len(cells) < 8:
            continue
        at, probs = 0, {}
        P = predict(np.concatenate([cells[f] for f in cells]))
        for f in cells:
            probs[f] = P[at:at + len(cells[f])]
            at += len(cells[f])
        res = decode(probs)
        if res is None:
            continue
        vals, info = res
        ok = info["fields_read"] >= GATE_FIELDS and info["changed"] <= GATE_CORRECTED
        rank = (ok, -info["changed"])
        if best is None or rank > best[0]:
            best = (rank, vals, info, probs, len(cells))
    if best is None:
        return None
    _, vals, info, probs, n = best
    return vals, info, probs, n


def _model(path):
    global _net
    if _net is None:
        import torch
        from digit_model import Net
        torch.set_num_threads(1)
        _net = Net()
        _net.load_state_dict(torch.load(path, map_location="cpu"))
        _net.eval()
    return _net


def work(args):
    code, path, model_path = args
    try:
        img = cv2.imread(path)
        if img is None:
            return dict(bureau_code=code, status="unreadable")
        from digit_model import predict_proba
        from certify_cells import IDENTITIES
        net = _model(model_path)
        got = read_image(img, lambda X: predict_proba(net, X))
        if got is None:
            return dict(bureau_code=code, status="no_grid")
        vals, info, probs, located = got

        raw = read_raw(probs)
        ok = 0
        for _, fields, pred, _s in IDENTITIES:
            if all(f in raw for f in fields) and pred(raw):
                ok += 1

        # a_registered takes part in no identity, so nothing on the form checks
        # it. The one thing that can be said is that a station cannot have more
        # voters than registered voters; where it reads lower, the reading is
        # wrong and no turnout is published for that row.
        reg_ok = (vals.get("a_registered") is not None
                  and vals["a_registered"] >= vals["w_voted"])
        turnout = (round(100 * vals["w_voted"] / vals["a_registered"], 2)
                   if reg_ok and vals["a_registered"] else None)
        votes = sum(vals.get(k) or 0 for k in ("zammel", "maghzaoui", "saied"))
        return dict(bureau_code=code, status="read",
                    **{f: vals.get(f) for f in VALUE_FIELDS},
                    candidate_sum=votes,
                    turnout_pct=turnout,
                    saied_share_pct=round(100 * vals["saied"] / votes, 2)
                    if votes and vals.get("saied") is not None else None,
                    a_registered_ok=int(reg_ok),
                    identities_ok=ok, cells_corrected=info["changed"],
                    logp_conceded=info["drop"], margin=info["margin"],
                    fields_read=info["fields_read"],
                    fields_located=located)
    except Exception as e:                       # one bad scan must not stop 9k
        return dict(bureau_code=code, status=f"error:{type(e).__name__}")


def load_index():
    """Bureau metadata, from the presidential collection only.

    `data/pv_index.csv` spans four elections and bureau codes are reused across
    them, so an unfiltered lookup silently attaches 2023 local-election geography
    to 2024 presidential rows.
    """
    if not os.path.exists(INDEX):
        return {}
    keep = ("governorate", "delegation", "sector", "polling_centre")
    with open(INDEX, encoding="utf-8") as fh:
        return {r["bureau_code"]: {k: r.get(k, "") for k in keep}
                for r in csv.DictReader(fh)
                if r.get("election") == "presidentielle_2024"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--model", default=".cache/digit_cnn.pt")
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 4)
    a = ap.parse_args()

    codes = sorted(f[:-4] for f in os.listdir(UPRIGHT) if f.endswith(".jpg"))
    if a.limit:
        codes = sorted(np.random.default_rng(0).permutation(codes)[:a.limit])
    jobs = [(c, os.path.join(UPRIGHT, f"{c}.jpg"), a.model) for c in codes]
    print(f"{len(jobs)} forms, {a.workers} workers", flush=True)

    meta, rows, tally = load_index(), [], {}
    with ProcessPoolExecutor(a.workers) as ex:
        for i, r in enumerate(ex.map(work, jobs, chunksize=8), 1):
            tally[r["status"]] = tally.get(r["status"], 0) + 1
            rows.append({**meta.get(r["bureau_code"], {}), **r})
            if i % 500 == 0:
                print(f"  {i}/{len(jobs)}  {tally}", flush=True)

    cols = (["bureau_code", "governorate", "delegation", "sector", "polling_centre"]
            + VALUE_FIELDS + ["candidate_sum", "turnout_pct", "saied_share_pct",
                              "a_registered_ok",
                              "identities_ok", "cells_corrected", "logp_conceded",
                              "margin", "fields_read", "fields_located", "status"])
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with open(a.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    read = [r for r in rows if r["status"] == "read"]
    clean = [r for r in read if r["cells_corrected"] == 0]
    print(f"\n{tally}")
    print(f"read {len(read)}/{len(rows)} = {len(read)/len(rows):.1%}")
    print(f"  of those, needed no correction: {len(clean)} ({len(clean)/max(len(read),1):.1%})")
    if read:
        tot = sum(r["saied"] for r in read if r.get("saied") is not None)
        allv = sum(r["candidate_sum"] for r in read if r.get("candidate_sum"))
        print(f"  Saied share over rows read: {100*tot/allv:.2f}% of {allv:,} votes")
    print(f"-> {a.out}")


if __name__ == "__main__":
    main()
