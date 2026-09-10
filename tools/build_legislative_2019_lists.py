"""Dataset 12c — 2019 legislative results, every list in every constituency.

This is the table the 2019 election is usually asked for: how many votes each
candidate list took in each of the 33 constituencies, and what share of the
valid vote that was. It is annex 15 of the ISIE's 2019 report, and it is the one
annex the report carries as page images rather than text. The standalone PDF the
ISIE published on 8 November 2019 is listed by the site's media library and 404s
on the server, so it comes from the Wayback Machine (see `tools/_rapport_2019.py`).

So it has to be read off the scan. The tables are cleanly ruled, which makes
cell-level OCR possible and whole-page OCR pointless — see `tools/grid.py` for
how the grid is found. Each cell is then read with the tool that fits it: the
rank and vote columns with the English model and a digits-only character set,
the share column with digits, comma and percent, the list names with the Arabic
model.

Every constituency then checks itself, three ways over, before any of it is
believed:

* the vote counts sum to the total the table prints in its own last row, which
  is what says no row was missed;
* each printed share matches the share recomputed from votes and that total;
* the rank printed beside each row matches the row's position in the table.

The share is the one that catches OCR: a digit misread moves a share by more
than the rounding tolerance, so a row that passes has had its vote count
confirmed by a number printed elsewhere on the page. Rows that fail are written
out flagged, not dropped — except where a table has exactly one such row, in
which case its printed total pins the count and the share that flagged it
confirms the repair.

`rank` is the row's position, not the cell's reading: a single misread rank used
to renumber every row after it, and position is what the printed number means
anyway. The reading is kept in `rank_printed` as a check on it.

The list names have no such backup and are the weak column, exactly as elsewhere
in this project: they are Arabic OCR of a 2019 scan, with the raw reading kept.

Usage: python3 tools/build_legislative_2019_lists.py
       (needs tesseract with the ara model; ~12 minutes for 55 pages)
"""
import csv, difflib, os, re, subprocess, sys, tempfile, unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _rapport_2019 import constituencies, lists_pdf, pages as page_text, report
from build_2019_turnout import CONTESTS, blocks as turnout
from grid import bands, deskew, horizontal_rules

import numpy as np
import pypdfium2 as pdfium

OUT = "data/legislative_2019_list_results.csv"
SCALE = 4          # render at ~400 dpi; the scans are ~200 dpi originals
TITLE = "الدائرة الانتخابية"
# The last row of each table reads "العدد الجملي للأصوات لكل القائمات". Matched
# against folded text, so القائمات is written here without its hamza.
TOTAL = re.compile(r"جملي|قايمات")
# The column caption over the name column, on its own. A list name is longer
# and always begins "قائمة", so only the caption itself scores this close.
CAPTION = "القائمات"
CAPTION_RATIO = 0.8
# How close a heading's OCR must come to "الدائرة الانتخابية <name>" to count.
TITLE_RATIO = 0.55
SHARE_TOLERANCE = 0.02   # percentage points, against a value printed to 2 dp
TASHKEEL = re.compile(r"[ً-ْـٰ]")
# Hamza carriers and ta-marbuta unified; Arabic-Indic digits and the exclamation
# mark Tesseract likes to return for a lone "1" folded onto Latin digits, because
# four of the 33 constituencies are told apart only by a trailing 1 or 2.
FOLD = str.maketrans("أإآىئؤة" + "٠١٢٣٤٥٦٧٨٩" + "!", "اااييوه" + "0123456789" + "1")


def ocr(image, lang, whitelist=None, psm="7"):
    with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
        image.save(tmp.name)
        cmd = ["tesseract", tmp.name, "-", "-l", lang, "--psm", psm]
        if whitelist:
            cmd += ["-c", "tessedit_char_whitelist=" + whitelist]
        done = subprocess.run(cmd, capture_output=True, text=True)
    return done.stdout.strip()


def fold(text):
    return TASHKEEL.sub("", unicodedata.normalize("NFC", text)).translate(FOLD)


def digits(text):
    text = re.sub(r"\D", "", text)
    return int(text) if text else None


def share(text):
    m = re.search(r"(\d+)[,.](\d+)", text)
    return float(f"{m.group(1)}.{m.group(2)}") if m else None


def ink_lines(image, bottom, gap=10, margin=8, minimum=60, most=5):
    """Crop each band of ink above `bottom` — one line of text per crop."""
    if bottom < minimum:
        return []
    array = np.asarray(image)[:bottom, :]
    rows = np.where((array < 200).sum(1) > 5)[0]
    if not len(rows):
        return []
    blocks, start, end = [], rows[0], rows[0]
    for y in rows[1:]:
        if y - end <= gap:
            end = y
        else:
            blocks.append((start, end))
            start = end = y
    blocks.append((start, end))
    return [image.crop((0, max(0, a - margin), array.shape[1], min(bottom, b + margin)))
            for a, b in blocks[:most]]


