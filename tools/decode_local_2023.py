"""Read every 2023 local-council PV offline and publish what the form certifies.

For each scan: load it and stand it upright (`pv_local_2023`), recover the
printed grid (`pv_grid`), place the twenty-six fields by detection where
possible and by registration against the template elsewhere, classify each cell
(`digit_model`), and decode the form jointly under its own identities
(`pv_decode_local_2023`).

Nothing published here is a bare model guess. Every row carries what the form
said about itself: how many of its identities the independent cell-by-cell
reading already satisfied before any correction, how many cells the arithmetic
had to overrule to reach a consistent reading, the likelihood given up doing so,
and the gap to the next reading the identities also admit.

**The form is three accounts, and they are published separately.** The ballot
account (papers delivered, extracted, damaged, remaining) closes on its own
identity; the paper account (valid, blank, spoilt against the papers counted)
closes on another; the vote account (the slots against the valid total) on a
third. A form whose ballot accounting is unreadable can still have vouched-for
votes, and requiring the whole form before publishing any of it would throw
those away.

**How many candidates a constituency fielded is decided per constituency, not
per form.** The nine vote boxes are pre-printed and the unused ones are left
blank or struck through, so the slate has to be inferred — but it is a property
of the constituency, identical on all of its bureaux, and `slate` settles it
across all of them at once rather than guessing per form. What settles it is the
form's own identity: for each prefix of the nine boxes, on how many of the
constituency's bureaux does that prefix actually sum to the valid vote count?
A wrong prefix has to hit an unrelated three-digit number by accident, bureau
after bureau. Ink only breaks ties, and decides alone only where no prefix
closes anywhere.

The image work happens once. `prepare` places the fields on every scan and
stores the normalised cell crops (`pv_local_2023.save_cells`); the slate
inference, the self-certification loop and the decode then all read those
arrays. Placement is up to four passes of line detection at 1,600 pixels plus a
registration fit plus a confidence-guided nudge of whatever the detector missed,
which is most of the cost of reading a form, and doing it once instead of three
times is the difference between hours and minutes — and it means retraining the
classifier and re-decoding costs a forward pass rather than another pass over
the corpus.

Usage:
  python3 tools/decode_local_2023.py prepare [limit] [workers]
  python3 tools/decode_local_2023.py slate            # slate per constituency
  python3 tools/decode_local_2023.py pilot            # score against the hand-read forms
  python3 tools/decode_local_2023.py run [limit] [workers]
"""
import collections, csv, json, os, sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pv_local_2023 as L
import pv_fields_local_2023 as F
from pv_grid import find_cells, group_runs, digit_image, LADDER
from pv_register import load_template
from pv_decode_local_2023 import decode
from harvest_local_2023 import PILOT, load_net

OUT = f"data/pv_{L.ELECTION.replace('locales_', 'local_')}.csv"
SLATE = f".cache/pv_{L.ELECTION}_slate.json"

# Every field on the form except the nine vote boxes, in the order it is printed
# in. The four مطابقات are published with the rest rather than kept as internal
# checks: a non-zero one is not a reading error, it is the polling bureau saying
# its own two counts of the same thing came out different, which the form then
# asks the officers to explain. That is a fact about the count.
VALUE_FIELDS = [f for f in F.ORDER if f not in F.SLOTS]

# Each block, as the fields it publishes and the identity that closes it. A
# block is certified when its identity holds on the decoded reading *and* the
# decoder did not have to overrule a cell inside it to get there.
BLOCKS = {
    "ballots": ["s_extracted", "d_damaged", "r_remaining", "m_total"],
    "papers": ["valid", "blank", "spoilt", "n_total"],
    "votes": ["valid"] + F.SLOTS,
}
# How much ink a vote box needs before it counts as written in, as a fraction of
# its normalised crops. Over all 71,643 slot boxes in the corpus an untouched box
# sits under 0.025, a box struck out with a pen stroke between 0.05 and 0.20, and
# a box with a number in it between 0.25 and 0.50. The struck boxes fill what
# would otherwise be the valley, so 0.25 is the edge of the written mode rather
# than the middle of a gap — which is why `slate` uses the form's arithmetic
# first and this only to break ties.
INK = 0.25


