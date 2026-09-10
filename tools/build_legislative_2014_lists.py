"""Every 2014 legislative list's vote, by constituency, from the annex of n° 94.

The annex to ISIE decision n° 34 is 59 pages of tables, one per constituency,
giving each candidate list's rank, name, share and vote — the 2014 counterpart
of `data/legislative_2019_list_results.csv`, and the row-level detail behind
`data/legislative_2014_constituency_results.csv`.

The figures are exact and the names are not. These annex pages are set in fonts
whose glyph mapping is broken: every ligature arrives as some unrelated
codepoint, and a few of them are drawn where they belong rather than emitted
where they are read, so "الجبهة" comes out as "ڈةّالج". Digits are unaffected —
they are single glyphs with a correct mapping — so the ranks, shares and votes
are read from the text layer, and the names are recovered the way the 2019
scans were: the page is rendered, the name column of each row is cut out and
read with Tesseract's Arabic model. `tools/_jort_2014.py` also repairs what it
can of the text-layer name, and both readings are kept in the output beside the
name this builder settles on, so every one can be audited.

Two things make that settling safe. The decision's own body, which is set in an
undamaged font, names in clean text every list that won a seat — 18 lists, and
between them most of the vote — so the OCR of those is corrected against the
decision itself rather than trusted. And a party list stands in many
constituencies under one name, so the readings of each are clustered and the
name the cluster agrees on is used for all of them.

None of that touches the arithmetic, which stands on its own: each
constituency's votes are summed against the total printed at the foot of its own
table and against the figure the decision's body gives it, each share is
recomputed from the votes, each rank is checked against its row's position, and
the 33 constituencies are summed against the decision's national total of
3,408,207 votes cast for lists.

Writes:
    data/legislative_2014_list_results.csv
"""
import collections, csv, difflib, os, re, subprocess, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _jort_2014 as J
from arabic_numerals import _fold
from build_legislative_2014 import (DECISION, constituencies, find,
                                    short_name)

OUT = "data/legislative_2014_list_results.csv"

DPI = 300
TOLERANCE = 0.02          # percentage points
COLUMN = 25               # points a cell may sit from its column's centre
MARGIN = 4                # points added above and below a row before cropping
TRIM = 4                  # pixels trimmed off the crop, to lose the rules
BORDER = 24               # pixels of white paper added around the cell
PAD = 6                   # points trimmed off each side of the name column
# Tesseract reads the cell's ruled border as a lone alef at either end.
EDGE = re.compile(r"^\s*[اإأ|]\s+|\s+[اإأ|]\s*$")
# Most tables print a share to two decimals and a few to one, so the number of
# decimals is read rather than assumed: the digits alone cannot say whether
# "385" is 38.5 or 3.85.
SHARE = re.compile(r"%\s*(\d+[.,]\d+)|(\d+[.,]\d+)\s*%")
# How close two readings of a name must be to be treated as the same list.
CLUSTER = 0.93
# How close an OCR'd name must be to a name from the decision's own text for
# the decision's spelling to be used instead.
SNAP = 0.85


