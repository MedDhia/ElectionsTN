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
from pv_register import load_template, register, refine
from pv_template import placed_layouts

UPRIGHT = ".cache/pv_upright"
INDEX = "data/pv_index.csv"
OUT = "data/pv_presidential_2024.csv"
WANT = sum(len(c[4]) for c in COLUMNS)

VALUE_FIELDS = ["a_registered", "b_delivered", "c_signed", "d_damaged",
                "r_remaining", "s_extracted", "valid", "blank", "spoilt",
                "w_voted", "q_declared", "zammel", "maghzaoui", "saied"]

# The form is three self-contained accounts, each closed by its own identity.
# A form whose ballot accounting is unreadable can still have vouched-for
# candidate votes, and requiring the whole form before publishing any of it
# throws those away — on this corpus, for about 1,900 polling stations.
BLOCKS = {
    "votes": ["zammel", "maghzaoui", "saied", "valid"],
    "papers": ["valid", "blank", "spoilt", "n_total"],
    "ballots": ["s_extracted", "d_damaged", "r_remaining", "m_total"],
}

_net = None


GATE_FIELDS = 18       # fields a published row must have been able to read
GATE_CORRECTED = 3     # cells the arithmetic may overrule before the row is
                       # a solution the constraints found rather than a reading
BLOCK_CORRECTED = 1    # a single account has far less redundancy behind it than
BLOCK_DROP = 4.0       # a whole form, so a block published on its own has to be
                       # nearly uncontested: at most one cell overruled, and
                       # little likelihood conceded to overrule it
GATE_DROP = 12.0       # and the likelihood it may concede doing so. Overruling
                       # two cells is cheap if they were near-ties and expensive
                       # if the classifier was sure; the second case is the one
                       # that turns out to be wrong. Set on 28 hand-verified
                       # forms, which is thin evidence for a threshold — it
                       # excludes exactly one form there, and is a bound on how
                       # hard the arithmetic argued rather than a tuned constant.

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


ROTATIONS = {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180,
             270: cv2.ROTATE_90_COUNTERCLOCKWISE}


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


def _read_one(img, predict, sharpen, registered=False):
    """Best reading of this image as it stands, or None."""
    from certify_cells import certified_fields
    best = None
    options = placed_layouts(img) if registered else layouts(img)
    for fields in options:
        if sharpen:
            fields = refine(img, fields, predict, digit_image)
        cells = _crops(img, fields)
        if len(cells) < 5:
            continue
        at, probs = 0, {}
        P = predict(np.concatenate([cells[f] for f in cells]))
        for f in cells:
            probs[f] = P[at:at + len(cells[f])]
            at += len(cells[f])
        raw = read_raw(probs)
        good = certified_fields(raw)
        res = decode(probs)
        vals, info = res if res else ({}, None)
        ok = bool(info) and (info["fields_read"] >= GATE_FIELDS
                             and info["changed"] <= GATE_CORRECTED
                             and info["drop"] <= GATE_DROP)
        rank = (ok, len(good), -(info["changed"] if info else 99))
        if best is None or rank > best[0]:
            best = (rank, dict(values=vals, info=info, probs=probs, raw=raw,
                               certified=good, whole_form=ok, located=len(cells),
                               cells=cells))
    return best


