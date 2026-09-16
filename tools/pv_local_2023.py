"""Shared access to the 2023 local-council PV scans.

One module for the three things every 2023 reading step needs: turning a cached
file into an upright image of the form, saying what a bureau code means, and
knowing which local constituency a bureau belongs to.

**Upright.** The scans arrive as PDFs and as JPEGs, at widths from 600 to 2500
pixels, and a third of them are rotated a quarter turn. The 2024 pipeline
settles orientation by OCR-ing the printed masthead (`pv_orient`); here the form
itself is a better witness. The 2023 form is landscape, so the aspect ratio
halves the question to one pair of rotations, and between those two the right
one is simply the one where the field template maps more fields. That uses the
printed grid rather than Tesseract, needs no language data, and scores exactly
the thing the rest of the pipeline depends on.

**Bureau codes.** The eleven digits of a 2023 bureau code are the six printed
identifiers in the form's header, most significant first:

    01 01 01 1 01 01
    │  │  │  │ │  └── مكتب الاقتراع      polling bureau
    │  │  │  │ └───── مركز الاقتراع      polling centre
    │  │  │  └─────── الدائرة الانتخابية  local constituency, within the imada
    │  │  └────────── العمادة            imada
    │  └───────────── المعتمدية          delegation
    └──────────────── الهيئة الفرعية      ISIE regional subdivision

So a bureau's local constituency — the unit that elects one council member, and
the unit the published results are reported for — is the first seven digits of
its code. No name matching is involved, which matters: the constituency names in
the index are Arabic strings from folder paths, and the published results carry
their own spellings.
"""
import os, sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pv_grid import find_cells, group_runs, LADDER
import pv_fields_local_2023 as F

# Both rounds of the 2023 local election were held on the same printed form, so
# the whole pipeline is the same for either; only the corpus, the cell cache and
# the output file differ. `PV_ELECTION=locales_2023_t2` switches all three. The
# digit classifier is deliberately *not* switched: it is trained on the form,
# not on the round, and round two is 779 scans against round one's 12,195.
ELECTION = os.environ.get("PV_ELECTION", "locales_2023_t1")
CACHE = f".cache/pv_{ELECTION}"
UPRIGHT = f".cache/pv_{ELECTION}_upright"
INDEX = "data/pv_index.csv"

# The form is landscape at 1.40:1. Anything appreciably taller than wide is a
# quarter turn out; the ambiguity that remains is always 180 degrees.
LANDSCAPE = 1.15
RENDER_WIDTH = 1600        # PDFs are rendered at the width the template uses


MAX_PAGES = 8


def images(path, width=RENDER_WIDTH, max_pages=MAX_PAGES):
    """Every page of a cached file as a BGR image, first page first.

    A bureau's scan is not reliably one page of one file. Some bundles are a
    five-page PDF whose counting record is the first page and whose remaining
    pages are the polling record; others are a decision. Which page carries the
    form is not written in the file name — one bureau's `-C01-5.pdf` is a
    five-page record bundle and another's `-C02-4.pdf` is a correction decision
    — so the caller settles it the way it settles orientation, by asking which
    candidate maps the most fields.
    """
    if path.lower().endswith(".pdf"):
        try:
            import pypdfium2 as pdfium
            pdf = pdfium.PdfDocument(path)
            for i in range(min(len(pdf), max_pages)):
                page = pdf[i]
                scale = width / page.get_size()[0]
                pil = page.render(scale=max(scale, 0.5)).to_pil().convert("RGB")
                yield cv2.cvtColor(np.asarray(pil), cv2.COLOR_RGB2BGR)
        except Exception:
            return
    else:
        img = cv2.imread(path)
        if img is not None:
            yield img


def load(path, width=RENDER_WIDTH):
    """One cached file as a BGR image of its first page, or None."""
    for img in images(path, width, max_pages=1):
        return img
    return None


