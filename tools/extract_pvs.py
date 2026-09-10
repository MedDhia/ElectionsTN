"""Extract results from every 2024 presidential PV via the Claude Batch API.

Pipeline, all stages resumable:

  1. orient   — pick the counting record out of everything the archive holds for
                a bureau (a PDF bundle, or several JPGs) by registering each page
                against the reference layout, put it upright with
                tools/pv_orient.py (header-based; 30/30 on the pilot set vs 21/30
                for Tesseract's OSD), downscale, and cache the result
  2. montage  — where the printed grid is fully recoverable, crop the digit
                cells and tile them one field per row: the same 20 fields at
                ~460 image tokens instead of ~2,400 for the page. Complete on
                40% of forms; the rest fall back to the page.
  3. submit   — build one Batch API request per bureau with a JSON-schema
                structured output, in chunks, and record the batch ids
  4. collect  — poll each batch, stream results, cache raw JSON per bureau
  5. validate — apply the seven internal consistency checks from the pilot and
                write data/pv_results_2024.csv

Batches run at 50% of standard price and most finish within an hour. Nothing is
re-sent on a re-run: oriented images and per-bureau results are both cached.

    python3 tools/extract_pvs.py estimate            # cost/size, no API needed
    python3 tools/extract_pvs.py orient  [workers]   # page pick + orientation
    python3 tools/extract_pvs.py montage [workers]
    python3 tools/extract_pvs.py submit  [--limit N]
    python3 tools/extract_pvs.py collect
    python3 tools/extract_pvs.py validate

Requires ANTHROPIC_API_KEY (or an `ant auth login` profile) for submit/collect.
"""
import base64, csv, glob, json, os, sys, time
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SRC_DIR = ".cache/pv_all"
ORIENT_DIR = ".cache/pv_upright"
MONTAGE_DIR = ".cache/pv_montage"
RESULT_DIR = ".cache/pv_results"
BATCH_LOG = ".cache/pv_batches.json"
OUT = "data/pv_results_2024.csv"

MODEL = "claude-opus-5"
EFFORT = os.environ.get("PV_EFFORT", "medium")   # perception task, not reasoning
LONG_EDGE = int(os.environ.get("PV_LONG_EDGE", "1600"))
PDF_DPI = int(os.environ.get("PV_PDF_DPI", "200"))
CHUNK = 2000                                     # requests per batch submission

# Anthropic bills images at roughly (width x height) / 750 tokens.
PRICE_IN, PRICE_OUT = 5.00, 25.00                # $/M tokens, Claude Opus 5
BATCH_DISCOUNT = 0.5

FIELDS = ["code_in_image", "date", "a_registered", "b_delivered", "c_signed",
          "d_damaged", "r_remaining", "s_extracted", "valid", "blank", "spoilt",
          "match1", "w_voted", "m_total", "match2", "n_total", "match3",
          "q_declared", "match4", "zammel", "maghzaoui", "saied"]
WORD_FIELDS = ["zammel_words", "maghzaoui_words", "saied_words"]

SCHEMA = {
    "type": "object",
    "properties": {
        **{f: {"type": ["integer", "null"]} for f in FIELDS if f not in ("code_in_image", "date")},
        "code_in_image": {"type": ["string", "null"]},
        "date": {"type": ["string", "null"]},
        **{f: {"type": ["string", "null"]} for f in WORD_FIELDS},
        "legible": {"type": "string", "enum": ["full", "partial", "poor"]},
        "fields_uncertain": {"type": "string"},
    },
    "required": FIELDS + WORD_FIELDS + ["legible", "fields_uncertain"],
    "additionalProperties": False,
}

