"""Enumerate a public Google Drive folder tree without API credentials.

Uses Drive's `embeddedfolderview` endpoint, which renders a public folder's
listing as plain HTML. Walks breadth-first and writes one JSON object per node
to inventory/drive_tree.jsonl.

Usage: python3 tools/crawl_drive.py [folder_id] [max_depth]
"""
import json, os, re, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = sys.argv[1] if len(sys.argv) > 1 else "1FfyVtwp-YqLpS4VCDOnoM03bjDn1oL0_"
MAX_DEPTH = int(sys.argv[2]) if len(sys.argv) > 2 else 12
OUT = "inventory/drive_tree.jsonl"
WORKERS = 16


def fetch(folder_id, tries=3):
    url = f"https://drive.google.com/embeddedfolderview?id={folder_id}#list"
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            return urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")
        except Exception:
            if attempt == tries - 1:
                return ""
            time.sleep(2 ** attempt)


def parse(html):
    """Pull (id, name, kind, mime) out of a rendered folder listing."""
    nodes = []
    for chunk in html.split('<div class="flip-entry" id="entry-')[1:]:
        node_id = chunk.split('"', 1)[0]
        href = re.search(r'<a href="([^"]+)"', chunk)
        title = re.search(r'<div class="flip-entry-title">(.*?)</div>', chunk, re.S)
        if not href or not title:
            continue
        name = re.sub(r"<[^>]+>", "", title.group(1)).strip()
        if "/drive/folders/" in href.group(1):
            kind, mime = "folder", "folder"
        else:
            kind = "file"
            icon = re.search(r"drive-thirdparty\.googleusercontent\.com/128/type/([^\"]+)\"", chunk)
            gdoc = re.search(r"docs\.google\.com/(\w+)/d/", href.group(1))
            mime = icon.group(1) if icon else (f"google-{gdoc.group(1)}" if gdoc else "unknown")
        nodes.append({"id": node_id, "name": name, "kind": kind, "mime": mime})
    return nodes


def main():
    os.makedirs("inventory", exist_ok=True)
    seen, total = set(), 0
    level = [("", ROOT)]
    with open(OUT, "w", encoding="utf-8") as out:
        for depth in range(MAX_DEPTH):
            if not level:
                break
            print(f"depth {depth}: expanding {len(level)} folders", flush=True)
            nxt = []
            with ThreadPoolExecutor(max_workers=WORKERS) as pool:
                results = pool.map(lambda it: (it[0], parse(fetch(it[1]))), level)
                for path, children in results:
                    for child in children:
                        child_path = f"{path}/{child['name']}"
                        out.write(json.dumps({"path": child_path, **child}, ensure_ascii=False) + "\n")
                        total += 1
                        if child["kind"] == "folder" and child["id"] not in seen:
                            seen.add(child["id"])
                            nxt.append((child_path, child["id"]))
            out.flush()
            level = nxt
            print(f"  {total} nodes so far", flush=True)
    print(f"done: {total} nodes, {len(level)} folders left unexpanded")


if __name__ == "__main__":
    main()
