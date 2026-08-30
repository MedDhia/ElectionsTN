"""Baseline: how much of a PV can conventional OCR read?

Establishes the contrast for the pilot. Scans are auto-oriented with tesseract's
OSD, then read twice: once for Arabic text (the printed form labels) and once
restricted to digits (the handwritten entries).

Usage: python3 tools/pv_tesseract_baseline.py
"""
import csv, os, re, sys
os.environ.setdefault("OMP_THREAD_LIMIT", "1")

from PIL import Image
import pytesseract

MANIFEST = ".cache/pv_pilot/sample.csv"
OUT = ".cache/pv_pilot/tesseract_baseline.csv"


def auto_orient(img):
    """Rotate by tesseract's detected page orientation; returns (img, degrees)."""
    try:
        osd = pytesseract.image_to_osd(img)
        deg = int(re.search(r"Rotate: (\d+)", osd).group(1))
    except Exception:
        deg = 0
    return (img.rotate(-deg, expand=True) if deg else img), deg


def main():
    with open(MANIFEST, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    out = []
    for r in rows:
        img = Image.open(r["local_path"])
        img, deg = auto_orient(img)
        # Upscale small scans; tesseract wants ~300 dpi equivalent.
        if max(img.size) < 1600:
            f = 1600 / max(img.size)
            img = img.resize((int(img.width * f), int(img.height * f)), Image.LANCZOS)
        arabic = pytesseract.image_to_string(img, lang="ara")
        digits = pytesseract.image_to_string(
            img, lang="eng", config="--psm 11 -c tessedit_char_whitelist=0123456789")
        nums = re.findall(r"\d+", digits)
        out.append({
            "bureau_code": r["bureau_code"],
            "governorate": r["governorate"],
            "size": f"{img.width}x{img.height}",
            "rotation_deg": deg,
            "arabic_chars": len(arabic.strip()),
            "digit_tokens": len(nums),
            "code_found": str(r["bureau_code"] in "".join(nums)).lower(),
            "sample_digits": " ".join(nums[:20]),
        })
        print(f"  {r['bureau_code']}  rot={deg:3d}  ar={len(arabic.strip()):5d}ch  "
              f"digits={len(nums):3d}  code_found={out[-1]['code_found']}", flush=True)

    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    found = sum(1 for r in out if r["code_found"] == "true")
    print(f"\nwrote {len(out)} rows -> {OUT}")
    print(f"  bureau code recovered from image: {found}/{len(out)}")
    print(f"  median arabic chars: {sorted(r['arabic_chars'] for r in out)[len(out)//2]}")
    print(f"  median digit tokens: {sorted(r['digit_tokens'] for r in out)[len(out)//2]}")


if __name__ == "__main__":
    main()