INSTRUCTIONS = """You are transcribing a Tunisian polling-station record: the \
"محضر عملية الفرز" (counting-operation record) for the 2024 presidential election.

The form is pre-printed. Labels and the three candidate names are printed; every \
number is handwritten, one digit per box. Read the digits exactly as written — do \
not correct them, do not infer a value from the other boxes, and do not compute \
anything the form does not state. Downstream checks depend on seeing the real \
readings, so a wrong-looking number must be reported as written.

Fields, by their printed labels:
- code_in_image: the six groups under "رمز مكتب الاقتراع", concatenated left to
  right into one digit string (هيئة فرعية، معتمدية، عمادة، دائرة، مركز، مكتب)
- date: the digits in the "التاريخ" box, e.g. 20241006
- a_registered  (أ) عدد الناخبين المرسمين بمكتب الاقتراع
- b_delivered   (ب) عدد أوراق التصويت المسلمة فعليا
- c_signed      (ج) عدد الناخبين الذين أمضوا في قائمة الناخبين
- d_damaged     (د) عدد أوراق التصويت التالفة
- r_remaining   (ر) عدد أوراق التصويت الباقية
- s_extracted   (س) عدد أوراق التصويت المستخرجة من صندوق الاقتراع
- valid         (ص) عدد أوراق التصويت الصحيحة
- blank         (ع) عدد أوراق التصويت البيضاء
- spoilt        (ف) عدد أوراق التصويت الملغاة
- w_voted       (و) عدد الناخبين الذين قاموا بالتصويت
- m_total       (م) المجموع = (س)+(د)+(ر)
- n_total       (ن) المجموع = (ص)+(ع)+(ف)
- q_declared    (ق) العدد الجملي للأصوات المصرح بها
- match1..match4: the four "المطابقة" difference boxes, in printed order
- zammel / maghzaoui / saied: the digit column for العياشي زمال، زهير المغزاوي، \
قيس سعيد, in that printed row order
- *_words: the same three counts as written out in Arabic words in the \
"بلسان القلم" column, transcribed verbatim

Use null for any box you cannot read confidently, and list those field names in \
fields_uncertain (comma-separated, empty string if none). Set legible to "full", \
"partial" or "poor" for the scan overall. Leading zeros are padding — return 118, \
not "0118"."""


MONTAGE_INSTRUCTIONS = """This image is a digit montage cropped from a Tunisian \
polling-station record (محضر عملية الفرز) for the 2024 presidential election.

Each row is one field: the field name is printed on the left, followed by that \
field's handwritten digits, one per cell, in order. Read the digits exactly as \
written — do not correct them, do not infer a value from other rows, and do not \
compute anything. Downstream checks depend on seeing the real readings.

Leading zeros are padding: return 118, not "0118". Use null for any cell you \
cannot read confidently and name its field in fields_uncertain. The montage \
carries no code_in_image, date or spelled-out word columns — return null for \
those. Set legible to "full", "partial" or "poor"."""


def bureau_of(path):
    return os.path.basename(path).split("__", 1)[0]


# ---------------------------------------------------------------- orient stage

# What "the right page" means, and why the masthead alone cannot say.
#
# The archive holds more than one image for about 200 bureaux: a PDF bundle of
# four to six pages, or several JPGs uploaded side by side. Only one of them is
# the counting record. The others are a decision correcting it
# (`قرار تصحيح محضر فرز`), a register page, or the sub-committee's signature
# block -- and the correction decision carries the *same* ISIE masthead as the
# record, down to "الانتخابات الرئاسية لسنة 2024".
#
# The first version of this stage picked the page whose masthead OCR'd best, and
# it was wrong on 126 bureaux. Not because the masthead is ambiguous in
# principle, but because on a poor scan the record's own masthead OCRs to
# *nothing*: measured across the failures, the record page scores 0 and the
# correction page beside it scores 2, so any legible other page wins. A relative
# score between pages is only as good as the OCR on the page you want, which is
# exactly the page that is hardest to read.
#
# So the test is now positive and absolute: register each page against the
# reference layout and keep the one that fits it. `tools/pick_page.py` already
# established the separation -- the counting record fits at 0.91-0.96 and every
# other page of its bundle at 0.49 or below -- and it is the same question, so
# it is the same code rather than a second rule that can disagree with the
# first. Having the weak rule here and the strong one in a repair script that
# runs only over uncertified bureaux is what let this survive: the repair could
# not reach a bureau whose votes had already been read off the wrong page.
#
# Where no reference layout is cached, the fallback is structural rather than
# textual: the record is the page carrying the form's printed red plate whose
# bottom band fits the six-rule template. Both are properties of the document
# being sought. The masthead survives only as a last tie-break.
#
# The JPG bundles had a second, quieter version of the same bug: the stage
# mapped one output per *source file*, so four files for one bureau raced for
# the same destination and whichever the pool reached first won, with no
# selection at all. Sources are grouped by bureau here so that every page of
# every file competes.

RED_PLATE = 0.004          # red-minus-grey pixels as a share of the page


def _pages_of(src):
    """(page index, PIL image) for every page of one archived file."""
    from PIL import Image
    if src.lower().endswith(".pdf"):
        import pypdfium2 as pdfium
        doc = pdfium.PdfDocument(src)
        for i in range(len(doc)):
            yield i, doc[i].render(scale=PDF_DPI / 72).to_pil().convert("RGB")
    else:
        yield 0, Image.open(src).convert("RGB")


