"""Enlarge an arbitrary fractional box of an upright PV scan.

The whole-page sheets put every remaining form in front of the eye, but on a
low-resolution scan the candidate block arrives too small to read. This crops a
box given in page fractions and scales it up on its own, so a blurred row gets
the full width of the render rather than a fifth of it.

Fractions, not pixels, because the pages differ in size; and no geometry,
because these are exactly the forms whose geometry could not be found.

Usage: python3 tools/zoom.py CODE [CODE...] [--box x0 y0 x1 y1] [--width 2400]
"""
import argparse, os

import cv2
import numpy as np

UPRIGHT = ".cache/pv_upright"
OUT = ".cache/zoom"


def crop(img, box):
    h, w = img.shape[:2]
    x0, y0, x1, y1 = box
    return img[int(h * y0):int(h * y1), int(w * x0):int(w * x1)]


def sharpen(im):
    """Pull the ink off the pink form on a scan of a few hundred pixels.

    The published scan for some bureaux is 470x650 for the whole page, so the
    candidate digits are a dozen pixels tall and interpolation alone gives a
    smooth blur. Dropping the printed pink to white and stretching what is left
    puts the strokes back within reach of the eye; it invents nothing, it only
    stops the background competing with the writing.
    """
    g = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    g = cv2.normalize(g, None, 0, 255, cv2.NORM_MINMAX)
    b, _, r = cv2.split(im.astype("int16"))
    ink = np.clip(255 - (r - b) * 2, 0, 255).astype("uint8")   # pink rules -> white
    g = cv2.max(g, 255 - ink)
    g = cv2.normalize(g, None, 0, 255, cv2.NORM_MINMAX)
    return cv2.cvtColor(g, cv2.COLOR_GRAY2BGR)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("codes", nargs="+")
    ap.add_argument("--box", nargs=4, type=float, default=[0.0, 0.40, 0.68, 0.82],
                    help="x0 y0 x1 y1 as fractions of the page; the default covers "
                         "the ballots column, the candidate rows and the declared "
                         "total in one crop, which is what settles a form")
    ap.add_argument("--width", type=int, default=1560)
    ap.add_argument("--sharp", action="store_true",
                    help="grey, contrast-stretch and unsharp-mask before scaling")
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--flip", action="store_true",
                    help="mirror the page left-to-right; a few scans were fed "
                         "through back-to-front and read as mirror writing")
    ap.add_argument("--rot", type=int, default=0, choices=[0, 90, 180, 270],
                    help="turn the page this many degrees clockwise before "
                         "cropping; a handful of scans reach the upright cache "
                         "still on their side")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    for code in a.codes:
        p = os.path.join(UPRIGHT, f"{code}.jpg")
        img = cv2.imread(p) if os.path.exists(p) else None
        if img is None:
            print("  no image", code); continue
        if a.rot:
            img = cv2.rotate(img, {90: cv2.ROTATE_90_CLOCKWISE,
                                   180: cv2.ROTATE_180,
                                   270: cv2.ROTATE_90_COUNTERCLOCKWISE}[a.rot])
        if a.flip:
            img = cv2.flip(img, 1)   # after the turn, so --rot and --flip compose
        im = crop(img, a.box)
        if im.size == 0:
            print("  empty box", code); continue
        if a.sharp:
            im = sharpen(im)
        f = a.width / im.shape[1]
        im = cv2.resize(im, (a.width, max(1, int(round(im.shape[0] * f)))),
                        interpolation=cv2.INTER_CUBIC)
        if a.sharp:
            im = cv2.addWeighted(im, 1.6, cv2.GaussianBlur(im, (0, 0), 3), -0.6, 0)
        d = os.path.join(a.out, f"{code}.png")
        cv2.imwrite(d, im)
        print(d, im.shape[1], "x", im.shape[0])


if __name__ == "__main__":
    main()
