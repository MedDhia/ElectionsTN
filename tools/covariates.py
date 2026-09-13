"""Outside covariates for the 2019 model, resolved down to the constituency.

The model's own archive knows elections. What it does not know is who lives in a
place, and that turns out to be the thing that predicts Saied's 2019 vote. This
module assembles four blocks that do know:

* **2014 census** -- 129 published percentages, delegation level (INS RGPH 2014)
* **geography** -- centroid and area, built up from delegation polygons
* **statistical yearbook** -- 29 per-head governorate indicators, latest year
  through 2018 (INS *Annuaire Statistique*)
* **2015 poverty map** -- poverty rate and three school-dropout rates,
  delegation level (INS *Carte de la pauvreté*)

**Everything is aggregated to whatever unit the model asks for, and the unit can
be a half-governorate.** Three governorates are split in two for elections --
Tunis, Sfax and Nabeul -- and every source above is published by delegation or
by whole governorate, so the split had to be recovered before a census could be
attached to Tunis 1 as distinct from Tunis 2. It was, from the archive's own
folder tree: the 2023 local-election collection files each delegation under its
numbered constituency, and those numbers are the same 27 domestic constituencies
the presidential election used. All 53 delegations of the three split
governorates resolve, none ambiguously, and the halves come out 11+10, 8+8 and
9+7, which is exactly each governorate's delegation count.

`validate()` checks that split against something it cannot have copied: seats.
The 2014 assembly allocated seats by population, so population per seat should
be near-constant across the six halves, and under this assignment it is --
56,200 to 63,180 -- while the best alternative pairing of the same delegations
is visibly worse. Run it with `python3 tools/covariates.py`.

**Names are matched by minimum-cost one-to-one assignment, never by nearest
neighbour.** The census writes MANNOUBA where the boundary layer writes Manubah,
three edits away and also three from *Jendouba*; it writes `Dar Chaabane` for
`Dar Chaabane El Fehri`, seven edits away. Both are resolved by the constraint
that the matching is a bijection, which nearest-neighbour matching throws away.
"""
import collections
import csv
import gzip
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_census
from make_maps import load_layer
from make_2019_maps import fold

CROSSWALK = "data/delegation_crosswalk.csv"
INS = "data/delegations_ins.csv"
SKELETON = "inventory/electoral_geography.csv"
SEATS = "data/legislative_2014_constituency_results.csv"

# The three governorates that elect in two halves, and the pattern their
# numbered constituencies take in the archive's folder names: `01-تونس 1`.
SPLIT_PATTERN = re.compile(r"^\d{1,2}-(?:تونس|صفاقس|نابل)\s*[12]$")
CODE_PREFIX = re.compile(r"^[A-Z]{2}\d{2}_")

# Which count column each stated census denominator refers to. A percentage has
# to be re-weighted by its own denominator to aggregate: averaging instead would
# give Carthage's 24,000 people the same say as Sfax's 270,000.
CENSUS_DENOM = {
    "pop 15+": "pop_15plus",
    "total population": "population",
    "pop 10+": "pop_10plus_educ",
    "employed 15+": "occupes_15plus",
    "employed": "occupes_sect",
    "unemployed 15+": "chomeurs_15plus",
    "unemployed": "chomeurs_age_total",
}

YEARBOOK_CUTOFF = 2018      # the last year before the election being predicted


def damerau(a, b):
    """Optimal string alignment distance, a transposition costing one edit."""
    n, m = len(a), len(b)
    d = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        d[i][0] = i
    for j in range(m + 1):
        d[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            c = 0 if a[i - 1] == b[j - 1] else 1
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + c)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[n][m]


def latin_fold(s):
    """Accents, case and punctuation away: `Médenine` and `MEDNINE` compare."""
    import unicodedata
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def pair_names(left, right, folder=latin_fold, cap=8):
    """Minimum-cost one-to-one matching between two equal-length name sets.

    Nearest-neighbour matching answers "what is closest to this name", which is
    the wrong question when both sides are known to be the same set of places:
    the right question is which complete pairing costs least, and under that
    constraint a name already spoken for at distance zero stops competing.
    """
    from scipy.optimize import linear_sum_assignment
    a, b = sorted(left), sorted(right)
    if len(a) != len(b):
        raise SystemExit(f"cannot pair {len(a)} names with {len(b)}")
    d = np.array([[damerau(folder(x), folder(y)) for y in b] for x in a])
    ri, ci = linear_sum_assignment(d)
    if len(a) and d[ri, ci].max() > cap:
        worst = max(zip(d[ri, ci], (a[i] for i in ri)))
        raise SystemExit(f"{worst[1]!r} matches nothing (best pairing costs "
                         f"{int(worst[0])})")
    return {a[i]: b[j] for i, j in zip(ri, ci)}, d[ri, ci]