def probs_for(net, img, fields):
    """{field: (n_cells, 10)} and the per-field ink fraction of each field."""
    from digit_model import predict_proba
    order, crops = [], []
    for name, cells in fields.items():
        for cell in cells:
            crop = digit_image(img, cell)
            crops.append(np.zeros((28, 28), np.uint8) if crop is None else crop)
            order.append(name)
    if not crops:
        return {}, {}
    arr = np.array(crops, np.uint8)
    probs = predict_proba(net, arr)
    out, ink = {}, {}
    at = 0
    for name, cells in fields.items():
        k = len(cells)
        out[name] = probs[at:at + k]
        ink[name] = float((arr[at:at + k] > 0).mean())
        at += k
    return out, ink


def place(img, template, net=None, rows=None):
    """(fields, detected) for one upright, canonicalised image.

    `rows` lets a caller hand in the cell runs it already has for the first
    detection setting, which `pv_local_2023.upright` computes on its way to
    choosing the rotation.
    """
    best = ({}, -1, set())
    H, W = img.shape[:2]
    for i, cfg in enumerate(LADDER):
        rows = rows if (i == 0 and rows) else group_runs(find_cells(img, settings=cfg))
        fields, detected, from_template = L.placed(rows, W, H, template)
        if detected > best[1]:
            best = (fields, detected, from_template)
        if len(fields) == F.WANT and detected >= F.WANT - 2:
            break
        rows = None
    fields, detected, from_template = best
    if fields and net is not None and from_template:
        # Only the fields registration had to place: a global transform leaves
        # individual blocks a few pixels out, which is enough to clip a digit,
        # while a field the detector found is already on its own printed box and
        # moving it can only make it worse.
        fields = nudge(img, fields, net, only=from_template)
    return fields, detected


def nudge(img, fields, net, step_frac=0.09, only=None):
    """`pv_register.refine`, with the whole form scored in one forward pass.

    Identical search — each field shifted one step over a 3x3 neighbourhood,
    keeping the offset the classifier reads most surely — but `refine` calls the
    model once per field, and twenty-six small batches cost several times what
    one batch of the same cells costs. Over eight thousand scans that is the
    difference between an afternoon and half an hour, so the batching is worth
    the bookkeeping.

    `only` restricts the search to named fields, which is where nearly all of
    the remaining saving is: nudging all twenty-six is 79% of the cost of
    preparing a form, and on a typical scan one or two of them are the ones that
    were not found on the scan's own grid.
    """
    from digit_model import predict_proba
    order, crops = [], []
    for name, cells in fields.items():
        if only is not None and name not in only:
            continue
        step = max(2, int(round(np.median([c[3] for c in cells]) * step_frac)))
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                moved = [(x + dx * step, y + dy * step, w, h)
                         for x, y, w, h in cells]
                got = [digit_image(img, c) for c in moved]
                if any(c is None for c in got):
                    continue
                order.append((name, moved, len(got)))
                crops.extend(got)
    if not crops:
        return fields
    P = predict_proba(net, np.array(crops, np.uint8))
    out, best, at = dict(fields), {}, 0
    for name, moved, k in order:
        score = float(P[at:at + k].max(1).mean())
        at += k
        if score > best.get(name, (-1.0,))[0]:
            best[name] = (score, moved)
    for name, (_, moved) in best.items():
        out[name] = moved
    return out


# ----------------------------------------------------------------- the crops