def rotations(img):
    """The rotations worth trying, best guess first.

    A landscape scan is either upright or upside down, a portrait one is a
    quarter turn either way; there is no point testing the other pair.
    """
    tall = img.shape[0] > LANDSCAPE * img.shape[1]
    if tall:
        return [(90, cv2.ROTATE_90_COUNTERCLOCKWISE), (270, cv2.ROTATE_90_CLOCKWISE)]
    return [(0, None), (180, cv2.ROTATE_180)]


def rotate(img, how):
    return img if how is None else cv2.rotate(img, how)


def upright(img, settings=None):
    """(upright image, degrees, fields mapped) for one scan.

    The winner is the rotation whose field map is most complete. A tie — which
    happens when neither rotation maps anything, so the grid was not found at
    all — keeps the first, and the caller sees a field count of zero.

    The grouped cell runs of the winning rotation come back with it, because the
    caller's next act is to map fields on exactly that image with exactly these
    settings: `pv_grid.find_cells` resamples to its own working width and runs
    two morphological passes over it, and doing that six times per form — twice
    to choose a rotation, four more down the detection ladder — is most of the
    cost of reading one.
    """
    best = (None, 0, -1, [])
    for deg, how in rotations(img):
        turned = rotate(img, how)
        H, W = turned.shape[:2]
        rows = group_runs(find_cells(turned, settings=settings))
        found = F.map_fields(rows, W, H)
        if len(found) > best[2]:
            best = (how, deg, len(found), rows)
        if best[2] == F.WANT:
            break
    return rotate(img, best[0]), best[1], best[2], best[3]


def find_fields(img):
    """(fields, ladder index) for an upright image, trying each grid setting.

    `pv_grid.find_fields` does this for the 2024 template; this is the same
    walk down the detection ladder against the 2023 one.
    """
    best, best_i = {}, -1
    for i, cfg in enumerate(LADDER):
        H, W = img.shape[:2]
        fields = F.map_fields(group_runs(find_cells(img, settings=cfg)), W, H)
        if len(fields) == F.WANT:
            return fields, i
        if len(fields) > len(best):
            best, best_i = fields, -1
    return best, best_i


# ------------------------------------------------------------------ template

TEMPLATE = f".cache/pv_{ELECTION}_template.json"
CANON_W = 1600             # the geometry is stored at a fixed width
# Which end of an over-long run a field sits at, from the template's own specs.
ALIGN = {name: (spec[5] if len(spec) > 5 else "left")
         for spec in F.COLUMNS for name in spec[4]}


def canon(img, width=CANON_W):
    """`img` resampled to the width the template geometry is stored at."""
    if img.shape[1] == width:
        return img
    scale = width / img.shape[1]
    return cv2.resize(img, (width, max(1, round(img.shape[0] * scale))),
                      interpolation=cv2.INTER_CUBIC if scale > 1 else cv2.INTER_AREA)


def precanon(img, width=CANON_W):
    """`img` scaled so that whichever rotation wins comes out `width` wide.

    Resampling before choosing the rotation rather than after is worth a
    paragraph, because it is most of the throughput of a corpus pass. Line
    detection resamples to its own working width internally, and the template
    geometry is stored at a fixed width, so a 2,500-pixel scan is resampled on
    every pass and the runs found while choosing the rotation are in
    coordinates nothing else uses. Scaled to the canonical width first, the
    rotation is chosen on the same pixels the fields are then mapped on, the
    detected runs carry straight over, and `find_cells` — two morphological
    passes, the dominant cost — runs once instead of up to six times.

    Which side to scale comes from the aspect ratio, which scaling preserves: a
    portrait scan is a quarter turn out, so its *height* is what becomes the
    width. Rounding leaves the result within a pixel of the target either way,
    and `canon` is a no-op when it is exact.
    """
    long_side = img.shape[0] if img.shape[0] > LANDSCAPE * img.shape[1] else img.shape[1]
    if long_side == width:
        return img
    scale = width / long_side
    return cv2.resize(img, (max(1, round(img.shape[1] * scale)),
                            max(1, round(img.shape[0] * scale))),
                      interpolation=cv2.INTER_CUBIC if scale > 1 else cv2.INTER_AREA)


