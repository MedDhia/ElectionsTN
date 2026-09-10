"""Annotate a real procès-verbal with the cells the turnout calculation reads.

Why this figure exists
----------------------
Turnout here is `w_voted / a_registered`, and both numbers are handwritten on a
scanned form. Every claim this repo makes about participation rests on two boxes
of ink, so it is worth being able to point at them.

The figure also makes visible the asymmetry that every turnout caption states in
words. The numerator is triangulated: three other lines on the same form
constrain it, and the form even prints the difference itself as a check. The
denominator is constrained by nothing. Drawn side by side, the arithmetic
support and its absence are obvious in a way a sentence cannot manage.

The reference form
------------------
Bureau `01060210102`, the same scan `tools/pv_template.py` uses as its layout
reference, chosen because it reads cleanly and its accounts all close. Cell
geometry comes from `.cache/pv_template.json` -- the field boxes the locator
found -- so the rectangles are the ones the reader actually sampled, not boxes
drawn by eye over a picture.

Its numbers: 1,226 registered, 353 voted, so 28.79% turnout. The papers block
closes exactly (337 valid + 2 blank + 14 spoilt = 353) and the form's own
printed difference on line 3 reads 0000.

No Arabic in the labels: matplotlib has no bidi or shaping support and mangles
it. The Latin letter in each label is the transliteration of the Arabic line
marker on the form, and the monospace name is the column in
`data/pv_presidential_2024.csv`, so the figure doubles as a map from the paper
to the dataset.
"""

import argparse
import csv
import textwrap
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from make_maps import HILITE, INK, INK_2, RAMP, SURFACE, save_figure

# The explanation column is this wide in characters. Fixed so the canvas is
# stable: see the wrap note below.
WHY_COLS = 118

TEMPLATE_JSON = ".cache/pv_template.json"
TEMPLATE_PNG = ".cache/pv_template.png"
PV = "data/pv_presidential_2024.csv"
OUT_DIR = "docs/figures"

# (badge, field, line marker, role colour, what it is, what constrains it)
ANNOTATIONS = [
    ("1", "a_registered", "a", HILITE,
     "DENOMINATOR — registered voters at this station",
     "Constrained by NOTHING. It appears in none of the form's eight "
     "identities, so no other number on the paper can contradict it and the "
     "decoder cannot correct it. This is the one field read by classifier "
     "alone."),
    ("2", "w_voted", "w", RAMP[6],
     "NUMERATOR — voters who voted",
     "Constrained twice: line (c) must equal it, and the form prints their "
     "difference itself on line 3."),
    ("3", "c_signed", "c", RAMP[4],
     "voters who signed the register",
     "Identity c_eq_w: (c) must equal (w). Here both read 353."),
    ("4", "n_total", "n", RAMP[4],
     "total papers accounted for — a form line, not a published column",
     "Identity match3: (w) − (n) is printed on the form as line 3, and reads "
     "0000 here."),
    ("5", "match3", "3", RAMP[4],
     "the form's printed check on (w) − (n) — also not published",
     "Pre-printed for the clerk to fill. A non-zero value is the form telling "
     "you the two disagree."),
    ("6", "valid", "s.", RAMP[2],
     "valid papers — with blank and spoilt below it",
     "Identity papers_sum: valid + blank + spoilt = (n). Here 337 + 2 + 14 = "
     "353, so the numerator is reachable from the counted papers too."),
    ("7", "s_extracted", "s", RAMP[2],
     "ballots extracted from the urn",
     "Identity match1: (c) − (s) is printed as line 1. A third route to the "
     "same number."),
]


