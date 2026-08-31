"""Decide a PV scan's orientation from its printed header.

The pilot found Tesseract's OSD wrong on 7 of 30 scans. OSD guesses page
orientation from glyph shapes across the whole page, and on this form the
printed Arabic is legible enough at every angle to fool it.

This uses Tesseract's actual strength instead. The form has a fixed printed
masthead — "الجمهورية التونسية / الانتخابات الرئاسية لسنة 2024 / محضر عملية الفرز" —
that appears only along the top edge. So: try all four rotations, OCR just the
top strip of each, and keep the one where the masthead words actually show up.
Handwriting is never involved, which is the part Tesseract cannot read.

Usage:
    from pv_orient import orient            # -> (PIL.Image, degrees, score)
    python3 tools/pv_orient.py <glob>       # report orientations for files
"""
import os, re, sys, unicodedata
os.environ.setdefault("OMP_THREAD_LIMIT", "1")

from PIL import Image
import pytesseract

# Masthead words, folded the same way the OCR output is folded below.
HEADER_WORDS = ["الجمهوريه", "التونسيه", "الانتخابات", "الرياسيه", "الرئاسيه",
                "محضر", "عمليه", "الفرز", "لسنه", "2024"]
TASHKEEL = re.compile(r"[ً-ْـٰ]")
STRIP_FRAC = 0.16          # top sixth of the page holds the masthead
MIN_SCORE = 2              # fewer than two masthead hits is not a confident call


def _fold(s):
    s = unicodedata.normalize("NFC", s).translate(str.maketrans("أإآىئؤة", "اااييوه"))
    return TASHKEEL.sub("", s)


def _score_top_strip(img):
    strip = img.crop((0, 0, img.width, max(1, int(img.height * STRIP_FRAC))))
    if strip.width < 900:                     # upscale small scans for OCR
        f = 900 / strip.width
        strip = strip.resize((int(strip.width * f), int(strip.height * f)), Image.LANCZOS)
    text = _fold(pytesseract.image_to_string(strip, lang="ara"))
    return sum(1 for w in HEADER_WORDS if w in text)


def orient(path_or_img):
    """Return (upright_image, degrees_rotated, score). Score 0 means unresolved."""
    img = Image.open(path_or_img) if isinstance(path_or_img, str) else path_or_img
    img = img.convert("RGB")
    best, best_deg, best_score = img, 0, -1
    for deg in (0, 90, 180, 270):
        cand = img if deg == 0 else img.rotate(-deg, expand=True)
        score = _score_top_strip(cand)
        if score > best_score:
            best, best_deg, best_score = cand, deg, score
        if score >= len(HEADER_WORDS) - 3:    # decisive; skip the rest
            break
    return best, best_deg, (best_score if best_score >= MIN_SCORE else 0)


def main():
    import glob
    files = sorted(glob.glob(sys.argv[1]))
    unresolved = 0
    for f in files:
        _, deg, score = orient(f)
        if not score:
            unresolved += 1
        print(f"{os.path.basename(f):34s} rot={deg:3d} score={score}")
    print(f"\n{len(files)} files, {unresolved} unresolved (score < {MIN_SCORE})")


if __name__ == "__main__":
    main()