def _prepare_one(args):
    code, paths = args
    if L.load_cells(code) is not None:
        return code, "cached"
    try:
        # Which file, and which of its pages, carries the counting record is not
        # something the file name settles — so the same test that settles
        # orientation settles this: the candidate whose field map is fullest.
        # The search stops at the first complete map, which is the first page of
        # the first file for the great majority of bureaux.
        best = None
        for path in paths:
            for img in L.images(path):
                up, degrees, n, rows = L.upright(L.precanon(img))
                if best is None or n > best[0]:
                    best = (n, up, degrees, rows, img.shape[1])
                if n == F.WANT:
                    break
            if best is not None and best[0] == F.WANT:
                break
        if best is None:
            return code, "unreadable"
        _, up, degrees, rows, width = best
        work = L.canon(up)
        fields, detected = place(work, _TPL, _NET,
                                 rows=rows if work.shape == up.shape else None)
        if not fields:
            return code, "no_grid"
        crops = {}
        for name, cells in fields.items():
            arr = []
            for cell in cells:
                crop = digit_image(work, cell)
                arr.append(np.zeros((28, 28), np.uint8) if crop is None else crop)
            crops[name] = np.array(arr, np.uint8)
        L.save_cells(code, fields, crops, detected, degrees, width)
        return code, "ok"
    except Exception as exc:
        return code, f"error:{type(exc).__name__}"


def prepare(limit=None, workers=4):
    """Place the fields on every scan once and cache the cell crops."""
    files = L.cached_files()
    jobs = [(c, p) for c, p in sorted(files.items())
            if len(c) == 11 and c.isdigit()]
    if limit:
        jobs = jobs[:limit]
    print(f"{len(jobs)} bureaux", flush=True)
    stats = collections.Counter()
    with ProcessPoolExecutor(max_workers=workers, initializer=_init) as pool:
        for i, (_, status) in enumerate(pool.map(_prepare_one, jobs, chunksize=8), 1):
            stats[status] += 1
            if i % 500 == 0:
                print(f"  {i}/{len(jobs)}  {dict(stats)}", flush=True)
    print(f"done: {dict(stats)} -> {L.CELLS}")


# ------------------------------------------------------------------- the slate


def _init():
    global _TPL, _NET
    import torch
    torch.set_num_threads(1)
    _TPL = load_template(L.TEMPLATE)
    _NET = load_net()


def _slate_one(code):
    """(constituency, arithmetic votes per prefix, ink per slot) for one form."""
    from digit_model import predict_proba
    key = L.constituency_of(code)
    got = L.load_cells(code)
    if key is None or got is None:
        return None
    crops = got[0]
    wanted = ["valid"] + F.SLOTS
    names = [n for n in wanted if crops.get(n) is not None and len(crops[n])]
    if "valid" not in names:
        return None
    stack = np.concatenate([crops[n] for n in names])
    flat = unwritten_is_zero(predict_proba(_NET, stack), stack)
    read, at = {}, 0
    for name in names:
        k = len(crops[name])
        read[name] = int("".join(str(int(d)) for d in flat[at:at + k].argmax(1)))
        at += k
    ink = [float((crops[s] > 0).mean()) if crops.get(s) is not None
           and len(crops[s]) else 0.0 for s in F.SLOTS]
    closes, running = [0] * len(F.SLOTS), 0
    for k, name in enumerate(F.SLOTS):
        if name not in read:
            break
        running += read[name]
        if running == read["valid"]:
            closes[k] = 1
    return key, closes, ink