def read(path):
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def split_halves():
    """{(governorate, delegation): constituency} for the three split ones.

    Keyed on the pair, not on the delegation alone: Kasserine has a delegation
    called الزهور and so does Tunis, and keying on the name by itself files the
    Kasserine one into Tunis 1.

    Read out of the archive's own 2023 local-election folder tree, where every
    delegation sits under its numbered constituency. Nothing else in the archive
    states the split, and it is what makes Tunis 1 a different row from Tunis 2
    in every block below.
    """
    cross = read(CROSSWALK)
    govs = {fold(g) for g in ("تونس", "صفاقس", "نابل")}
    keys = {(fold(r["governorate_ar"]), fold(r["delegation_ar"]))
            for r in cross if fold(r["governorate_ar"]) in govs}
    votes = collections.defaultdict(collections.Counter)
    for r in read(SKELETON):
        c = r["constituency"].strip()
        if not SPLIT_PATTERN.match(c):
            continue
        name = CODE_PREFIX.sub("", (r["delegation"] or
                                    r["city_or_delegation"] or "").strip())
        if not name or re.match(r"^\d{2}_", name):
            continue
        gov = fold(re.sub(r"^\d{1,2}-", "", c).rsplit(" ", 1)[0])
        here = [k for k in keys if k[0] == gov]
        if not here:
            raise SystemExit(f"constituency {c!r} names no known governorate")
        best = min((damerau(fold(name), k[1]), k) for k in here)
        if best[0] <= 3:
            votes[best[1]][fold(c.split("-", 1)[1])] += 1
    out = {}
    for d, seen in votes.items():
        if len(seen) > 1:
            raise SystemExit(f"delegation {d!r} filed under {list(seen)}")
        out[d] = next(iter(seen))
    if len(out) != len(keys):
        raise SystemExit(f"{len(keys) - len(out)} split-governorate "
                         f"delegations were never filed: {sorted(keys - set(out))}")
    return out


def bridge():
    """One row per delegation, joined across the archive, INS and the census.

    Returns {id_delegation: {...}} carrying the census row, the delegation's
    folded Arabic name, its governorate as the boundary layer spells it, and the
    constituency it votes in -- the governorate, or one of its two halves.
    """
    ins = read(INS)
    cross = {latin_fold(r["delegation_name"]): r for r in read(CROSSWALK)}
    with gzip.open(fetch_census.paths()["master"], "rt", encoding="utf-8") as fh:
        cen = list(csv.DictReader(fh))

    gp, _ = pair_names({r["governorate"] for r in cen},
                       {r["governorate_name"] for r in ins})
    layer = {f["properties"]["adm2_name"]: fold(f["properties"]["adm2_name1"])
             for f in load_layer("tun_admin2.geojson")}
    lp, _ = pair_names({r["governorate_name"] for r in ins}, set(layer))

    by_ins = collections.defaultdict(list)
    by_cen = collections.defaultdict(list)
    for r in ins:
        by_ins[r["governorate_name"]].append(r)
    for r in cen:
        by_cen[gp[r["governorate"]]].append(r)

    halves = split_halves()
    out = {}
    for g, rows in sorted(by_ins.items()):
        pair, _ = pair_names([r["delegation_fr"] for r in by_cen[g]],
                             [r["delegation_name"] for r in rows])
        cenrow = {r["delegation_fr"]: r for r in by_cen[g]}
        insrow = {r["delegation_name"]: r for r in rows}
        arabic = layer[lp[g]]
        for cf, inf in pair.items():
            i = insrow[inf]
            ar = cross.get(latin_fold(inf), {}).get("delegation_ar", "")
            out[i["id_delegation"]] = {
                "census": cenrow[cf], "ins": i, "governorate": arabic,
                "delegation_ar": fold(ar),
                "constituency": halves.get((arabic, fold(ar)), arabic),
                "population": float(cenrow[cf]["population"] or 0),
            }
    if len(out) != 264:
        raise SystemExit(f"bridged {len(out)} delegations, expected 264")
    return out


