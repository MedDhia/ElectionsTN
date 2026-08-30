"""Pre-download a subset of the manifest into the local cache."""
import sys
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, "tools")
from _fetch import manifest, fetch

PATTERN = sys.argv[1]
rows = manifest(lambda r: PATTERN in r["path"] and r["ext"] == "pdf")
print(f"{len(rows)} files match {PATTERN!r}", flush=True)
ok = 0
with ThreadPoolExecutor(max_workers=8) as pool:
    for i, path in enumerate(pool.map(fetch, rows), 1):
        ok += path is not None
        if i % 25 == 0:
            print(f"  {i}/{len(rows)} ({ok} ok)", flush=True)
print(f"done: {ok}/{len(rows)} cached")