def _red_share(img):
    """How much of the page is printed in the form's red plate.

    The counting record is ruled in red throughout; the correction decision and
    the register pages are black on white. Greyscale scans of a record read 0
    here too, which is why this ranks pages rather than deciding on its own.
    """
    import numpy as np
    a = np.asarray(img, dtype=np.int16)
    if a.ndim != 3 or a.shape[2] < 3:
        return 0.0
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    return float(((r - np.maximum(g, b)) > 40).mean())


def _band_fit(img):
    """(fits, rules matched): does the page's bottom band fit the template?

    `pv_reps_geom` fits the form's six full-width rules and then demands the
    representatives table's own column rules at 0.20 and 0.60 of its width. No
    other page of the bundle is ruled that way. It is permissive enough to fire
    on a busy correction page now and then, so the count of template rules it
    matched is kept as the strength of the evidence rather than a yes/no.
    """
    import cv2
    import numpy as np
    from pv_reps_geom import locate_any
    a = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
    try:
        loc, _, _, _ = locate_any(a)
    except Exception:
        return False, 0
    if loc is None:
        return False, 0
    return True, int(loc.get("rules_hit", 0)) + int(loc.get("col_rules", 0))


def _pick_page(sources):
    """Choose the counting record among every page the archive holds.

    Returns (image, degrees, masthead score, why) where `why` records what the
    choice was made on, so a bad pick is auditable afterwards instead of silent.
    """
    import cv2
    import numpy as np
    from pv_orient import orient
    from pick_page import fit, reference, TAKE, KEEP
    raw = []
    for src in sorted(sources):
        try:
            pages = list(_pages_of(src))
        except Exception:
            continue
        raw += [(src, i, pil) for i, pil in pages]
    if not raw:
        return None, 0, 0, {}
    # Registration and the band fit cost seconds a page, and where the archive
    # holds one page there is nothing to choose between: skip the evidence and
    # keep the single-page case, 9,254 of 9,449 bureaux, at the cost it had.
    if len(raw) == 1:
        src, _, pil = raw[0]
        up, deg, score = orient(pil)
        return up, deg, score, {"src": src, "page": 0, "pages": 1,
                                "decisive": "only page"}
    have_ref = reference()[0] is not None
    cands = []
    for src, i, pil in raw:
        try:
            up, deg, score = orient(pil)
        except Exception:
            continue
        # Register at each rotation rather than trusting the masthead's. On the
        # pages this stage used to get wrong the masthead scores 0, so `up` is
        # not upright either, and a fit measured on it would be as blind as the
        # pick was. The correlation settles the turn as well as the page, which
        # is what `pick_page` does for an inset form the masthead cannot score.
        cc, turned_img, turned_deg = 0.0, None, deg
        if have_ref:
            bgr = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
            for d, flag in ((0, None), (90, cv2.ROTATE_90_CLOCKWISE),
                            (180, cv2.ROTATE_180),
                            (270, cv2.ROTATE_90_COUNTERCLOCKWISE)):
                page = bgr if flag is None else cv2.rotate(bgr, flag)
                c, im = fit(page, rotations=False)
                if c > cc:
                    cc, turned_img, turned_deg = c, im, d
                if cc >= TAKE:
                    break
        if turned_img is not None and cc >= KEEP:
            from PIL import Image as _Image
            up = _Image.fromarray(cv2.cvtColor(turned_img, cv2.COLOR_BGR2RGB))
            deg = turned_deg
        red = _red_share(up)
        fits, strength = _band_fit(up)
        cands.append({"src": src, "page": i, "img": up, "deg": deg,
                      "score": score, "fit": round(cc, 4), "red": round(red, 5),
                      "plate": red >= RED_PLATE, "band": fits,
                      "strength": strength})
        # Stopping here is safe in a way the old masthead exit was not: this is
        # an absolute threshold on how well the page matches the counting record,
        # not a score compared against pages that have not been looked at yet.
        if cc >= TAKE:
            break
    if not cands:
        return None, 0, 0, {}
    best = max(cands, key=lambda c: (c["fit"] >= KEEP, c["fit"], c["plate"],
                                     c["band"], c["strength"], c["score"],
                                     -c["page"]))
    why = {k: best[k] for k in ("src", "page", "fit", "red", "plate", "band",
                                "strength")}
    why["pages"] = len(raw)            # how many the archive holds...
    why["weighed"] = len(cands)        # ...and how many were looked at
    why["decisive"] = ("registration" if best["fit"] >= KEEP else
                       "plate" if best["plate"] else
                       "band" if best["band"] else
                       "masthead" if best["score"] else "order")
    return best["img"], best["deg"], best["score"], why


