"""Assert the surname dot maps' colours survive the reader they were drawn for.

Why this exists
---------------
`tools/check_palette.py` already guards the repo's one documented ramp: seven
blues, lightness strictly monotone, every figure colour a hex from that ramp.
The surname maps break that rule once, deliberately, and this is the price.

The single-surname dot maps do not break it: one quantity, one colour, and that
colour is `#184f95`, the ramp's sixth step. What breaks it are the two overlays
-- `overlay_common_names` and `overlay_concentrated_names` -- where six family
names share one map. Six sequential blues would be unreadable as six categories
-- a sequential ramp orders values, and these are not ordered -- so an overlay
needs a qualitative palette, and a qualitative palette needs hues the blue ramp
does not contain.

The hues are not invented: they are the best six-colour set over five published
qualitative palettes, exhaustively searched. Taking a published palette on trust
is still trust, so this asserts the three properties the overlays depend on:

1. **Separable in pairs.** Every pair of overlay colours differs by at least
   `PAIR_MIN` CIEDE2000 -- under normal vision, and under simulated protanopia,
   deuteranopia and tritanopia. Red-green blindness is not rare (about 8% of
   men), and a dot map that collapses two families into one colour for those
   readers is simply wrong for them.

2. **Visible against the ground.** Every dot colour differs from the land fill
   by at least `GROUND_MIN` CIEDE2000. A 2pt dot has no area to carry a pale
   colour, which is what rules out the pale end of every palette in the pool --
   Okabe-Ito's yellow sits 16.3 from a near-white ground.

3. **The single-surname colour is still ramp-legal.** `DOT` has to be a hex
   from `RAMP`, and dark enough against the land to read at 1.3pt.

Dichromacy is simulated with the Viénot-Brettel-Mollon linear-RGB matrices, the
same ones the common simulators use; the colour maths itself lives in
`tools/colour.py`, which both this and the tools it checks import. They model a dichromat, which is the hard
case; an anomalous trichromat sees something between that and normal vision.

Usage: python3 tools/check_dot_palette.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np

from make_maps import RAMP
from make_surname_dots import DOT, LAND, MESH
from make_surname_leaders import OVERLAY_COLOURS

# Floors, in CIEDE2000. 15 is comfortably above the ~2.3 "just noticeable"
# threshold and above the ~10 at which two marks of different hue start being
# confused at small sizes; 25 against the ground is what a 2pt dot needs to be
# found at all on a page.
PAIR_MIN = 15.0
GROUND_MIN = 25.0
# A dot is small text, near enough: WCAG asks 4.5:1 of body copy.
DOT_CONTRAST_MIN = 4.5

from colour import (DICHROMACY, ciede2000, contrast, hex_rgb,
                    relative_luminance, simulate)

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
