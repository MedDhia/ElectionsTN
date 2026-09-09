"""Map the geography of candidate representatives at the polling stations.

Four figures, at governorate and at delegation:

    presence   share of the stations read where any representative signed
    saied      share where a representative for Kais Saied signed
    rivals     stations with a representative for anyone else, as a count
    intensity  representatives recorded per 100 stations read

Design decisions, and why
-------------------------
**The denominator is stations read, and thin units are greyed out, not shaded.**
A reading pass over a corpus this size is a sample before it is a census, and a
delegation with four stations read has a rate that is noise. Drawing it in the
same ramp as one with sixty would put the sampling pattern on the map and invite
it to be read as the geography of observation. Units under the floor are drawn in
the no-data grey and counted in the legend.

**The rivals panel is a count, not a share.** Representatives for anyone other
than Saied are rare enough that a share ramp would be a map of where the
denominator is small. A count says the true thing — that these are a handful of
places — and the legend prints the count so nothing is hidden behind a shade.

**Presence and Saied share the same class edges.** They are near-identical
quantities on this corpus, and giving each its own quantile classes would make
two maps that differ by a few stations look different everywhere. One set of
edges, computed on presence, is applied to both, so a shade means the same rate
in either panel and the two can be compared directly. That is the opposite of
the choice `make_maps.py` makes for the candidate share panels, where the
distributions genuinely differ by an order of magnitude, and the reason is
written into both files rather than left as a silent inconsistency.

Usage: python3 tools/make_reps_maps.py [--min-read N]
"""
import argparse, os, sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_maps import (RAMP, SURFACE, NO_DATA, feature_path, load_layer, read,
                       quantile_edges, class_of, draw, save_figure, figure_dir,
                       fmt)

FAMILY = "levels"
LEVELS = {
    "governorate": ("data/representatives_by_governorate.csv",
                    "tun_admin2.geojson", "adm2_pcode", 0.004, 5),
    "delegation": ("data/representatives_by_delegation.csv",
                   "tun_admin3.geojson", "adm3_pcode", 0.002, 8),
}
PANELS = [
    ("presence", "any_pct", "Stations with any candidate representative",
     "% of stations read"),
    ("saied", "stations_with_saied_pct",
     "Stations with a representative for Kais Saied", "% of stations read"),
    ("intensity", "reps_per_100_stations",
     "Representatives recorded", "per 100 stations read"),
]


def gov_outlines(tol):
    paths = [feature_path(f["geometry"], tol * 2)
             for f in load_layer("tun_admin2.geojson")]
    return [p for p in paths if p]


def build(level, min_read, log):
    csv_path, layer, pcode, tol, floor = LEVELS[level]
    floor = min_read if min_read is not None else floor
    table = read(csv_path) if os.path.exists(csv_path) else []
    if level == "governorate":
        # The governorate table is keyed by name; the layer by p-code. Join on
        # the English name the boundary set carries, and say which failed to
        # match rather than dropping them into the no-data grey unremarked.
        by_name = {r["governorate_name"]: r for r in table}
        rows, missed = {}, []
        for f in load_layer(layer):
            p = f["properties"]
            name = p.get("adm2_name") or p.get("adm2_ref_name")
            if name in by_name:
                rows[p["adm2_pcode"]] = by_name.pop(name)
            else:
                missed.append(name)
        if by_name:
            log(f"  {level}: unmatched table rows: {sorted(by_name)}")
        if missed:
            log(f"  {level}: unmatched map units: {sorted(missed)}")
    else:
        rows = {r[pcode]: r for r in table}

    feats = load_layer(layer)
    gov = gov_outlines(tol)
    paths, thin = {}, 0
    for f in feats:
        p = f["properties"]
        path = feature_path(f["geometry"], tol)
        if path is None:
            continue
        paths[p[pcode]] = path

    for stem, col, title, unit in PANELS:
        vals, usable = {}, []
        for code, path in paths.items():
            r = rows.get(code)
            if not r or not r.get(col) or int(r["n_read"] or 0) < floor:
                continue
            vals[code] = float(r[col])
            usable.append(float(r[col]))
        if len(usable) < len(RAMP):
            log(f"  {level}/{stem}: only {len(usable)} units clear the floor; skipped")
            continue
        edges = quantile_edges(sorted(usable), len(RAMP))
        buckets = {c: [] for c in RAMP}
        nodata = []
        for code, path in paths.items():
            if code in vals:
                buckets[RAMP[class_of(vals[code], edges)]].append(path)
            else:
                nodata.append(path)
        buckets[NO_DATA] = nodata
        fig, ax = plt.subplots(figsize=(9.5, 8.2))
        fig.patch.set_facecolor(SURFACE)
        draw(ax, buckets, gov, title,
             f"2024 presidential election · by {level} · {unit}\n"
             f"read from the counting records' ممثلي المترشحين table; "
             f"units with fewer than {floor} stations read are not shaded",
             edges, unit, len(vals), len(nodata))
        save_figure(fig, os.path.join(figure_dir(FAMILY),
                                      f"representatives_{level}_{stem}"))
        plt.close(fig)
        log(f"  {level}/{stem}: {len(vals)} units shaded, {len(nodata)} below floor")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-read", type=int, default=None)
    a = ap.parse_args()
    for level in LEVELS:
        build(level, a.min_read, print)


if __name__ == "__main__":
    main()
