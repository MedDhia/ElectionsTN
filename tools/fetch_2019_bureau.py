"""Recover the 2019 per-bureau results from the Wayback Machine.

What this is
------------
ISIE published 2019 results as spreadsheets under a `filebases/` tree, one
workbook per delegation, named `pv-auto-bv-...` -- *procès-verbal, automatique,
bureau de vote*. That is **per polling bureau**, finer than the delegation PDFs
mapped in `data/verification/2019_delegation_sources.jsonl`, and finer than
anything the repo currently holds for 2019 (33 constituencies).

The tree is gone from isie.tn -- every pre-2020 upload 404s -- but it survives
in the Wayback Machine. Two captures are confirmed by hand:

    .../filebases/pv-auto-bv-presidentielles-tour2/Tunisie/Ariana/Ettadhamen.xlsx
    .../filebases/pv-auto-bv-presidentielles-tour2/Tunisie/Tozeur/Tameghza.xlsx

both under the 20191026093137 snapshot.

Enumerate, do not guess
-----------------------
The path uses ISIE's own ASCII spellings, which are close to but not the same
as `data/delegations_ins.csv` (`Tozeur/Tameghza` matches exactly; `Cité
Ettadhamen` appears as `Ariana/Ettadhamen`). Generating 264 candidate names
from the INS list would therefore mis-hit an unknown number of them, so this
enumerates the real paths from Wayback's CDX index instead and only reports
what the archive actually holds.

Sibling trees almost certainly exist -- round one, and the legislative
contest -- so `--survey` lists every distinct `filebases/` path prefix the
index knows rather than assuming the round-two name is the only one.

NOT YET RUN AGAINST THE NETWORK
-------------------------------
`web.archive.org` was unreachable from the session that wrote this: the
environment's egress policy was widened mid-session, but a session reads its
network configuration once at startup, so the change needs a fresh session.
Treat the first run as a probe -- `--survey`, then `--plan` -- and check what
comes back before starting a bulk download.
"""

import argparse
import csv
import json
import os
import sys
import time
import urllib.parse
import urllib.request

CDX = "http://web.archive.org/cdx/search/cdx"
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
