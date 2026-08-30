"""How often does grid detection recover the full field set?

A montage is only usable when every printed field was located; otherwise the
caller must fall back to sending the whole page. This measures that rate on a
random sample so the fallback cost is known before a run.

Usage: python3 tools/check_montage_coverage.py [n] [workers]
"""
import glob, os, random, sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def probe(path):
    import cv2
    from pv_grid import find_cells, group_runs
    from pv_fields import map_fields, COLUMNS
    img = cv2.imread(path)
    if img is None:
        return "unreadable", 0
    H, W = img.shape[:2]
    fields = map_fields(group_runs(find_cells(img)), W, H)
    want = sum(len(c[4]) for c in COLUMNS)
    n = len(fields)
    if n == want:
        return "complete", n
    if n >= want - 4:
        return "near-complete", n
    return "partial", n


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    files = sorted(glob.glob(".cache/pv_upright/*.jpg"))
    random.Random(0).shuffle(files)
    files = files[:n]
    tally, counts = Counter(), []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for status, k in pool.map(probe, files, chunksize=4):
            tally[status] += 1
            counts.append(k)
    total = sum(tally.values())
    print(f"sampled {total} forms")
    for k, v in tally.most_common():
        print(f"  {k:14s} {v:5d}  ({100*v/total:.1f}%)")
    counts.sort()
    print(f"  median fields located: {counts[len(counts)//2]} of 20")


if __name__ == "__main__":
    main()
