"""Audit the bureau-level 2023 local reading, and roll it up to constituencies.

Three questions, in order of how much they can be trusted.

**Does each form agree with itself?** Every published row says how many of its
eight identities the raw cell-by-cell reading already satisfied and how many
cells the arithmetic had to overrule. This counts them, per block, so the
coverage figures quoted anywhere else can be checked against the file.

**Do the bureaux of one constituency agree with each other?** They should sum to
one coherent constituency result: the same slate, a plausible register, and a
valid-vote total that is the sum of its parts. This rolls them up and writes
`data/local_2023_t1_bureau_rollup.csv`, one row per constituency, flagging the
ones where some of the bureaux could not be read — because a partial
constituency is not a constituency result, and summing it anyway would
understate it silently.

**Does it agree with what ISIE published?** Only partly answerable.
`data/local_2023_candidate_results.csv` is itself an OCR reading of ISIE's
own results decisions and covers 938 of the round's constituencies; its keys are
Arabic delegation and constituency names from those PDFs, while a bureau is
keyed by the eleven-digit code printed on its form. There is no crosswalk
between the two, and inventing one out of two sets of OCR'd Arabic names would
be a worse measurement than the one it was checking. What is comparable without
a join is the shape of the thing: the number of constituencies, the distribution
of slate sizes, and the national totals. Those are reported and no more is
claimed.

Usage: python3 tools/audit_local_2023.py
       PV_ELECTION=locales_2023_t2 python3 tools/audit_local_2023.py
"""
import collections, csv, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pv_fields_local_2023 as F
from decode_local_2023 import OUT as READING
import pv_local_2023 as L

PUBLISHED_CANDIDATES = "data/local_2023_candidate_results.csv"
PUBLISHED_TURNOUT = "data/local_2023_constituency_turnout.csv"
ROLLUP = f"data/{L.ELECTION.replace('locales_', 'local_')}_bureau_rollup.csv"
# The published extraction covers round one only; the shape comparison is
# meaningless against a round-two reading, so it is skipped there.
ROUND = L.ELECTION[-1]

ROLLUP_COLUMNS = ["constituency", "scope", "constituency_name", "n_candidates",
                  "bureaux", "bureaux_read", "bureaux_votes_certified",
                  "bureaux_valid_corroborated", "complete", "registered",
                  "voters", "valid_votes", "blank_ballots", "spoilt_ballots",
                  "turnout_pct", "slot_votes", "winning_slot", "winning_votes",
                  "margin_votes"]