def slate(limit=None, workers=4):
    """How many slots each constituency's slate fills.

    A slate fills a prefix of the nine printed boxes, and which prefix is not
    written anywhere on the form. Two things say so, and they are used in that
    order.

    **The arithmetic, first.** The form states that the slots sum to the valid
    total. So for each prefix length, ask on how many of the constituency's
    bureaux that prefix actually sums to the valid vote count read off the same
    form. A wrong prefix has to hit an unrelated three-digit number by accident,
    on bureau after bureau; the right one closes almost everywhere. This is the
    form's own identity doing the work rather than a threshold.

    **Ink, to break ties.** A candidate who took no votes at all leaves a box
    reading zero, so the prefix that stops before them closes just as often as
    the one that includes them. Between prefixes the arithmetic likes equally,
    the longer one wins if its last box carries ink on most of the bureaux.

    Ink alone decides only where no prefix closes anywhere — a constituency
    whose forms could not be read. Its threshold is deliberately high: measured
    over all 71,643 slot boxes in the corpus, an untouched box sits under 0.025,
    a box struck out with a pen stroke between 0.05 and 0.20, and a box with a
    number in it between 0.25 and 0.50. There is no clean valley, only a
    shoulder, which is exactly why this is the fallback and not the rule.
    """
    codes = L.cached_codes()
    if limit:
        codes = codes[:limit]
    print(f"{len(codes)} forms with cached cells", flush=True)
    closed = collections.defaultdict(lambda: [0] * len(F.SLOTS))
    inks = collections.defaultdict(lambda: [[] for _ in F.SLOTS])
    seen = collections.Counter()
    with ProcessPoolExecutor(max_workers=workers, initializer=_init) as pool:
        for i, got in enumerate(pool.map(_slate_one, codes, chunksize=16), 1):
            if got is None:
                continue
            key, closes, ink = got
            seen[key] += 1
            for k in range(len(F.SLOTS)):
                closed[key][k] += closes[k]
                inks[key][k].append(ink[k])
            if i % 2000 == 0:
                print(f"  {i}/{len(codes)}", flush=True)
    out = {}
    for key, votes in closed.items():
        n_forms = seen[key]
        inked = [float(np.mean([v > INK for v in col])) if col else 0.0
                 for col in inks[key]]
        top = max(votes)
        if top:
            best = [k for k in range(len(votes)) if votes[k] == top]
            # Among prefixes the arithmetic likes equally, the longest whose own
            # box is written in; failing that, the shortest, which assumes no
            # candidate rather than an unevidenced one.
            with_ink = [k for k in best if inked[k] >= 0.5]
            n = (max(with_ink) if with_ink else min(best)) + 1
            how = "arithmetic"
        else:
            n = 0
            for k, frac in enumerate(inked, 1):
                if frac >= 0.5:
                    n = k
                else:
                    break
            how = "ink"
        out[key] = {"n_candidates": n, "bureaux": n_forms, "decided_by": how,
                    "closes": votes,
                    "ink": [round(float(np.mean(col)), 4) if col else 0.0
                            for col in inks[key]]}
    os.makedirs(".cache", exist_ok=True)
    json.dump(out, open(SLATE, "w"))
    counts = collections.Counter(v["n_candidates"] for v in out.values())
    how = collections.Counter(v["decided_by"] for v in out.values())
    print(f"{len(out)} constituencies -> {SLATE}")
    print("slate sizes:", dict(sorted(counts.items())))
    print("decided by:", dict(how))
    return out


# ------------------------------------------------------------------ the reading

def read_cached(code, net, n_slots):
    """One form, decoded from its cached cell crops."""
    from digit_model import predict_proba
    got = L.load_cells(code)
    if got is None:
        return None
    crops, detected, degrees, width = got
    names = [n for n in crops if len(crops[n])]
    if not names:
        return None
    stack = np.concatenate([crops[n] for n in names])
    flat = unwritten_is_zero(predict_proba(net, stack), stack)
    probs, at = {}, 0
    for name in names:
        k = len(crops[name])
        probs[name] = flat[at:at + k]
        at += k
    out = decode(probs, n_slots)
    if out is None:
        return None
    values, info = out
    raw = {f: int("".join(str(int(d)) for d in probs[f].argmax(1))) for f in probs}
    return {"values": values, "info": info, "raw": raw,
            "detected": detected, "degrees": degrees, "width": width}


# Below this much ink a cell holds no handwriting. It is not a guess: over the
# 227,528 cells the forms' own arithmetic vouches for, the *first* percentile of
# every digit class is above 0.19, and the least inky class is the 1s at a median
# of 0.34. Nothing the corpus certifies comes near 0.15.
BLANK_INK = 0.15
# How much of an empty cell's reading to hand to the zero. Half, not all: the
# classifier keeps a vote, so a cell that is faint but genuinely written can
# still be read as what it says.
BLANK_WEIGHT = 0.5


