"""Find and repair the cached scans the orientation detector left sideways.

`pv_orient` decides a scan's orientation by OCRing the printed masthead at all
four rotations and keeping the one where the header words appear. It is good, and
it is what `.cache/pv_upright` was built with — but it was run once, before the
corpus was fully cached, and it left pages behind. Re-running it over the cache
finds **81 scans stored at 90 or 270 degrees from upright**, each with a
confident masthead score.

They are findable without OCR at all, which is what makes this cheap: the form is
landscape, so a portrait-shaped file in a cache of upright forms is already
suspect. 197 of 9,449 are portrait, and re-checking just those catches all 81.

**No published value is wrong because of this.** `read_image` has a fourth pass —
"the other three rotations, for scans the orientation detector called wrong" —
so the decoder rotated them itself and read them correctly; all 81 rows carry
certified votes and 64 read whole. The arithmetic proves it: a sideways read
produces digits that would not close three identities.

What the sideways cache breaks is everything that crops by **page fraction**
rather than by located geometry — which is every review sheet in this repo, and
`tools/zoom.py`. Those tools hand a human a rotated page and ask them to read a
box that is not where the fraction says. Two consequences turned up before the
cause did:

- The ballot-account sheets yielded nothing for these stations, and the gap got
  written down as a scan-quality floor. It was not: it was an orientation floor,
  and rendering one of them at 270 degrees recovered a whole ballot account
  (13120810101).
- `spotcheck_sheet.py` would show an auditor a sideways form. That is the same
  shape of bug as showing them a superseded document: the sheet asks a person to
  verify a number against something they cannot read, and any mismatch they
  report is the tool's fault.

So the cache is repaired in place. `.cache` is a build artifact and not in the
repository, which is exactly why this has to be a tool rather than a one-off
command: the next person to build the cache gets the same 81 pages sideways.

Usage: python3 tools/fix_orientation.py [--write] [--workers 4]
"""
import argparse, collections, glob, json, os, sys
from concurrent.futures import ProcessPoolExecutor

import cv2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

UPRIGHT = ".cache/pv_upright"
LOG = "data/verification/orientation_repairs.jsonl"
MIN_SCORE = 2          # pv_orient's own threshold for a confident call
JPEG_QUALITY = 92


def portrait(path):
    """True when the cached file is taller than wide. The form is landscape."""
    im = cv2.imread(path, cv2.IMREAD_REDUCED_COLOR_8)
    return im is not None and im.shape[1] / im.shape[0] < 1.0


def _check(path):
    try:
        from pv_orient import orient
        _, deg, score = orient(path)
        return path, deg, score
    except Exception:
        return path, None, -1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default=UPRIGHT)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    files = sorted(glob.glob(os.path.join(a.cache, "*.jpg")))
    if not files:
        sys.exit(f"no scans in {a.cache}")
    suspect = [p for p in files if portrait(p)]
    print(f"{len(files):,} cached scans, {len(suspect)} portrait-shaped\n"
          f"re-checking the masthead on those {len(suspect)}", flush=True)

    results = []
    with ProcessPoolExecutor(a.workers) as ex:
        for i, out in enumerate(ex.map(_check, suspect, chunksize=4), 1):
            results.append(out)
            if i % 50 == 0:
                print(f"  {i}/{len(suspect)}", flush=True)

    tally = collections.Counter()
    wrong = []
    for path, deg, score in results:
        confident = isinstance(score, int) and score >= MIN_SCORE
        tally[(deg, confident)] += 1
        if confident and deg in (90, 270):
            wrong.append((path, deg, score))

    print("\nmasthead verdict on the portrait scans")
    for (deg, confident), n in sorted(tally.items(), key=lambda kv: str(kv[0])):
        print(f"   rotate {deg}   confident={confident}   {n}")
    print(f"\n{len(wrong)} scans are stored sideways and can be repaired")
    print(f"{len(suspect) - len(wrong)} portrait scans the masthead cannot "
          "resolve — those are a genuine scan-quality floor")

    if not a.write:
        print("\ndry run, cache untouched")
        return

    from pv_orient import orient
    notes = []
    for path, deg, score in wrong:
        code = os.path.basename(path)[:-4]
        img, got, sc = orient(path)
        if got != deg:
            print(f"  {code}: verdict moved between passes ({deg} -> {got})"
                  ", skipped")
            continue
        before = cv2.imread(path)
        img.save(path, quality=JPEG_QUALITY)
        after = cv2.imread(path)
        if after is None or after.shape[0] != before.shape[1]:
            sys.exit(f"{code}: rewrite did not transpose the page — stopping")
        notes.append({"bureau_code": code, "rotated_degrees": deg,
                      "masthead_score": sc,
                      "was": f"{before.shape[1]}x{before.shape[0]}",
                      "now": f"{after.shape[1]}x{after.shape[0]}"})
        print(f"  {code}: rotated {deg} degrees   "
              f"{before.shape[1]}x{before.shape[0]} -> "
              f"{after.shape[1]}x{after.shape[0]}")

    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "w", encoding="utf-8") as fh:
        for n in notes:
            fh.write(json.dumps(n, ensure_ascii=False) + "\n")
    print(f"\n{len(notes)} scans repaired in {a.cache}\n-> {LOG}")


if __name__ == "__main__":
    main()
