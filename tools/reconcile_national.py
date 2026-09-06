"""Reconcile this dataset against ISIE's published national figures.

The dataset has been compared against ISIE's headline — Saied 90.69% — for as
long as it has existed, and the residual gap has been carried as an open
question. The comparison was wrong, in a way worth writing down rather than
quietly fixing.

**ISIE's headline is national. This dataset is in-country.** The archive holds
9,448 procès-verbaux and every one of them is in a Tunisian governorate; the 24
in the dataset are the 24 that exist. The 331 out-of-country polling stations in
58 countries are not in it. Saied took **77.99%** abroad against 91-odd at home,
so including a diaspora the dataset does not cover drags the comparison figure
down by about four tenths of a point — which is very close to the whole gap that
was being treated as unexplained reading error.

Subtracting the published diaspora totals from the published national ones gives
the number this dataset should actually be compared against. It agrees to **five
hundredths of a percentage point**.

The second reconciliation is coverage. ISIE ran **9,669** polling stations inside
Tunisia and published **9,448** procès-verbaux, so 221 stations are absent from
the archive before any reading begins; 31 more are published but unreadable. The
votes missing from this dataset, divided by those 252 stations, come to a
per-station average close to the dataset's own — which is what it should be if
the shortfall is simply the stations that are not there, and not a systematic
under-reading.

Figures are ISIE's as reported; sources are listed in docs/DATASETS.md.

Usage: python3 tools/reconcile_national.py
"""
import csv

RESULTS = "data/pv_presidential_2024.csv"
CAND = ("zammel", "maghzaoui", "saied")

# ISIE published totals, national (including the out-of-country constituencies).
NATIONAL = {"saied": 2438954, "zammel": 197551, "maghzaoui": 52903,
            "valid": 2689408, "registered": 9753217, "turnout_pct": 28.80}
# ISIE published totals for the out-of-country constituencies alone.
DIASPORA = {"saied": 76707, "zammel": 17385, "maghzaoui": 4264}
# Polling stations ISIE operated inside Tunisia, against 9,448 PVs published.
STATIONS_IN_COUNTRY = 9669


def main():
    rows = list(csv.DictReader(open(RESULTS, encoding="utf-8")))
    certified = [r for r in rows if r["votes_certified"] == "1"]
    ours = {c: sum(int(r[c]) for r in certified) for c in CAND}
    ours["valid"] = sum(ours[c] for c in CAND)

    dia_valid = sum(DIASPORA.values())
    isie = {c: NATIONAL[c] - DIASPORA[c] for c in CAND}
    isie["valid"] = NATIONAL["valid"] - dia_valid

    print("ISIE as published, national (includes 331 out-of-country stations)")
    for c in CAND:
        print(f"  {c:10s} {NATIONAL[c]:>10,}  {100*NATIONAL[c]/NATIONAL['valid']:6.2f}%")
    print(f"  {'valid':10s} {NATIONAL['valid']:>10,}\n")

    print("ISIE's out-of-country constituencies alone")
    for c in CAND:
        print(f"  {c:10s} {DIASPORA[c]:>10,}  {100*DIASPORA[c]/dia_valid:6.2f}%")
    print(f"  {'valid':10s} {dia_valid:>10,}\n")

    print("ISIE in-country = national minus diaspora — what this dataset covers")
    for c in CAND:
        print(f"  {c:10s} {isie[c]:>10,}  {100*isie[c]/isie['valid']:6.2f}%")
    print(f"  {'valid':10s} {isie['valid']:>10,}\n")

    print(f"this dataset, {len(certified):,} certified stations of {len(rows):,}")
    for c in CAND:
        print(f"  {c:10s} {ours[c]:>10,}  {100*ours[c]/ours['valid']:6.2f}%")
    print(f"  {'valid':10s} {ours['valid']:>10,}\n")

    print("difference in share, this dataset against ISIE in-country")
    for c in CAND:
        d = 100 * ours[c] / ours["valid"] - 100 * isie[c] / isie["valid"]
        print(f"  {c:10s} {d:+.2f} points")
    d_nat = (100 * ours["saied"] / ours["valid"]
             - 100 * NATIONAL["saied"] / NATIONAL["valid"])
    print(f"\n  against the NATIONAL headline instead: saied {d_nat:+.2f} points"
          "  <- the comparison that was being made")

    missing_votes = isie["valid"] - ours["valid"]
    missing_stations = STATIONS_IN_COUNTRY - len(certified)
    unpublished = STATIONS_IN_COUNTRY - len(rows)
    print(f"\ncoverage")
    print(f"  {STATIONS_IN_COUNTRY:,} polling stations ISIE ran inside Tunisia")
    print(f"  {len(rows):,} procès-verbaux published in the archive "
          f"({unpublished} stations never published)")
    print(f"  {len(certified):,} of those certified here "
          f"({len(rows) - len(certified)} published but unreadable)")
    print(f"  {missing_votes:,} valid votes not in this dataset, over "
          f"{missing_stations} stations = {missing_votes/missing_stations:.0f} each")
    print(f"  against a mean of {ours['valid']/len(certified):.0f} per station "
          "covered — the shortfall is the stations that are absent, not a\n"
          "  systematic under-reading of the ones that are present")


if __name__ == "__main__":
    main()
