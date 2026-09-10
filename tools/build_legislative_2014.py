"""The 2014 legislative result: constituency figures, seats and the 217 members.

ISIE decision n° 34 of 21 November 2014, in Official Gazette n° 94, declares the
final results of the legislative election of 26 October 2014. Its body is
seventeen pages of running text rather than a table, and it is unusually
complete: for each of the 33 constituencies it gives the number of voters, the
valid votes, the valid votes cast for lists, the spoilt and blank ballots, the
number of seats and the electoral quotient, and then names every list that won a
seat, how many it won, and every member elected on it.

That last part makes this the membership roll of the Assembly of the
Representatives of the People as it was declared — 217 people, by name, by list
and by constituency — which no other file in this repository holds for any year.

The decision's own arithmetic is checked throughout: the 33 constituencies are
summed against the national block at the head of the decision, each
constituency's ballot identity is closed (valid plus spoilt plus blank against
voters, and lists' votes against valid votes), the seats named per list are
summed against the seat count printed for the constituency, the quotient is
recomputed from the votes and the seats, and the whole comes to 217.

Writes three files:
    data/legislative_2014_constituency_results.csv   33 rows
    data/legislative_2014_elected_members.csv       217 rows
    data/legislative_2014_seats.csv                  one row per list with a seat
"""
import csv, os, re, sys
from fractions import Fraction

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _jort_2014 as J

OUT_CONSTITUENCY = "data/legislative_2014_constituency_results.csv"
OUT_MEMBERS = "data/legislative_2014_elected_members.csv"
OUT_SEATS = "data/legislative_2014_seats.csv"

DECISION = "آلت عمليات الاقتراع"
HEADING = "الدائرة"
# Each figure of a constituency's block, keyed by a phrase from its label. The
# order matters: "لكل القائمات" is a longer form of the valid-votes label, so it
# is tested first.
FIGURES = [
    ("voters", "الناخبين الذين قاموا"),
    ("valid_votes_lists", "لكل القائمات"),
    ("valid_votes", "الأصوات المصرح"),
    ("spoilt_ballots", "الملغاة"),
    ("blank_ballots", "البيضاء"),
    ("seats", "عدد المقاعد"),
    ("quotient", "الحاصل الانتخابي"),
]
NATIONAL = [("voters", "للناخبين"), ("valid_votes_lists", "لكل القائمات"),
            ("valid_votes", "الجملي للأصوات"), ("spoilt_ballots", "الملغاة"),
            ("blank_ballots", "البيضاء")]
# "3 مقاعد" for three or more, and these two spellings for one and for two.
# Two seats appear in both cases, "مقعدين اثنين" and "مقعدان اثنان".
ONE_SEAT, TWO_SEATS = "مقعد وحيد", ("مقعدين اثنين", "مقعدان اثنان")
LIST = "قائمة"
# "تحصلت على" — a shadda breaks the verb into two tokens in places ("ت حصلت",
# "تحص لت"), so it is matched squeezed and its pieces are counted off the end
# of the list's name.
VERB, ASSIGNED = "تحصلت", "أسند"
END = "الفصل 2"
MEMBER = re.compile(r"^\.?(\d{1,2})[.\s]+(.+)$")
# The ordinal in "the first electoral constituency of the governorate of Tunis".
ORDINALS = {"الأولى": " 1", "الثانية": " 2", "الثالثة": " 3", "الوحيدة": ""}


def find(pages, phrase):
    for i, text in enumerate(pages):
        if any(phrase in line for line in map(J.clean, J.lines(pages[i]))):
            return i
    raise LookupError(phrase)


DECIMAL = re.compile(r"\d+[.,]\d+")


def figure(line):
    """(key, value) for a labelled figure line, or None.

    Two of the seven need more than the digits. The quotient is a decimal, and
    a decimal comma would be read away as a thousands separator, so it is
    matched as a decimal first. And a seat count of one or two is spelled out —
    "عدد المقاعد: مقعد وحيد" — rather than printed in digits.
    """
    label = J.squeeze(line)
    for key, phrase in FIGURES:
        if J.squeeze(phrase) not in label:
            continue
        if key == "quotient":
            decimal = DECIMAL.search(line)
            if decimal:
                return key, float(decimal.group().replace(",", "."))
        if key == "seats":
            spelled = spelled_seats(label)
            if spelled:
                return key, spelled
        got = J.numbers(line)
        if got:
            return key, got[-1]
    return None


def spelled_seats(label):
    """1 or 2 where a seat count is written out, else None."""
    if any(J.squeeze(form) in label for form in TWO_SEATS):
        return 2
    if J.squeeze(ONE_SEAT) in label:
        return 1
    return None