def _load_best_page(src):
    """The counting-record page of one archived file, as (image, degrees, score).

    Kept for `confirm_pages.py` and `retry_alternates.py`, which ask the question
    of a single file rather than of a bureau. Routed through the same picker so
    there is one answer to "which page is the record" in the repository.
    """
    img, deg, score, _ = _pick_page([src])
    return img, deg, score


def _orient_one(job):
    from PIL import Image
    code, sources = job
    dest = os.path.join(ORIENT_DIR, code + ".jpg")
    meta = dest + ".json"
    if os.path.exists(dest) and os.path.exists(meta):
        return "cached"
    try:
        img, deg, score, why = _pick_page(sources)
        if img is None:
            return "fail: no readable page"
        if max(img.size) > LONG_EDGE:
            f = LONG_EDGE / max(img.size)
            img = img.resize((max(1, int(img.width * f)), max(1, int(img.height * f))),
                             Image.LANCZOS)
        img.save(dest, quality=88)
        json.dump({"rotation": deg, "confidence": score, "source": why.get("src"),
                   "page": why.get("page", 0), "sources": sorted(sources),
                   "pages_available": why.get("pages", 1),
                   "pages_weighed": why.get("weighed", 1),
                   "fit": why.get("fit"), "red_share": why.get("red"),
                   "band_fits": why.get("band"), "chosen_on": why.get("decisive"),
                   "size": list(img.size)}, open(meta, "w"))
        if why.get("pages", 1) > 1:
            return ("ok" if why.get("decisive") in ("registration", "plate", "band")
                    else "weak-pick")
        return "low-confidence" if score == 0 else "ok"
    except Exception as exc:
        return f"fail: {type(exc).__name__}"


def stage_orient(workers=4):
    os.makedirs(ORIENT_DIR, exist_ok=True)
    files = sorted(glob.glob(os.path.join(SRC_DIR, "*")))
    files = [f for f in files if not f.endswith((".part", ".json"))]
    from collections import Counter, defaultdict
    by_bureau = defaultdict(list)
    for f in files:
        code = bureau_of(f)
        # Files whose name carries no bureau code have nothing to group on --
        # eleven unrelated forms would otherwise compete as one bureau -- so each
        # keeps its own key and its own output.
        key = code if code != "nocode" else f"nocode_{os.path.basename(f)[:-4]}"
        by_bureau[key].append(f)
    jobs = sorted(by_bureau.items())
    multi = sum(1 for _, v in jobs if len(v) > 1)
    print(f"{len(files)} scans, {len(jobs)} bureaux to orient "
          f"({multi} with more than one archived file)", flush=True)
    tally = Counter()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for i, status in enumerate(pool.map(_orient_one, jobs, chunksize=8), 1):
            tally[status.split(":")[0]] += 1
            if i % 250 == 0:
                print(f"  {i}/{len(jobs)} {dict(tally)}", flush=True)
    print("orient done:", dict(tally))
    if tally["weak-pick"]:
        print(f"  {tally['weak-pick']} multi-page bureaux were decided on the "
              f"masthead or document order alone -- check their .json meta")


def _montage_one(src):
    import cv2
    from pv_grid import find_fields
    from pv_fields import map_fields
    from pv_montage import montage, ORDER
    code = os.path.basename(src)[:-4]
    dest = os.path.join(MONTAGE_DIR, code + ".png")
    if os.path.exists(dest):
        return "cached"
    img = cv2.imread(src)
    if img is None:
        return "unreadable"
    fields, _ = find_fields(img, map_fields, len(ORDER))
    if len(fields) != len(ORDER):
        return "incomplete"          # this bureau falls back to the full page
    canvas, _ = montage(img, fields)
    cv2.imwrite(dest, canvas)
    return "ok"