def build_template(code, path=TEMPLATE):
    """Store the geometry of a form whose grid detection reads completely.

    A reference has to be a form detection finds on its own, so the candidate
    is checked rather than trusted: if its own field map is short, nothing is
    written and the caller is told.
    """
    import json
    files = cached_files().get(str(code)) or []
    for candidate in files:
        img = load(candidate)
        if img is None:
            continue
        work = canon(upright(img)[0])
        fields, _ = find_fields(work)
        if len(fields) != F.WANT:
            continue
        H, W = work.shape[:2]
        os.makedirs(os.path.dirname(path), exist_ok=True)
        json.dump({"bureau_code": str(code), "width": W, "height": H,
                   "fields": {k: [list(map(int, c)) for c in v]
                              for k, v in fields.items()}},
                  open(path, "w"))
        return path
    return None


def placed(rows, W, H, template):
    """`pv_register.register`, with every field trimmed to its printed length.

    Registration claims a template field with whatever run it matched, and on
    this form a vote box's run carries the neighbouring group's printed slot
    number as a fifth cell. Left in, that digit would be read as part of the
    number. Trimming here rather than inside `pv_register` keeps the 2024
    pipeline's copy of it untouched.

    Returns (fields, n_detected, from_template) — the third being the fields
    whose cells did *not* come off this scan's own detected grid, either because
    registration had to place them or because the run found was short enough to
    be discarded. They are the only ones worth nudging afterwards.
    """
    from pv_register import register
    fields, detected, found = register(rows, W, H, template, with_source=True)
    fit = _fit_to(fields, template, W, H)
    out, from_template = {}, set(fields) - found
    for name, cells in fields.items():
        want = template[name][5]
        if len(cells) > want:
            cells = (cells[-want:] if ALIGN.get(name) == "right" else cells[:want])
        elif len(cells) < want and fit:
            # A run shorter than the printed field means detection lost a cell,
            # and reading the field off what is left drops a digit — "0128"
            # becomes "012". The template knows where the missing cell is, so a
            # short run defers to it entirely rather than being padded, which
            # would mix two coordinate systems inside one field.
            cells = _place(template[name][0], fit, W, H)
            from_template.add(name)
        out[name] = cells
    return out, detected, from_template


def _fit_to(fields, template, W, H):
    """The affine scale and offset from template coordinates to this scan."""
    import numpy as np
    pairs = [(template[n][1], template[n][2], c[0][0] / W, min(x[1] for x in c) / H)
             for n, c in fields.items() if n in template]
    if len(pairs) < 3:
        return None
    ax = np.array([[p[0], 1.0] for p in pairs])
    ay = np.array([[p[1], 1.0] for p in pairs])
    (sx, bx), *_ = np.linalg.lstsq(ax, [p[2] for p in pairs], rcond=None)
    (sy, by), *_ = np.linalg.lstsq(ay, [p[3] for p in pairs], rcond=None)
    if not (0.7 < sx < 1.4 and 0.7 < sy < 1.4):
        return None
    return float(sx), float(bx), float(sy), float(by)


def _place(cells, fit, W, H):
    sx, bx, sy, by = fit
    return [(int(round((sx * cx + bx) * W)), int(round((sy * cy + by) * H)),
             max(1, int(round(sx * cw * W))), max(1, int(round(sy * ch * H))))
            for cx, cy, cw, ch in cells]


def constituency_of(bureau_code):
    """The local constituency a bureau belongs to: the code's first 7 digits."""
    code = str(bureau_code or "")
    return code[:7] if len(code) == 11 else None


def parts(bureau_code):
    """The six printed identifiers a bureau code is made of."""
    code = str(bureau_code or "")
    if len(code) != 11:
        return None
    return {"subdivision": code[0:2], "delegation": code[2:4],
            "imada": code[4:6], "constituency": code[6:7],
            "centre": code[7:9], "bureau": code[9:11]}


