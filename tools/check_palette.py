"""Assert the continuous percentage ramp is a legitimate sequential scale.

Why this exists
---------------
The palette instance documents a blue ramp as seven hexes, steps 100-700, and
its rule is that every colour used is one of those hexes rather than an
eyeballed value. The percentage figures now read a *continuous* ramp
interpolated between those seven stops, which produces colours that are not
themselves in the instance file. That is a relaxation of the rule and it needs a
justification stronger than "it looks fine".

The property that made the seven steps a sequential ramp is that lightness falls
strictly and evenly: L* from 90.5 down to 33.8 in steps of 9.3-9.5. A sequential
scale is readable exactly because lightness is monotone in the value, so a
reader can order two shades without a legend. This asserts the interpolation
preserves that -- across all 256 sampled entries, not just at the seven stops --
and that the endpoints are unchanged, so the ramp still spans the documented
range and invents no hue.

Interpolation in sRGB does not guarantee monotone L*: it is a straight line in
the wrong space, and a ramp whose stops wander in hue can dip. This checks
rather than assumes.

Usage: python3 tools/check_palette.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np

from make_maps import CMAP, RAMP


def _linear(c):
    """sRGB channel to linear light."""
    c = np.asarray(c, dtype=float)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def lstar(rgb):
    """CIE L* (0-100) for an sRGB triple in 0-1, D65 white."""
    r, g, b = _linear(rgb[0]), _linear(rgb[1]), _linear(rgb[2])
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return float(116.0 * (y ** (1.0 / 3.0)) - 16.0 if y > 0.008856
                 else 903.3 * y)


def main():
    fail, passed = [], [0]

    def check(ok, msg):
        if ok:
            passed[0] += 1
        else:
            fail.append(msg)
            print(f"  FAIL  {msg}")

    # ---- the seven documented steps, unchanged
    stops = [lstar(tuple(int(h[i:i + 2], 16) / 255.0 for i in (1, 3, 5)))
             for h in RAMP]
    print("documented steps, L*:", "  ".join(f"{v:.1f}" for v in stops))
    drops = [stops[i] - stops[i + 1] for i in range(len(stops) - 1)]
    check(all(d > 0 for d in drops),
          f"the documented ramp is not monotone in L*: drops {drops}")
    check(min(drops) > 0.5 * max(drops),
          f"the documented ramp's steps are uneven: {min(drops):.1f} to "
          f"{max(drops):.1f}")

    # ---- the interpolation, sampled across the whole bar
    xs = np.linspace(0.0, 1.0, 256)
    ls = [lstar(CMAP(x)[:3]) for x in xs]
    diffs = np.diff(ls)
    check(bool((diffs < 0).all()),
          f"the interpolated ramp is not strictly monotone in L*: "
          f"{int((diffs >= 0).sum())} of {len(diffs)} samples do not darken "
          f"(worst {diffs.max():+.4f})")
    print(f"interpolated: L* {ls[0]:.1f} -> {ls[-1]:.1f} over {len(ls)} samples, "
          f"steepest {-diffs.min():.3f}, flattest {-diffs.max():.3f}")

    # ---- endpoints are the documented ones, so the ramp spans no further
    check(abs(ls[0] - stops[0]) < 0.05,
          f"the pale end moved: {ls[0]:.2f} against the documented {stops[0]:.2f}")
    check(abs(ls[-1] - stops[-1]) < 0.05,
          f"the dark end moved: {ls[-1]:.2f} against the documented "
          f"{stops[-1]:.2f}")
    check(min(ls) >= stops[-1] - 0.05 and max(ls) <= stops[0] + 0.05,
          "the interpolation leaves the documented lightness range")

    # ---- no hue invented: every sample sits between the ramp's own extremes on
    # each channel, which is what interpolating within one hue guarantees
    lo = np.array([min(int(h[i:i + 2], 16) for h in RAMP) for i in (1, 3, 5)])
    hi = np.array([max(int(h[i:i + 2], 16) for h in RAMP) for i in (1, 3, 5)])
    sampled = np.array([[round(c * 255) for c in CMAP(x)[:3]] for x in xs])
    check(bool((sampled >= lo - 1).all() and (sampled <= hi + 1).all()),
          "an interpolated colour falls outside the documented ramp's own "
          "per-channel range")

    # ---- the mapping callers actually use
    from make_maps import PCT_VMAX, PCT_VMIN, pct_colour, pct_is_dark
    check(pct_colour(PCT_VMIN).lower() == RAMP[0].lower(),
          f"0% is {pct_colour(PCT_VMIN)}, not the ramp's pale end {RAMP[0]}")
    check(pct_colour(PCT_VMAX).lower() == RAMP[-1].lower(),
          f"100% is {pct_colour(PCT_VMAX)}, not the ramp's dark end {RAMP[-1]}")
    # Out-of-range values clamp rather than wrapping or raising: a smoothed
    # surface can overshoot its inputs by a rounding step, and a figure must not
    # paint such a cell with the opposite end of the ramp.
    check(pct_colour(-5.0) == pct_colour(PCT_VMIN)
          and pct_colour(140.0) == pct_colour(PCT_VMAX),
          "values outside 0-100 do not clamp to the ramp's ends")
    seq = [lstar(tuple(int(pct_colour(v)[i:i + 2], 16) / 255.0
                       for i in (1, 3, 5)))
           for v in np.linspace(PCT_VMIN, PCT_VMAX, 101)]
    check(all(seq[i] > seq[i + 1] for i in range(len(seq) - 1)),
          "pct_colour is not monotone in lightness across 0-100")
    # The label-ink cut must sit where the fill is genuinely dark, or the
    # numbers printed on the levels maps become unreadable at one end.
    check(not pct_is_dark(0.0) and pct_is_dark(100.0),
          "pct_is_dark does not separate the ends of the ramp")
    flip = [v for v in range(101) if pct_is_dark(float(v))]
    check(flip and flip == list(range(flip[0], 101)),
          f"pct_is_dark is not monotone: it flips at {flip[:3]}")
    print(f"  pct_colour: L* {seq[0]:.1f} -> {seq[-1]:.1f}; label ink turns "
          f"pale at {flip[0]}%")

    print(f"{len(fail) + passed[0]} checks run")
    if fail:
        print(f"\n{len(fail)} check(s) failed")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