def number(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def load(path):
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def per_form(rows):
    """What the forms say about themselves."""
    read = [r for r in rows if r["status"] == "read"]
    print(f"{len(read)}/{len(rows)} forms decoded")
    for block in ("votes", "papers", "ballots", "valid_corroborated"):
        col = block if block == "valid_corroborated" else f"{block}_certified"
        n = sum(1 for r in read if r.get(col) == "1")
        print(f"  {block:18s} certified on {n:5d} bureaux "
              f"({100 * n / max(1, len(rows)):5.1f}% of the corpus)")
    ident = collections.Counter(r["identities_ok"] for r in read)
    print("  identities the raw reading already satisfied:",
          dict(sorted(ident.items(), key=lambda kv: -int(kv[0] or 0))))
    corrected = collections.Counter(min(4, number(r["cells_corrected"]) or 0)
                                    for r in read)
    print("  cells the arithmetic overruled (4 = four or more):",
          dict(sorted(corrected.items())))
    # A مطابقة is the bureau's own note that its two counts of one quantity came
    # out different. Where the block it belongs to is certified, a non-zero value
    # is not a misreading — it is a discrepancy the polling bureau reported.
    for field, block in (("match1", "ballots"), ("match2", "ballots"),
                         ("match3", "papers"), ("match4", "votes")):
        rows_ = [r for r in read if r.get(f"{block}_certified") == "1"
                 and number(r.get(field)) is not None]
        nz = sum(1 for r in rows_ if number(r[field]) != 0)
        if rows_:
            print(f"  {field}: non-zero on {nz} of {len(rows_)} bureaux whose "
                  f"{block} block is certified ({100 * nz / len(rows_):.2f}%)")
    return read


def rollup(rows):
    """One row per constituency, summed over its bureaux."""
    groups = collections.defaultdict(list)
    for r in rows:
        if r["constituency"]:
            groups[r["constituency"]].append(r)
    out = []
    for key, forms in sorted(groups.items()):
        n_cands = number(forms[0]["n_candidates"]) or 0
        usable = [r for r in forms if r.get("votes_certified") == "1"]
        read = [r for r in forms if r["status"] == "read"]
        slots = [sum((number(r.get(s)) or 0) for r in usable)
                 for s in F.SLOTS[:n_cands]]
        row = {
            "constituency": key,
            "scope": forms[0].get("scope", ""),
            "constituency_name": forms[0].get("constituency_name", ""),
            "n_candidates": n_cands,
            "bureaux": len(forms),
            "bureaux_read": len(read),
            "bureaux_votes_certified": len(usable),
            "bureaux_valid_corroborated": sum(
                1 for r in forms if r.get("valid_corroborated") == "1"),
            "complete": int(len(usable) == len(forms)),
            "registered": sum((number(r.get("a_registered")) or 0) for r in read),
            "voters": sum((number(r.get("w_voted")) or 0) for r in usable),
            "valid_votes": sum((number(r.get("valid")) or 0) for r in usable),
            "blank_ballots": sum((number(r.get("blank")) or 0) for r in usable),
            "spoilt_ballots": sum((number(r.get("spoilt")) or 0) for r in usable),
            "slot_votes": " ".join(str(v) for v in slots),
        }
        if slots:
            order = sorted(range(len(slots)), key=lambda i: -slots[i])
            row["winning_slot"] = order[0] + 1
            row["winning_votes"] = slots[order[0]]
            row["margin_votes"] = (slots[order[0]] - slots[order[1]]
                                   if len(slots) > 1 else slots[order[0]])
        else:
            row["winning_slot"] = row["winning_votes"] = row["margin_votes"] = ""
        row["turnout_pct"] = (round(100 * row["voters"] / row["registered"], 2)
                              if row["registered"] else "")
        out.append(row)
    return out


def check_rollup(rolled):
    """The constituency-level consistency checks, and what they found."""
    problems = 0
    for row in rolled:
        if not row["valid_votes"]:
            continue
        summed = sum(int(v) for v in row["slot_votes"].split() if v)
        if row["n_candidates"] and summed != row["valid_votes"]:
            problems += 1
            print(f"  ! {row['constituency']}: slots sum to {summed}, "
                  f"valid votes {row['valid_votes']}")
        if row["voters"] and row["registered"] and row["voters"] > row["registered"]:
            problems += 1
            print(f"  ! {row['constituency']}: more voters than registered")
    complete = sum(1 for r in rolled if r["complete"])
    print(f"{len(rolled)} constituencies, {complete} with every bureau certified")
    print(f"{problems} constituency-level checks failed")
    return problems


def against_published(rolled):
    """What can be compared without inventing a name crosswalk."""
    if not os.path.exists(PUBLISHED_CANDIDATES):
        return
    cand = [r for r in load(PUBLISHED_CANDIDATES) if r["round"] == ROUND]
    turnout = [r for r in load(PUBLISHED_TURNOUT) if r["round"] == ROUND]
    pub_cons = {(r["governorate"], r["delegation"], r["constituency"])
                for r in cand}
    pub_turn = {(r["governorate"], r["delegation"], r["constituency"])
                for r in turnout}
    print("\nagainst the published extraction "
          "(no code-to-name crosswalk exists, so this is shape only)")
    print(f"  constituencies: {len(rolled)} read from PVs, "
          f"{len(pub_cons)} in the candidate results, "
          f"{len(pub_turn)} in the turnout file")
    mine = collections.Counter(r["n_candidates"] for r in rolled
                               if r["n_candidates"])
    theirs = collections.Counter()
    by_cons = collections.defaultdict(int)
    for r in cand:
        by_cons[(r["governorate"], r["delegation"], r["constituency"])] += 1
    theirs.update(by_cons.values())
    print("  slate sizes, from the PVs:      ",
          dict(sorted(mine.items())))
    print("  slate sizes, from the decisions:",
          dict(sorted(theirs.items())))
    pub_valid = sum(number(r["votes_valid_best"]) or 0 for r in turnout)
    mine_valid = sum(r["valid_votes"] for r in rolled)
    print(f"  valid votes: {mine_valid} over {len(rolled)} constituencies from "
          f"the PVs, {pub_valid} over {len(pub_turn)} from the decisions")
    published_self_check(turnout)


def published_self_check(turnout):
    """What the published extraction says about its own rows.

    This is the one comparison a missing crosswalk does not block, because it
    needs no join: both files carry per-row checks of their own arithmetic, and
    the rates are directly comparable. The published extraction reads ISIE's
    results decisions through OCR and says, row by row, whether the ballot
    identity and the candidate sum came out; where they did not, or where a
    figure had to be repaired, it says that too. Quoting those rates beside the
    per-block certification rates above is the fair way to say what reading the
    primary scans buys, and it cuts both ways — the decisions are the
    authoritative document, and the PVs are only the paperwork behind them.
    """
    n = len(turnout)
    ballot = sum(1 for r in turnout if r["ballot_identity_ok"] == "true")
    cand_ok = sum(1 for r in turnout if r["candidate_sum_ok"] == "true")
    repaired = sum(1 for r in turnout if r["turnout_repaired"] not in ("", None))
    over = sum(1 for r in turnout
               if (number(r["registered"]) or 0) and (number(r["voters"]) or 0)
               and number(r["voters"]) > number(r["registered"]))
    print(f"  the published extraction's own checks, over its {n} "
          f"round-{ROUND} rows: "
          f"ballot identity holds on {ballot} ({100 * ballot / max(1, n):.0f}%), "
          f"candidate sum on {cand_ok} ({100 * cand_ok / max(1, n):.0f}%), "
          f"{repaired} rows carry a repaired figure, and {over} report more "
          f"voters than registered")


def main():
    rows = load(READING)
    read = per_form(rows)
    rolled = rollup(rows)
    print()
    check_rollup(rolled)
    with open(ROLLUP, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=ROLLUP_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in rolled:
            w.writerow(r)
    print(f"wrote {ROLLUP} ({len(rolled)} rows)")
    against_published(rolled)
    # National totals, over the bureaux whose own arithmetic vouches for them.
    certified = [r for r in read if r.get("votes_certified") == "1"]
    print(f"\n{len(certified)} bureaux with a certified vote account: "
          f"{sum((number(r['valid']) or 0) for r in certified)} valid votes, "
          f"{sum((number(r['w_voted']) or 0) for r in certified)} voters")


if __name__ == "__main__":
    main()
