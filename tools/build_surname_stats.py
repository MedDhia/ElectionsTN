"""One row of statistics per family name in the 2024 voter register.

What this adds to what was already there
----------------------------------------
`data/voter_surnames_2024/surnames_spatial_metrics.csv.gz` already carries
national metrics, and this does not replace it. It answers a different question,
in three ways:

**It is keyed on the family, not the spelling.** The register prints `العبيدي`
and `عبيدي` as separate strings, and the metrics table scores them separately:
33,347 voters and 29,100, two HHIs, two top imadas. They are one family name.
Rows here pool on the same key the maps pool on -- the normalised string with the
leading definite article removed -- and name the spellings they pooled. That
changes the ranking as well as the counts: pooled, `عبيدي` is the commonest
family name in the country, and unpooled it is third.

**It carries the geography the maps are drawn on.** The metrics table names a top
imada as a string; this joins every imada to its admin4 p-code through
`data/surname_imada_crosswalk.csv`, so a family's distribution can be counted at
three levels (imada, delegation, governorate), and what the bridge could not
resolve is reported per family rather than silently dropped.

**It measures dispersion in kilometres as well as in shares.** HHI and entropy
say how concentrated a distribution is; neither says how far apart the holders
are. Two families can share an HHI while one sits in two neighbouring imadas and
the other has half its holders in Bizerte and half in Tataouine. So each row
also carries the family's centre of gravity and the voter-weighted mean distance
from it, in km.

The columns, and how to read them
---------------------------------
Counts split three ways and they do not overlap: `domestic_voters` are on the
map, `diaspora_voters` are in the ten consular constituencies which have no
geometry at all, and `unplaced_voters` are domestic voters in the six registry
imadas the bridge could not resolve. Every geographic statistic in the row is
computed on `domestic_voters` alone, because that is the only part with a place.

`hhi_imada` is the Herfindahl index over imadas: 1.0 is one imada, and the floor
is 1/2,069. `spatial_entropy` is Shannon over the same shares in nats;
`entropy_pct_of_max` divides it by ln(imadas_present), so 100% means a family is
spread evenly across the imadas it occupies and a low value means it occupies
many but sits in few. The two disagree usefully: a name in 500 imadas with 60% of
its holders in one has a high entropy and a high HHI at the same time.

`is_patronymic` marks a name whose first word is `بن`, `ابن` or `ولد` -- a
father's name standing in for a family name. They are left in the file, since
they are in the register, and flagged so they can be excluded from any ranking of
family names. `figure` names the map in `maps/surnames/` where one exists.

Usage: python3 tools/build_surname_stats.py
"""

import array
import collections
import csv
import gzip
import math
import os
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from arabic_latin import ar_norm
from arabic_translit import slug, translit
from make_surname_dots import (CENTER_GZ, IMADA_GZ, METRICS_GZ,
                               PATRONYMIC_PREFIXES, XW, family_key)

OUT = "data/voter_surnames_2024/surname_family_stats.csv.gz"
INDEX = "data/maps/surname_dot_index.csv"

EARTH_KM = 6371.0088