def unwritten_is_zero(probs, crops):
    """Push an empty cell's reading towards zero, by how much ink it holds.

    Every number on this form is written right-aligned into a fixed-width box
    and padded with written zeros — which is why a certified zero is the inkiest
    class on the form, not the emptiest. So a cell with no ink in it is not a
    zero the officer wrote; it is a box they left alone, and on a right-aligned
    number that means the same thing.

    It matters most where the reading is worst. A struck-out vote box reads as a
    row of 1s, because that is what a diagonal pen stroke through four cells
    looks like; a faint leading cell catches a fragment of the neighbouring
    group's printed slot number and reads as a confident 9. Both are cells with
    almost nothing in them, and both were costing whole vote blocks.

    This is a measurement rather than a model: `(crop > 0).mean()` asks how much
    of the normalised crop is dark, which no classifier is consulted about.
    """
    ink = (crops > 0).reshape(len(crops), -1).mean(1)
    low = ink < BLANK_INK
    if not low.any():
        return probs
    out = probs.copy()
    out[low] *= (1.0 - BLANK_WEIGHT)
    out[low, 0] += BLANK_WEIGHT
    return out


def identities_ok(values, n_slots=0):
    """How many of the eight identities a reading satisfies, and which.

    An identity is only counted where every field it names was read; a form
    whose ballot column never got located is not credited with failing the
    ballot identity, and the count says how many of the ones that *could* be
    checked came out. The slot sum is checked only where the constituency's
    slate is known, which is what `n_slots` says.
    """
    v = values
    def g(k):
        return v.get(k)
    tests = {
        "signed_voted": g("c_signed") == g("w_voted"),
        "match1": g("match1") == (g("c_signed") or 0) - (g("s_extracted") or 0),
        "papers": g("n_total") == (g("valid") or 0) + (g("blank") or 0) + (g("spoilt") or 0),
        "match3": g("match3") == (g("w_voted") or 0) - (g("n_total") or 0),
        "ballots": g("m_total") == (g("s_extracted") or 0) + (g("d_damaged") or 0)
                   + (g("r_remaining") or 0),
        "match2": g("match2") == (g("b_delivered") or 0) - (g("m_total") or 0),
        "declared": g("q_declared") == g("valid"),
    }
    needs = dict(_NEEDS)
    if n_slots:
        slots = F.SLOTS[:n_slots]
        tests["slots"] = g("valid") == sum(g(s) or 0 for s in slots)
        needs["slots"] = ["valid"] + slots
    present = {k: bool(x) for k, x in tests.items()
               if all(g(f) is not None for f in needs[k])}
    return sum(present.values()), present


_NEEDS = {
    "signed_voted": ["c_signed", "w_voted"],
    "match1": ["match1", "c_signed", "s_extracted"],
    "papers": ["n_total", "valid", "blank", "spoilt"],
    "match3": ["match3", "w_voted", "n_total"],
    "ballots": ["m_total", "s_extracted", "d_damaged", "r_remaining"],
    "match2": ["match2", "b_delivered", "m_total"],
    "declared": ["q_declared", "valid"],
}


def _read(args):
    code, n_slots = args
    try:
        if not os.path.exists(L.cells_path(code)):
            # `prepare` found no grid on any page of any file for this bureau.
            # That is a different thing from a form that was read and did not
            # certify, so the two are not published under one word.
            return code, {"error": "no_grid"}
        return code, read_cached(code, _NET, n_slots)
    except Exception as exc:
        return code, {"error": f"{type(exc).__name__}"}


