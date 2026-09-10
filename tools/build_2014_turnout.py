"""Turnout for the three 2014 contests, and how each accounts for its ballots.

The three declaring decisions each open with a "معطيات عامة" block giving the
number of voters, the valid votes, the spoilt ballots and the blank ballots.
Those four are collected here, per contest, and checked against each other.

They do not account for their ballots the same way, which is worth knowing
before any of these figures is used. Both presidential rounds count blanks
outside the valid votes, so voters = valid + spoilt + blank, exactly. The
legislative decision counts them inside: its valid-votes figure is the votes
cast for lists plus the blank ballots, so the identity there is
voters = valid + spoilt, and it misses by 29 ballots nationally.

Neither decision gives the size of the electoral register, so the denominator
of a turnout rate comes from the ISIE's own report on the year, published as
Official Gazette n° 32 of 21 April 2015: 5,306,324 voluntary registrations at
the close of the correction period of 2–8 November 2014, of which 4,926,084 in
the constituencies inside the republic and 380,240 in those abroad. That is the
register as it stood between the legislative election and the presidential
rounds, so it is the right denominator for the two presidential rounds; the
legislative election ran on a smaller register, so its rate here is a slight
understatement. The rate is recomputed rather than quoted either way: the report
states no turnout figure at all.

Writes:
    data/elections_2014_turnout.csv   3 rows
"""
import csv, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _jort_2014 as J

OUT = "data/elections_2014_turnout.csv"

DECISION = "آلت عمليات الاقتراع"
# The contests, in the order they were held, with the date of the poll.
CONTESTS = [
    ("legislative", "legislative", "2014-10-26"),
    ("presidential_r1", "presidential_r1", "2014-11-23"),
    ("presidential_r2", "presidential_r2", "2014-12-21"),
]
FIGURES = [("voters", "للناخبين"), ("valid_votes_lists", "لكل القائمات"),
           ("valid_votes", "الجملي للأصوات"), ("spoilt_ballots", "الملغاة"),
           ("blank_ballots", "البيضاء")]
# The report's sentence on the register, on one line of n° 32 of 2015.
REGISTER = "العدد الإجمالي للمسجلين"
REGISTER_TAIL = "الإجمالي للمسجلين"


def general_data(text):
    """The voters / valid / spoilt / blank block of a decision."""
    out = {}
    for line in map(J.clean, J.lines(text)):
        squeezed = J.squeeze(line)
        for key, label in FIGURES:
            if J.squeeze(label) in squeezed and key not in out:
                got = J.numbers(line)
                if got:
                    out[key] = got[-1]
    return out


def register():
    """(total, at home, abroad) registrations, from the ISIE's 2014 report.

    One sentence of the report carries all three, and they are checked against
    each other: the two parts must come to the total.
    """
    for text in J.pages(J.issue("report")):
        for line in map(J.clean, J.lines(text)):
            if J.squeeze(REGISTER_TAIL) not in J.squeeze(line):
                continue
            got = [n for n in J.numbers(line) if n > 100000]
            if len(got) == 3:
                total, home, abroad = got
                if home + abroad == total:
                    return total, home, abroad
    raise LookupError(REGISTER)


def main():
    total, home, abroad = register()
    print(f"the register: {total} = {home} at home + {abroad} abroad")

    rows, problems = [], []
    for contest, source, date in CONTESTS:
        pages = J.pages(J.issue(source))
        page = next(i for i, text in enumerate(pages)
                    if any(DECISION in line
                           for line in map(J.clean, J.lines(text))))
        block = general_data(pages[page])
        lists = block.get("valid_votes_lists")
        # Blanks sit inside the legislative decision's valid votes and outside
        # the presidential ones', so what "accounted for" means differs.
        accounted = block["valid_votes"] + block["spoilt_ballots"]
        if lists is None:
            accounted += block["blank_ballots"]
        elif lists + block["blank_ballots"] != block["valid_votes"]:
            problems.append(f"{contest}: the votes cast for lists plus the "
                            "blank ballots are not the valid votes")
        rows.append({
            "contest": contest, "poll_date": date,
            "registered": total,
            "voters": block["voters"],
            "valid_votes": block["valid_votes"],
            "valid_votes_lists": lists or "",
            "spoilt_ballots": block["spoilt_ballots"],
            "blank_ballots": block["blank_ballots"],
            "blanks_inside_valid_votes": 1 if lists is not None else 0,
            "ballots_accounted": accounted,
            "ballot_identity_gap": block["voters"] - accounted,
            "turnout_pct": round(100 * block["voters"] / total, 2),
            "source_issue": f"{J.ISSUES[source][0]} n° "
                            f"{J.ISSUES[source][1].lstrip('0')}",
            "source_page": page + 1,
        })
        print(f"{contest}: {block}")

    write(OUT, rows)
    for row in rows:
        print(f"{row['contest']}: {row['voters']} voters, "
              f"{row['turnout_pct']}% of the register, ballot identity "
              f"{'closes' if not row['ballot_identity_gap'] else 'off by ' + str(row['ballot_identity_gap'])}")
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
