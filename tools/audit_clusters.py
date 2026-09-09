"""Standing check over the spatial cluster tables.

Reads only published files and exits non-zero on a violation, like the four
audits already in the repo. Four of its checks are worth naming, because they
test the things that could go wrong silently.

**Each electoral region is contiguous.** That is the whole claim of the
regionalisation -- Ward was run under a connectivity constraint precisely so no
region is a scatter of disconnected pieces -- and it is checkable directly
against the same queen graph the figures used. A broken connectivity matrix
would still produce a plausible-looking map with sensible cluster means; only
walking the graph catches it.

**LISA and Gi\\* must select the same units.** Under conditional permutation both
statistics hold unit i's own value fixed, so both reduce to asking whether its
neighbourhood mean is extreme, and their p-values agree to within one
permutation. That makes an exact agreement of the two significant sets a real
check on the permutation machinery rather than a restatement: if the neighbour
gathering, the skip-self remap or the FDR step broke in one path and not the
other, the sets would diverge.

**The quadrant labels must agree with the arithmetic.** `HH` means the unit is
above the mean *and* its neighbours are; that is recomputable from the published
share and the graph, so a mislabelled quadrant -- an inverted sign, a stale
array -- cannot hide.

**Significance must survive its own correction.** The FDR-significant count can
never exceed the raw p <= 0.05 count, and every p must lie in
[1/(perms+1), 1]: a p of 0 would mean the observed value was excluded from its
own reference distribution, which is the classic off-by-one in permutation code.
"""

import argparse
import collections
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DELEG = "data/delegation_clusters.csv"
IMADA = "data/imada_clusters.csv"
DELEG_MARGINS = "data/delegation_margins.csv"
IMADA_MARGINS = "data/imada_margins.csv"
VERIFY = "data/verification/clusters.jsonl"

LEVELS = [
    ("delegation", DELEG, DELEG_MARGINS, "adm3_pcode", "tun_admin3.geojson", 264),
    ("imada", IMADA, IMADA_MARGINS, "adm4_pcode", "tun_admin4.geojson", 2042),
]
CANDIDATES = ("saied", "zammel", "maghzaoui")
CLASSES = {"HH", "LL", "HL", "LH", "ns"}
PERMS = 9999
K_REGIONS = 6


