"""The 2023 local-council PV's field geometry, for `pv_fields.map_fields`.

The 2023 form is landscape where the 2024 presidential one is portrait, but it
is the same instrument underneath: three numbered stages laid out as columns and
read right-to-left, each stage's fields running top to bottom in printed order,
and the same field names carry over unchanged.

    stage 1  معطيات حول عملية الاقتراع     (أ) registered, (ب) delivered,
             — right-hand column           (ج) signed, (د) damaged, (ر) remaining
    stage 2  after the urn is opened        (س) extracted, (ص) valid,
             — middle column                (ع) blank, (ف) spoilt
    stage 3  المطابقات — left-hand column   match1, (و) voted, (م) total,
                                            match2, (ن) total, match3

What differs is the vote block. A presidential form has one box per candidate
for three known candidates; this one has **nine numbered slots** laid out as
three side-by-side groups of three rows, and a local constituency fields
anywhere from one candidate to ten. The slots are printed whether or not they
are used, so all nine boxes are detected on every form and an unused slot reads
as an empty box — which is what lets the vote total decide how many slots were
really in play.

Each group's columns run, right to left: the printed slot number (ر/ع), the
candidate's name in hand, the score spelled out in Arabic words, and the score
in digits. The digit box of one group abuts the next group's slot-number column
on its left, so the grid detector merges the two and returns a five-cell run
where the field is four cells. Those specs are therefore right-aligned: the
field is the run's last four cells, and the slot number that came with it is
dropped.

Ten-candidate constituencies — three of the 938 in round one — overflow the nine
slots. Nothing here handles that; their tenth slot is simply not on the form.

Every field is four cells wide except the declared result (`q_declared`), whose
printed box is three: a polling bureau's valid-vote total does not reach four
digits. The expected run length is declared per column rather than assumed, so
that box is read as the three digits it holds instead of borrowing a fourth from
whatever sits beside it.
"""
from pv_fields import map_fields as _map_fields

# Slot k's votes, named for the order the candidate appears on the ballot paper
# ("حسب الترتيب الوارد في ورقة التصويت"), which is all the form itself says
# about who the vote was for.
SLOTS = [f"slot{i}" for i in range(1, 10)]

COLUMNS = [
    ("stage1", (0.64, 0.78), (0.26, 0.48), 4,
     ["a_registered", "b_delivered", "c_signed", "d_damaged", "r_remaining"]),
    ("stage2", (0.32, 0.45), (0.26, 0.48), 4,
     ["s_extracted", "valid", "blank", "spoilt"]),
    ("stage3", (0.01, 0.14), (0.23, 0.51), 4,
     ["match1", "w_voted", "m_total", "match2", "n_total", "match3"]),
    # The three vote groups, right to left: slots 1-3, 4-6, 7-9.
    ("slots123", (0.68, 0.76), (0.57, 0.73), 4, SLOTS[0:3], "right"),
    ("slots456", (0.36, 0.44), (0.57, 0.73), 4, SLOTS[3:6], "right"),
    ("slots789", (0.05, 0.13), (0.57, 0.73), 4, SLOTS[6:9], "right"),
    # The declared result is the one three-cell box on the form: a bureau's
    # valid total does not reach four digits, and the printed grid says so.
    ("q", (0.55, 0.66), (0.71, 0.78), 3, ["q_declared"]),
    ("match4", (0.19, 0.31), (0.71, 0.78), 4, ["match4"], "right"),
]

# Every field the template locates, and how many a complete map has.
ORDER = [name for spec in COLUMNS for name in spec[4]]
WANT = len(ORDER)


def map_fields(rows, width, height, origin=(0, 0)):
    """`pv_fields.map_fields` bound to this form's geometry."""
    return _map_fields(rows, width, height, origin, columns=COLUMNS)
