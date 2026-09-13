"""Find the candidate-representatives table on every presidential PV and record it.

The 2024 counting record ends with a table the rest of this project never read:

    أسماء وإمضاءات ممثلي المترشحين

three rows of `إسم ولقب ممثل المترشح` | `المترشح` | `الإمضاء`. Where a candidate
sent an agent to watch the count at a polling station, that is where it is
written down — so read across 9,448 stations the table is a map of which
campaigns could actually put a body in the room, which is a different question
from where their votes were.

This stage does the part that is mechanical: locate the table (`pv_reps_geom`),
and measure how much pen is in each of its nine cells. It decides nothing about
who a representative was for. What it produces is the geometry every later stage
crops from, and the ink measure that says which cells are worth a reading at all.

Ink is dark pixels that are not red, because the polling-bureau seal is printed
in the same red as the layout and lands across this block on most forms. Counting
it as pen would put a representative in every station that stamped its own record.

Usage: python3 tools/harvest_representatives.py [workers]
"""
import csv, glob, os, sys
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

UPRIGHT = ".cache/pv_upright"
OUT = ".cache/reps_geometry.csv"

FIELDS = ["bureau_code", "width", "height", "status", "rotation", "source", "rules_hit",
          "col_rules", "row_rules", "x0", "y0", "x1", "y1", "c1", "c2",
          "r0", "r1", "r2", "r3"]
for _i in (1, 2, 3):
    for _c in ("name", "cand", "sign"):
        FIELDS += [f"ink{_i}_{_c}", f"cols{_i}_{_c}", f"rows{_i}_{_c}"]


def _one(path):
    import cv2
    from pv_reps_geom import locate_any, cells, ink
    code = os.path.basename(path)[:-4]
    img = cv2.imread(path)
    if img is None:
        return {"bureau_code": code, "status": "unreadable file"}
    h, w = img.shape[:2]
    row = {"bureau_code": code, "width": w, "height": h}
    loc, img, deg, err = locate_any(img)
    if loc is None:
        row["status"] = err
        return row
    row["rotation"] = deg
    if deg:
        h, w = img.shape[:2]
        row["width"], row["height"] = w, h
    x0, y0, x1, y1 = loc["box"]
    row.update(status="located", source=loc["source"], rules_hit=loc["rules_hit"],
               col_rules=loc["col_rules"], row_rules=loc["row_rules"],
               x0=x0, y0=y0, x1=x1, y1=y1, c1=loc["cols"][0], c2=loc["cols"][1],
               **{f"r{i}": loc["rows"][i] for i in range(4)})
    for i, cs in enumerate(cells(img, loc), 1):
        for name, cell in zip(("name", "cand", "sign"), cs):
            m = ink(cell)
            if m:
                row[f"ink{i}_{name}"] = round(m["frac"], 5)
                row[f"cols{i}_{name}"] = round(m["cols"], 4)
                row[f"rows{i}_{name}"] = round(m["rows"], 4)
    return row


def main():
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    files = sorted(glob.glob(os.path.join(UPRIGHT, "*.jpg")))
    print(f"{len(files)} upright forms", flush=True)
    tally = {}
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, FIELDS, extrasaction="ignore")
        wr.writeheader()
        with ProcessPoolExecutor(max_workers=workers) as pool:
            for i, row in enumerate(pool.map(_one, files, chunksize=16), 1):
                wr.writerow(row)
                tally[row["status"]] = tally.get(row["status"], 0) + 1
                if i % 1000 == 0:
                    print(f"  {i}/{len(files)} {tally}", flush=True)
    print("done:", tally)


if __name__ == "__main__":
    main()
