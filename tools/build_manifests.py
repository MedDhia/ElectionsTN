"""Turn the raw Drive crawl (inventory/drive_tree.jsonl) into analysis-ready manifests."""
import csv, gzip, json, os, collections

SRC = "inventory/drive_tree.jsonl.gz"   # crawl_drive.py writes the plain .jsonl

# Election collections whose folder tree encodes electoral geography, with the
# meaning of each path level below the collection root.
COLLECTIONS = {
    "2024/PvCvPresidentielle24": ("presidentielle_2024", "pv_centre_vote",
        ["governorate", "delegation", "sector", "polling_centre", "extra1", "extra2"]),
    "2023/PvLegTour1": ("legislatives_2023_t1", "pv",
        ["scope", "governorate", "constituency", "polling_centre", "bureau", "document"]),
    "2023/ElecLocPvTour1": ("locales_2023_t1", "pv",
        ["constituency", "batch", "delegation", "imada", "polling_centre", "bureau"]),
    "filebases/pv-legislative2019": ("legislatives_2019", "pv",
        ["scope", "country_or_governorate", "city_or_delegation", "polling_centre", "bureau", "document"]),
    "2024/ListesElecteurs06Juillet2024": ("electeurs_2024", "liste_electorale",
        ["scope", "governorate", "constituency", "extra1", "extra2", "extra3"]),
    "2023/ResultatsLocales2023": ("locales_2023", "resultats",
        ["governorate", "delegation", "extra1", "extra2", "extra3", "extra4"]),
    "2024/ResultatsFinaux2emeTour": ("locales_2024_t2", "resultats_finaux",
        ["constituency", "delegation", "extra1", "extra2", "extra3", "extra4"]),
    "2024/Resultats1erTour": ("locales_2024_t1", "resultats",
        ["constituency", "delegation", "extra1", "extra2", "extra3", "extra4"]),
    "2024/Resultats2emeTour": ("locales_2024_t2", "resultats",
        ["constituency", "delegation", "extra1", "extra2", "extra3", "extra4"]),
    "2024/PV2emeTour": ("locales_2024_t2", "pv",
        ["governorate", "delegation", "extra1", "extra2", "extra3", "extra4"]),
    "2023/TemplateCandidats2023": ("locales_2023", "candidats",
        ["constituency", "delegation", "extra1", "extra2", "extra3", "extra4"]),
    "2024/CompositionConseilLocales": ("conseils_locaux_2024", "composition",
        ["governorate", "extra1", "extra2", "extra3", "extra4", "extra5"]),
    "2024/ExemplaireBVTour2": ("locales_2024_t2", "bulletin_vote",
        ["governorate", "delegation", "extra1", "extra2", "extra3", "extra4"]),
}


def load():
    seen = {}
    opener = gzip.open if SRC.endswith(".gz") else open
    with opener(SRC, "rt", encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            seen[r["path"]] = r          # crawl appends; last write wins
    return list(seen.values())


def write(path, fieldnames, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows):7d} rows -> {path}")


def main():
    rows = load()

    # 1. Full node manifest.
    write("inventory/drive_tree.csv",
          ["path", "name", "kind", "mime", "drive_id", "depth"],
          [{"path": r["path"], "name": r["name"], "kind": r["kind"], "mime": r["mime"],
            "drive_id": r["id"], "depth": r["path"].count("/")} for r in rows])

    # 2. Downloadable files only.
    files = [r for r in rows if r["kind"] == "file"]
    write("inventory/files.csv",
          ["path", "name", "ext", "mime", "drive_id", "download_url"],
          [{"path": r["path"], "name": r["name"],
            "ext": os.path.splitext(r["name"])[1].lower().lstrip("."),
            "mime": r["mime"], "drive_id": r["id"],
            "download_url": (f"https://docs.google.com/document/d/{r['id']}/export?format=txt"
                             if r["mime"] == "google-document"
                             else f"https://drive.google.com/uc?export=download&id={r['id']}")}
           for r in sorted(files, key=lambda x: x["path"])])

    # 3. Electoral-geography gazetteer derived from the folder skeleton.
    gaz, seen = [], set()
    for coll, (election, doctype, levels) in COLLECTIONS.items():
        prefix = f"/wp-content/uploads/{coll}/"
        for r in rows:
            if not r["path"].startswith(prefix):
                continue
            parts = r["path"][len(prefix):].split("/")
            rec = {"election": election, "doc_type": doctype, "collection": coll,
                   "node_kind": r["kind"], "level": len(parts),
                   "drive_id": r["id"], "path": r["path"]}
            for i, lvl in enumerate(levels):
                rec[lvl] = parts[i] if i < len(parts) else ""
            key = (election, coll, r["path"])
            if key in seen:
                continue
            seen.add(key)
            gaz.append(rec)
    fields = (["election", "doc_type", "collection", "node_kind", "level"]
              + sorted({k for r in gaz for k in r} - {"election", "doc_type", "collection",
                                                      "node_kind", "level", "drive_id", "path"})
              + ["drive_id", "path"])
    write("inventory/electoral_geography.csv", fields,
          [{f: r.get(f, "") for f in fields} for r in gaz])

    # 4. Per-collection summary.
    summ = collections.Counter()
    nfiles = collections.Counter()
    for r in rows:
        p = r["path"].split("/")
        key = "/".join(p[3:5]) if len(p) > 5 and p[1] == "wp-content" and p[2] == "uploads" else p[1]
        summ[key] += 1
        if r["kind"] == "file":
            nfiles[key] += 1
    write("inventory/collections_summary.csv",
          ["collection", "nodes", "files", "empty_folders"],
          [{"collection": k, "nodes": v, "files": nfiles[k], "empty_folders": v - nfiles[k]}
           for k, v in sorted(summ.items(), key=lambda x: -x[1])])


if __name__ == "__main__":
    main()