def read_csv(path):
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def haversine(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = (math.sin(dp / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2)
    return 2 * EARTH_KM * math.asin(min(1.0, math.sqrt(a)))


class Family:
    """Running aggregates for one pooled family name.

    The counts must be summed per *imada* before any of these statistics are
    taken, not per register row: a family with two spellings has two rows in the
    same imada, and accumulating row by row counted that imada twice. It made
    `Abidi` occupy 2,642 of 2,069 imadas, and it understated every HHI, because
    two halves of one place look like two places. So the (family, imada) pairs
    are aggregated first, in one sorted array, and every statistic below is taken
    from the aggregated pair.
    """

    __slots__ = ("national", "domestic", "diaspora", "unplaced", "sum_sq",
                 "sum_clnc", "imadas", "top_imada", "top_imada_n", "by_gov",
                 "by_deleg", "lat_sum", "lon_sum", "dist_sum", "variants",
                 "with_article", "without_article")

    def __init__(self):
        self.national = self.domestic = self.diaspora = self.unplaced = 0
        self.sum_sq = 0
        self.sum_clnc = 0.0
        self.imadas = 0
        self.top_imada = None
        self.top_imada_n = 0
        self.by_gov = collections.Counter()
        self.by_deleg = collections.Counter()
        self.lat_sum = self.lon_sum = 0.0
        self.dist_sum = 0.0
        self.variants = collections.Counter()
        self.with_article = self.without_article = 0

    def add_imada(self, n, row):
        """One aggregated (family, imada) pair."""
        self.domestic += n
        self.sum_sq += n * n
        self.sum_clnc += n * math.log(n)
        self.imadas += 1
        if n > self.top_imada_n:
            self.top_imada_n, self.top_imada = n, row
        self.by_gov[row["governorate_name"]] += n
        self.by_deleg[(row["governorate_name"], row["delegation_name"])] += n
        self.lat_sum += n * float(row["lat"])
        self.lon_sum += n * float(row["lon"])

    def centroid(self):
        if not self.domestic:
            return None, None
        return self.lat_sum / self.domestic, self.lon_sum / self.domestic

    def hhi(self):
        return self.sum_sq / float(self.domestic) ** 2 if self.domestic else 0.0

    def entropy(self):
        if not self.domestic:
            return 0.0
        return math.log(self.domestic) - self.sum_clnc / self.domestic

    def gov_hhi(self):
        if not self.domestic:
            return 0.0
        return sum(v * v for v in self.by_gov.values()) / float(self.domestic) ** 2


def main():
    for path in (METRICS_GZ, IMADA_GZ, CENTER_GZ, XW):
        if not os.path.exists(path):
            sys.exit(f"missing {path}")

    xw = {(r["governorate_ar"], r["constituency_ar"], r["imada_ar"]): r
          for r in read_csv(XW)}
    electorate = sum(int(r["registry_voters"]) for r in xw.values())
    drawn = {}
    if os.path.exists(INDEX):
        drawn = {family_key(r["surname"]): r for r in read_csv(INDEX)}

    fams = collections.defaultdict(Family)

    # ---- 1. the spellings, and the national totals they pool into
    print("reading the spelling metrics ...")
    with gzip.open(METRICS_GZ, "rt", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            key = family_key(row["surname_norm"])
            if not key:
                continue
            n = int(row["national_voters"])
            f = fams[key]
            f.national += n
            spelled = ar_norm(row["surname_norm"])
            f.variants[spelled] += n
            if spelled.startswith("ال"):
                f.with_article += n
            else:
                f.without_article += n
    print(f"  {len(fams):,} pooled family names")

    # ---- 2. where they are, imada by imada
    #
    # Rows are packed into one int64 array and sorted, so the two rows a
    # two-spelling family has in the same imada become one pair before anything
    # is measured. 1.67 million domestic rows is 13 MB packed, against several
    # hundred megabytes as a dict of dicts.
    ids = {k: i for i, k in enumerate(fams)}
    pcode_ids, pcode_rows = {}, []
    for r in xw.values():
        if r["adm4_pcode"] not in pcode_ids:
            pcode_ids[r["adm4_pcode"]] = len(pcode_rows)
            pcode_rows.append(r)
    COUNT_BITS, PCODE_BITS = 21, 12
    COUNT_MASK = (1 << COUNT_BITS) - 1
    assert len(pcode_rows) < (1 << PCODE_BITS)

    print("reading the imada table ...")
    packed = array.array("q")
    with gzip.open(IMADA_GZ, "rt", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            key = family_key(row["surname_norm"])
            f = fams.get(key)
            if f is None:
                continue
            n = int(row["voter_count"])
            if row["is_diaspora"] == "1":
                f.diaspora += n
                continue
            hit = xw.get((row["governorate"], row["constituency"], row["imada"]))
            if hit is None:
                f.unplaced += n
                continue
            if n > COUNT_MASK:
                sys.exit(f"count {n} does not fit the packing; widen COUNT_BITS")
            packed.append((ids[key] << (COUNT_BITS + PCODE_BITS))
                          | (pcode_ids[hit["adm4_pcode"]] << COUNT_BITS) | n)
    packed = sorted(packed)

    # One pass to fold the pairs together and take every count-based statistic.
    pairs = []                      # (family id, pcode id, voters), aggregated
    i, n_rows = 0, len(packed)
    while i < n_rows:
        head = packed[i] >> COUNT_BITS
        total = packed[i] & COUNT_MASK
        j = i + 1
        while j < n_rows and (packed[j] >> COUNT_BITS) == head:
            total += packed[j] & COUNT_MASK
            j += 1
        fam_id = head >> PCODE_BITS
        pcode_id = head & ((1 << PCODE_BITS) - 1)
        pairs.append((fam_id, pcode_id, total))
        i = j
    del packed
    keys = list(fams)
    for fam_id, pcode_id, total in pairs:
        fams[keys[fam_id]].add_imada(total, pcode_rows[pcode_id])
    print(f"  {len(pairs):,} (family, imada) pairs")

    # ---- 3. how far the holders are from their own centre of gravity
    # A second pass over the same pairs, because the centre is only known once
    # the first has run.
    print("measuring dispersion around each centre of gravity ...")
    centroids = {k: f.centroid() for k, f in fams.items()}
    for fam_id, pcode_id, total in pairs:
        key = keys[fam_id]
        clat, clon = centroids[key]
        if clat is None:
            continue
        r = pcode_rows[pcode_id]
        fams[key].dist_sum += total * haversine(
            clat, clon, float(r["lat"]), float(r["lon"]))
    del pairs

    # ---- 4. how many polling centres each family reaches
    # Held as one sorted array of packed (family, centre) keys rather than a set
    # per family: 2.6 million pairs, 21 MB as int64, and the count per family
    # falls out of one linear scan.
    print("reading the polling-centre table ...")
    packed = array.array("q")
    with gzip.open(CENTER_GZ, "rt", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["is_diaspora"] == "1":
                continue
            key = family_key(row["surname_norm"])
            i = ids.get(key)
            if i is None:
                continue
            hit = xw.get((row["governorate"], row["constituency"], row["imada"]))
            if hit is None:
                continue
            tag = zlib.crc32(
                (hit["adm4_pcode"] + "|" + row["polling_center"]).encode("utf-8"))
            packed.append((i << 32) | tag)
    packed = sorted(packed)
    centres = collections.Counter()
    prev = None
    for v in packed:
        if v != prev:
            centres[v >> 32] += 1
            prev = v
    del packed

    # ---- 5. write
    order = sorted(fams.items(), key=lambda kv: (-kv[1].national, kv[0]))
    rows = []
    for rank, (key, f) in enumerate(order, 1):
        spelling = f.variants.most_common(1)[0][0] if f.variants else key
        top_gov, top_gov_n = (f.by_gov.most_common(1)[0] if f.by_gov
                              else ("", 0))
        top_deleg, top_deleg_n = (f.by_deleg.most_common(1)[0] if f.by_deleg
                                  else (("", ""), 0))
        clat, clon = f.centroid()
        ent = f.entropy()
        ent_max = math.log(f.imadas) if f.imadas > 1 else 0.0
        fig = drawn.get(key)
        rows.append({
            "rank": rank,
            "surname": spelling,
            "surname_latin": translit(spelling),
            "family_key": key,
            "is_patronymic": int(key.split()[0] in PATRONYMIC_PREFIXES),
            "spellings_pooled": len(f.variants),
            "voters_with_article": f.with_article,
            "voters_without_article": f.without_article,
            "national_voters": f.national,
            "domestic_voters": f.domestic,
            "diaspora_voters": f.diaspora,
            "unplaced_voters": f.unplaced,
            "mapped_electorate_share_pct": f"{100.0 * f.domestic / electorate:.6f}",
            "imadas_present": f.imadas,
            "delegations_present": len(f.by_deleg),
            "governorates_present": len(f.by_gov),
            "polling_centres_present": centres.get(ids[key], 0),
            "top_governorate": top_gov,
            "top_governorate_voters": top_gov_n,
            "top_governorate_share_pct": (f"{100.0 * top_gov_n / f.domestic:.2f}"
                                          if f.domestic else ""),
            "top_delegation": (f"{top_deleg[0]} — {top_deleg[1]}"
                               if top_deleg[1] else ""),
            "top_delegation_share_pct": (f"{100.0 * top_deleg_n / f.domestic:.2f}"
                                         if f.domestic else ""),
            "top_imada": (f"{f.top_imada['governorate_name']} — "
                          f"{f.top_imada['adm4_name']}" if f.top_imada else ""),
            "top_imada_pcode": f.top_imada["adm4_pcode"] if f.top_imada else "",
            "top_imada_share_pct": (f"{100.0 * f.top_imada_n / f.domestic:.2f}"
                                    if f.domestic else ""),
            "hhi_imada": f"{f.hhi():.6f}" if f.domestic else "",
            "hhi_governorate": f"{f.gov_hhi():.6f}" if f.domestic else "",
            "spatial_entropy": f"{ent:.4f}" if f.domestic else "",
            "entropy_pct_of_max": (f"{100.0 * ent / ent_max:.1f}"
                                   if ent_max > 0 else ""),
            "centroid_lat": f"{clat:.6f}" if clat is not None else "",
            "centroid_lon": f"{clon:.6f}" if clon is not None else "",
            "mean_km_from_centroid": (f"{f.dist_sum / f.domestic:.1f}"
                                      if f.domestic else ""),
            "figure": (f"maps/surnames/{slug(fig['surname'])}_dots.pdf"
                       if fig else ""),
        })

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with gzip.open(OUT, "wt", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    placed = sum(1 for r in rows if r["domestic_voters"])
    print(f"\nwrote {OUT}")
    print(f"  {len(rows):,} family names, {placed:,} of them with a place on the map")
    print(f"  {sum(r['domestic_voters'] for r in rows):,} domestic voters, "
          f"{sum(r['diaspora_voters'] for r in rows):,} abroad, "
          f"{sum(r['unplaced_voters'] for r in rows):,} in unresolved imadas")
    print(f"  {sum(1 for r in rows if r['figure']):,} of them have a figure")
    print("\n  the ten commonest family names, patronymics excluded:")
    shown = 0
    for r in rows:
        if r["is_patronymic"]:
            continue
        print(f"    {r['surname_latin']:<12} {r['national_voters']:>7,}  "
              f"{r['imadas_present']:>4} imadas  "
              f"{r['polling_centres_present']:>5} centres  "
              f"HHI {r['hhi_imada']}  "
              f"mean {r['mean_km_from_centroid']} km from its centre")
        shown += 1
        if shown == 10:
            break
    return 0


if __name__ == "__main__":
    sys.exit(main())
