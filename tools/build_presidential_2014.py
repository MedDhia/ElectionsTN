"""The 2014 presidential result, from the two decisions that declared it.

Round one (23 November 2014) is ISIE decision n° 35 of 8 December 2014 and round
two (21 December 2014) is decision n° 36 of 29 December 2014; both are in the
Official Gazette, n° 99 and n° 105 (see `tools/_jort_2014.py` for why the Gazette
and not isie.tn). Between them they publish four tables:

* the national count for each of the 27 first-round candidates, printed in
  digits and spelled out in Arabic words,
* the same for the two candidates of round two,
* general data per collection centre for round one — voters, valid votes,
  spoilt and blank ballots — and a table per centre giving each candidate's
  vote, share and rank,
* one annex table for round two, giving both candidates' votes and the spoilt
  and blank ballots in each of the 33 centres.

Everything the decisions print twice is checked against itself here. The words
are parsed and compared with the digits; each centre's candidate votes are summed
against the total printed at the foot of its own table; every share is recomputed
from the votes and the printed valid total; each printed rank is compared with
the row's position; and the 33 centres are summed against the national figures in
the decision's own "معطيات عامة" block. Both rounds also close the ballot
identity — valid plus spoilt plus blank against the number of voters — centre by
centre, which is the check the 2019 turnout figures had no way to pass.

Writes three files:
    data/presidential_2014_national.csv        29 rows (27 + 2)
    data/presidential_2014_constituency.csv    957 rows
    data/presidential_2014_centre_turnout.csv  66 rows
"""
import csv, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _jort_2014 as J
from arabic_numerals import _fold

OUT_NATIONAL = "data/presidential_2014_national.csv"
OUT_CENTRE = "data/presidential_2014_constituency.csv"
OUT_TURNOUT = "data/presidential_2014_centre_turnout.csv"

CENTRE = "مركز جمع"
DECISION = "آلت عمليات الاقتراع"
# The four figures of the "general data" block, each on its own line, keyed by
# a phrase from its label.
GENERAL = [("voters", "للناخبين"), ("valid_votes", "للأصوات"),
           ("spoilt_ballots", "الملغاة"), ("blank_ballots", "البيضاء")]
CENTRE_TOTAL = "العدد الجملي"
SHARE = re.compile(r"%\s*(\d+[.,]\d+)|(\d+[.,]\d+)\s*%")
TOLERANCE = 0.02          # percentage points, as in the 2019 builders


def share_value(match):
    """The percentage a `SHARE` match found, whichever side the sign fell."""
    return float((match.group(1) or match.group(2)).replace(",", "."))


def find(pages, phrase, start=0):
    """The first page at or after `start` whose text contains `phrase`."""
    for i in range(start, len(pages)):
        if any(phrase in line for line in map(J.clean, J.lines(pages[i]))):
            return i
    raise LookupError(phrase)


def general_data(text):
    """The voters / valid / spoilt / blank block of a decision."""
    out = {}
    for line in map(J.clean, J.lines(text)):
        for key, label in GENERAL:
            if label in line and key not in out:
                got = J.numbers(line)
                if got:
                    out[key] = got[-1]
    return out


def national_rows(text):
    """(name, spelled, digits, share) for each candidate of a national table.

    A row is a name, the count spelled out, the count in digits and the share.
    Round one fits each on one line; round two's counts run to seven words and
    wrap, so the tail of the words lands after the digits and the share. The
    row is therefore read by kind rather than by position: the one percentage
    is the share, the one long integer the count, everything before the first
    number word is the name and every number word after it is the spelling.
    """
    rows, previous = [], ""
    for line in map(J.clean, J.lines(text)):
        share = SHARE.search(line)
        if not share:
            previous = line
            continue
        # The line on its own first: joining is only ever needed when the row
        # wrapped, and joining a row that did not wrap drags the header in.
        row = read_row(line, share) or read_row(f"{previous} {line}", share)
        previous = ""
        if row:
            rows.append(row)
    return rows


