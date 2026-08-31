"""Cache every 2024 presidential PV locally so an extraction run is I/O-free.

Resumable: already-downloaded files are skipped, so this can be re-run after an
interruption. Files land in .cache/pv_all/<bureau_code>__<filename>.

Usage: python3 tools/download_all_pvs.py [workers]
"""
import csv, os, sys, threading, time, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor

INDEX = "data/pv_index.csv"
DEST = ".cache/pv_all"
LOG = ".cache/pv_all_manifest.csv"

lock = threading.Lock()
done = {"ok": 0, "skip": 0, "fail": 0, "bytes": 0}


def target(row):
    safe = row["filename"].replace("/", "_")
    return os.path.join(DEST, f"{row['bureau_code'] or 'nocode'}__{safe}")


def fetch(row, tries=3):
    path = target(row)
    if os.path.exists(path) and os.path.getsize(path) > 2048:
        with lock:
            done["skip"] += 1
        return path, "cached"
    url = urllib.parse.quote(row["file_url"], safe=":/")
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            data = urllib.request.urlopen(req, timeout=180).read()
            if len(data) < 2048:
                raise OSError("short read")
            with open(path + ".part", "wb") as fh:
                fh.write(data)
            os.replace(path + ".part", path)
            with lock:
                done["ok"] += 1
                done["bytes"] += len(data)
            return path, "ok"
        except Exception as exc:
            if attempt == tries - 1:
                with lock:
                    done["fail"] += 1
                return path, f"fail: {type(exc).__name__}"
            time.sleep(2 ** attempt)


def main():
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    os.makedirs(DEST, exist_ok=True)
    with open(INDEX, encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh) if r["election"] == "presidentielle_2024"]
    print(f"{len(rows)} presidential files", flush=True)

    results = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for i, (path, status) in enumerate(pool.map(fetch, rows), 1):
            results.append((rows[i - 1]["bureau_code"], path, status))
            if i % 250 == 0:
                print(f"  {i}/{len(rows)}  ok={done['ok']} cached={done['skip']} "
                      f"fail={done['fail']}  {done['bytes']/1e9:.2f} GB", flush=True)

    with open(LOG, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["bureau_code", "local_path", "status"])
        w.writerows(results)
    print(f"done: ok={done['ok']} cached={done['skip']} fail={done['fail']} "
          f"({done['bytes']/1e9:.2f} GB) -> {DEST}")


if __name__ == "__main__":
    main()
