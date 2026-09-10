"""Dataset 12b — 2019 legislative seats, from the ISIE report's text layer.

Two tables sit at the end of the report's legislative chapter and are the only
2019 seat counts still published anywhere on isie.tn:

* seats won by each of the 31 lists that took at least one — 217 in total;
* the men/women split of the winners in each of the 33 constituencies —
  164 men and 53 women, again 217.

Both print their own total, so both check themselves. The lists table is read
line by line; two of its 31 rows come out of the text layer with the row number
and the seat count transposed into the middle of the party name (a wrapped
ta-marbuta), and those are recovered by taking the row number that continues the
sequence and reading the other integer as the seat count. Their names are marked
`name_scrambled` rather than guessed at.

The vote counts behind these seats are dataset 12c — a scan, not text — and are
built by `tools/build_legislative_2019_lists.py`.

Usage: python3 tools/build_legislative_2019.py
"""
import csv, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _rapport_2019 import clean, pages as page_text, report

OUT_SEATS = "data/legislative_2019_seats.csv"
OUT_CONSTIT = "data/legislative_2019_constituency_seats.csv"

SEATS_HEAD = "العدد القائمة مجموع املقاعد"
SEATS_TOTAL = "العدد الجملي للمقاعد"
GENDER_HEAD = "الهيئة الفرعية عدد الرجال عدد النساء"
GENDER_TOTAL = "املجموع"
ROW = re.compile(r"^(\d{1,2})\s+(.+?)\s+(\d{1,3})$")
INT = re.compile(r"\d{1,4}")


def seats_by_list(pages):
    """The 31 lists that won seats, in the report's order, plus its total."""
    rows, total = [], None
    for text in (p for p in pages if SEATS_HEAD in p):
        for line in (l.strip() for l in text.split("\r\n")):
            if SEATS_TOTAL in line:
                total = int(INT.findall(line)[-1])
                continue
            m = ROW.match(line)
            if m and int(m.group(1)) == len(rows) + 1:
                rows.append({"rank": int(m.group(1)), "list_name": clean(m.group(2)),
                             "seats": int(m.group(3)), "name_scrambled": 0})
                continue
            # A wrapped row: the number and the seat count landed inside the name.
            found = [int(v) for v in INT.findall(line)]
            if len(rows) + 1 in found and len(found) == 2:
                seats = [v for v in found if v != len(rows) + 1] or [len(rows) + 1]
                rows.append({"rank": len(rows) + 1,
                             "list_name": clean(INT.sub(" ", line)),
                             "seats": seats[0], "name_scrambled": 1})
    return rows, total


def seats_by_constituency(pages):
    """Winners per constituency, split by gender, plus the printed totals."""
    rows, totals = [], None
    for text in (p for p in pages if GENDER_HEAD in p):
        started = False
        for line in (l.strip() for l in text.split("\r\n")):
            if GENDER_HEAD in line:
                started = True
                continue
            if not started:
                continue
            # "تونس 1 5 4" — the name may itself end in a number, so the two
            # counts are taken as the last two integers on the line.
            m = re.match(r"^(.*?)\s+(\d{1,3})\s+(\d{1,3})$", line)
            if not m:
                if rows:
                    break
                continue
            name = clean(m.group(1))
            men, women = int(m.group(2)), int(m.group(3))
            if name.startswith(GENDER_TOTAL):
                totals = (men, women)
                started = False
                continue
            rows.append({"constituency": name, "men": men, "women": women,
                         "seats": men + women})
    return rows, totals


def main():
    pages = page_text(report())

    lists, total = seats_by_list(pages)
    summed = sum(r["seats"] for r in lists)
    print(f"seats by list: {len(lists)} lists, {summed} seats, printed total {total}"
          + (" — mismatch" if summed != total else ""))
    scrambled = [r["rank"] for r in lists if r["name_scrambled"]]
    if scrambled:
        print(f"  rows {scrambled} had their name broken across the numbers")

    constituencies, totals = seats_by_constituency(pages)
    men = sum(r["men"] for r in constituencies)
    women = sum(r["women"] for r in constituencies)
    print(f"seats by constituency: {len(constituencies)} constituencies, "
          f"{men} men + {women} women = {men + women}, printed totals {totals}"
          + (" — mismatch" if (men, women) != totals else ""))

    os.makedirs("data", exist_ok=True)
    with open(OUT_SEATS, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, ["rank", "list_name", "seats", "name_scrambled"])
        writer.writeheader()
        writer.writerows(lists)
    print(f"wrote {OUT_SEATS} ({len(lists)} rows)")

    with open(OUT_CONSTIT, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, ["constituency", "seats", "men", "women"])
        writer.writeheader()
        writer.writerows(constituencies)
    print(f"wrote {OUT_CONSTIT} ({len(constituencies)} rows)")


if __name__ == "__main__":
    main()