def read_row(line, share):
    """One national-table row read out of `line`, or None if it is not one."""
    rest = SHARE.sub(" ", J.clean(line)).split()
    digits = [t for t in rest if t.isdigit() and len(t) > 3]
    if len(digits) != 1:
        return None
    rest = [t for t in rest if t != digits[0]]
    cut = next((i for i, t in enumerate(rest) if J.is_number_word(t)), len(rest))
    name, words = rest[:cut], [t for t in rest[cut:] if J.is_number_word(t)]
    if not name or not words:
        return None
    return " ".join(name), " ".join(words), int(digits[0]), share_value(share)


FILLER = {"بن", "بنت", "ال"}


def name_words(name):
    """The content words of a name, folded and stripped of their article."""
    out = []
    for word in J.clean(name).split():
        folded = _fold(word)
        folded = folded[2:] if folded.startswith("ال") else folded
        if folded and folded not in FILLER:
            out.append(folded)
    return out


def same_person(short, full):
    """Whether a centre table's short name and a full civil name agree.

    The national table gives the full civil-status name and the centre tables
    an everyday short form — "محمد الهاشمي بن يوسف حامدي" against "محمد الهاشمي
    حامدي" — so the two are compared on the words they share. One word is
    allowed to differ, because the Gazette's national table spells one
    candidate's given name "يسين" where its own centre tables have "ياسين".
    """
    a, b = name_words(short), name_words(full)
    if not a or not b or a[-1] != b[-1]:
        return False
    return len(set(a) & set(b)) >= len(set(a)) - 1


def centre_tables(pages, first):
    """Yield (centre, [(rank, name, votes, share)], printed total)."""
    for text in pages[first:]:
        lines = list(map(J.clean, J.lines(text)))
        heads = [l for l in lines if l.startswith(CENTRE)]
        if not heads:
            return
        centre = J.clean(heads[0][len(CENTRE):])
        rows, total = [], None
        for line in lines:
            if line.startswith(CENTRE_TOTAL):
                got = J.numbers(line)
                total = got[-1] if got else None
                continue
            share = SHARE.search(line)
            tokens = line.split()
            if not share or not tokens or not tokens[0].isdigit():
                continue
            rest = tokens[1:]
            votes = [t for t in rest if t.isdigit()]
            name = [t for t in rest if not re.fullmatch(r"[\d.,%]+", t)]
            if not votes or not name:
                continue
            rows.append((int(tokens[0]), " ".join(name), int(votes[-1]),
                         share_value(share)))
        if rows:
            yield centre, rows, total


def table_rows(path, page, columns):
    """Rows of `columns` numbers, left to right, off one page's glyph grid.

    Both tables read this way group thousands with a space, which the text
    layer cannot be trusted to undo, and both carry a centre name that may end
    in a digit — "تونس 1" — which lands in a column of its own on the right and
    is dropped by taking the leftmost `columns` cells.
    """
    out = []
    for _, _, cells in J.grid(path, page):
        if len(cells) >= columns:
            out.append([value for _, _, value in cells[:columns]])
    return out


def annex_names(text):
    """The centre names of the round-two annex, in the order it prints them.

    The annex names a centre in the same cell as its figures, and the last two
    names wrap onto the line above, so a row's name is whatever of it is not a
    figure, joined to the line before when that line has no figures at all.
    """
    names, carry = [], ""
    for line in map(J.clean, J.lines(text)):
        words = [t for t in line.split() if not re.fullmatch(r"[\d,.%]+", t)]
        figures = len(line.split()) - len(words)
        if figures < 5 or "المجموع" in line:
            carry = " ".join(words) if not figures else ""
            continue
        names.append(J.clean(f"{carry} {' '.join(words)}"))
        carry = ""
    return names