def columns(rows):
    """The x centre of the share, votes and rank columns of one page.

    Taken from the rows that carry exactly three figures, which is all of them
    but the header, the foot and the occasional list whose name has a number in
    it. The median is used so that one stray row cannot move a column.
    """
    triples = [cells for _, _, cells in rows if len(cells) == 3]
    if len(triples) < 3:
        return None
    out = []
    for position in range(3):
        centres = sorted((c[position][0] + c[position][1]) / 2
                         for c in triples)
        out.append(centres[len(centres) // 2])
    return out


def read_rows(rows, centres, expected):
    """(rank, votes, share, top, bottom) for each data row of one page.

    A row qualifies when it has a figure in each of the three columns and its
    rank continues the table's numbering. That second test is what keeps the
    page's footer out: it has figures near two of the columns, but no rank of
    the right value.
    """
    out = []
    for top, bottom, cells in rows:
        picked = {}
        for x0, x1, value in cells:
            centre = (x0 + x1) / 2
            best = min(range(3), key=lambda i: abs(centre - centres[i]))
            if abs(centre - centres[best]) <= COLUMN and best not in picked:
                picked[best] = value
        if len(picked) != 3 or picked[2] != expected + len(out):
            continue
        out.append((picked[2], picked[1], picked[0], top, bottom))
    return out


def text_rows(text):
    """(share, the text layer's own name) for each row of one page, in order.

    The share has to come from the text because the glyph grid cannot see the
    decimal point, and the text-layer name comes with it because both are read
    off the same line.
    """
    out = []
    for line in map(J.clean, J.lines(text)):
        share = SHARE.search(line)
        if not share:
            continue
        words = [t for t in line.split() if not re.fullmatch(r"[\d.,%]+", t)]
        printed = (share.group(1) or share.group(2)).replace(",", ".")
        out.append((float(printed), printed.replace(".", ""),
                    len(printed.split(".")[1]), J.repair(" ".join(words))))
    return out


def totals(rows, centres):
    """(votes cast for lists, the table's own reference total) from the header.

    The header prints the two side by side, in the wide margins outside the
    three data columns, so a row of two figures that belong to no column is it.
    The smaller is always the votes cast for lists — which is what identifies
    the constituency, since the decision gives every one of the 33 a different
    figure — and the larger is the total each share on the page is a percentage
    of. That larger figure is the constituency's valid votes in 32 of the 33
    tables and its number of voters in the last one, so it is carried through
    as printed rather than assumed.
    """
    for _, _, cells in rows:
        if len(cells) != 2:
            continue
        if any(min(abs((x0 + x1) / 2 - c) for c in centres) <= COLUMN
               for x0, x1, _ in cells):
            continue
        values = sorted(value for _, _, value in cells)
        return values[0], values[1]
    return None


def name_column(rows):
    """(left, right) of the name column of one page, in points.

    The name sits between the votes and the rank, and both of those columns are
    measured on the page itself, so nothing here is a fixed coordinate. The
    widest extent of each is used: a name is set flush against its cell's right
    edge, and cropping even a few points inside it loses the first word.
    """
    triples = [cells for _, _, cells in rows if len(cells) == 3]
    return (max(c[1][1] for c in triples) + PAD,
            min(c[2][0] for c in triples) - PAD)


def crop_names(path, index, rows, column):
    """OCR the name cell of each row of one page, top to bottom."""
    import pypdfium2 as pdfium
    from PIL import ImageOps

    pdf = pdfium.PdfDocument(path)
    page = pdf[index]
    _, height = page.get_size()
    scale = DPI / 72
    image = page.render(scale=scale).to_pil().convert("L")
    left, right = column
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        for i, (_, _, _, top, bottom) in enumerate(rows):
            box = (int(left * scale), int((height - top - MARGIN) * scale),
                   int(right * scale), int((height - bottom + MARGIN) * scale))
            crop = image.crop(box)
            # The cell's own ruled border falls on the edges of the crop, and
            # Tesseract's single-line mode returns nothing at all when a rule
            # runs the width of the image, so the rules are trimmed off and the
            # cell is set on white paper with room around it.
            width, tall = crop.size
            crop = crop.crop((TRIM, TRIM, width - TRIM, tall - TRIM))
            cell = os.path.join(tmp, f"{i}.png")
            ImageOps.expand(crop, border=BORDER, fill=255).save(cell)
            out.append(read_cell(cell))
    return out


def read_cell(path):
    """One cell read with Tesseract's Arabic model.

    A single line is what these cells hold, so `--psm 7` suits them, but it
    returns nothing at all on a few, and the block mode reads those.
    """
    for mode in ("7", "6"):
        done = subprocess.run(
            ["tesseract", path, "stdout", "-l", "ara", "--psm", mode],
            capture_output=True, text=True)
        text = J.clean(EDGE.sub(" ", done.stdout.replace("\n", " ")).strip())
        if text:
            return text
    return ""


def similar(a, b):
    return difflib.SequenceMatcher(None, _fold(a), _fold(b)).ratio()


def pin(tables, body, by_constituency):
    """(similarity, name, reading) for every reading the decision pins down.

    A list that won a seat is named in the decision's own text, in the
    constituency where it won it, so its row in that constituency's table is
    known to be a reading of that name. Which row is settled by matching the
    two within the constituency, best pair first: a constituency names at most
    a handful of winners and they are always near the top of its table, so
    there is nothing ambiguous to resolve.
    """
    out = []
    for table in tables:
        constituency = body.get(table["totals"][0])
        winners = by_constituency.get(constituency, [])
        pairs = sorted(((similar(reading, name), name, reading)
                        for name in winners
                        for reading in table["readings"]), reverse=True)
        claimed, used = set(), set()
        for score, name, reading in pairs:
            if name in claimed or reading in used or score < 0.5:
                continue
            claimed.add(name)
            used.add(reading)
            out.append((score, name, reading))
    return out


def settle(readings, clean_names, pinned=()):
    """Decide, for every reading of a name, which name it is a reading of.

    `readings` is (constituency, reading) pairs, and the result maps each
    distinct reading onto the name to use for it. Two things make that
    possible. The decision's own body names in clean text every list that won a
    seat, so a reading close enough to one of those is a misreading of it. And
    a party list stands in most of the 33 constituencies under one name, so
    thirty-odd independent readings of it are available and the one the most of
    them agree on is almost certainly right.

    Running through the constraint at both steps: a constituency lists each of
    its lists once, so two readings from the same constituency are never two
    readings of one name. That is what keeps "قائمة حزب الريادة", which
    Tesseract reads as "الربادة", from being taken for the "قائمة حزب المبادرة"
    two rows above it in نابل 1. The closest reading claims a name first, so
    the one that is really a misreading gets it.
    """
    where = collections.defaultdict(set)
    for constituency, reading in readings:
        where[reading].add(constituency)
    counts = collections.Counter(reading for _, reading in readings)
    settled, taken = {}, collections.defaultdict(set)

    def claim(reading, name):
        if where[reading] & taken[name]:
            return False
        settled[reading] = name
        taken[name] |= where[reading]
        return True

    for score, name, reading in sorted(pinned, reverse=True):
        claim(reading, name)
    scored = []
    for reading in where:
        if reading in settled:
            continue
        best = max(clean_names, key=lambda c: similar(reading, c))
        scored.append((similar(reading, best), best, reading))
    for score, name, reading in sorted(scored, reverse=True):
        if score >= SNAP:
            claim(reading, name)
    for reading, _ in counts.most_common():
        if reading in settled:
            continue
        claim(reading, reading)
        for other, _ in counts.most_common():
            if other not in settled and similar(reading, other) >= CLUSTER:
                claim(other, reading)
    return settled


def main():
    path = J.issue("legislative")
    pages = J.pages(path)
    start = find(pages, DECISION)
    names = J.centres()

    # The decision's body: the figures each constituency's table must come to,
    # and the clean spelling of every list that won a seat.
    body, valid, clean_names, by_constituency = {}, {}, set(), {}
    for block in constituencies(pages[start:]):
        name, _ = short_name(block["description"], names)
        body[block["valid_votes_lists"]] = name
        valid[block["valid_votes_lists"]] = block["valid_votes"]
        clean_names.update(list_of for list_of, _ in block["lists"])
        by_constituency[name] = [list_of for list_of, _ in block["lists"]]
    print(f"{len(body)} constituencies in the decision, "
          f"{len(clean_names)} lists named in clean text")

    # ------------------------------------------------------------- the tables
    tables, problems, notes = [], [], []
    for index in range(start, len(pages)):
        rows = J.grid(path, index)
        centres = columns(rows)
        if not centres:
            continue
        pair = totals(rows, centres)
        if not pair:
            continue
        if not tables or tables[-1]["totals"] != pair:
            tables.append({"totals": pair, "pages": [], "rows": [],
                           "names": [], "shares": [], "raw": []})
        table = tables[-1]
        read = read_rows(rows, centres, len(table["rows"]) + 1)
        if not read:
            continue
        printed = text_rows(pages[index])
        if len(printed) != len(read):
            problems.append(f"page {index + 1}: {len(read)} rows in the grid "
                            f"against {len(printed)} in the text")
            continue
        table["pages"].append(index + 1)
        table["names"] += crop_names(path, index, read, name_column(rows))
        table["rows"] += read
        table["shares"] += [p[:3] for p in printed]
        table["raw"] += [p[3] for p in printed]
        print(f"  page {index + 1}: {len(read)} lists "
              f"({body.get(pair[0], 'unidentified')})")
    print(f"{len(tables)} tables read")

    # ------------------------------------------------------------ the results
    # OCR is the first reading of a name and the repaired text layer the
    # fallback, for the eleven cells Tesseract returns nothing for.
    for table in tables:
        table["readings"] = [ocr or raw for ocr, raw
                             in zip(table["names"], table["raw"])]
    readings = [(body.get(t["totals"][0]), reading) for t in tables
                for reading in t["readings"]]
    pinned = pin(tables, body, by_constituency)
    settled = settle(readings, clean_names, pinned)

    out, seen = [], set()
    for table in tables:
        printed, reference = table["totals"]
        constituency = body.get(printed)
        if not constituency:
            problems.append(f"pages {table['pages']}: a total of {printed} "
                            "matches no constituency")
            continue
        seen.add(constituency)
        summed = sum(votes for _, votes, *_ in table["rows"])
        if summed != printed:
            problems.append(f"{constituency}: votes come to {summed}, the "
                            f"decision gives the lists {printed}")
        printed_valid = valid[printed]
        if reference != printed_valid:
            notes.append(f"{constituency}: the annex's header gives "
                         f"{reference} where the decision's body gives "
                         f"{printed_valid} valid votes")
        # Which of the two header figures the shares are a percentage of is
        # decided by trying both: the header says "of the valid votes" and one
        # table in 33 takes them over the votes cast for lists instead.
        reference = max((agreement(table, over), over)
                        for over in (reference, printed))[1]
        if reference == printed:
            notes.append(f"{constituency}: the annex takes its shares over the "
                         f"{printed} votes cast for lists, not the valid votes")
        for position, (row, share, ocr, raw, reading) in enumerate(
                zip(table["rows"], table["shares"], table["names"],
                    table["raw"], table["readings"]), 1):
            rank, votes, digits = row[0], row[1], row[2]
            share, printed_share, decimals = share
            if digits != int(printed_share):
                problems.append(f"{constituency} rank {rank}: the share reads "
                                f"{share} but its glyphs are {digits}")
            # Four tables print their shares to one decimal and the rest to
            # two, so each is recomputed to the precision it was printed at.
            recomputed = round(100 * votes / reference, decimals)
            name = settled[reading]
            out.append({
                "constituency": constituency, "rank": rank,
                "rank_check": "agree" if rank == position else "differs",
                "list_name": name,
                "list_name_source": ("decision" if name in clean_names
                                     else "ocr" if ocr else "text-layer"),
                "list_name_ocr": ocr, "list_name_text_layer": raw,
                "votes": votes, "share_pct": share,
                "share_recomputed": recomputed,
                "share_decimals": decimals,
                "share_check": ("agree" if abs(recomputed - share) <= TOLERANCE
                                else "differs"),
                "constituency_valid_votes_lists": printed,
                "share_over": reference,
                "source_pages": " ".join(str(p) for p in table["pages"]),
            })
    repeated = [pair for pair, count in collections.Counter(
        (r["constituency"], r["list_name"]) for r in out).items() if count > 1]
    for constituency, name in repeated:
        problems.append(f"{constituency}: two rows read as {name!r}")
    found = collections.defaultdict(set)
    for row in out:
        found[row["constituency"]].add(row["list_name"])
    for constituency, winners in by_constituency.items():
        for name in winners:
            if name not in found[constituency]:
                problems.append(f"{constituency}: no row reads as {name!r}, "
                                "which the decision says won a seat there")
    for missing in set(body.values()) - seen:
        problems.append(f"{missing}: no table found")

    national = sum(r["votes"] for r in out)
    if national != 3408207:
        problems.append(f"the votes come to {national}, the decision's "
                        "national total is 3408207")

    write(OUT, out)
    shares = sum(1 for r in out if r["share_check"] == "agree")
    ranks = sum(1 for r in out if r["rank_check"] == "agree")
    named = sum(1 for r in out if r["list_name_source"] == "decision")
    still = sum(1 for r in out if J.damaged(r["list_name_text_layer"]))
    read_twice = [r for r in out if r["list_name_ocr"]]
    same = sum(1 for r in read_twice
               if r["list_name_ocr"] == r["list_name_text_layer"])
    near = sum(1 for r in read_twice
               if similar(r["list_name_ocr"], r["list_name_text_layer"]) >= 0.9)
    print(f"{len(out)} lists across {len(seen)} constituencies")
    print(f"{shares}/{len(out)} shares recompute to the printed value, "
          f"{ranks}/{len(out)} ranks to the printed rank")
    print(f"{named} rows carry a name the decision's own text confirms, "
          f"{sum(r['votes'] for r in out if r['list_name_source'] == 'decision')}"
          f" of the {national} votes")
    for line in notes:
        print("  -", line)
    print(f"{still} of {len(out)} text-layer readings still carry a glyph the "
          "repair table does not know")
    print(f"the two readings of a name agree exactly in {same} of "
          f"{len(read_twice)} rows and to within 0.9 in {near}")
    if problems:
        print(f"{len(problems)} checks failed:")
        for line in problems:
            print("  !", line)
    else:
        print("every check passed")


def agreement(table, over):
    """How many of a table's printed shares recompute over `over`."""
    return sum(1 for (_, votes, *_), (share, _, decimals) in
               zip(table["rows"], table["shares"])
               if abs(round(100 * votes / over, decimals) - share) <= TOLERANCE)


def write(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {path} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