def read_page(pdf, index, canonical):
    """Read one page: its constituency heading, if any, and its rows."""
    image, angle = deskew(pdf[index].render(scale=SCALE).to_pil().convert("L"))
    array = np.asarray(image)
    grids = list(bands(array))
    complete = [g for g in grids if len(g[2]) == 5]
    if not complete:
        return None, [], angle

    # The constituency heading sits above the table, alongside the column
    # headers and, on some pages, a stray scanner line. Reading that whole
    # region at once loses the heading on the sparser pages, so it is split
    # into its bands of ink and each is read as the single line it is.
    title, head = None, complete[0][0]
    crops = ink_lines(image, head - 6)
    if head > 60:
        crops.append(image.crop((0, 0, array.shape[1], head - 6)))
    for crop in crops:
        for psm in ("7", "6"):
            title = match_constituency(ocr(crop, "ara", psm=psm), canonical)
            if title:
                break
        if title:
            break

    # The header row and the total row merge two of their cells, so they show
    # fewer than four columns and borrow a neighbour's grid to be cut up. The
    # nearest complete one above is used, or the first one below when the page
    # opens on a merged band — which is what a continuation page does.
    rows, last, seen = [], None, False
    ahead = complete[0][2]
    for y0, y1, detected in grids:
        merged = len(detected) != 5
        cols = (last or ahead) if merged else detected
        if not merged:
            last = cols
        cell = lambda i: image.crop((cols[i] + 8, y0, cols[i + 1] - 8, y1))
        votes = digits(ocr(cell(1), "eng", "0123456789"))
        if votes is None:
            continue                              # the column-header band
        name = ocr(cell(2), "ara")
        label = name + " " + ocr(cell(3), "ara") if merged else name
        # The total row and the column headers both say "القائمات" and neither
        # prints a rank or a share, so word alone cannot tell them apart when
        # the OCR drops "الجملي". Position can: the headers open a table, the
        # total closes one, and only the total has rows above it.
        if TOTAL.search(fold(label)) and votes >= 1000 and (seen or "جملي" in fold(label)):
            rows.append({"kind": "total", "votes": votes})
            continue
        rank = digits(ocr(cell(3), "eng", "0123456789"))
        percentage = share(ocr(cell(0), "eng", "0123456789,.%"))
        # A row prints a rank, a name, a count and a share. A band with neither
        # a readable rank nor a readable share is not a row at all: it is the
        # constituency heading or the column headers, which sit where a first
        # row would and leave stray digits in the vote column. The headers can
        # also leave a stray digit in the rank column, so a band whose name is
        # the caption and whose share is missing goes the same way.
        if percentage is None and (rank is None or difflib.SequenceMatcher(
                None, fold(name).strip(), fold(CAPTION)).ratio() >= CAPTION_RATIO):
            continue
        seen = True
        rows.append({"kind": "list", "votes": votes, "votes_read": None,
                     "rank_printed": rank,
                     "list_name": re.sub(r"^[^ء-ي]+", "", name).strip(),
                     "share_pct": percentage})
    return title, rows, angle


def agrees(votes, percentage, total):
    return (percentage is not None and total
            and abs(percentage - round(100 * votes / total, 2)) <= SHARE_TOLERANCE)


def repair(lists, total):
    """Recover one misread count per table from the table's own two other numbers.

    A row whose printed share contradicts its vote count has had a digit
    misread. When it is the only such row, the total the table prints pins what
    the count must be — and the repair is accepted only if the value that pins
    it also reproduces the share that flagged it. Two printed figures then agree
    on the answer, which is the same standard the spelled-out vote counts set
    for the 2023 local results.
    """
    if not total:
        return
    flagged = [r for r in lists if not agrees(r["votes"], r["share_pct"], total)]
    if len(flagged) != 1 or flagged[0]["share_pct"] is None:
        return
    row = flagged[0]
    residual = total - sum(r["votes"] for r in lists if r is not row)
    if residual > 0 and agrees(residual, row["share_pct"], total):
        row["votes_read"], row["votes"] = row["votes"], residual


def match_constituency(text, canonical):
    """The canonical constituency this heading names, or None if it is not one."""
    best_ratio, best_name = 0.0, None
    for line in (fold(l) for l in text.split("\n") if l.strip()):
        ratio, name = max((difflib.SequenceMatcher(
            None, fold(TITLE + " " + c), line).ratio(), c) for c in canonical)
        if ratio > best_ratio:
            best_ratio, best_name = ratio, name
    return best_name if best_ratio >= TITLE_RATIO else None