def read_image(img, predict):
    """Read one scan. Returns a dict of what could be established, or None.

    Four passes, each only run when the one before left something unresolved, so
    the cost falls on the scans that need it:

      1. the cells as detected, and as the template places them from the runs
         detection did find;
      2. the same with each field nudged to where it reads most surely;
      3. the whole form registered against the reference by colour correlation,
         for scans with too little printed grid to anchor on at all — this is
         the only pass that needs no cells found, and it recovers about a third
         of the forms nothing else can read;
      4. the other three rotations, for scans the orientation detector called
         wrong.

    Where more than one reading is on offer the form chooses: first one its own
    identities accept whole, then the one whose identities vouch for the most
    fields, then the one that needed least correcting.
    """
    def better(best, cand):
        return cand if cand and (best is None or cand[0] > best[0]) else best

    best = _read_one(img, predict, sharpen=False)
    if best is None or not (best[1]["whole_form"] and len(best[1]["certified"]) >= 14):
        best = better(best, _read_one(img, predict, sharpen=True))
    if best is None or len(best[1]["certified"]) < 14:
        best = better(best, _read_one(img, predict, sharpen=True, registered=True))
    if best is None or not best[1]["certified"]:
        for code in ROTATIONS.values():
            best = better(best, _read_one(cv2.rotate(img, code), predict,
                                          sharpen=True, registered=True))
            if best and best[1]["certified"]:
                break
    return best[1] if best else None


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

        raw, certified = got["raw"], got["certified"]
        info, vals_all = got["info"], got["values"]
        ok = sum(1 for _, fields, pred, _s in IDENTITIES
                 if all(f in raw for f in fields) and pred(raw))
        # A block is published when the independent reading already closes its
        # identity, or when the decoder closes it having barely argued with the
        # classifier there. The second is the same standard the whole form is
        # held to, applied to one account: most of the forms still unread have
        # every field located and simply read a digit or two wrongly, which is
        # what the arithmetic exists to repair.
        per_field = (info or {}).get("per_field", {})

        def decoder_backs(fields):
            if not info or any(vals_all.get(f) is None for f in fields):
                return False
            c = d = 0.0
            for f in fields:
                fc, fd = per_field.get(f, (99, 99.0))
                c += fc
                d += fd
            return c <= BLOCK_CORRECTED and d <= BLOCK_DROP

        blocks = {k: int(set(v) <= certified or decoder_backs(v))
                  for k, v in BLOCKS.items()}

        # A form the identities accept whole is published whole. Otherwise only
        # the fields they individually vouch for are published, and the rest are
        # left empty rather than filled with a reading nothing checked.
        if got["whole_form"]:
            vals, reading = dict(vals_all), "decoded"
            blocks = {k: 1 for k in BLOCKS}
        elif certified or any(blocks.values()):
            vals = {f: raw[f] for f in certified}
            for k, fields in BLOCKS.items():
                if blocks[k] and not set(fields) <= certified:
                    vals.update({f: vals_all[f] for f in fields})
            reading = "blocks"
        else:
            vals, reading = {}, "none"

        reg_ok = (vals.get("a_registered") is not None
                  and vals.get("w_voted") is not None
                  and vals["a_registered"] >= vals["w_voted"])
        votes = (sum(vals[k] for k in ("zammel", "maghzaoui", "saied"))
                 if all(vals.get(k) is not None
                        for k in ("zammel", "maghzaoui", "saied")) else None)
        return dict(
            bureau_code=code, status="read" if reading != "none" else "unverified",
            reading=reading,
            **{f: vals.get(f) for f in VALUE_FIELDS},
            candidate_sum=votes,
            turnout_pct=round(100 * vals["w_voted"] / vals["a_registered"], 2)
            if reg_ok and vals["a_registered"] else None,
            saied_share_pct=round(100 * vals["saied"] / votes, 2)
            if votes and vals.get("saied") is not None else None,
            a_registered_ok=int(reg_ok),
            votes_certified=blocks["votes"], papers_certified=blocks["papers"],
            ballots_certified=blocks["ballots"],
            identities_ok=ok,
            cells_corrected=info["changed"] if info else None,
            logp_conceded=info["drop"] if info else None,
            margin=info["margin"] if info else None,
            fields_read=info["fields_read"] if info else 0,
            fields_published=len(vals),
            fields_located=got["located"])
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
                if r.get("election") == "presidentielle_2024"
                and r["bureau_code"].isdigit()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--model", default=".cache/digit_cnn.pt")
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 4)
    a = ap.parse_args()

    # 14 presidential PVs are filed by ISIE under an Arabic school name carrying
    # no bureau code. They all collapse onto one or two cache keys, so at most two
    # of them survive as files, and neither can be joined to a polling station —
    # keying metadata off an unparseable code attaches some other station's
    # geography to a real reading. They are excluded rather than published wrong.
    codes = sorted(f[:-4] for f in os.listdir(UPRIGHT)
                   if f.endswith(".jpg") and f[:-4].isdigit())
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
                              "a_registered_ok", "votes_certified",
                              "papers_certified", "ballots_certified",
                              "identities_ok", "cells_corrected", "logp_conceded",
                              "margin", "fields_read", "fields_published",
                              "fields_located", "reading", "status"])
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with open(a.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    whole = [r for r in rows if r.get("reading") == "decoded"]
    blocks = [r for r in rows if r.get("reading") == "blocks"]
    votes = [r for r in rows if r.get("votes_certified")]
    print(f"\n{tally}")
    print(f"published whole form : {len(whole)}/{len(rows)} = {len(whole)/len(rows):.1%}")
    print(f"published some blocks: {len(blocks)} ({len(blocks)/len(rows):.1%})")
    print(f"candidate votes vouched for: {len(votes)} "
          f"({len(votes)/len(rows):.1%} of all bureaux)")
    if votes:
        tot = sum(r["saied"] for r in votes if r.get("saied") is not None)
        allv = sum(r["candidate_sum"] for r in votes if r.get("candidate_sum"))
        print(f"  Saied share over those: {100*tot/allv:.2f}% of {allv:,} votes")
    print(f"-> {a.out}")


if __name__ == "__main__":
    main()
