"""Regression test: the header-based orientation detector against the pilot set.

Ground truth is the rotation that produced the image actually read and verified
in the pilot (docs/PV_PILOT.md) — every one of those 30 readings passed the
bureau-code check, so the orientation behind them is known correct.

Usage: python3 tools/test_pv_orient.py
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pv_orient import orient

# bureau_code -> degrees the original must be rotated to come out upright.
TRUTH = {
    "01090610101": 90, "01100610203": 270, "02010210103": 270, "02100410201": 270,
    "03030410101": 0, "04010310201": 90, "05020810401": 0, "06120710201": 270,
    "07030410201": 0, "08030810501": 90, "08080510404": 90, "09010810101": 90,
    "10090310107": 0, "12090210104": 0, "13010610202": 90, "13120110101": 90,
    "14030810302": 0, "14030910301": 0, "15051010101": 0, "16060610101": 90,
    "17030510102": 90, "17060710101": 90, "18100510204": 0, "19070110201": 0,
    "20080510302": 0, "21050110201": 0, "22110410201": 90, "23030110202": 0,
    "24040110101": 0, "24051410401": 0,
}
# What tesseract's OSD returned on the same files, for comparison.
OSD = {
    "01090610101": 90, "01100610203": 270, "02010210103": 270, "02100410201": 270,
    "03030410101": 180, "04010310201": 90, "05020810401": 0, "06120710201": 180,
    "07030410201": 0, "08030810501": 90, "08080510404": 0, "09010810101": 90,
    "10090310107": 180, "12090210104": 0, "13010610202": 0, "13120110101": 0,
    "14030810302": 0, "14030910301": 180, "15051010101": 0, "16060610101": 90,
    "17030510102": 90, "17060710101": 90, "18100510204": 270, "19070110201": 0,
    "20080510302": 0, "21050110201": 0, "22110410201": 90, "23030110202": 0,
    "24040110101": 180, "24051410401": 0,
}


def main():
    ok = bad = low_conf = 0
    osd_ok = 0
    t0 = time.time()
    for code, want in sorted(TRUTH.items()):
        path = f".cache/pv_pilot/{code}.jpg"
        if not os.path.exists(path):
            print(f"  missing {path}")
            continue
        _, deg, score = orient(path)
        hit = deg == want
        ok += hit
        bad += not hit
        low_conf += score == 0
        osd_ok += OSD[code] == want
        if not hit or score == 0:
            print(f"  {code} want={want:3d} got={deg:3d} score={score}"
                  f"{'  WRONG' if not hit else '  (low confidence, but correct)'}")
    n = ok + bad
    print(f"\nheader detector: {ok}/{n} correct, {low_conf} below confidence threshold")
    print(f"tesseract OSD:   {osd_ok}/{n} correct")
    print(f"{(time.time()-t0)/max(n,1):.2f}s per image")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