def _resolve(units, keys):
    """Map each unit key onto the constituency label the bridge produced.

    A unit with no match is dropped rather than forced: the six out-of-country
    constituencies have no delegations, no census and no polygon, and every
    block here is silent about them by construction. Matching is exact where it
    can be and otherwise has to be both close and unambiguous, because فرنسا 1
    and تونس 1 are only a few edits apart and a loose threshold would file
    France under Tunis.
    """
    out = {}
    for u in units:
        if u in keys:
            out[u] = u
            continue
        scored = sorted((damerau(u, k), k) for k in keys)
        if scored[0][0] <= 2 and scored[0][0] < scored[1][0]:
            out[u] = scored[0][1]
    if not out:
        raise SystemExit(f"none of {len(units)} units matched the bridge")
    return out


def _delegations_by_unit(units, br, level):
    """Attach each delegation to the model's unit key."""
    labels = {d["constituency"] if level == "constituency" else d["governorate"]
              for d in br.values()}
    resolved = _resolve(units, labels)
    back = collections.defaultdict(list)
    for u, label in resolved.items():
        back[label].append(u)
    out = []
    for d in br.values():
        label = (d["constituency"] if level == "constituency"
                 else d["governorate"])
        for u in back.get(label, []):
            out.append(dict(d, unit=u))
    return out


def census(units, level, spread=False):
    """{unit: {variable: value}} for every published census percentage.

    With `spread`, each variable also gets a `_sd` companion: the
    population-weighted standard deviation of that variable across the unit's
    own delegations. A constituency's mean says how the average delegation
    looks; the spread says whether it is one kind of place or two, which is a
    different fact about an electorate and one the mean throws away.
    """
    with open(fetch_census.paths()["codebook"], encoding="utf-8") as fh:
        book = {r["variable"]: r for r in csv.DictReader(fh)}
    pct = [v for v, r in book.items() if r["unit"] == "percent"]
    br = bridge()
    rows = _delegations_by_unit(units, br, level)

    per, pop = [], collections.Counter()
    for d in rows:
        c = d["census"]
        vals = {}
        for v in pct:
            try:
                vals[v] = float(c[v])
            except (TypeError, ValueError, KeyError):
                vals[v] = None
        per.append((d, vals))
        pop[d["unit"]] += d["population"]

    def weight(d, k):
        col = CENSUS_DENOM.get(book[k]["denominator"], "")
        try:
            w = float(d["census"].get(col) or 0)
        except (TypeError, ValueError):
            w = 0.0
        return w or d["population"]

    num = collections.defaultdict(collections.Counter)
    den = collections.defaultdict(collections.Counter)
    for d, vals in per:
        for k, v in vals.items():
            if v is None:
                continue
            w = weight(d, k)
            if w <= 0:
                continue
            num[d["unit"]][k] += v * w
            den[d["unit"]][k] += w
    out = {u: {k: num[u][k] / den[u][k] for k in den[u] if den[u][k] > 0}
           for u in den}
    if spread:
        var = collections.defaultdict(collections.Counter)
        for d, vals in per:
            for k, v in vals.items():
                if v is None or k not in out[d["unit"]]:
                    continue
                w = weight(d, k)
                if w > 0:
                    var[d["unit"]][k] += w * (v - out[d["unit"]][k]) ** 2
        for u in out:
            for k in list(out[u]):
                if den[u][k] > 0:
                    out[u][f"{k}_sd"] = float(np.sqrt(var[u][k] / den[u][k]))
    for u in out:
        out[u]["log_population"] = float(np.log(pop[u]))
    keys = sorted(set.intersection(*(set(v) for v in out.values())))
    return out, keys