def index_rows():
    """{bureau_code: row} from `data/pv_index.csv`, for this election only.

    The index carries the only geography the scans come with: the ISIE
    subdivision the folder tree filed the form under, and the Arabic names of
    the constituency and the polling centre. They are folder names rather than
    a gazetteer, but they are what the publisher called these places.
    """
    import csv
    out = {}
    with open(INDEX, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["election"] == ELECTION and row["bureau_code"]:
                out.setdefault(row["bureau_code"], row)
    return out


def cached_files():
    """{bureau_code: [path, ...]} over everything the downloader cached, best first.

    A bureau's bundle is usually one file, but 1,036 of the 8,109 hold several,
    and the extras are not extra pages of the counting record. They are the
    pages of a *قرار تصحيح محضر فرز* — a decision naming a field of the record,
    the value written in error and the value replacing it — filed under the same
    bureau. Sixty bureaux hold nothing else at all.

    They are named for it: the counting record is `<code>__<code>.<ext>` and a
    decision page carries a `-C..` suffix. Plain ASCII order puts the suffixed
    names *first* (both `-` and a space sort below `.`), so taking the first file
    fed a correction decision to the reader for one bureau in eight, and the
    grid of a wholly different form was not found. Ordering the record first
    fixes that here rather than in each of the four callers.
    """
    out = {}
    if not os.path.isdir(CACHE):
        return out
    for name in sorted(os.listdir(CACHE)):
        if "__" not in name or name.endswith(".part"):
            continue
        code = name.split("__", 1)[0]
        out.setdefault(code, []).append(os.path.join(CACHE, name))
    for code, paths in out.items():
        paths.sort(key=lambda p: (0 if _is_record(p, code) else 1, p))
    return out


def _is_record(path, code):
    """Is this file the counting record rather than a decision page?"""
    stem = os.path.splitext(os.path.basename(path))[0]
    return stem.split("__", 1)[-1].strip() == code


# ------------------------------------------------------------------ cell cache

CELLS = f".cache/pv_{ELECTION}_cells"


def cells_path(code):
    return os.path.join(CELLS, f"{code}.npz")


def save_cells(code, fields, crops, detected, degrees, width):
    """Store one form's placed cells and their normalised crops.

    Placement and cropping are the expensive half of reading a form — four
    passes of line detection at 1600 pixels, a registration fit, then a
    confidence-guided nudge — and three later steps need exactly the same
    result: the slate inference, the self-certification loop, and the decode.
    Caching the crops rather than the classifier's output is what makes
    retraining cheap: a new model is then one forward pass over arrays already
    on disk, not another pass over eight thousand scans.
    """
    os.makedirs(CELLS, exist_ok=True)
    names = list(fields)
    counts = np.array([len(fields[n]) for n in names], np.int32)
    stack = (np.concatenate([crops[n] for n in names]) if names
             else np.empty((0, 28, 28), np.uint8))
    np.savez_compressed(cells_path(code), names=np.array(names), counts=counts,
                        crops=stack,
                        meta=np.array([detected, degrees, width], np.int32))


def load_cells(code):
    """({field: (n, 28, 28) crops}, detected, degrees, width), or None."""
    path = cells_path(code)
    if not os.path.exists(path):
        return None
    try:
        d = np.load(path, allow_pickle=False)
    except Exception:
        return None
    names, counts, stack = d["names"], d["counts"], d["crops"]
    out, at = {}, 0
    for name, k in zip(names, counts):
        out[str(name)] = stack[at:at + int(k)]
        at += int(k)
    detected, degrees, width = (int(x) for x in d["meta"])
    return out, detected, degrees, width


def cached_codes():
    """Every bureau code whose cells are cached."""
    if not os.path.isdir(CELLS):
        return []
    return sorted(n[:-4] for n in os.listdir(CELLS) if n.endswith(".npz"))
