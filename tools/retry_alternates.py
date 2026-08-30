"""Retry the bureaux that failed, using the other scan ISIE published of them.

ISIE serves nothing better at a given URL — every file fetched back matches the
copy already held, byte for byte, and the PVs sit in a custom upload directory so
WordPress generates no resized variants. There is no higher-resolution original to
go and get.

But 629 presidential bureaux appear in the index more than once, filed under two
polling-centre paths, and some of those really are different scans of the same
form rather than the same file linked twice. The downloader kept one copy per
bureau — same basename, so the second overwrote or was skipped as cached — and the
reader has only ever seen whichever arrived. Where the copy it saw is unreadable,
the other one may not be.

This re-reads every bureau whose votes are not yet vouched for and which has an
alternative, and keeps whichever scan the form's own identities like better. The
upright cache is updated in place, so a normal `decode_all` run afterwards picks
the improvement up.

Usage: python3 tools/retry_alternates.py [--limit N] [--workers 3]
"""
import argparse, collections, csv, os, sys
import urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

INDEX = "data/pv_index.csv"
RESULTS = "data/pv_presidential_2024.csv"
MANIFEST = ".cache/pv_all_manifest.csv"
ALT_DIR = ".cache/pv_alt"
UPRIGHT = ".cache/pv_upright"
UA = {"User-Agent": "Mozilla/5.0"}


def encode(url):
    q = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((q.scheme, q.netloc,
                                    urllib.parse.quote(q.path), "", ""))


def candidates():
    """{bureau: [source path or url]} for bureaux without certified votes."""
    idx = [r for r in csv.DictReader(open(INDEX, encoding="utf-8"))
           if r["election"] == "presidentielle_2024"]
    res = {r["bureau_code"]: r for r in csv.DictReader(open(RESULTS, encoding="utf-8"))}
    held = collections.defaultdict(list)
    for f in os.listdir(".cache/pv_all"):
        held[f.split("__", 1)[0]].append(os.path.join(".cache/pv_all", f))
    per = collections.defaultdict(list)
    for r in idx:
        per[r["bureau_code"]].append(r)
    out = {}
    for b, rows in per.items():
        if res.get(b, {}).get("votes_certified") == "1":
            continue
        urls = sorted({r["file_url"] for r in rows})
        if len(urls) < 2 and len(held.get(b, [])) < 2:
            continue
        out[b] = (sorted(held.get(b, [])), urls)
    return out


def download(bureau, urls, workers):
    """Fetch any alternative not already on disk; returns local paths."""
    os.makedirs(ALT_DIR, exist_ok=True)
    paths = []
    for i, u in enumerate(urls):
        ext = os.path.splitext(urllib.parse.urlsplit(u).path)[1] or ".jpg"
        dest = os.path.join(ALT_DIR, f"{bureau}__{i}{ext}")
        if os.path.exists(dest):
            paths.append(dest)
            continue
        try:
            with urllib.request.urlopen(
                    urllib.request.Request(encode(u), headers=UA), timeout=90) as r:
                data = r.read()
            if len(data) > 1000:
                open(dest, "wb").write(data)
                paths.append(dest)
        except Exception:
            pass
    return paths


def rank(got):
    return (got["whole_form"], len(got["certified"]),
            -(got["info"]["changed"] if got["info"] else 99))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--model", default=".cache/digit_cnn.pt")
    a = ap.parse_args()

    import torch
    from digit_model import Net, predict_proba
    from decode_all import read_image
    from extract_pvs import _load_best_page
    torch.set_num_threads(os.cpu_count() or 4)
    net = Net()
    net.load_state_dict(torch.load(a.model, map_location="cpu"))
    net.eval()
    predict = lambda X: predict_proba(net, X)

    todo = candidates()
    codes = sorted(todo)[:a.limit] if a.limit else sorted(todo)
    print(f"{len(codes)} bureaux without certified votes that have another scan",
          flush=True)

    # Fetch first, in parallel, so the reading loop is not waiting on the network.
    with ThreadPoolExecutor(a.workers) as ex:
        fetched = list(ex.map(lambda b: download(b, todo[b][1], a.workers), codes))

    improved = tried = 0
    for b, alts in zip(codes, fetched):
        local, _ = todo[b]
        sources = list(dict.fromkeys(local + alts))
        cur = os.path.join(UPRIGHT, f"{b}.jpg")
        best, best_img = None, None
        if os.path.exists(cur):
            img = cv2.imread(cur)
            if img is not None:
                got = read_image(img, predict)
                if got:
                    best = rank(got)
        for src in sources:
            try:
                page, _deg, _sc = _load_best_page(src)
                if page is None:
                    continue
                img = cv2.cvtColor(np.array(page.convert("RGB")), cv2.COLOR_RGB2BGR)
            except Exception:
                continue
            got = read_image(img, predict)
            if not got:
                continue
            r = rank(got)
            if best is None or r > best:
                best, best_img = r, img
        tried += 1
        if best_img is not None:
            cv2.imwrite(cur, best_img, [cv2.IMWRITE_JPEG_QUALITY, 92])
            improved += 1
        if tried % 25 == 0:
            print(f"  {tried}/{len(codes)}  {improved} replaced", flush=True)

    print(f"\ntried {tried}, replaced the cached scan for {improved}")
    print("re-run tools/decode_all.py to pick the improvements up")


if __name__ == "__main__":
    main()