def check_share(votes, valid, printed):
    if not valid:
        return "no-total"
    recomputed = round(100 * votes / valid, 2)
    return "agree" if abs(recomputed - printed) <= TOLERANCE else "differs"


def main():
    r1_path, r2_path = J.issue("presidential_r1"), J.issue("presidential_r2")
    r1, r2 = J.pages(r1_path), J.pages(r2_path)

    # ---------------------------------------------------------------- round one
    decision = find(r1, DECISION)
    r1_general = general_data(r1[decision])
    r1_national = national_rows(r1[decision + 1])
    centres, r1_rows = [], []
    for centre, rows, total in centre_tables(r1, decision + 3):
        centres.append(centre)
        r1_rows.append((centre, rows, total))
    print(f"round one: decision on page {decision + 1}, {len(r1_national)} "
          f"candidates, {len(centres)} collection centres")
    print(f"  {r1_general}")

    # Voters, spoilt and blank per centre; valid is the fourth column and is
    # cross-checked below against the foot of each centre's own table.
    general = table_rows(r1_path, decision + 2, 4)
    r1_turnout = [dict(zip(("blank_ballots", "spoilt_ballots", "valid_votes",
                            "voters"), row)) for row in general]

    # ---------------------------------------------------------------- round two
    r2_decision = find(r2, DECISION)
    r2_general = general_data(r2[r2_decision])
    r2_national = national_rows(r2[r2_decision])
    r2_table = table_rows(r2_path, r2_decision + 1, 5)
    r2_centres = annex_names(r2[r2_decision + 1])
    print(f"round two: decision on page {r2_decision + 1}, {len(r2_national)} "
          f"candidates, {len(r2_table)} rows in the annex")
    print(f"  {r2_general}")

    problems = []

    # ------------------------------------------------------------- the national
    national = []
    for stage, block, rows in (("r1", r1_general, r1_national),
                               ("r2", r2_general, r2_national)):
        ranks = {name: rank for rank, (name, *_) in enumerate(
            sorted(rows, key=lambda r: -r[2]), 1)}
        for order, (name, spelled, digits, share) in enumerate(rows, 1):
            value = J.parse_words(spelled)
            status = ("agree" if value == digits else
                      "words-differ" if value is not None else "words-unread")
            if status != "agree":
                problems.append(f"{stage} {name}: words read {value}, "
                                f"digits say {digits}")
            national.append({
                "round": stage, "ballot_order": order, "rank": ranks[name],
                "candidate": J.clean(name), "votes": digits,
                "share_pct": share,
                "share_check": check_share(digits, block["valid_votes"], share),
                "votes_spelled": J.clean(spelled), "words_value": value,
                "words_check": status,
            })
        summed = sum(r[2] for r in rows)
        if summed != block["valid_votes"]:
            problems.append(f"{stage}: candidate votes come to {summed}, "
                            f"printed valid total is {block['valid_votes']}")
    # The centre tables number their rows in the order the national table lists
    # the candidates, so a row's rank identifies whose vote it is.
    r1_order = [J.clean(name) for name, *_ in r1_national]

    # -------------------------------------------------------- by centre, round 1
    constituency, turnout = [], []
    for centre, rows, total in r1_rows:
        summed = sum(r[2] for r in rows)
        if total is not None and summed != total:
            problems.append(f"r1 {centre}: votes come to {summed}, printed "
                            f"total is {total}")
        for position, (rank, name, votes, share) in enumerate(rows, 1):
            full = r1_order[rank - 1] if rank <= len(r1_order) else ""
            if not same_person(name, full):
                problems.append(f"r1 {centre}: rank {rank} is {name}, which is "
                                f"not the national table's {full}")
            constituency.append({
                "round": "r1", "centre": centre, "rank": rank,
                "rank_check": "agree" if rank == position else "differs",
                "candidate": J.clean(name), "candidate_full": full,
                "votes": votes, "share_pct": share,
                "share_check": check_share(votes, total, share),
                "centre_valid_votes": total,
            })

    if len(r1_turnout) < len(centres):
        problems.append(f"round one general data: {len(r1_turnout)} rows for "
                        f"{len(centres)} centres")
    for centre, figures, (_, _, total) in zip(centres, r1_turnout, r1_rows):
        if figures["valid_votes"] != total:
            problems.append(f"r1 {centre}: general data says "
                            f"{figures['valid_votes']} valid votes, the "
                            f"centre's own table says {total}")
        accounted = sum(figures[k] for k in ("valid_votes", "spoilt_ballots",
                                             "blank_ballots"))
        turnout.append({
            "round": "r1", "centre": centre, "voters": figures["voters"],
            "valid_votes": figures["valid_votes"],
            "spoilt_ballots": figures["spoilt_ballots"],
            "blank_ballots": figures["blank_ballots"],
            "ballots_accounted": accounted,
            "ballot_identity_gap": figures["voters"] - accounted,
        })

    # -------------------------------------------------------- by centre, round 2
    r2_rows = [r for r in national if r["round"] == "r2"]
    winner, runner_up = [r["candidate"] for r in sorted(
        r2_rows, key=lambda r: r["ballot_order"])]
    for centre, row, printed in zip(centres, r2_table, r2_centres):
        # Both rounds are keyed to the round-one spelling of a centre's name,
        # so the annex's own heading is checked against it rather than used.
        if not set(name_words(printed)) & set(name_words(centre)):
            problems.append(f"r2 row {len(turnout) + 1} is headed {printed}, "
                            f"where round one has {centre}")
        blank, spoilt, second, first, voters = row
        valid = first + second
        accounted = valid + spoilt + blank
        if voters != accounted:
            problems.append(f"r2 {centre}: {voters} voters against "
                            f"{accounted} ballots accounted for")
        turnout.append({
            "round": "r2", "centre": centre, "voters": voters,
            "valid_votes": valid, "spoilt_ballots": spoilt,
            "blank_ballots": blank, "ballots_accounted": accounted,
            "ballot_identity_gap": voters - accounted,
        })
        for rank, (candidate, votes) in enumerate(
                sorted(((winner, first), (runner_up, second)),
                       key=lambda p: -p[1]), 1):
            constituency.append({
                "round": "r2", "centre": centre, "rank": rank,
                "rank_check": "", "candidate": candidate,
                "candidate_full": candidate, "votes": votes,
                "share_pct": round(100 * votes / valid, 2),
                "share_check": "recomputed", "centre_valid_votes": valid,
            })

    # ------------------------------------------------------- national vs centres
    for stage, block in (("r1", r1_general), ("r2", r2_general)):
        for field in ("voters", "valid_votes", "spoilt_ballots",
                      "blank_ballots"):
            summed = sum(t[field] for t in turnout if t["round"] == stage)
            if summed != block[field]:
                problems.append(f"{stage} {field}: the centres come to "
                                f"{summed}, the decision says {block[field]}")

    write(OUT_NATIONAL, national)
    write(OUT_CENTRE, constituency)
    write(OUT_TURNOUT, turnout)

    words_ok = sum(1 for r in national if r["words_check"] == "agree")
    r1_share = [r for r in constituency if r["round"] == "r1"]
    shares_ok = sum(1 for r in r1_share if r["share_check"] == "agree")
    ranks_ok = sum(1 for r in r1_share if r["rank_check"] == "agree")
    print(f"{words_ok}/{len(national)} national counts confirmed by their "
          "own spelled-out form")
    print(f"{shares_ok}/{len(r1_share)} round-one shares recompute to the "
          f"printed value, {ranks_ok}/{len(r1_share)} ranks to the printed rank")
    if problems:
        print(f"{len(problems)} checks failed:")
        for line in problems:
            print("  !", line)
    else:
        print("every check passed")


def write(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {path} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
