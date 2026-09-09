"""Join the representatives readings to the geography and publish the dataset.

One row per polling station in the 2024 presidential election, carrying what the
counting record's `أسماء وإمضاءات ممثلي المترشحين` table says: how many candidate
representatives signed for that station, and which candidates they acted for.

Three things are kept apart, because they are different states and collapsing
them would overstate what is known:

- **read**: the table was located on the scan and its three rows were read.
- **located, unread**: the table was found but its rows have not been read yet.
- **not located**: no table was recovered from this station's scan at all.

A station in the second or third state is not a station with no representatives,
and `n_representatives` is left empty there rather than set to zero. Every rate
this dataset supports is therefore a rate over `reading == "read"`, and the
codebook says so.

Usage: python3 tools/build_representatives.py
"""
import csv, json, os, sys

GEOM = ".cache/reps_geometry.csv"
READINGS = "data/verification/representatives_readings.jsonl"
MARGINS = "data/station_margins.csv"
INDEX = "data/pv_index.csv"
OUT = "data/pv_representatives_2024.csv"

CANDIDATES = ("saied", "zammel", "maghzaoui")
FIELDS = (["bureau_code", "governorate_ar", "delegation_ar", "sector_ar",
           "polling_centre_ar", "governorate_name", "delegation_name",
           "imada_name", "adm3_pcode", "adm4_pcode", "reading", "rows",
           "n_representatives"]
          + [f"rep_{c}" for c in CANDIDATES]
          + ["unattributed", "table_source", "rotation", "registered", "voters",
             "valid", "turnout_pct", "saied_share_pct", "winner"])


def main():
    margins = {r["bureau_code"]: r for r in csv.DictReader(
        open(MARGINS, encoding="utf-8"))}
    index = {}
    for r in csv.DictReader(open(INDEX, encoding="utf-8")):
        if r["election"] == "presidentielle_2024" and r["bureau_code"]:
            index.setdefault(r["bureau_code"], r)
    geom = {r["bureau_code"]: r for r in csv.DictReader(
        open(GEOM, encoding="utf-8"))} if os.path.exists(GEOM) else {}
    readings = {}
    if os.path.exists(READINGS):
        for line in open(READINGS, encoding="utf-8"):
            d = json.loads(line)
            readings[d["bureau_code"]] = d

    codes = sorted(set(margins) | set(index))
    tally = {"read": 0, "located": 0, "not located": 0, "no scan": 0}
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, FIELDS)
        w.writeheader()
        for code in codes:
            m, ix, g = margins.get(code, {}), index.get(code, {}), geom.get(code, {})
            d = readings.get(code)
            if d:
                state = "read"
            elif g.get("status") == "located":
                state = "located"
            elif g:
                state = "not located"
            else:
                state = "no scan"
            tally[state] += 1
            row = {
                "bureau_code": code,
                "governorate_ar": ix.get("governorate", ""),
                "delegation_ar": ix.get("delegation", ""),
                "sector_ar": ix.get("sector", ""),
                "polling_centre_ar": ix.get("polling_centre", ""),
                "governorate_name": m.get("governorate_name", ""),
                "delegation_name": m.get("delegation_name", ""),
                "imada_name": m.get("imada_name", ""),
                "adm3_pcode": m.get("adm3_pcode", ""),
                "adm4_pcode": m.get("adm4_pcode", ""),
                "reading": state,
                "table_source": g.get("source", ""),
                "rotation": g.get("rotation", ""),
                "registered": m.get("registered", ""),
                "voters": m.get("voters", ""),
                "valid": m.get("valid", ""),
                "turnout_pct": m.get("turnout_pct", ""),
                "saied_share_pct": m.get("saied_share_pct", ""),
                "winner": m.get("winner", ""),
            }
            if d:
                row["rows"] = "".join(d["rows"])
                row["n_representatives"] = d["n_representatives"]
                row["unattributed"] = d["unattributed"]
                for c in CANDIDATES:
                    row[f"rep_{c}"] = d["candidates"].count(c)
            w.writerow(row)
    print(f"{len(codes)} stations -> {OUT}")
    print("  " + ", ".join(f"{k}: {v}" for k, v in tally.items()))


if __name__ == "__main__":
    main()
