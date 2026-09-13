"""Colour science shared by the palette checks and the tools they check.

Nothing here is specific to this repository: sRGB to linear light, CIE L*a*b*,
the CIEDE2000 difference, the Vienot-Brettel-Mollon dichromacy simulations, and
WCAG relative luminance and contrast. It lives in its own module because two
tools need it and the import used to run the other way -- `check_dot_palette`
imported the tool it checks, the tool imported the checker for these functions,
and Python refused the circle, correctly.

CIEDE2000 is written out rather than imported: the repo pins matplotlib, numpy,
scipy and scikit-learn, and none of them ships it.
"""

import numpy as np

WHITE = np.array([95.047, 100.0, 108.883])      # D65


# Viénot, Brettel & Mollon (1999), applied to linear RGB.
DICHROMACY = {
    "protanopia": np.array([[0.152286, 1.052583, -0.204868],
                            [0.114503, 0.786281, 0.099216],
                            [-0.003882, -0.048116, 1.051998]]),
    "deuteranopia": np.array([[0.367322, 0.860646, -0.227968],
                              [0.280085, 0.672501, 0.047413],
                              [-0.011820, 0.042940, 0.968881]]),
    "tritanopia": np.array([[1.255528, -0.076749, -0.178779],
                            [-0.078411, 0.930809, 0.147602],
                            [0.004733, 0.691367, 0.303900]]),
}

WHITE = np.array([95.047, 100.0, 108.883])      # D65


def hex_rgb(h):
    return np.array([int(h.lstrip("#")[i:i + 2], 16) / 255.0 for i in (0, 2, 4)])


def to_linear(c):
    c = np.asarray(c, dtype=float)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def to_srgb(c):
    c = np.clip(np.asarray(c, dtype=float), 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


def lab(rgb):
    lin = to_linear(rgb)
    m = np.array([[0.4124, 0.3576, 0.1805],
                  [0.2126, 0.7152, 0.0722],
                  [0.0193, 0.1192, 0.9505]])
    xyz = 100.0 * (m @ lin) / WHITE
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16.0 / 116.0)
    return np.array([116.0 * f[1] - 16.0,
                     500.0 * (f[0] - f[1]),
                     200.0 * (f[1] - f[2])])


def ciede2000(rgb1, rgb2):
    """Perceptual distance. Written out rather than imported: the repo pins
    matplotlib, numpy, scipy and scikit-learn and nothing that ships this."""
    l1, a1, b1 = lab(rgb1)
    l2, a2, b2 = lab(rgb2)
    c1, c2 = np.hypot(a1, b1), np.hypot(a2, b2)
    cbar = 0.5 * (c1 + c2)
    g = 0.5 * (1.0 - np.sqrt(cbar ** 7 / (cbar ** 7 + 25.0 ** 7))) if cbar else 0.5
    a1p, a2p = (1 + g) * a1, (1 + g) * a2
    c1p, c2p = np.hypot(a1p, b1), np.hypot(a2p, b2)
    h1p = np.degrees(np.arctan2(b1, a1p)) % 360.0
    h2p = np.degrees(np.arctan2(b2, a2p)) % 360.0
    dlp = l2 - l1
    dcp = c2p - c1p
    if c1p * c2p == 0:
        dhp = 0.0
    elif abs(h2p - h1p) <= 180:
        dhp = h2p - h1p
    elif h2p - h1p > 180:
        dhp = h2p - h1p - 360.0
    else:
        dhp = h2p - h1p + 360.0
    dHp = 2.0 * np.sqrt(c1p * c2p) * np.sin(np.radians(dhp) / 2.0)
    lbar = 0.5 * (l1 + l2)
    cbarp = 0.5 * (c1p + c2p)
    if c1p * c2p == 0:
        hbarp = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        hbarp = 0.5 * (h1p + h2p)
    elif h1p + h2p < 360:
        hbarp = 0.5 * (h1p + h2p + 360.0)
    else:
        hbarp = 0.5 * (h1p + h2p - 360.0)
    t = (1 - 0.17 * np.cos(np.radians(hbarp - 30))
         + 0.24 * np.cos(np.radians(2 * hbarp))
         + 0.32 * np.cos(np.radians(3 * hbarp + 6))
         - 0.20 * np.cos(np.radians(4 * hbarp - 63)))
    dtheta = 30.0 * np.exp(-(((hbarp - 275.0) / 25.0) ** 2))
    rc = 2.0 * np.sqrt(cbarp ** 7 / (cbarp ** 7 + 25.0 ** 7))
    sl = 1 + (0.015 * (lbar - 50) ** 2) / np.sqrt(20 + (lbar - 50) ** 2)
    sc = 1 + 0.045 * cbarp
    sh = 1 + 0.015 * cbarp * t
    rt = -np.sin(np.radians(2 * dtheta)) * rc
    return float(np.sqrt((dlp / sl) ** 2 + (dcp / sc) ** 2 + (dHp / sh) ** 2
                         + rt * (dcp / sc) * (dHp / sh)))


def simulate(rgb, kind):
    return to_srgb(DICHROMACY[kind] @ to_linear(rgb))


def relative_luminance(rgb):
    lin = to_linear(rgb)
    return float(0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2])


def contrast(rgb1, rgb2):
    a, b = relative_luminance(rgb1), relative_luminance(rgb2)
    lo, hi = min(a, b), max(a, b)
    return (hi + 0.05) / (lo + 0.05)