def main():
    pages = page_text(report())
    canonical = constituencies(pages)
    national = dict(zip(CONTESTS, (f for _, f in turnout(pages))))["legislative"]
    print(f"{len(canonical)} constituencies named in the report, which puts the "
          f"national valid vote at {national['valid_votes']}")

    pdf = pdfium.PdfDocument(lists_pdf())
    print(f"reading {len(pdf)} scanned pages")

    # Every table ends with its own total row, and every table's first page
    # carries a heading, so either boundary opens the next one — a heading the
    # OCR could not read still does not merge two constituencies into one.
    tables, current, closed = [], None, True
    for index in range(len(pdf)):
        title, rows, angle = read_page(pdf, index, canonical)
        if title:
            closed = True
        for row in rows:
            if closed or current is None:
                current = {"constituency": title, "rows": [], "pages": []}
                tables.append(current)
                closed = False
            if index + 1 not in current["pages"]:
                current["pages"].append(index + 1)
            current["rows"].append(row)
            if row["kind"] == "total":
                closed = True
        print(f"  page {index + 1}: "
              + (f"{title} — " if title else "")
              + f"{sum(1 for r in rows if r['kind'] == 'list')} lists"
              + (", total" if any(r["kind"] == "total" for r in rows) else "")
              + (f", deskewed {angle}°" if angle else ""))

    # A heading the OCR could not read leaves one table unnamed. When exactly
    # one name is also unaccounted for, the two are each other's only option.
    unnamed = [t for t in tables if not t["constituency"]]
    missing = [c for c in canonical if c not in {t["constituency"] for t in tables}]
    if len(unnamed) == len(missing) == 1:
        unnamed[0]["constituency"] = missing[0]
        print(f"one heading unread; {missing[0]} is the only constituency left, "
              f"so it is assigned by elimination")
    elif unnamed:
        print(f"{len(unnamed)} tables have no heading; {len(missing)} names unused")
    print(f"{len(tables)} tables, {len(set(t['constituency'] for t in tables) - {None})} "
          f"of {len(canonical)} constituencies named")

    out, failures = [], 0
    for table in tables:
        lists = [r for r in table["rows"] if r["kind"] == "list"]
        totals = [r["votes"] for r in table["rows"] if r["kind"] == "total"]
        printed = totals[-1] if totals else None
        repair(lists, printed)
        summed = sum(r["votes"] for r in lists)
        # Rank is the row's position in the table, which is what the printed
        # numbering means; the cell is read too and kept as a check on it.
        matched = sum(1 for i, r in enumerate(lists, 1) if r["rank_printed"] == i)
        if printed != summed or matched != len(lists):
            failures += 1
            print(f"  ! {table['constituency']}: {len(lists)} lists, sum {summed}, "
                  f"printed {printed}, {len(lists) - matched} ranks not confirmed")
        for i, r in enumerate(lists, 1):
            base = printed or summed
            recomputed = round(100 * r["votes"] / base, 2) if base else None
            out.append({
                "constituency": table["constituency"],
                "rank": i,
                "rank_printed": r["rank_printed"] if r["rank_printed"] is not None else "",
                "rank_check": ("agree" if r["rank_printed"] == i
                               else "unread" if r["rank_printed"] is None else "differ"),
                "list_name": r["list_name"],
                "votes": r["votes"],
                "votes_read": r["votes_read"] if r["votes_read"] is not None else "",
                "share_pct": r["share_pct"],
                "share_recomputed": recomputed,
                "share_check": ("repaired" if r["votes_read"] is not None
                                else "agree" if agrees(r["votes"], r["share_pct"], base)
                                else "differ"),
                "constituency_valid_votes": printed,
                "total_matches_sum": int(printed == summed),
                "source_pages": " ".join(str(p) for p in table["pages"]),
            })

    agree = sum(1 for r in out if r["share_check"] in ("agree", "repaired"))
    fixed = sum(1 for r in out if r["share_check"] == "repaired")
    ranked = sum(1 for r in out if r["rank_check"] == "agree")
    exact = len({r["constituency"] for r in out if r["total_matches_sum"]})
    read = sum(r["votes"] for r in out)
    printed_totals = sum({r["constituency"]: r["constituency_valid_votes"] or 0
                          for r in out}.values())
    print(f"{len(out)} rows across {len(tables)} constituencies; "
          f"{failures} constituencies fail a check; {exact} sum to their printed total; "
          f"{agree} rows ({100 * agree / max(len(out), 1):.1f}%) share-validated "
          f"({fixed} of them repaired from the printed total), "
          f"{ranked} ({100 * ranked / max(len(out), 1):.1f}%) rank-confirmed")
    print(f"votes read {read} — {100 * read / national['valid_votes']:.2f}% of the "
          f"national valid vote; the 33 printed totals come to {printed_totals}, "
          f"{national['valid_votes'] - printed_totals} short of it")

    os.makedirs("data", exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, ["constituency", "rank", "rank_printed",
                                     "rank_check", "list_name", "votes", "votes_read",
                                     "share_pct",
                                     "share_recomputed", "share_check",
                                     "constituency_valid_votes", "total_matches_sum",
                                     "source_pages"])
        writer.writeheader()
        writer.writerows(out)
    print(f"wrote {OUT} ({len(out)} rows)")


if __name__ == "__main__":
    main()
