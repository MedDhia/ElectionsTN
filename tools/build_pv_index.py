"""Dataset 8 — polling-station PV index, recovered from the live ISIE site.

The Drive archive preserved the procès-verbaux directory tree but none of the
files. The live site still serves them, rendered by a php_file_tree widget that
emits the whole tree inline, so the complete index can be recovered from a
handful of page fetches.

Each leaf is a scan of one polling bureau's PV, named for its bureau code (an
11-digit identifier such as 03010110101). This builds the index — geography,
bureau code and file URL — not the scans themselves; the PVs are handwritten
forms, and downloading ~23,600 images is a separate exercise.

Usage: python3 tools/build_pv_index.py
"""
import csv, html, re, sys, time, urllib.parse, urllib.request
from collections import Counter

OUT = "data/pv_index.csv"
BASE = "https://www.isie.tn"
# Each page hosts one election's file tree.
PAGES = [
    ("presidentielle_2024", "pv_centre_vote", "/ar/presidentielle-pv-centre-de-vote/",
     ["governorate", "delegation", "sector", "polling_centre"]),
    ("locales_2023_t1", "pv", "/ar/pv-resultats-elections-locales-1er-tour/",
     ["scope", "governorate", "constituency", "polling_centre", "bureau_folder"]),
    ("locales_2023_t2", "exemplaire_bv", "/elections-locales-exemplaire-bv-second-tour/",
     ["governorate", "delegation", "polling_centre"]),
]
LINK = re.compile(r'href="(https://www\.isie\.tn/wp-content/uploads/[^"]+)"')
# Windows leftovers and interrupted uploads sit in the same folders as the scans.
JUNK_EXT = {"ini", "lnk", "filepart", "db", "tmp"}
BUREAU = re.compile(r"(\d{8,13})")


def fetch(url, tries=3):
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            return urllib.request.urlopen(req, timeout=180).read().decode("utf-8", "replace")
        except Exception:
            if attempt == tries - 1:
                raise
            time.sleep(2 ** attempt)


def main():
    rows = []
    for election, doc_type, page, levels in PAGES:
        body = fetch(BASE + page)
        links = [html.unescape(u) for u in LINK.findall(body)]
        seen = set()
        for url in links:
            if url in seen:
                continue
            seen.add(url)
            decoded = urllib.parse.unquote(url)
            tail = decoded.split("/wp-content/uploads/", 1)[1]
            parts = tail.split("/")
            # parts[0] is the year folder, parts[1] the collection.
            collection = parts[1] if len(parts) > 1 else ""
            path_parts, filename = parts[2:-1], parts[-1]
            rec = {"election": election, "doc_type": doc_type, "collection": collection,
                   "filename": filename,
                   "file_ext": filename.rsplit(".", 1)[-1].lower() if "." in filename else "",
                   "file_url": url, "path": tail}
            for i, level in enumerate(levels):
                rec[level] = path_parts[i] if i < len(path_parts) else ""
            m = BUREAU.search(filename)
            rec["bureau_code"] = m.group(1) if m else ""
            if rec["file_ext"] in JUNK_EXT:
                continue
            rows.append(rec)
        print(f"{election}: {len(seen)} links from {page}")

    fields = ["election", "doc_type", "collection", "scope", "governorate", "delegation",
              "constituency", "sector", "polling_centre", "bureau_folder", "bureau_code",
              "filename", "file_ext", "file_url", "path"]
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({f: r.get(f, "") for f in fields})
    print(f"\nwrote {len(rows)} rows -> {OUT}")
    print("  by election:", dict(Counter(r["election"] for r in rows)))
    print("  by extension:", dict(Counter(r["file_ext"] for r in rows).most_common(5)))
    print("  with bureau code:", sum(1 for r in rows if r["bureau_code"]))
    pres = [r for r in rows if r["election"] == "presidentielle_2024"]
    print("  presidentielle 2024: %d governorates, %d delegations, %d centres" % (
        len({r["governorate"] for r in pres if r["governorate"]}),
        len({(r["governorate"], r["delegation"]) for r in pres if r["delegation"]}),
        len({(r["governorate"], r["delegation"], r["polling_centre"]) for r in pres if r["polling_centre"]})))


if __name__ == "__main__":
    main()