def geography(units, level):
    """Population-weighted centroid, summed area and region, per unit.

    Built from the 264 delegation polygons rather than the 24 governorate ones,
    so a half-governorate gets its own centre of population and its own area
    instead of half its parent's.
    """
    poly = {}
    for f in load_layer("tun_admin3.geojson"):
        p = f["properties"]
        poly[p["adm3_pcode"]] = (p["center_lat"], p["center_lon"],
                                 p["area_sqkm"])
    region = {fold(f["properties"]["adm2_name1"]): f["properties"]["adm1_name"]
              for f in load_layer("tun_admin2.geojson")}
    br = bridge()
    rows = _delegations_by_unit(units, br, level)

    acc = collections.defaultdict(lambda: {"w": 0.0, "lat": 0.0, "lon": 0.0,
                                           "area": 0.0, "region": None})
    for d in rows:
        code = "TN" + d["ins"]["id_delegation"]
        if code not in poly:
            raise SystemExit(f"no polygon for delegation {code}")
        lat, lon, area = poly[code]
        a = acc[d["unit"]]
        w = max(d["population"], 1.0)
        a["w"] += w
        a["lat"] += w * lat
        a["lon"] += w * lon
        a["area"] += area
        a["region"] = region[d["governorate"]]
    out = {u: {"lat": a["lat"] / a["w"], "lon": a["lon"] / a["w"],
               "log_area": float(np.log(a["area"])), "region": a["region"]}
           for u, a in acc.items()}
    return out, sorted({v["region"] for v in out.values()})


def yearbook(units, level):
    """29 per-head governorate indicators, each at its latest year to 2018.

    Published statistics rather than survey estimates: bank branches, primary
    schools and teachers, public libraries and what is borrowed from them, youth
    centres, sports halls, money orders from abroad, road deaths, marriages.
    Both halves of a split governorate get the same value, because that is the
    level at which the yearbook prints them.
    """
    rows = read(fetch_census.paths("surveys")["yearbook"])
    latest = collections.defaultdict(dict)
    for r in rows:
        if r["basis"] != "per_head" or r["geography"] != "as_printed":
            continue
        try:
            year, val = int(r["year"]), float(r["comparable"])
        except (TypeError, ValueError):
            continue
        if year > YEARBOOK_CUTOFF:
            continue
        latest[r["indicator"]].setdefault(year, {})[r["governorate"]] = val
    keep = {}
    govs = {r["governorate"] for r in rows}
    for ind, years in latest.items():
        full = [y for y, d in years.items() if len(d) >= 24]
        if full:
            keep[ind] = years[max(full)]
    # The yearbook names governorates in Latin, the bridge in Arabic, so the
    # pairing goes through the boundary layer, which carries both.
    latin_to_ar = {f["properties"]["adm2_name"]: fold(f["properties"]["adm2_name1"])
                   for f in load_layer("tun_admin2.geojson")}
    gp, _ = pair_names(govs, set(latin_to_ar))
    to_ar = {a: latin_to_ar[b] for a, b in gp.items()}
    by_ar = {v: k for k, v in to_ar.items()}
    br = bridge()
    rows = _delegations_by_unit(units, br, level)
    seen, out = {}, collections.defaultdict(dict)
    for d in rows:
        seen[d["unit"]] = by_ar[d["governorate"]]
    for u, g in seen.items():
        for ind, vals in keep.items():
            out[u][ind] = vals[g]
    return dict(out), sorted(keep)


def poverty(units, level):
    """2015 small-area poverty and school-dropout rates, by delegation.

    INS's *Carte de la pauvreté* models a poverty rate for each delegation. It
    covers 253 of the 264: **Siliana's eleven delegations are absent from the
    published table**, so the block is missing for that one constituency and the
    caller has to decide what to do about it rather than being handed a filled
    hole.
    """
    rows = read(fetch_census.paths("surveys")["poverty"])
    fields = ["poverty_rate_pct", "dropout_primary_pct", "dropout_secondary_pct",
              "dropout_both_cycles_pct"]
    br = bridge()
    by_gov = collections.defaultdict(list)
    for d in br.values():
        by_gov[latin_fold(d["ins"]["governorate_name"])].append(d)
    src = collections.defaultdict(list)
    for r in rows:
        src[latin_fold(r["governorate"])].append(r)

    got = {}
    for g, rs in src.items():
        best = min((damerau(g, k), k) for k in by_gov)
        if best[0] > 4 or len(rs) != len(by_gov[best[1]]):
            continue                       # partial coverage is not usable here
        # The poverty map writes delegation names in upper-case French with a
        # freer hand than INS -- `SIDI ALI BEN NASRALLAH` for `Nasrallah` -- so
        # the distance cap is loose here and the bijection does the work.
        pair, _ = pair_names([r["delegation"] for r in rs],
                             [d["ins"]["delegation_name"] for d in by_gov[best[1]]],
                             cap=20)
        by_name = {d["ins"]["delegation_name"]: d for d in by_gov[best[1]]}
        for a, b in pair.items():
            row = next(r for r in rs if r["delegation"] == a)
            got[by_name[b]["ins"]["id_delegation"]] = row

    rows = _delegations_by_unit(units, br, level)
    num = collections.defaultdict(collections.Counter)
    den = collections.defaultdict(collections.Counter)
    for d in rows:
        r = got.get(d["ins"]["id_delegation"])
        if r is None:
            continue
        for f in fields:
            try:
                v = float(r[f])
            except (TypeError, ValueError):
                continue
            num[d["unit"]][f] += v * d["population"]
            den[d["unit"]][f] += d["population"]
    out = {u: {f: num[u][f] / den[u][f] for f in fields if den[u][f] > 0}
           for u in den}
    return out, fields