def seats_won(line):
    """How many seats a list line says it won.

    Three or more are printed in digits, one and two are spelled out, and one
    constituency spells three out as well ("تحصلت على ثلاثة مقاعد"), so a
    number word between the verb and "مقاعد" is read too.
    """
    spelled = spelled_seats(J.squeeze(line))
    if spelled:
        return spelled
    got = [n for n in J.numbers(line) if 1 <= n <= 40]
    if got:
        return got[0]
    words = [t for t in line.split() if J.is_number_word(t)]
    return J.parse_words(" ".join(words)) if words else None


def is_list_line(line):
    """Whether `line` says how many seats a list won and to whom they went.

    Almost every one of these opens with "قائمة", but one in سليانة does not,
    so the test is the sentence rather than the opening word.
    """
    squeezed = J.squeeze(line)
    return VERB in squeezed and ASSIGNED in squeezed


def list_name(line):
    """The list's name, which runs from "قائمة" to the verb that follows it.

    Where the verb falls is the only hard part: a shadda breaks it across
    tokens in a third of these lines, and in one it breaks "على" too, so the
    line's words are squeezed into one string, the verb found in that, and the
    offset mapped back to the word it starts in.
    """
    tokens = line.split()
    start = next((i for i, t in enumerate(tokens) if t.startswith(LIST)), 0)
    squeezed = [J.squeeze(t) for t in tokens]
    at = "".join(squeezed[start:]).find(VERB)
    if at < 0:
        return None
    offset, end = 0, len(tokens)
    for i in range(start, len(tokens)):
        if offset <= at < offset + len(squeezed[i]):
            end = i
            break
        offset += len(squeezed[i])
    # The one list the decision does not introduce with "قائمة" is given it
    # here, so that it aggregates with its own name in the other constituencies.
    text = J.clean(" ".join(tokens[start:end]))
    return text if text.startswith(LIST) else f"{LIST} {text}"


def tidy(name):
    """A person's name with the reversal's stray punctuation taken off."""
    return J.clean(" ".join(t.strip(".,،:") for t in name.split()))


def describe(heading):
    """A constituency heading without its number or the reversal's colons."""
    return J.clean(J.PUNCT.sub(" ", heading)).lstrip("0123456789 ")


def short_name(description, names):
    """"الدائرة الانتخابية الأولى لولاية تونس" -> "تونس 1".

    The decision describes a constituency where its own annex and the
    presidential decisions abbreviate it, so the description is turned back
    into the abbreviation: the ordinal becomes a suffix and the place is
    whatever follows "لولاية" for the 27 at home, or the country or region the
    voters abroad are resident in for the other six. The result is then snapped
    onto the canonical spelling, which differs by a word for two of the six.
    """
    text = J.clean(J.PUNCT.sub(" ", description))
    ordinal = next((o for o in ORDINALS if o in text), None)
    place = re.sub(r".*?(لولاية|المقيمين)\s*", "", text)
    place = re.sub(r"\s*والمسجلين بها.*$", "", place).strip(" :.")
    if place.startswith("ب") and place[1:2] not in ("ا", "أ", "إ", ""):
        place = place[1:]
    elif place.startswith("بال"):
        place = place[1:]
    guess = J.clean(place + ORDINALS.get(ordinal, ""))
    return J.canonical(guess, names) or guess, guess


def split_figures(line):
    """One merged line of figures back into one line each.

    Two of the 231 figure lines were set as a single line, and every figure's
    label starts with "عدد", so the line is cut before each of those.
    """
    parts = re.split(r"\s(?=عدد\s)", line)
    return parts if len(parts) > 1 else [line]


def constituencies(pages):
    """Yield one dict per constituency, in the order the decision prints them.

    Each block starts with a numbered heading and ends at the next one; the
    figures come first, then the lists that won seats, each followed by its
    members.
    """
    block, current_list, position = None, None, 0
    for text in pages:
        for line in map(J.clean, J.lines(text)):
            if line.startswith(END):
                if block:
                    yield block
                return
            tokens = line.split()
            if tokens and tokens[0].isdigit() and HEADING in line \
                    and "الانتخابية" in line and len(tokens) > 3:
                if block:
                    yield block
                number = int(tokens[0])
                block = {"number": number, "description": line,
                         "lists": [], "members": []}
                current_list, position = None, 0
                continue
            if not block:
                continue
            found = [figure(part) for part in split_figures(line)]
            if any(found):
                for got in found:
                    if got and got[1] is not None:
                        block[got[0]] = got[1]
                continue
            if is_list_line(line):
                current_list = list_name(line)
                block["lists"].append((current_list, seats_won(line)))
                position = 0
                continue
            member = MEMBER.match(line)
            if member and current_list and not figure(line):
                position += 1
                block["members"].append((current_list, position,
                                         tidy(member.group(2))))