def run(limit=None, workers=4, out=OUT):
    """Decode every bureau in the corpus and write the published file.

    Every bureau gets a row, including the ones whose grid was never found and
    the ones whose bundle holds a correction decision and no counting record.
    They are published with `status` saying so and their value columns empty,
    because a dataset that silently omits what it could not read reports a
    coverage it does not have.
    """
    slates = json.load(open(SLATE)) if os.path.exists(SLATE) else {}
    jobs = []
    for code in sorted(L.cached_files()):
        if not (len(code) == 11 and code.isdigit()):
            continue
        key = L.constituency_of(code)
        jobs.append((code, (slates.get(key) or {}).get("n_candidates", 0)))
    if limit:
        jobs = jobs[:limit]
    print(f"{len(jobs)} bureaux", flush=True)

    slots_by_code = {j[0]: j[1] for j in jobs}
    meta = L.index_rows()
    rows, stats = [], collections.Counter()
    with ProcessPoolExecutor(max_workers=workers, initializer=_init) as pool:
        for i, (code, got) in enumerate(pool.map(_read, jobs, chunksize=8), 1):
            rows.append(publish(code, got, slots_by_code[code], meta.get(code)))
            stats[rows[-1]["status"]] += 1
            if i % 500 == 0:
                print(f"  {i}/{len(jobs)}  {dict(stats)}", flush=True)
    write(out, rows)
    report(rows)
    return rows


def publish(code, got, n_slots, meta=None):
    """One output row: the values, per-block certification, and the diagnostics."""
    row = {"bureau_code": code, "constituency": L.constituency_of(code)}
    # `parts` calls the single printed digit "constituency"; the column of that
    # name here is the seven-digit key, so the digit is published beside it.
    part = dict(L.parts(code) or {})
    part["constituency_number"] = part.pop("constituency", "")
    row.update(part)
    meta = meta or {}
    row["scope"] = meta.get("scope", "")
    row["constituency_name"] = meta.get("constituency", "")
    row["polling_centre"] = meta.get("polling_centre", "")
    row["n_candidates"] = n_slots
    if not got or "error" in got or "values" not in got:
        row["status"] = "unread" if not got else got.get("error", "unread")
        for f in VALUE_FIELDS + F.SLOTS:
            row[f] = ""
        row.update({"identities_ok": "", "cells_corrected": "", "logp_conceded": "",
                    "margin": "", "fields_read": "", "fields_located": "",
                    "fields_detected": "", "votes_certified": "",
                    "papers_certified": "", "ballots_certified": "",
                    "valid_corroborated": "",
                    "turnout_pct": "", "scan_width": "", "rotated_deg": ""})
        return row
    values, info = got["values"], got["info"]
    ok_n, ok = identities_ok(values, n_slots)
    raw_n, _ = identities_ok(got["raw"], n_slots)
    for f in VALUE_FIELDS:
        row[f] = values.get(f) if values.get(f) is not None else ""
    for k, name in enumerate(F.SLOTS, 1):
        row[name] = values.get(name) if k <= n_slots else ""
    changed = {f: c for f, (c, _) in info["per_field"].items()}
    row["status"] = "read"
    row["identities_ok"] = raw_n
    row["cells_corrected"] = info["changed"]
    row["logp_conceded"] = info["drop"]
    row["margin"] = info["margin"]
    row["fields_read"] = info["fields_read"]
    row["fields_located"] = info["fields_located"]
    row["fields_detected"] = got["detected"]
    row["scan_width"] = got["width"]
    row["rotated_deg"] = got["degrees"]
    for block, fields in BLOCKS.items():
        # The vote block's fields depend on the slate: only the slots the
        # constituency actually filled are part of its identity.
        wanted = (["valid"] + F.SLOTS[:n_slots]) if block == "votes" else fields
        have = all(values.get(f) is not None for f in wanted)
        clean = all(changed.get(f, 0) == 0 for f in wanted)
        closes = {"ballots": ok.get("ballots"), "papers": ok.get("papers"),
                  "votes": (n_slots > 0 and values.get("valid") is not None
                            and sum(values.get(s) or 0
                                    for s in F.SLOTS[:n_slots]) == values["valid"])}[block]
        row[f"{block}_certified"] = int(bool(have and clean and closes))
    # `valid` is the one number two blocks both state, and the vote identity has
    # a blind spot the paper identity does not share: a misreading that moves a
    # candidate and the total together satisfies the slot sum exactly, and no
    # amount of care inside the vote block can ever say so. Where both blocks
    # certify, `valid` survived two independent statements of itself; where only
    # one does, this column says so rather than leaving it to be assumed. (The
    # same move as `tools/cross_check.py` makes on the 2024 presidential file.)
    row["valid_corroborated"] = int(bool(row["votes_certified"]
                                         and row["papers_certified"]))
    reg, voted = values.get("a_registered"), values.get("w_voted")
    row["turnout_pct"] = (round(100 * voted / reg, 2)
                          if reg and voted is not None and reg > 0 else "")
    return row


