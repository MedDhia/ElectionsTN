"""Shared access to the ISIE's 2019 election report and its scanned annex.

Both 2019 sources are recovered rather than simply downloaded, and both are
fetched by the builders that read them:

* `تقرير-الانتخابات-الرئاسية-والتشريعية-لسنة-2019.pdf` — the ISIE's own report on
  the 2019 presidential and legislative elections, 576 pages, still served from
  isie.tn (re-uploaded under `uploads/2026/01/`). It has a text layer.
* `النتائج-النهائية-للانتخابات-التشريعية-2019-حسب-القائمات.pdf` — the final
  legislative results, one table per constituency. This is annex 15 of the same
  report, but the report's copy of it is page images with no text, and the
  standalone file is gone from isie.tn: the media library still lists it, at
  `uploads/2019/11/`, and the URL 404s. It survives in the Wayback Machine's
  22 December 2019 capture, which is what is fetched here.

Everything under `uploads/2019/` on isie.tn is in the same state — listed by the
API, dead on the server — so the Wayback fallback is the rule for 2019, not an
exception. `pdfplumber` reads neither file (the report's fonts carry no usable
`ToUnicode` map, and the annex is a scan), so text comes from pdfium.
"""
import os, re, time, urllib.parse, urllib.request

import pypdfium2 as pdfium

CACHE = ".cache/pdfs"
REPORT_URL = ("https://www.isie.tn/wp-content/uploads/2026/01/"
              "تقرير-الانتخابات-الرئاسية-والتشريعية-لسنة-2019.pdf")
REPORT_FILE = os.path.join(CACHE, "rapport_isie_2019.pdf")
# The Wayback capture of the standalone final legislative results.
LISTS_ORIGINAL = ("http://www.isie.tn/wp-content/uploads/2019/11/"
                  "النتائج-النهائية-للانتخابات-التشريعية-2019-حسب-القائمات.pdf")
LISTS_TIMESTAMP = "20191222143959"
LISTS_FILE = os.path.join(CACHE, "legislatives_2019_par_liste.pdf")


def wayback(url, timestamp):
    """The raw (un-rewritten) Wayback URL for one capture of `url`."""
    return f"https://web.archive.org/web/{timestamp}id_/{url}"


def fetch(url, dest, tries=6):
    """Download `url` to `dest` once; later runs reuse the cached copy."""
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if os.path.exists(dest) and os.path.getsize(dest) > 1024:
        return dest
    quoted = urllib.parse.quote(url, safe=":/?&=%")
    for attempt in range(tries):
        try:
            req = urllib.request.Request(quoted, headers={"User-Agent": "Mozilla/5.0"})
            data = urllib.request.urlopen(req, timeout=600).read()
            if not data.startswith(b"%PDF"):
                raise OSError(f"not a PDF ({len(data)} bytes)")
            tmp = dest + ".part"
            with open(tmp, "wb") as fh:
                fh.write(data)
            os.replace(tmp, dest)
            return dest
        except Exception as exc:
            if attempt == tries - 1:
                raise
            print(f"  retry {attempt + 1}: {exc}")
            time.sleep(3 * (attempt + 1))


def report():
    """Path to the cached report, downloading it if need be."""
    return fetch(REPORT_URL, REPORT_FILE)


def lists_pdf():
    """Path to the cached scan of the final results by list."""
    return fetch(wayback(LISTS_ORIGINAL, LISTS_TIMESTAMP), LISTS_FILE)


def pages(path):
    """Every page's text, in reading order."""
    pdf = pdfium.PdfDocument(path)
    return [pdf[i].get_textpage().get_text_range() for i in range(len(pdf))]


def clean(text):
    """Collapse whitespace and drop the orphan diacritics pdfium emits."""
    return re.sub(r"\s+", " ", re.sub(r"^[ً-ْ\s]+", "", text)).strip()


CENTRE = "مركز جمع"


def constituencies(pages):
    """The 33 constituencies, named as annex 7 of the report names them.

    Every 2019 table is broken down the same way — ISIE calls the unit a
    collection centre (مركز جمع) in the presidential annexes and an electoral
    constituency (دائرة انتخابية) in the legislative ones, but it is the same
    33 units. Annex 7 heads each of its pages with one, in clean text, so that
    is the spelling every 2019 dataset here is keyed to.
    """
    names, seen = [], set()
    for text in pages:
        for line in (l.strip() for l in text.split("\r\n")):
            if line.startswith(CENTRE):
                name = clean(line[len(CENTRE):])
                if name and name not in seen:
                    seen.add(name)
                    names.append(name)
    return names