def main():
    pages = J.pages(J.issue("legislative"))
    start = find(pages, DECISION)
    national = {}
    for line in map(J.clean, J.lines(pages[start])):
        for key, label in NATIONAL:
            if J.squeeze(label) in J.squeeze(line) \
                    and key not in national:
                got = J.numbers(line)
                if got:
                    national[key] = got[-1]
    print(f"decision on page {start + 1}; national block {national}")

    names = J.centres()
    blocks = list(constituencies(pages[start:]))
    print(f"{len(blocks)} constituencies read")

    problems, rows, members, seats = [], [], [], {}
    for block in blocks:
        name, printed = short_name(block["description"], names)
        if name not in names:
            problems.append(f"constituency {block['number']}: "
                            f"{printed} is not one of the 33")
        # The legislative decision counts blank ballots inside its valid-votes
        # figure and the presidential ones do not, so the identity here is
        # voters = valid + spoilt, with valid = lists' votes + blank.
        accounted = block["valid_votes"] + block["spoilt_ballots"]
        named = sum(count for _, count in block["lists"])
        if named != block["seats"]:
            problems.append(f"{name}: lists account for {named} seats, "
                            f"the block says {block['seats']}")
        if len(block["members"]) != block["seats"]:
            problems.append(f"{name}: {len(block['members'])} members named "
                            f"for {block['seats']} seats")

        lists_gap = (block["valid_votes"] - block["valid_votes_lists"]
                     - block["blank_ballots"])
        if lists_gap:
            problems.append(f"{name}: valid votes exceed the lists' votes plus "
                            f"the blank ballots by {lists_gap}")
        exact = Fraction(block["valid_votes_lists"], block["seats"])
        # The Gazette rounds the quotient half up, and truncates it in two
        # constituencies; Python's own round would go half to even.
        quotient = float((exact * 100 + Fraction(1, 2)).__floor__()) / 100
        if block["quotient"] not in (quotient, float((exact * 100).__floor__()) / 100):
            problems.append(f"{name}: quotient recomputes to {quotient}, "
                            f"printed as {block['quotient']}")
        rows.append({
            "constituency": name, "constituency_number": block["number"],
            "constituency_printed": printed,
            "voters": block["voters"], "valid_votes": block["valid_votes"],
            "valid_votes_lists": block["valid_votes_lists"],
            "spoilt_ballots": block["spoilt_ballots"],
            "blank_ballots": block["blank_ballots"],
            "ballots_accounted": accounted,
            "ballot_identity_gap": block["voters"] - accounted,
            "lists_and_blank_gap": lists_gap,
            "seats": block["seats"], "quotient_printed": block["quotient"],
            "quotient_recomputed": quotient,
            "lists_with_seats": len(block["lists"]),
            "description": describe(block["description"]),
        })
        for list_of, count in block["lists"]:
            seats[list_of] = seats.get(list_of, 0) + count
        for list_of, position, member in block["members"]:
            members.append({"constituency": name, "list_name": list_of,
                            "seat_on_list": position, "member": member})

    for key in national:
        summed = sum(r[key] for r in rows)
        if summed != national[key]:
            problems.append(f"{key}: the constituencies come to {summed}, "
                            f"the decision says {national[key]}")
    total_seats = sum(r["seats"] for r in rows)
    if total_seats != 217:
        problems.append(f"the seats come to {total_seats}, not 217")
    if len(members) != total_seats:
        problems.append(f"{len(members)} members named for {total_seats} seats")

    ranked = sorted(seats.items(), key=lambda kv: (-kv[1], kv[0]))
    write(OUT_CONSTITUENCY, rows)
    write(OUT_MEMBERS, members)
    write(OUT_SEATS, [{"rank": i, "list_name": name, "seats": count}
                      for i, (name, count) in enumerate(ranked, 1)])
    closed = sum(1 for r in rows if not r["ballot_identity_gap"])
    net = sum(r["ballot_identity_gap"] for r in rows)
    print(f"{total_seats} seats across {len(rows)} constituencies and "
          f"{len(seats)} lists; {len(members)} members named")
    print(f"the ballot identity closes in {closed}/{len(rows)} "
          f"constituencies; the 33 gaps net to {net} ballots against the "
          "decision's own national figures")
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