COLUMNS = (["bureau_code", "constituency", "scope", "constituency_name",
            "polling_centre", "subdivision", "delegation", "imada",
            "constituency_number", "centre", "bureau", "n_candidates"]
           + VALUE_FIELDS + F.SLOTS
           + ["turnout_pct", "votes_certified", "papers_certified",
              "ballots_certified", "valid_corroborated",
              "identities_ok", "cells_corrected",
              "logp_conceded", "margin", "fields_read", "fields_located",
              "fields_detected", "scan_width", "rotated_deg", "status"])


def write(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"wrote {path} ({len(rows)} rows)")


def report(rows):
    read = [r for r in rows if r["status"] == "read"]
    print(f"{len(read)}/{len(rows)} forms decoded")
    for col in ("votes_certified", "papers_certified", "ballots_certified",
                "valid_corroborated"):
        n = sum(1 for r in read if r.get(col) == 1)
        print(f"  {col:18s} on {n:5d} bureaux "
              f"({100 * n / max(1, len(rows)):5.1f}%)")


def pilot():
    """Score the reader against the hand-read forms, field by field.

    Fields the transcription left blank are skipped: a blank means the sheet did
    not show that box legibly, so nothing was claimed about it and there is
    nothing to be right or wrong about.
    """
    net = load_net()
    slates = json.load(open(SLATE)) if os.path.exists(SLATE) else {}
    truth = list(csv.DictReader(open(PILOT, encoding="utf-8")))
    fields_ok = fields_n = forms_ok = 0
    for row in truth:
        code = row["bureau_code"]
        key = L.constituency_of(code)
        n_slots = (slates.get(key) or {}).get("n_candidates") or \
            len([s for s in F.SLOTS if row.get(s) not in ("", None)])
        got = read_cached(code, net, n_slots)
        if not got:
            print(f"  {code}: not decoded")
            continue
        values = got["values"]
        wrong = []
        for name in F.ORDER:
            want = row.get(name, "")
            if want == "":
                continue
            fields_n += 1
            if values.get(name) == int(want):
                fields_ok += 1
            else:
                wrong.append(f"{name}={values.get(name)}≠{want}")
        forms_ok += not wrong
        mark = "ok " if not wrong else "!  "
        print(f"  {mark}{code}  corrected={got['info']['changed']:2d} "
              f"margin={got['info']['margin']:6.1f}  {' '.join(wrong[:6])}")
    print(f"{fields_ok}/{fields_n} fields exact ({100*fields_ok/max(1,fields_n):.1f}%), "
          f"{forms_ok}/{len(truth)} forms wholly exact")


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "run"
    def arg(i, default=None):
        """Positional argument `i`, where an empty string means "all"."""
        if len(sys.argv) <= i or sys.argv[i] == "":
            return default
        return int(sys.argv[i])

    if what == "prepare":
        prepare(arg(2), arg(3, 4))
    elif what == "slate":
        slate(arg(2), arg(3, 4))
    elif what == "pilot":
        pilot()
    else:
        run(arg(2), arg(3, 4))
