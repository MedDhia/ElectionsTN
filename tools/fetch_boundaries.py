"""Fetch the Tunisian administrative boundaries the maps are drawn on.

Source: the OCHA/HDX Common Operational Dataset for Tunisia (COD-AB), which
carries five nested levels with p-codes, French *and* Arabic names, centroids and
areas:

    admin0  country
    admin1  6 regions        (matches `region_name` in data/delegations_ins.csv)
    admin2  24 governorates
    admin3  264 delegations  <- joins to id_delegation by code, exactly
    admin4  2,084 imadas     <- the finest level available

The delegation join needs no name matching at all: `adm3_pcode` is "TN" plus the
INS `id_delegation`, so Carthage is TN1151. All 264 match, both ways.

geoBoundaries was tried first and is unusable here: its download URLs point at
github.com, which this session's repo scoping blocks with a 403. That is a
correct restriction, not a fault to work around.

The archive is 54 MB and its admin4 layer alone is 42 MB of geometry, so it is
cached under .cache/ (gitignored) rather than committed. What *is* committed is
the provenance record, so a later reader can re-fetch the identical bytes.
"""

import argparse
import hashlib
import json
import os
import sys
import urllib.request

HDX_PACKAGE = "https://data.humdata.org/api/3/action/package_show?id=cod-ab-tun"
CACHE_DIR = ".cache/boundaries"
ARCHIVE = os.path.join(CACHE_DIR, "tun_admin_boundaries.geojson.zip")
PROVENANCE = "data/verification/boundaries_source.json"

# Every layer the maps and tables use, with the unit each one represents.
LAYERS = {
    "tun_admin1.geojson": "region",
    "tun_admin2.geojson": "governorate",
    "tun_admin3.geojson": "delegation",
    "tun_admin4.geojson": "imada",
}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def resolve():
    """Ask HDX for the GeoJSON resource, rather than hard-coding a URL."""
    with urllib.request.urlopen(HDX_PACKAGE, timeout=90) as fh:
        pkg = json.load(fh)["result"]
    for r in pkg["resources"]:
        if r.get("format", "").lower() == "geojson":
            return {
                "dataset": pkg.get("name"),
                "dataset_title": pkg.get("title"),
                "licence": pkg.get("license_title"),
                "resource_id": r.get("id"),
                "resource_name": r.get("name"),
                "url": r["url"],
                "last_modified": r.get("last_modified"),
            }
    sys.exit("no GeoJSON resource in the HDX package")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true", help="re-download even if cached")
    args = ap.parse_args()

    os.makedirs(CACHE_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(PROVENANCE), exist_ok=True)

    have = os.path.exists(ARCHIVE)
    if have and not args.force:
        print(f"cached: {ARCHIVE} ({os.path.getsize(ARCHIVE):,} bytes)")
    else:
        meta = resolve()
        print(f"downloading {meta['url']}")
        urllib.request.urlretrieve(meta["url"], ARCHIVE)
        print(f"  wrote {ARCHIVE} ({os.path.getsize(ARCHIVE):,} bytes)")

    digest = sha256(ARCHIVE)

    # Confirm the archive really holds the layers the pipeline expects, and count
    # the features, so a silently changed upstream release is visible here rather
    # than as a puzzling gap on a map.
    import zipfile
    counts = {}
    with zipfile.ZipFile(ARCHIVE) as z:
        names = set(z.namelist())
        missing = sorted(set(LAYERS) - names)
        if missing:
            sys.exit(f"archive is missing expected layers: {missing}")
        for layer in LAYERS:
            with z.open(layer) as fh:
                counts[layer] = len(json.load(fh)["features"])

    record = {
        "archive": ARCHIVE,
        "sha256": digest,
        "bytes": os.path.getsize(ARCHIVE),
        "layers": {k: {"unit": v, "features": counts[k]} for k, v in LAYERS.items()},
        "note": ("OCHA/HDX COD-AB for Tunisia. adm3_pcode == 'TN' + INS "
                 "id_delegation, so the delegation join is by code. Cached "
                 "under .cache/ because admin4 alone is 42 MB of geometry."),
    }
    # The source fields must always be present: a provenance record without the
    # URL and licence is not provenance. Reuse what was recorded before if it is
    # there, and otherwise ask HDX even when the archive came from cache.
    source_keys = ("dataset", "dataset_title", "licence", "resource_id",
                   "resource_name", "url", "last_modified")
    prior = {}
    if os.path.exists(PROVENANCE):
        prior = json.load(open(PROVENANCE, encoding="utf-8"))
    if all(prior.get(k) for k in source_keys):
        record.update({k: prior[k] for k in source_keys})
    else:
        record.update(resolve())

    with open(PROVENANCE, "w", encoding="utf-8") as fh:
        json.dump(record, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")

    print(f"sha256 {digest}")
    for k, v in counts.items():
        print(f"  {LAYERS[k]:13} {v:5d}  ({k})")
    print(f"provenance -> {PROVENANCE}")


if __name__ == "__main__":
    main()
