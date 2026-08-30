"""Dataset 7 — ISIE communications timeline.

The mirror did not capture article bodies, but the dated permalink folders
survive as folder names: /actualites/YYYY/MM/DD/<slug>/ in the French tree and
/ar/communiques-ar/YYYY/MM/DD/<slug>/ in the Arabic one. That is enough for a
dated index of ISIE's public communications.

Coverage is partial by construction. The Arabic section's surviving pagination
stubs run to page/14, so the live site carried far more communiqués than the
two the mirror captured.
"""
import csv, collections, re, urllib.parse

SRC = "inventory/drive_tree.csv"
OUT = "data/communications_timeline.csv"
ITEM = re.compile(
    r"^/(?:(?P<ar>ar)/communiques-ar|actualites)"
    r"/(?P<y>\d{4})/(?P<m>\d{2})/(?P<d>\d{2})/(?P<slug>[^/]+)")


def main():
    with open(SRC, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    items, extras = {}, collections.Counter()
    for r in rows:
        m = ITEM.match(r["path"])
        if not m:
            continue
        slug = m["slug"]
        key = (m["y"], m["m"], m["d"], slug, bool(m["ar"]))
        # An /attachment/ node under the slug means the item carried images.
        if "/attachment" in r["path"]:
            extras[key] += 1
            continue
        depth = 6 if m["ar"] else 5
        items.setdefault(key, r["drive_id"] if r["path"].count("/") == depth else "")

    out = []
    for (y, mo, d, slug, is_ar), drive_id in sorted(items.items()):
        title = urllib.parse.unquote(slug).replace("-", " ").strip()
        out.append({
            "date": f"{y}-{mo}-{d}",
            "year": y,
            "language": "ar" if is_ar else "fr",
            "slug": slug,
            "title_from_slug": title,
            "attachments": extras[(y, mo, d, slug, is_ar)],
            "section": "communiques-ar" if is_ar else "actualites",
            "source_url": (f"https://www.isie.tn/ar/communiques-ar/{y}/{mo}/{d}/{slug}/"
                           if is_ar else
                           f"https://www.isie.tn/actualites/{y}/{mo}/{d}/{slug}/"),
            "drive_folder_id": drive_id,
        })

    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)

    print(f"wrote {len(out)} rows -> {OUT}")
    print("  by language:", dict(collections.Counter(r["language"] for r in out)))
    print("  by year    :", dict(sorted(collections.Counter(r["year"] for r in out).items())))
    print("  with attachments:", sum(1 for r in out if r["attachments"]))


if __name__ == "__main__":
    main()
