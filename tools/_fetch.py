"""Shared helpers: read the file manifest and fetch/cache Drive files."""
import csv, os, time, urllib.request

CACHE = ".cache/pdfs"
MANIFEST = "inventory/files.csv"


def manifest(predicate=None):
    with open(MANIFEST, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    return [r for r in rows if predicate is None or predicate(r)]


def fetch(row, tries=4):
    """Download a manifest row to the cache, returning the local path."""
    os.makedirs(CACHE, exist_ok=True)
    dest = os.path.join(CACHE, f"{row['drive_id']}.pdf")
    if os.path.exists(dest) and os.path.getsize(dest) > 1024:
        return dest
    url = f"https://drive.google.com/uc?export=download&id={row['drive_id']}"
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            data = urllib.request.urlopen(req, timeout=180).read()
            if len(data) < 1024:
                raise OSError(f"short read ({len(data)} bytes)")
            tmp = dest + ".part"
            with open(tmp, "wb") as fh:
                fh.write(data)
            os.replace(tmp, dest)
            return dest
        except Exception:
            if attempt == tries - 1:
                return None
            time.sleep(2 ** attempt)
