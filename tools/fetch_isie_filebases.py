"""Recover ISIE's `filebases/` archive from the Wayback Machine.

What is in there
----------------
ISIE served a `wp-content/uploads/filebases/` tree holding the raw counting
record for several elections, one file per polling bureau. The whole tree is
gone from isie.tn -- every pre-2020 upload 404s -- but the Wayback Machine
holds it. `--survey` enumerates it from the CDX index:

    pv-bv-presidentielles              18,109  jpg/pdf   scans, per bureau
    pv-elections-legislatives          17,238  jpg/pdf   scans, per bureau
    pv-bv-presidentielles-tour2        12,735  jpg/pdf   scans, per bureau
    pv-legislative2019                  8,753  pdf       scans, per bureau, 2019
    pv-auto-bv-presidentielles-tour2      270  xlsx      *tabulated*, per bureau
    controleCampagne                       39            campaign finance

Two counting traps, both of which caught me:

* **`pv-bv-presidentielles` is a string prefix of `pv-bv-presidentielles-tour2`,**
  so a `/pv-bv-presidentielles/*` query returns both. It answers 30,844, of
  which 12,735 are the runoff -- the round-one figure above is the difference.
  Split on the first path segment, do not trust the prefix.
* **CDX ignores `offset`.** Twelve "pages" of it returned the same rows twelve
  times, which showed up as every tree being inflated by exactly 12.0x. Real
  pagination is `showResumeKey=true`, then `resumeKey=` on the next request --
  and the response may arrive as several *concatenated* JSON documents, which
  `json.loads` rejects with "Extra data". Decode with `raw_decode` in a loop.

The path names carry no year, and one of them is actively misleading.

`pv-auto-bv-presidentielles-tour2` is the 2014 runoff, not 2019
---------------------------------------------------------------
Its candidate columns read محمد الباجي القايد السبسي and محمد المنصف المرزوقي
-- Beji Caid Essebsi and Moncef Marzouki, who contested the **December 2014**
runoff. The 2019 runoff was Saied against Karoui. The `20191026093137` in the
URL is Wayback's capture date, not the election's. Read the candidate names
before trusting any tree's apparent year; the path will not tell you.

That tree is the valuable one regardless: 270 workbooks, one sheet
`resultatParDelegation` each, one row per polling bureau, 11-digit bureau codes
in the same format `data/pv_presidential_2024.csv` uses, votes per candidate and
a row total. It needs parsing, not OCR.

Everything else is scans of handwritten forms -- the problem
`tools/read_representatives.py` and the 2024 decode pipeline already solve, but
a reading project rather than a parse.

Enumerate, do not guess
-----------------------
ISIE's ASCII spellings are close to `data/delegations_ins.csv` but not identical
(`Tozeur/Tameghza` matches exactly; `Cité Ettadhamen` appears as
`Ariana/Ettadhamen`), so generating candidate names would mis-hit an unknown
number, and a wrong name is indistinguishable from an unarchived one. The CDX
index gives the real paths.

Two things the archive requires
-------------------------------
* **CDX over HTTPS.** The plain-HTTP endpoint answers 403.
* **Patience.** The archive rate-limits and resets connections freely, so
  `get()` retries with a backoff and `--download` is resumable: it skips files
  already in the cache, so an interrupted run is re-run, not restarted.
"""

import argparse
import csv
import json
import os
import sys
import time
import urllib.parse
import urllib.request

CDX = "https://web.archive.org/cdx/search/cdx"
BASE = "isie.tn/wp-content/uploads/filebases"
SNAPSHOT = "20191026093137"          # the capture the confirmed URLs come from
CACHE = ".cache/isie2019"
OUT = "data/verification/2019_bureau_sources.jsonl"
CONFIRMED = [
    "http://www.isie.tn/wp-content/uploads/filebases/"
    "pv-auto-bv-presidentielles-tour2/Tunisie/Ariana/Ettadhamen.xlsx",
    "http://www.isie.tn/wp-content/uploads/filebases/"
    "pv-auto-bv-presidentielles-tour2/Tunisie/Tozeur/Tameghza.xlsx",
]


def get(url, tries=4, timeout=120):
    """Fetch bytes, retrying: the archive rate-limits and resets freely."""
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ElectionsTN/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as fh:
                return fh.read()
        except Exception as exc:                      # noqa: BLE001
            last = exc
            time.sleep(2 ** attempt * 3)
    raise OSError(f"{url}: {last}")


def cdx(pattern, limit=50000):
    """Every distinct archived URL under `pattern`."""
    q = (f"{CDX}?url={urllib.parse.quote(pattern, safe='')}"
         f"&output=json&fl=original,timestamp,statuscode,length"
         f"&collapse=urlkey&limit={limit}")
    raw = get(q).decode("utf-8", "replace").strip()
    if not raw:
        return []
    rows = json.loads(raw)
    return [dict(zip(rows[0], r)) for r in rows[1:]]