def stage_montage(workers=4):
    os.makedirs(MONTAGE_DIR, exist_ok=True)
    files = sorted(glob.glob(os.path.join(ORIENT_DIR, "*.jpg")))
    print(f"{len(files)} oriented pages", flush=True)
    from collections import Counter
    tally = Counter()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for i, status in enumerate(pool.map(_montage_one, files, chunksize=8), 1):
            tally[status] += 1
            if i % 500 == 0:
                print(f"  {i}/{len(files)} {dict(tally)}", flush=True)
    built = tally["ok"] + tally["cached"]
    print(f"montage done: {dict(tally)}")
    print(f"  {built}/{len(files)} bureaux ({100*built/max(len(files),1):.1f}%) "
          f"will send a montage; the rest send the full page")


# ---------------------------------------------------------------- submit stage

def _request_for(path):
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request
    code = os.path.basename(path)[:-4]
    montage_path = os.path.join(MONTAGE_DIR, code + ".png")
    if os.path.exists(montage_path):
        path, media, prompt = montage_path, "image/png", MONTAGE_INSTRUCTIONS
    else:
        media, prompt = "image/jpeg", INSTRUCTIONS
    data = base64.standard_b64encode(open(path, "rb").read()).decode()
    return Request(
        custom_id=code,
        params=MessageCreateParamsNonStreaming(
            model=MODEL,
            max_tokens=2000,
            output_config={"effort": EFFORT,
                           "format": {"type": "json_schema", "schema": SCHEMA}},
            messages=[{"role": "user", "content": [
                {"type": "text", "text": prompt,
                 "cache_control": {"type": "ephemeral"}},
                {"type": "image", "source": {"type": "base64",
                                             "media_type": media, "data": data}},
            ]}],
        ),
    )


def stage_submit(limit=None):
    import anthropic
    client = anthropic.Anthropic()
    files = sorted(glob.glob(os.path.join(ORIENT_DIR, "*.jpg")))
    pending = [f for f in files
               if not os.path.exists(os.path.join(RESULT_DIR, os.path.basename(f)[:-4] + ".json"))]
    if limit:
        pending = pending[:limit]
    print(f"{len(pending)} bureaux to submit ({len(files) - len(pending)} already done)")
    log = json.load(open(BATCH_LOG)) if os.path.exists(BATCH_LOG) else []
    for start in range(0, len(pending), CHUNK):
        chunk = pending[start:start + CHUNK]
        batch = client.messages.batches.create(requests=[_request_for(f) for f in chunk])
        log.append({"id": batch.id, "n": len(chunk), "created": time.time()})
        json.dump(log, open(BATCH_LOG, "w"), indent=1)
        print(f"  submitted {batch.id} ({len(chunk)} requests)", flush=True)
    print(f"{len(log)} batches recorded in {BATCH_LOG}")


# --------------------------------------------------------------- collect stage

def stage_collect(poll=60):
    import anthropic
    client = anthropic.Anthropic()
    os.makedirs(RESULT_DIR, exist_ok=True)
    log = json.load(open(BATCH_LOG))
    for entry in log:
        while True:
            batch = client.messages.batches.retrieve(entry["id"])
            if batch.processing_status == "ended":
                break
            print(f"  {entry['id']}: {batch.processing_status}, "
                  f"{batch.request_counts.processing} processing", flush=True)
            time.sleep(poll)
        saved = errors = 0
        for result in client.messages.batches.results(entry["id"]):
            if result.result.type != "succeeded":
                errors += 1
                continue
            msg = result.result.message
            text = next((b.text for b in msg.content if b.type == "text"), "")
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                errors += 1
                continue
            payload["_usage"] = {"input": msg.usage.input_tokens,
                                 "output": msg.usage.output_tokens,
                                 "cache_read": getattr(msg.usage, "cache_read_input_tokens", 0)}
            json.dump(payload, open(os.path.join(RESULT_DIR, f"{result.custom_id}.json"), "w"))
            saved += 1
        print(f"  {entry['id']}: {saved} saved, {errors} errored", flush=True)
    print(f"results in {RESULT_DIR}")


# -------------------------------------------------------------- validate stage

