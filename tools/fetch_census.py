"""Fetch the 2014 census tables the Saied model uses as covariates.

Source: `MedDhia/rgph2014tn`, an R package wrapping Tunisia's 2014 *Recensement
Général de la Population et de l'Habitat* (INS) at delegation level -- 169
variables over 264 delegations, licensed CC BY 4.0. The package ships the merged
table as a gzipped CSV under `inst/extdata/`, so nothing here needs R.

Why this source and not the model's own archive: the 2014 census is the only
measurement of the electorate in this project that is not itself an election. It
was taken in April 2014, five years before the vote being predicted, so it is
available to a forecaster and cannot have been contaminated by the outcome.

The checkout is cached under `.cache/` and gitignored, as the boundaries are.
What is committed is the provenance record -- the commit the files came from and
their SHA-256 -- so a later reader can re-fetch the identical bytes and tell
whether the upstream package has moved underneath a published result.

Usage:
    python3 tools/fetch_census.py           # fetch if missing, then verify
    python3 tools/fetch_census.py --force   # re-clone from scratch
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys

REPO = "https://github.com/MedDhia/rgph2014tn"
CACHE_DIR = ".cache/census/rgph2014tn"
PROVENANCE = "data/verification/census_source.json"

# The two files the model reads. `master_merged` is the table; `codebook` names
# every variable's unit and denominator, which is what makes a correct
# population-weighted aggregation to governorate possible at all.
WANTED = {
    "master": "inst/extdata/master_merged.csv.gz",
    "codebook": "inst/extdata/codebook.csv",
}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def clone(force=False):
    if force and os.path.isdir(CACHE_DIR):
        shutil.rmtree(CACHE_DIR)
    if os.path.isdir(os.path.join(CACHE_DIR, ".git")):
        return False
    os.makedirs(os.path.dirname(CACHE_DIR), exist_ok=True)
    env = dict(os.environ, GIT_LFS_SKIP_SMUDGE="1")
    subprocess.run(["git", "clone", "--depth", "1", REPO, CACHE_DIR],
                   check=True, env=env)
    return True


def head():
    out = subprocess.run(["git", "-C", CACHE_DIR, "rev-parse", "HEAD"],
                         check=True, capture_output=True, text=True)
    return out.stdout.strip()


def paths():
    """{role: path} for the files the model reads, checked to exist."""
    out = {}
    for role, rel in WANTED.items():
        p = os.path.join(CACHE_DIR, rel)
        if not os.path.exists(p):
            raise SystemExit(f"{p} is missing -- run tools/fetch_census.py")
        out[role] = p
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true",
                    help="delete the cached checkout and clone again")
    a = ap.parse_args()

    fetched = clone(a.force)
    p = paths()
    record = {
        "repository": REPO,
        "commit": head(),
        "cache_dir": CACHE_DIR,
        "licence": "Creative Commons Attribution 4.0 (CC BY 4.0)",
        "upstream_source": "Institut National de la Statistique, Recensement "
                           "General de la Population et de l'Habitat 2014",
        "note": "Delegation-level 2014 census, 169 variables over 264 "
                "delegations. Cached under .cache/ and gitignored; this record "
                "is what makes the fetch reproducible. Read by "
                "tools/model_saied_2019.py.",
        "files": {role: {"path": path, "bytes": os.path.getsize(path),
                         "sha256": sha256(path)} for role, path in p.items()},
    }
    prior = None
    if os.path.exists(PROVENANCE):
        with open(PROVENANCE, encoding="utf-8") as fh:
            prior = json.load(fh)
    os.makedirs(os.path.dirname(PROVENANCE), exist_ok=True)
    with open(PROVENANCE, "w", encoding="utf-8") as fh:
        json.dump(record, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")

    print(("cloned" if fetched else "already cached") + f": {CACHE_DIR}")
    print(f"commit {record['commit']}")
    for role, f in sorted(record["files"].items()):
        moved = ""
        if prior and prior.get("files", {}).get(role, {}).get("sha256") not in (
                None, f["sha256"]):
            moved = "   CHANGED since the last record"
        print(f"  {role:<9} {f['bytes']:>9,} bytes  {f['sha256'][:16]}{moved}")
    print(f"wrote {PROVENANCE}")


if __name__ == "__main__":
    main()