def field_box(cells, pad=6):
    """One rectangle around a field's four digit cells."""
    x0 = min(c[0] for c in cells) - pad
    y0 = min(c[1] for c in cells) - pad
    x1 = max(c[0] + c[2] for c in cells) + pad
    y1 = max(c[1] + c[3] for c in cells) + pad
    return x0, y0, x1 - x0, y1 - y0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--formats", help="comma-separated, e.g. pdf,png")
    args = ap.parse_args()
    for p in (TEMPLATE_JSON, TEMPLATE_PNG, PV):
        if not os.path.exists(p):
            sys.exit(f"missing {p}")

    tpl = json.load(open(TEMPLATE_JSON, encoding="utf-8"))
    code = tpl["bureau_code"]
    fields = tpl["fields"]
    row = next(r for r in csv.DictReader(open(PV, encoding="utf-8"))
               if r["bureau_code"] == code)
    img = plt.imread(TEMPLATE_PNG)
    h, w = img.shape[:2]

    reg, vot = int(row["a_registered"]), int(row["w_voted"])
    turnout = 100.0 * vot / reg

    # The form is 1.37:1 landscape; the key below it needs about half that
    # again, so the canvas is sized from the image rather than guessed.
    fig_w = 13.0
    form_h = fig_w * h / w
    key_h = 6.8
    fig = plt.figure(figsize=(fig_w, form_h + key_h), facecolor=SURFACE)
    ax = fig.add_axes([0, key_h / (form_h + key_h), 1, form_h / (form_h + key_h)])
    ax.imshow(img)
    ax.set_axis_off()

    for badge, field, marker, colour, _, _ in ANNOTATIONS:
        if field not in fields:
            print(f"  {field}: not in the template, skipped")
            continue
        cells = fields[field]
        if field == "valid":
            # Draw one box over valid + blank + spoilt: the identity is about
            # the three together, and three separate boxes would say otherwise.
            cells = cells + fields["blank"] + fields["spoilt"]
        bx, by, bw, bh = field_box(cells)
        ax.add_patch(Rectangle((bx, by), bw, bh, fill=False, edgecolor=colour,
                               linewidth=2.6 if badge in "12" else 1.8,
                               zorder=5))
        # badge to the left of the box, or right where the box hugs the margin
        lx = bx - 20 if bx > 90 else bx + bw + 20
        ax.add_patch(FancyBboxPatch(
            (lx - 13, by + bh / 2 - 13), 26, 26,
            boxstyle="round,pad=1", facecolor=colour, edgecolor="white",
            linewidth=1.2, zorder=6))
        ax.text(lx, by + bh / 2, badge, ha="center", va="center",
                fontsize=11, fontweight="bold",
                color="white" if badge in "1234567" else INK, zorder=7)

    ax.set_xlim(-70, w + 40)
    ax.set_ylim(h, -10)

    # ---- the key
    kx, ky = 0.035, (key_h - 0.55) / (form_h + key_h)
    fig.text(0.035, 1 - 0.012, "", va="top")
    fig.text(kx, ky, "Where turnout comes from on the form",
             fontsize=15, fontweight="bold", color=INK, va="top",
             transform=fig.transFigure)
    fig.text(kx, ky - 0.030,
             f"Bureau {code} · {reg:,} registered · {vot:,} voted · "
             f"turnout {turnout:.2f}%",
             fontsize=10.5, color=INK_2, va="top", transform=fig.transFigure)

    line = ky - 0.062
    # Row pitch derived from the type size rather than guessed: an 8.2pt line
    # at 1.45 linespacing is 0.165in, and the canvas is form_h + key_h inches
    # tall, so a wrapped row needs that much more room per extra line.
    line_frac = (8.2 / 72.0) * 1.45 / (form_h + key_h)
    step = 0.0125 + 1.6 * line_frac
    for badge, field, marker, colour, what, why in ANNOTATIONS:
        # `n_total`, `m_total` and the four match lines are read off the form
        # by the decoder but are not columns in the published CSV, so their
        # value here is the one written on this paper.
        on_form = {"n_total": str(int(row["valid"]) + int(row["blank"])
                                  + int(row["spoilt"])),
                   "match3": "0"}
        if field == "valid":
            shown = f"{row['valid']}+{row['blank']}+{row['spoilt']}"
        else:
            shown = row.get(field) or on_form.get(field, "—")
        fig.add_artist(FancyBboxPatch(
            (kx, line - 0.008), 0.016, 0.016,
            boxstyle="round,pad=0.002", facecolor=colour, edgecolor="white",
            linewidth=0.8, transform=fig.transFigure))
        fig.text(kx + 0.008, line, badge, ha="center", va="center",
                 fontsize=8.5, fontweight="bold", color="white",
                 transform=fig.transFigure)
        fig.text(kx + 0.026, line, f"({marker})", fontsize=9.5,
                 color=INK, va="center", fontweight="bold",
                 transform=fig.transFigure)
        fig.text(kx + 0.052, line, field, fontsize=9.5, color=INK,
                 va="center", family="monospace", transform=fig.transFigure)
        fig.text(kx + 0.148, line, f"= {shown}", fontsize=9.5, color=INK,
                 va="center", family="monospace", transform=fig.transFigure)
        fig.text(kx + 0.238, line, what, fontsize=9.5, color=INK,
                 va="center", transform=fig.transFigure)
        # Wrapped before the figure is drawn, not after. save_figure uses
        # bbox_inches="tight", which expands the canvas around any text that
        # overflows it -- an unwrapped line here grew the render by 102px and
        # would size the figure to its own longest sentence.
        wrapped = textwrap.fill(why, WHY_COLS)
        fig.text(kx + 0.238, line - 0.0125, wrapped, fontsize=8.2,
                 color=INK_2, va="top", linespacing=1.45,
                 transform=fig.transFigure)
        line -= step + line_frac * wrapped.count("\n")

    foot = (
        f"turnout = (w) voters ÷ (a) registered = {vot:,} ÷ {reg:,} = "
        f"{turnout:.2f}%   ·   Boxes are the cells the reader actually sampled, "
        f"taken from the locator's own field map in .cache/pv_template.json, "
        f"not drawn by eye.\n"
        f"The Latin letter in each row transliterates the Arabic line marker on "
        f"the paper; the monospace name is the column in "
        f"data/pv_presidential_2024.csv. Every number here is handwritten, and "
        f"the whole dataset is 9,448 forms like this one.\n"
        f"Note the asymmetry: rows 3–7 all constrain the numerator, and the "
        f"form even prints two of those differences itself. Nothing constrains "
        f"row 1. That is why turnout is a certified numerator over an "
        f"uncertified denominator.")
    fig.text(kx, line - 0.004, foot, fontsize=8.4, color=INK_2, va="top",
             transform=fig.transFigure)

    os.makedirs(OUT_DIR, exist_ok=True)
    formats = tuple(args.formats.split(",")) if args.formats else ("pdf", "png")
    made = save_figure(fig, f"{OUT_DIR}/pv_turnout_fields", formats)
    plt.close(fig)
    for f in made:
        print(f"    {os.path.getsize(f):>9,}  {f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