def stage_validate():
    from validate_pv_pilot import check   # the seven pilot constraints, reused
    index = {}
    with open("data/pv_index.csv", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["election"] == "presidentielle_2024" and r["bureau_code"]:
                index.setdefault(r["bureau_code"], r)

    rows, usage = [], {"input": 0, "output": 0, "cache_read": 0}
    for path in sorted(glob.glob(os.path.join(RESULT_DIR, "*.json"))):
        code = os.path.basename(path)[:-5]
        rec = json.load(open(path))
        for k, v in rec.pop("_usage", {}).items():
            usage[k] = usage.get(k, 0) + v
        rec["bureau_code"] = code
        checks, votes = check(rec)
        # The code written on the form is authoritative. It matched the filename
        # on 30/30 JPG scans in the pilot, but PDF bundles have been seen to
        # disagree, so both are kept and the disagreement is flagged.
        in_form = (rec.get("code_in_image") or "").strip()
        geo = index.get(in_form) or index.get(code, {})
        rows.append({
            "bureau_code": in_form or code,
            "bureau_code_from_filename": code,
            "code_source": "form" if in_form else "filename",
            "code_mismatch": str(bool(in_form and in_form != code)).lower(),
            "governorate": geo.get("governorate", ""),
            "delegation": geo.get("delegation", ""),
            "polling_centre": geo.get("polling_centre", ""),
            **{f: rec.get(f) for f in FIELDS},
            "candidate_sum": votes,
            "checks_passed": sum(1 for v in checks.values() if v is True),
            "checks_testable": sum(1 for v in checks.values() if v is not None),
            "checks_failed": ",".join(k for k, v in checks.items() if v is False),
            "legibility": rec.get("legible", ""),
            "fields_uncertain": rec.get("fields_uncertain", ""),
            "verified": str(sum(1 for v in checks.values() if v is True) == 7).lower(),
        })

    if not rows:
        print("no results yet — run submit and collect first")
        return
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    verified = sum(1 for r in rows if r["verified"] == "true")
    print(f"wrote {len(rows)} rows -> {OUT}")
    print(f"  fully verified (7/7 checks): {verified} ({100*verified/len(rows):.1f}%)")
    print(f"  needs review: {len(rows) - verified}")
    cost = (usage["input"] / 1e6 * PRICE_IN + usage["output"] / 1e6 * PRICE_OUT) * BATCH_DISCOUNT
    print(f"  tokens in/out: {usage['input']:,}/{usage['output']:,}  (~${cost:,.2f} at batch rates)")


# -------------------------------------------------------------- estimate stage

def stage_estimate():
    files = [f for f in glob.glob(os.path.join(SRC_DIR, "*"))
             if not f.endswith((".part", ".json"))]
    oriented = glob.glob(os.path.join(ORIENT_DIR, "*.jpg"))
    montages = glob.glob(os.path.join(MONTAGE_DIR, "*.png"))
    n = len(oriented) or len(files)
    n_mont = min(len(montages), n)
    n_page = n - n_mont

    # Anthropic bills images at roughly (width x height) / 750 tokens.
    page_img = LONG_EDGE * int(LONG_EDGE * 0.707) / 750     # full landscape page
    mont_img = 374 * 926 / 750                              # measured montage
    prompt, out_tok = 700, 320

    tin = n_page * (page_img + prompt) + n_mont * (mont_img + prompt)
    tout = n * out_tok
    std = tin / 1e6 * PRICE_IN + tout / 1e6 * PRICE_OUT
    all_page_in = n * (page_img + prompt)
    std_all_page = all_page_in / 1e6 * PRICE_IN + tout / 1e6 * PRICE_OUT

    print(f"scans downloaded : {len(files):,}")
    print(f"scans oriented   : {len(oriented):,}")
    print(f"montages built   : {n_mont:,} ({100*n_mont/max(n,1):.1f}%) — the rest send the page")
    print(f"model            : {MODEL}, effort={EFFORT}, long edge={LONG_EDGE}px")
    print(f"tokens (est.)    : {tin/1e6:.1f}M in, {tout/1e6:.1f}M out")
    print(f"cost (est.)      : ${std:,.0f} standard, ${std*BATCH_DISCOUNT:,.0f} via Batch API")
    print(f"  without montages: ${std_all_page*BATCH_DISCOUNT:,.0f} via Batch API "
          f"({100*(1-std/std_all_page):.0f}% saved)")
    print(f"batches          : {-(-n // CHUNK)} of up to {CHUNK} requests")
    print("note: output tokens and the shared instruction block do not shrink with the")
    print("      montage, which is why the saving is well below the 5x image-token cut.")
    print("      Prompt caching on the instruction block reduces the input side further.")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "estimate"
    if cmd == "montage":
        stage_montage(int(sys.argv[2]) if len(sys.argv) > 2 else 4)
    elif cmd == "orient":
        stage_orient(int(sys.argv[2]) if len(sys.argv) > 2 else 4)
    elif cmd == "submit":
        lim = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
        stage_submit(lim)
    elif cmd == "collect":
        stage_collect()
    elif cmd == "validate":
        stage_validate()
    else:
        stage_estimate()