def replay(original, timestamp):
    """The raw (un-rewritten) Wayback URL, so the bytes are the original file."""
    return f"https://web.archive.org/web/{timestamp}id_/{original}"


def survey():
    """Which filebases trees does the archive know about?"""
    rows = cdx(f"{BASE}/*")
    print(f"{len(rows)} archived URLs under {BASE}/")
    trees = {}
    for r in rows:
        rest = r["original"].split("/filebases/", 1)[-1]
        trees.setdefault(rest.split("/")[0], []).append(r)
    for name, rs in sorted(trees.items(), key=lambda kv: -len(kv[1])):
        ok = sum(1 for r in rs if r.get("statuscode") == "200")
        print(f"  {name:<48} {len(rs):>6} urls, {ok} at 200")
    return trees


def plan(tree):
    """Per-delegation workbooks in one tree, as (governorate, delegation, url)."""
    rows = [r for r in cdx(f"{BASE}/{tree}/*")
            if r["original"].lower().endswith((".xlsx", ".xls"))]
    out = []
    for r in rows:
        parts = urllib.parse.unquote(r["original"]).split("/filebases/")[-1].split("/")
        # <tree>/Tunisie/<governorate>/<delegation>.xlsx, or a deeper variant
        if len(parts) < 3:
            continue
        gov, deleg = parts[-2], os.path.splitext(parts[-1])[0]
        out.append({"tree": tree, "governorate": gov, "delegation": deleg,
                    "url": r["original"], "timestamp": r["timestamp"],
                    "status": r.get("statuscode"), "length": r.get("length")})
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--survey", action="store_true",
                    help="list every filebases tree the archive holds")
    ap.add_argument("--plan", metavar="TREE",
                    help="list the workbooks in one tree without downloading")
    ap.add_argument("--probe", action="store_true",
                    help="fetch only the two confirmed URLs, to prove the route")
    ap.add_argument("--download", metavar="TREE",
                    help="download every workbook in a tree into .cache")
    ap.add_argument("--write", action="store_true",
                    help=f"record what was found in {OUT}")
    args = ap.parse_args()

    if args.probe:
        os.makedirs(CACHE, exist_ok=True)
        for u in CONFIRMED:
            try:
                body = get(replay(u, SNAPSHOT))
            except OSError as exc:
                print(f"  FAIL {u.split('/')[-1]}: {exc}")
                continue
            name = "__".join(u.split("/filebases/")[-1].split("/"))
            open(os.path.join(CACHE, name), "wb").write(body)
            head = body[:4]
            kind = ("xlsx/zip" if head[:2] == b"PK" else
                    "xls/ole" if head == b"\xd0\xcf\x11\xe0" else repr(head))
            print(f"  ok   {name}  {len(body)} bytes, {kind}")
        return 0

    if args.survey:
        trees = survey()
        if args.write and trees:
            os.makedirs(os.path.dirname(OUT), exist_ok=True)
            with open(OUT, "w", encoding="utf-8") as fh:
                for name, rs in trees.items():
                    json.dump({"record": "tree", "name": name,
                               "urls": len(rs)}, fh)
                    fh.write("\n")
            print(f"wrote {OUT}")
        return 0

    if args.plan:
        rows = plan(args.plan)
        govs = {r["governorate"] for r in rows}
        print(f"{len(rows)} workbooks across {len(govs)} governorates")
        for r in sorted(rows, key=lambda r: (r["governorate"], r["delegation"]))[:20]:
            print(f"  {r['governorate']:<18} {r['delegation']:<26} {r['status']}")
        if args.write:
            os.makedirs(os.path.dirname(OUT), exist_ok=True)
            with open(OUT, "a", encoding="utf-8") as fh:
                for r in rows:
                    json.dump({"record": "workbook", **r}, fh, ensure_ascii=False)
                    fh.write("\n")
            print(f"appended {len(rows)} rows to {OUT}")
        return 0

    if args.download:
        rows = plan(args.download)
        os.makedirs(CACHE, exist_ok=True)
        ok = bad = 0
        for i, r in enumerate(rows, start=1):
            name = f"{r['tree']}__{r['governorate']}__{r['delegation']}.xlsx"
            dest = os.path.join(CACHE, name)
            if os.path.exists(dest) and os.path.getsize(dest) > 0:
                ok += 1
                continue
            try:
                open(dest, "wb").write(get(replay(r["url"], r["timestamp"])))
                ok += 1
            except OSError as exc:
                bad += 1
                print(f"  FAIL {name}: {exc}")
            if i % 25 == 0:
                print(f"    {i}/{len(rows)}")
        print(f"{ok} downloaded, {bad} failed, into {CACHE}")
        return 0

    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