OUT = "data/constituency_delegations.csv"


def write_map():
    """Publish the delegation-to-constituency map as a dataset in its own right.

    It is the piece nothing else in the archive states outright: which of the
    27 domestic constituencies each of the 264 delegations votes in, including
    the halves of Tunis, Sfax and Nabeul. Any analysis that wants to attach
    delegation-level data -- a census, a poverty map, anything -- to an election
    fought in constituencies needs it, and it should not have to re-derive it.
    """
    br = bridge()
    rows = sorted(br.items(), key=lambda kv: (kv[1]["governorate"],
                                              kv[1]["ins"]["delegation_name"]))
    with open(OUT, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["id_delegation", "governorate_ar", "governorate_name",
                    "delegation_ar", "delegation_name", "constituency_ar",
                    "is_split_half", "population_2014"])
        for i, d in rows:
            w.writerow([i, d["governorate"], d["ins"]["governorate_name"],
                        d["delegation_ar"], d["ins"]["delegation_name"],
                        d["constituency"],
                        int(d["constituency"] != d["governorate"]),
                        int(d["population"])])
    print(f"wrote {OUT}: {len(rows)} delegations")


def validate():
    """Check the recovered split against something it cannot have copied."""
    br = bridge()
    print(f"{len(br)} delegations bridged across the archive, INS and the census")
    halves = collections.defaultdict(list)
    for d in br.values():
        if d["constituency"] != d["governorate"]:
            halves[d["constituency"]].append(d)
    print(f"{sum(len(v) for v in halves.values())} of them in a split "
          f"governorate, in {len(halves)} halves:")
    seats = {fold(r["constituency"]): float(r["seats"]) for r in read(SEATS)}
    ratios = []
    for c in sorted(halves):
        pop = sum(d["population"] for d in halves[c])
        s = seats[c]
        ratios.append(pop / s)
        print(f"  {c:<12} {len(halves[c]):3d} delegations  {pop:10,.0f} people"
              f"  {s:4.0f} seats  {pop / s:8,.0f} per seat")
    spread = max(ratios) - min(ratios)
    print(f"population per seat spans {spread:,.0f} "
          f"({min(ratios):,.0f} to {max(ratios):,.0f})")

    # the same delegations, halves swapped: seats were allocated on population,
    # so the true assignment should be the flatter one
    worse = 0
    for gov in ("تونس", "صفاقس", "نابل"):
        names = sorted(c for c in halves if fold(gov) in c)
        pops = [sum(d["population"] for d in halves[c]) for c in names]
        s = [seats[c] for c in names]
        if max(pops[0] / s[1], pops[1] / s[0]) - min(pops[0] / s[1],
                                                     pops[1] / s[0]) > \
           max(pops[0] / s[0], pops[1] / s[1]) - min(pops[0] / s[0],
                                                     pops[1] / s[1]):
            worse += 1
    print(f"swapping the halves makes the fit worse in {worse} of 3 "
          f"governorates")
    return len(br) == 264 and spread < 10000


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true",
                    help=f"also write {OUT}")
    if ap.parse_args().write:
        write_map()
    ok = validate()
    print("ok" if ok else "CHECK FAILED")
    raise SystemExit(0 if ok else 1)
