"""Assert the surname dot maps' colours survive the reader they were drawn for.

Why this exists
---------------
`tools/check_palette.py` already guards the repo's one documented ramp: seven
blues, lightness strictly monotone, every figure colour a hex from that ramp.
The surname maps break that rule once, deliberately, and this is the price.

The single-surname dot maps do not break it: one quantity, one colour, and that
colour is `#184f95`, the ramp's sixth step. What breaks it is
`maps/surnames/overlay_four_names`, where four family names share one map. Four
sequential blues would be unreadable as four categories -- a sequential ramp
orders values, and these are not ordered -- so the overlay needs a qualitative
palette, and a qualitative palette needs hues the blue ramp does not contain.

The hues are not invented. They are four of the eight Okabe-Ito colours, a
palette published for exactly this purpose and already tested against the three
dichromacies. Taking a published palette on trust is still trust, and it did not
survive the test: six of those eight on one map fall to 12.2 CIEDE2000 under
simulated protanopia, which is why the overlay carries four names rather than
six. This asserts the three properties the overlay depends on:

1. **Separable in pairs.** Every pair of overlay colours differs by at least
   `PAIR_MIN` CIEDE2000 -- under normal vision, and under simulated protanopia,
   deuteranopia and tritanopia. Red-green blindness is not rare (about 8% of
   men), and a dot map that collapses two families into one colour for those
   readers is simply wrong for them.

2. **Visible against the ground.** Every dot colour differs from the land fill
   by at least `GROUND_MIN` CIEDE2000. A 2pt dot has no area to carry a pale
   colour, which is why the palette's own yellow -- 16.3 from a near-white
   ground -- is not among the four used.

3. **The single-surname colour is still ramp-legal.** `DOT` has to be a hex
   from `RAMP`, and dark enough against the land to read at 1.3pt.

Dichromacy is simulated with the Viénot-Brettel-Mollon linear-RGB matrices, the
same ones the common simulators use. They model a dichromat, which is the hard
case; an anomalous trichromat sees something between that and normal vision.

Usage: python3 tools/check_dot_palette.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np

from make_maps import RAMP
from make_surname_dots import DOT, LAND, MESH, OVERLAY_COLOURS

# Floors, in CIEDE2000. 15 is comfortably above the ~2.3 "just noticeable"
# threshold and above the ~10 at which two marks of different hue start being
# confused at small sizes; 25 against the ground is what a 2pt dot needs to be
# found at all on a page.
PAIR_MIN = 15.0
GROUND_MIN = 25.0
# A dot is small text, near enough: WCAG asks 4.5:1 of body copy.
DOT_CONTRAST_MIN = 4.5

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


def main():
    fails, passed = [], [0]

    def check(ok, msg):
        if ok:
            passed[0] += 1
        else:
            fails.append(msg)
            print(f"  FAIL  {msg}")

    cols = [hex_rgb(h) for h in OVERLAY_COLOURS]
    land = hex_rgb(LAND)
    dot = hex_rgb(DOT)

    # ---- 1. the overlay hues stay apart, for every reader
    print("overlay palette, minimum CIEDE2000 between any two of its colours:")
    for kind in ("normal vision",) + tuple(DICHROMACY):
        seen = (cols if kind == "normal vision"
                else [simulate(c, kind) for c in cols])
        worst, pair = 1e9, None
        for i in range(len(seen)):
            for j in range(i + 1, len(seen)):
                d = ciede2000(seen[i], seen[j])
                if d < worst:
                    worst, pair = d, (OVERLAY_COLOURS[i], OVERLAY_COLOURS[j])
        print(f"  {kind:<14} {worst:6.1f}   closest pair {pair[0]} / {pair[1]}")
        check(worst >= PAIR_MIN,
              f"under {kind} two overlay colours are {worst:.1f} apart, "
              f"below the {PAIR_MIN} floor: {pair[0]} and {pair[1]}")

    # ---- 2. every dot colour is findable on the land
    print(f"\nagainst the land fill {LAND}:")
    for h, c in zip(OVERLAY_COLOURS, cols):
        d = ciede2000(c, land)
        worst_cvd = min(ciede2000(simulate(c, k), simulate(land, k))
                        for k in DICHROMACY)
        print(f"  {h}  ΔE {d:5.1f}   worst under dichromacy {worst_cvd:5.1f}")
        check(min(d, worst_cvd) >= GROUND_MIN,
              f"{h} is only {min(d, worst_cvd):.1f} from the land fill, "
              f"below the {GROUND_MIN} floor")

    # ---- 3. the single-surname colour is still a ramp hex, and dark enough
    print(f"\nsingle-surname dot {DOT}:")
    check(DOT in RAMP, f"the dot colour {DOT} is not one of the documented "
                       f"ramp steps {RAMP}")
    ratio = contrast(dot, land)
    print(f"  contrast against the land {ratio:.2f}:1")
    check(ratio >= DOT_CONTRAST_MIN,
          f"the dot colour reaches only {ratio:.2f}:1 against the land, "
          f"below {DOT_CONTRAST_MIN}:1")
    mesh_ratio = contrast(dot, hex_rgb(MESH))
    print(f"  contrast against the imada mesh {mesh_ratio:.2f}:1")
    check(mesh_ratio >= 1.8,
          f"the dot colour is {mesh_ratio:.2f}:1 against the mesh lines, "
          f"which is too close to read a dot from a boundary")

    print(f"\n{passed[0]} checks passed, {len(fails)} failed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
