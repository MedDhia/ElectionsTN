"""Fetch the outside measurements the Saied model uses as covariates.

Two sources, neither of them an election, both of them measured before the vote
being predicted:

**`MedDhia/rgph2014tn`** -- an R package wrapping Tunisia's 2014 *Recensement
Général de la Population et de l'Habitat* (INS) at delegation level: 169
variables over 264 delegations, CC BY 4.0. The package ships the merged table as
a gzipped CSV under `inst/extdata/`, so nothing here needs R. The census was
taken in April 2014, five years before the vote.

**`MedDhia/ConsumptionSurveysTN`** -- datasets built from INS's household budget
survey and from the *Annuaire Statistique de la Tunisie*. Two files are used: a
governorate-by-year panel of published statistics, from which the model takes 29
per-head indicators at their latest year up to 2018, and the 2015 small-area
poverty map at delegation level.

Why these and not the ISIE archive: they are the only measurements of the
electorate in this project that are not themselves elections, so they can
distinguish a place's social structure from its voting history.

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

PROVENANCE = "data/verification/census_source.json"

# `master_merged` is the census table; `codebook` names every variable's unit and
# denominator, which is what makes a correct population-weighted aggregation
# possible at all. From the survey repository: the governorate panel already
# reduced to comparable per-head series, and the delegation poverty map.
SOURCES = {
    "census": {
        "repo": "https://github.com/MedDhia/rgph2014tn",
        "cache": ".cache/census/rgph2014tn",
        "licence": "Creative Commons Attribution 4.0 (CC BY 4.0)",
        "upstream": "Institut National de la Statistique, Recensement General "
                    "de la Population et de l'Habitat 2014",
        "files": {"master": "inst/extdata/master_merged.csv.gz",
                  "codebook": "inst/extdata/codebook.csv"},
    },
    "surveys": {
        "repo": "https://github.com/MedDhia/ConsumptionSurveysTN",
        "cache": ".cache/census/consumptionsurveystn",
        "licence": "see the repository",
        "upstream": "Institut National de la Statistique, Annuaire Statistique "
                    "de la Tunisie and Carte de la pauvrete en Tunisie (2020)",
        "files": {"yearbook": "data/processed/tn_governorate_comparable.csv",
                  "poverty": "data/processed/tn_poverty_delegations_2015.csv"},
    },
}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def clone(source, force=False):
    cache = SOURCES[source]["cache"]
    if force and os.path.isdir(cache):
        shutil.rmtree(cache)
    if os.path.isdir(os.path.join(cache, ".git")):
        return False
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    env = dict(os.environ, GIT_LFS_SKIP_SMUDGE="1")
    subprocess.run(["git", "clone", "--depth", "1", SOURCES[source]["repo"],
                    cache], check=True, env=env)
    return True


def head(source):
    out = subprocess.run(["git", "-C", SOURCES[source]["cache"], "rev-parse",
                          "HEAD"], check=True, capture_output=True, text=True)
    return out.stdout.strip()


def paths(source="census"):
    """{role: path} for the files the model reads, checked to exist."""
    out = {}
    for role, rel in SOURCES[source]["files"].items():
        p = os.path.join(SOURCES[source]["cache"], rel)
        if not os.path.exists(p):
            raise SystemExit(f"{p} is missing -- run tools/fetch_census.py")
        out[role] = p
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true",
                    help="delete the cached checkout and clone again")
    a = ap.parse_args()

    prior = None
    if os.path.exists(PROVENANCE):
        with open(PROVENANCE, encoding="utf-8") as fh:
            prior = json.load(fh)

    record = {"note": "Outside covariates for tools/model_saied_2019.py, "
                      "cached under .cache/ and gitignored. This record is what "
                      "makes the fetch reproducible: it names the commit each "
                      "file came from and its SHA-256, so a later reader can "
                      "tell whether the upstream data moved under a published "
                      "result.", "sources": {}}
    for source in SOURCES:
        fetched = clone(source, a.force)
        p = paths(source)
        record["sources"][source] = {
            "repository": SOURCES[source]["repo"],
            "commit": head(source),
            "cache_dir": SOURCES[source]["cache"],
            "licence": SOURCES[source]["licence"],
            "upstream_source": SOURCES[source]["upstream"],
            "files": {role: {"path": path, "bytes": os.path.getsize(path),
                             "sha256": sha256(path)}
                      for role, path in p.items()},
        }
        print(("cloned" if fetched else "already cached") +
              f": {SOURCES[source]['cache']}   commit "
              f"{record['sources'][source]['commit'][:12]}")
        was = (prior or {}).get("sources", {}).get(source, {}).get("files", {})
        for role, f in sorted(record["sources"][source]["files"].items()):
            moved = ("   CHANGED since the last record"
                     if was.get(role, {}).get("sha256") not in
                     (None, f["sha256"]) else "")
            print(f"  {role:<9} {f['bytes']:>10,} bytes  "
                  f"{f['sha256'][:16]}{moved}")

    os.makedirs(os.path.dirname(PROVENANCE), exist_ok=True)
    with open(PROVENANCE, "w", encoding="utf-8") as fh:
        json.dump(record, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    print(f"wrote {PROVENANCE}")


if __name__ == "__main__":
    main()
