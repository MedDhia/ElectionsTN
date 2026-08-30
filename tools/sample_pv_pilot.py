"""Draw and download a stratified pilot sample of 2024 presidential PVs.

The 2024 presidential collection is the one uniform template in the archive —
a single pre-printed form per polling bureau, three candidates, one image per
bureau for 8,820 of 9,448 bureaux. The locales collections mix correction pages
and multi-page documents, so the pilot deliberately scopes to the presidential
set.

Usage: python3 tools/sample_pv_pilot.py [n] [seed]
"""
import csv, os, random, re, sys, time, urllib.parse, urllib.request
from collections import Counter, defaultdict

INDEX = "data/pv_index.csv"
OUT_DIR = ".cache/pv_pilot"
MANIFEST = ".cache/pv_pilot/sample.csv"
PURE_CODE = re.compile(r"^\d{11}$")


def fetch(url, dest, tries=3):
    if os.path.exists(dest) and os.path.getsize(dest) > 2048:
        return True
    safe = urllib.parse.quote(url, safe=":/")
    for attempt in range(tries):
        try:
            req = urllib.request.Request(safe, headers={"User-Agent": "Mozilla/5.0"})
            data = urllib.request.urlopen(req, timeout=180).read()
            if len(data) < 2048:
                raise OSError("short read")
            with open(dest + ".part", "wb") as fh:
                fh.write(data)
            os.replace(dest + ".part", dest)
            return True
        except Exception:
            if attempt == tries - 1:
                return False
            time.sleep(2 ** attempt)


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 7
    os.makedirs(OUT_DIR, exist_ok=True)

    with open(INDEX, encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh) if r["election"] == "presidentielle_2024"]

    # One image per bureau, unambiguous filename, so the code in the image can be
    # checked against the code in the path.
    per_code = Counter(r["bureau_code"] for r in rows)
    pool = [r for r in rows
            if r["file_ext"] == "jpg"
            and PURE_CODE.match(r["filename"].rsplit(".", 1)[0])
            and per_code[r["bureau_code"]] == 1]

    by_gov = defaultdict(list)
    for r in pool:
        by_gov[r["governorate"]].append(r)
    rng = random.Random(seed)

    # Spread across governorates: round-robin so every governorate is represented
    # before any is sampled twice.
    for v in by_gov.values():
        rng.shuffle(v)
    govs = sorted(by_gov)
    rng.shuffle(govs)
    sample, i = [], 0
    while len(sample) < n and any(by_gov[g] for g in govs):
        g = govs[i % len(govs)]
        if by_gov[g]:
            sample.append(by_gov[g].pop())
        i += 1

    print(f"pool {len(pool)} single-image bureaux across {len(by_gov)} governorates")
    ok = []
    for r in sample:
        dest = os.path.join(OUT_DIR, f"{r['bureau_code']}.jpg")
        if fetch(r["file_url"], dest):
            r["local_path"] = dest
            r["bytes"] = os.path.getsize(dest)
            ok.append(r)
        else:
            print("  download failed:", r["file_url"])

    fields = ["bureau_code", "governorate", "delegation", "sector", "polling_centre",
              "filename", "file_url", "local_path", "bytes"]
    with open(MANIFEST, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(ok)
    print(f"downloaded {len(ok)}/{len(sample)} -> {OUT_DIR}")
    print("governorates in sample:", len({r['governorate'] for r in ok}))


if __name__ == "__main__":
    main()
