"""Render every page of a bureau's bundle so the counting record can be found by eye.

The cached page for a bureau is whichever page the chooser liked best, and for a
handful of files it liked the wrong one: a correction decision, the polling
record, or a blank continuation. Those bundles hold several pages, so before
declaring a bureau unreadable it is worth looking at all of them.

Usage: python3 tools/bundle_pages.py CODE [CODE...] [--out DIR] [--width 1500]
"""
import argparse, glob, os

import cv2
import numpy as np

SRC = ".cache/pv_all"
DPI = 200


def pages(path):
    if path.lower().endswith(".pdf"):
        import pypdfium2 as pdfium
        doc = pdfium.PdfDocument(path)
        for i in range(len(doc)):
            im = doc[i].render(scale=DPI / 72).to_pil().convert("RGB")
            yield i, cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR)
    else:
        img = cv2.imread(path)
        if img is not None:
            yield 0, img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("codes", nargs="+")
    ap.add_argument("--out", default=".cache/bundle")
    ap.add_argument("--width", type=int, default=1500)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    for code in a.codes:
        g = glob.glob(os.path.join(SRC, code + "*"))
        if not g:
            print("  no file", code); continue
        for i, img in pages(g[0]):
            f = a.width / img.shape[1]
            im = cv2.resize(img, (a.width, max(1, int(round(img.shape[0] * f)))),
                            interpolation=cv2.INTER_AREA)
            d = os.path.join(a.out, f"{code}_p{i}.png")
            cv2.imwrite(d, im)
            print(d, im.shape[1], "x", im.shape[0])


if __name__ == "__main__":
    main()
