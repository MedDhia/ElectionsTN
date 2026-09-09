"""Order the located tables into a reading plan, and turn the plan into sheets.

Reading 9,448 handwritten cells is done in one pass through contact sheets, and a
pass that long may be interrupted. So the order is not the corpus order: stations
are drawn round-robin across governorates, and within a governorate in a fixed
shuffled order, so that *any prefix of the plan is a stratified sample of the
whole*. Stopping early then costs coverage rather than representativeness, and
what has been read can still be reported without a caveat about which parts of
the country it came from.

Usage:
    python3 tools/reps_reading_plan.py plan      # -> .cache/reps_plan.csv
    python3 tools/reps_reading_plan.py sheets    # -> .cache/reps_sheets/
"""
import csv, os, random, sys
from collections import defaultdict

GEO = ".cache/reps_geometry.csv"
INDEX = "data/pv_index.csv"
PLAN = ".cache/reps_plan.csv"
SHEET_DIR = ".cache/reps_sheets"
SEED = 20241006          # the date on the forms


def geography():
    """bureau_code -> (governorate, delegation, sector, polling centre)."""
    out = {}
    for r in csv.DictReader(open(INDEX, encoding="utf-8")):
        if r["election"] != "presidentielle_2024" or not r["bureau_code"]:
            continue
        out.setdefault(r["bureau_code"], (r["governorate"], r["delegation"],
                                          r["sector"], r["polling_centre"]))
    return out


def build_plan(exclude=()):
    geo = geography()
    rows = [r for r in csv.DictReader(open(GEO, encoding="utf-8"))
            if r["status"] == "located" and r["bureau_code"] not in exclude
            and r["bureau_code"].isdigit()]
    by_gov = defaultdict(list)
    for r in rows:
        g = geo.get(r["bureau_code"], ("?",))[0]
        r["governorate"] = g
        by_gov[g].append(r)
    rnd = random.Random(SEED)
    for g in by_gov:
        rnd.shuffle(by_gov[g])
    order = sorted(by_gov, key=lambda g: -len(by_gov[g]))
    plan, i = [], 0
    while any(by_gov[g] for g in order):
        for g in order:
            if by_gov[g]:
                plan.append(by_gov[g].pop())
    fields = list(rows[0].keys()) + ["sheet"]
    with open(PLAN, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fields)
        w.writeheader()
        for n, r in enumerate(plan):
            r["sheet"] = n // 36
            w.writerow(r)
    print(f"{len(plan)} stations planned over {len(by_gov)} governorates "
          f"-> {PLAN} ({(len(plan) + 35) // 36} sheets)")


def build_sheets():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from reps_sheets import sheets
    rows = list(csv.DictReader(open(PLAN, encoding="utf-8")))
    made = sheets(rows, SHEET_DIR, 36)
    print(f"{len(made)} sheets -> {SHEET_DIR}")


def already_read():
    """Bureau codes whose rows are already transcribed, to keep out of the plan."""
    import json
    path = "data/verification/representatives_readings.jsonl"
    if not os.path.exists(path):
        return set()
    return {json.loads(l)["bureau_code"] for l in open(path, encoding="utf-8")}


if __name__ == "__main__":
    if sys.argv[1] == "plan":
        build_plan(already_read())
    else:
        build_sheets()