def read(p):
    with open(p, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    for p in (DELEG, IMADA, DELEG_MARGINS, IMADA_MARGINS, VERIFY):
        if not os.path.exists(p):
            sys.exit(f"missing {p}; run tools/make_clusters.py")

    import numpy as np
    import spatial_weights as sw
    from make_maps import ARCHIVE, load_layer

    if not os.path.exists(ARCHIVE):
        sys.exit(f"missing {ARCHIVE}; run tools/fetch_boundaries.py")

    fail = []
    passed = [0]

    # Messages state the failure condition, so echoing them on success would
    # read backwards. Successes are counted; only failures print.
    def check(ok, msg):
        if ok:
            passed[0] += 1
        else:
            fail.append(msg)
            print(f"  FAIL  {msg}")

    records = [json.loads(line) for line in open(VERIFY, encoding="utf-8")]

    for level, path, margins_path, pcode, layer, want_rows in LEVELS:
        rows = read(path)
        margins = {r[pcode]: r for r in read(margins_path)}
        check(len(rows) == want_rows,
              f"{path} has {len(rows)} rows, expected {want_rows}")
        codes = [r["pcode"] for r in rows]
        check(len(set(codes)) == len(codes), f"{path} repeats a pcode")
        missing = set(codes) - set(margins)
        check(not missing,
              f"{path} has {len(missing)} pcode(s) absent from {margins_path}")

        # ---- the graph the figures used, rebuilt from the boundaries
        feats = load_layer(layer)
        names = [f["properties"][pcode.replace("_pcode", "_name")]
                 for f in feats]
        adj_all = sw.queen_adjacency(feats)
        keep = [i for i, f in enumerate(feats)
                if f["properties"][pcode] in margins]
        adj, _ = sw.subset(adj_all, keep)
        xy = sw.centroids_km(
            [float(feats[i]["properties"]["center_lat"]) for i in keep],
            [float(feats[i]["properties"]["center_lon"]) for i in keep])
        bridges = sw.bridge_components(adj, xy, [names[i] for i in keep])
        order = {feats[i]["properties"][pcode]: n for n, i in enumerate(keep)}
        check(len(sw.components(adj)) == 1,
              f"{level}: the weights graph is not connected")

        pos = {c: i for i, c in enumerate(codes)}
        check(set(order) == set(pos),
              f"{level}: the published rows and the rebuilt graph cover "
              f"different units")
        if set(order) != set(pos):
            continue
        # published order must match the graph's, or every index below is wrong
        check(all(order[c] == pos[c] for c in codes),
              f"{level}: {path} is not in the graph's unit order")

        # ---- no unit may be left without a neighbourhood
        for r in rows:
            i = order[r["pcode"]]
            check(int(r["n_neighbours"]) == len(adj[i]),
                  f"{level}/{r['name']}: n_neighbours={r['n_neighbours']} but "
                  f"the graph gives {len(adj[i])}")
            if int(r["n_neighbours"]) < 1:
                check(False, f"{level}/{r['name']} has no neighbours")
        check(min(int(r["n_neighbours"]) for r in rows) >= 1,
              f"{level}: some unit has an empty neighbourhood")

        # ---- island flags must match the bridges actually built
        flagged = {r["pcode"] for r in rows if r["island_bridged"] == "1"}
        want = {codes[i] for b in bridges for i in b[:2]}
        check(flagged == want,
              f"{level}: island_bridged marks {len(flagged)} units, the "
              f"bridges touch {len(want)}")

        for key in CANDIDATES:
            share = np.array([float(margins[c][f"{key}_share_pct"])
                              for c in codes])
            z = (share - share.mean()) / share.std()
            lag = np.array([np.mean([z[j] for j in sorted(adj[i])])
                            for i in range(len(codes))])
            cls = [r[f"{key}_lisa_class"] for r in rows]
            sig = [r[f"{key}_lisa_sig"] == "1" for r in rows]
            gsig = [r[f"{key}_gi_sig"] == "1" for r in rows]
            p = np.array([float(r[f"{key}_lisa_p"]) for r in rows])

            check(set(cls) <= CLASSES,
                  f"{level}/{key}: unknown LISA class "
                  f"{sorted(set(cls) - CLASSES)}")
            check(all((c == "ns") == (not s) for c, s in zip(cls, sig)),
                  f"{level}/{key}: a class is 'ns' while flagged significant, "
                  f"or vice versa")

            # quadrant labels must follow from the two signs
            bad = []
            for i, (c, s) in enumerate(zip(cls, sig)):
                if not s:
                    continue
                want_cls = ("HH" if z[i] > 0 and lag[i] > 0 else
                            "HL" if z[i] > 0 else
                            "LH" if lag[i] > 0 else "LL")
                if c != want_cls:
                    bad.append(f"{rows[i]['name']} labelled {c}, arithmetic "
                               f"says {want_cls}")
            check(not bad,
                  f"{level}/{key}: {len(bad)} quadrant label(s) disagree with "
                  f"the signs, e.g. {bad[0] if bad else ''}")

            # LISA and Gi* share a null, so they must select the same units
            check(sig == gsig,
                  f"{level}/{key}: LISA flags {sum(sig)} units and Gi* "
                  f"{sum(gsig)}; they share a null and must agree")

            # permutation p-values live in [1/(perms+1), 1]
            check(p.min() >= 1.0 / (PERMS + 1) - 1e-12,
                  f"{level}/{key}: p-value {p.min():.2e} below the "
                  f"permutation floor {1 / (PERMS + 1):.2e}")
            check(p.max() <= 1.0,
                  f"{level}/{key}: p-value above 1")
            check(sum(sig) <= int((p <= 0.05).sum()),
                  f"{level}/{key}: {sum(sig)} significant after FDR exceeds "
                  f"the {int((p <= 0.05).sum())} at raw p <= 0.05")

        # ---- the regionalisation: contiguity is the whole claim
        lab = [int(r["region_cluster"]) for r in rows]
        check(set(lab) == set(range(K_REGIONS)),
              f"{level}: region clusters are {sorted(set(lab))}, expected "
              f"0..{K_REGIONS - 1}")
        for l in sorted(set(lab)):
            members = {i for i, v in enumerate(lab) if v == l}
            seen, stack = {next(iter(members))}, [next(iter(members))]
            while stack:
                u = stack.pop()
                for v in adj[u]:
                    if v in members and v not in seen:
                        seen.add(v)
                        stack.append(v)
            check(seen == members,
                  f"{level}: region {l} is not contiguous -- {len(members)} "
                  f"units but only {len(seen)} reachable from one of them")

        # cluster index must be ordered by mean Saied share, descending
        means = []
        for l in range(K_REGIONS):
            vals = [float(margins[codes[i]]["saied_share_pct"])
                    for i, v in enumerate(lab) if v == l]
            means.append(sum(vals) / len(vals))
        check(means == sorted(means, reverse=True),
              f"{level}: region indices are not ordered by mean Saied share "
              f"({[round(m, 1) for m in means]})")
        # and the mean columns must be those means, not something else
        for l in range(K_REGIONS):
            got = {float(r["region_saied_mean"]) for r in rows
                   if int(r["region_cluster"]) == l}
            check(len(got) == 1 and abs(got.pop() - means[l]) < 5e-4,
                  f"{level}: region {l} publishes a saied mean that is not "
                  f"the mean of its own units ({means[l]:.4f})")

        # ---- the verification log must describe this same run
        recs = [r for r in records if r["level"] == level]
        wrec = [r for r in recs if r["kind"] == "weights"]
        check(len(wrec) == 1, f"{level}: expected one weights record in {VERIFY}")
        if wrec:
            check(wrec[0]["units_analysed"] == len(rows),
                  f"{level}: {VERIFY} says {wrec[0]['units_analysed']} units, "
                  f"the table has {len(rows)}")
            check(len(wrec[0]["bridges"]) == len(bridges),
                  f"{level}: {VERIFY} logs {len(wrec[0]['bridges'])} bridges, "
                  f"rebuilding gives {len(bridges)}")
        for key in CANDIDATES:
            arec = [r for r in recs
                    if r["kind"] == "autocorrelation" and r["candidate"] == key]
            check(len(arec) == 1,
                  f"{level}/{key}: expected one autocorrelation record")
            if arec:
                n_sig = sum(1 for r in rows if r[f"{key}_lisa_sig"] == "1")
                check(arec[0]["lisa_fdr_significant"] == n_sig,
                      f"{level}/{key}: {VERIFY} says "
                      f"{arec[0]['lisa_fdr_significant']} significant, the "
                      f"table has {n_sig}")
                check(arec[0]["permutations"] == PERMS,
                      f"{level}/{key}: {VERIFY} records "
                      f"{arec[0]['permutations']} permutations, expected {PERMS}")

        rrec = [r for r in recs if r["kind"] == "regionalisation"]
        check(len(rrec) == 1, f"{level}: expected one regionalisation record")
        if rrec:
            check(rrec[0]["r2"] > rrec[0]["r2_official_regions"],
                  f"{level}: the clustering explains less than the official "
                  f"regions, which Ward's own criterion makes impossible")
            check(rrec[0]["k"] == K_REGIONS,
                  f"{level}: {VERIFY} records k={rrec[0]['k']}")

        if args.verbose:
            counts = collections.Counter(
                r["saied_lisa_class"] for r in rows)
            print(f"  {level}: {len(rows):,} units · Saied LISA {dict(counts)} "
                  f"· {len(bridges)} island bridge(s)")

    print(f"{len(fail) + passed[0]} checks run")
    if fail:
        print(f"\n{len(fail)} check(s) failed")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
