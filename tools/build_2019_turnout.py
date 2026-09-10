"""Dataset 12a — 2019 turnout, the three "معطيات عامة" blocks of the ISIE report.

Each of the three 2019 contests — the presidential first round, the presidential
run-off and the legislative election — is introduced in the report by the same
five-figure block: registered voters, voters who turned out, valid votes, spoilt
ballots, blank ballots. The labels come out of the text layer scrambled against
their values, but the five figures always appear in that order, so they are read
positionally and then checked against the identity the block itself implies:

    valid + spoilt + blank == voters

Both presidential rounds satisfy it exactly. The legislative block does not: its
figures fall 207 short of the stated turnout. That is the source's arithmetic,
not this parser's, so the row is written with the gap recorded rather than
adjusted.

Usage: python3 tools/build_2019_turnout.py
"""
import csv, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _rapport_2019 import pages as page_text, report

OUT = "data/elections_2019_turnout.csv"

BLOCK = "معطيات عامة"
# The block is only the results one when it carries the ballot-paper lines
# ("الملغاة" — spoilt; the text layer transposes its lam and meem).
BALLOTS = "لغاة"
FIGURE = re.compile(r"\b\d{5,8}\b")
FIELDS = ["registered", "voters", "valid_votes", "spoilt_ballots", "blank_ballots"]
# In document order: round one, the run-off, then the legislative election.
CONTESTS = ["presidential_r1", "presidential_r2", "legislative"]


def blocks(pages):
    for i, text in enumerate(pages):
        if BLOCK not in text or BALLOTS not in text:
            continue
        after = text[text.index(BLOCK):]
        figures = [int(f) for f in FIGURE.findall(after)][:len(FIELDS)]
        if len(figures) == len(FIELDS):
            yield i, dict(zip(FIELDS, figures))


def main():
    pages = page_text(report())
    found = list(blocks(pages))
    if len(found) != len(CONTESTS):
        raise LookupError(f"expected {len(CONTESTS)} turnout blocks, found {len(found)}")

    rows = []
    for contest, (page, figures) in zip(CONTESTS, found):
        counted = figures["valid_votes"] + figures["spoilt_ballots"] + figures["blank_ballots"]
        gap = figures["voters"] - counted
        rows.append({
            "contest": contest, **figures,
            "ballots_accounted": counted,
            "ballot_identity_gap": gap,
            "turnout_pct": round(100 * figures["voters"] / figures["registered"], 2),
            "source_page": page + 1,
        })
        state = "balances" if gap == 0 else f"is {gap} short of the stated turnout"
        print(f"{contest}: {figures['voters']} voters, {state}")

    os.makedirs("data", exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, ["contest"] + FIELDS + [
            "ballots_accounted", "ballot_identity_gap", "turnout_pct", "source_page"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {OUT} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
