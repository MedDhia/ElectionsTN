"""Dot maps of where a Tunisian family name actually lives.

What this draws, and why a dot map rather than a choropleth
-----------------------------------------------------------
`data/voter_surnames_2024/` counts every registered voter's surname down to the
imada and the polling centre. A surname is a **count**, and a count is the one
quantity a choropleth cannot show: fill an imada by how many Trabelsis it holds
and the eye reads the fill as a density over its area, so the empty south turns
dark and Tunis turns invisible. Fill it by *share of the imada electorate* and a
30-voter hamlet outranks a 4,000-voter quarter of Tunis.

A dot map states the count and nothing else. One dot is a fixed number of
voters, so ten thousand voters look like ten thousand voters wherever they are,
and the picture that emerges is the thing the dataset is for: which names are
spread flat across the country and which ones sit in a few places.

**Concentration is not continuity.** A name that sits in one delegation is a
name whose holders are *registered* there in 2024, and the register cannot say
why. Tunisia's twentieth century moved people: rural depopulation into Greater
Tunis and the Sahel, the resettlement schemes of the 1960s and 70s, the
displacements of the colonial period and after, work migration to the coast and
abroad. A concentration can be a family that stayed, a family that was moved
together, or a family that arrived together. The figures say where the names are
and nothing about how they got there.

Three things the reader has to be told, and every figure says them
------------------------------------------------------------------
**Placement inside an imada is arbitrary.** The finest geography the registry
gives is the imada, and the finest geometry that exists for Tunisia is the same
2,084 imadas (OCHA COD-AB admin4). Dots are scattered at random *inside* the
imada that holds them, which is what a dot-density map has always done -- the
count per imada is data, the position within it is not. Every figure prints
this.

**The zoom panel is drawn at polling-centre resolution and is not more
precise.** Within an imada the registry splits the same voters across named
polling centres -- a primary school, a youth centre -- and that split is real
data: it says a surname sits at one school out of six. But no coordinate exists
for a polling centre anywhere in the ISIE material, so each centre is given an
arbitrary anchor inside its imada and its dots cluster there. The *clumping* is
data. *Where* the clump sits is not.

**Dots are voters, not people.** The registry is the electorate: adults who
registered by 6 July 2024. A family with many minors, or one that did not
register, is smaller here than it is on the ground.

The set of surnames
-------------------
`--set common` draws `NAMED_COMMON`, the list of common Tunisian family names
the maintainer asked for, in the order given. It is a named list rather than a
top-N off the register, and the two are not the same set: a frequency ranking
puts the patronymics `بن محمد` and `بن علي` near the top, which are father's
names doing duty as surnames and not families at all, and it leaves out names
that are common in the ordinary sense while sitting below the cut. The register
still decides every number on every figure -- the list decides only which names
get one, and the tool says so when a name it was given is not in the register.

The named list is not the whole common set. Every family name the register puts
above `--min-common-voters` holders is drawn too, so that a reader looking for a
name as ordinary as `سعيدي` or `غربي` finds one. What that automatic set leaves
out is the patronymics: `بن محمد` is the fifth commonest string in the register
and `بن علي` the tenth, but they are a father's name standing in for a family
name, and mapping them would map the given name Mohamed rather than a family.
They are skipped unless the named list asks for one by name.

`--set concentrated` is computed, not named: the surnames whose voters sit in
the fewest places, by Herfindahl index over imadas among names with at least
`--min-voters` holders, excluding anything already in the named list. The two
answer different questions. A common name is everywhere by construction; the
interesting map is the rare name that is 60% of one imada -- wherever that
concentration came from.

Article variants are pooled. `العبيدي` and `عبيدي` are one family written two
ways -- 33,347 and 29,100 voters -- and mapping them apart would halve a family
and draw the same geography twice. Names are pooled on the normalised string
with the leading definite article removed, and each figure names the spellings
it pooled and their counts.

Colour
------
**One hue for one quantity.** A single-surname map encodes one count, so it uses
one colour: `#184f95`, the dark end of the repo's documented blue ramp. Dot maps
fail when the dots are pale -- a 1.2pt mark at 40% lightness disappears against
any ground -- so the dark end is the only end of that ramp a dot can use.

**The overlay is the one figure that needs a qualitative palette**, because
several surnames share one map and the reader has to tell them apart --
including the 8% of men who cannot separate red from green. It takes four of
the eight Okabe-Ito colours, a published palette designed for exactly this,
rather than hues picked by eye -- and four rather than six because six of them
on one map is *not* separable under protanopia, which is a thing measured here
and not assumed.
`tools/check_dot_palette.py` asserts what that palette has to deliver here:
every pair separable under normal vision and under simulated protanopia,
deuteranopia and tritanopia, and every dot dark enough to hold against the land.

Reproducibility
---------------
Every random placement is seeded from the registry date, the imada's own p-code
and a stream taken from the surname itself, so a rebuild puts every dot back
where it was whatever subset is being drawn. Arabic labels are shaped
by Pillow's Raqm layout engine and set in Amiri (`apt-get install -y
fonts-hosny-amiri`); without that font the figures build with Latin labels only
and say so.

Usage:
    python3 tools/make_surname_dots.py --set common --top 24
    python3 tools/make_surname_dots.py --set concentrated --top 16
    python3 tools/make_surname_dots.py --set sheets      # composites + overlay
    python3 tools/make_surname_dots.py --set all
"""

import argparse
import collections
import csv
import gzip
import math
import os
import sys
import zlib

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import PathCollection
from matplotlib.offsetbox import AnnotationBbox, OffsetImage

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from arabic_latin import ar_norm
from arabic_translit import slug, translit
from make_maps import (ARCHIVE, GOV_LINE, INK, INK_2, RAMP, SURFACE, albers,
                       feature_path, figure_dir, load_layer, save_figure)

FAMILY = "surnames"
XW = "data/surname_imada_crosswalk.csv"
IMADA_GZ = "data/voter_surnames_2024/surnames_by_imada.csv.gz"
CENTER_GZ = "data/voter_surnames_2024/surnames_by_polling_center.csv.gz"
METRICS_GZ = "data/voter_surnames_2024/surnames_spatial_metrics.csv.gz"
INDEX_OUT = "data/maps/surname_dot_index.csv"

# The dark end of the documented blue ramp. A dot has no area to carry a pale
# shade, so the pale end of that ramp is unusable here.
DOT = RAMP[5]
LAND = SURFACE
MESH = GOV_LINE

# Four of the eight Okabe-Ito colours, in the order the overlay assigns them.
#
# Four, not six, and the number was measured rather than chosen.
# `tools/check_dot_palette.py` scores every pair under simulated protanopia,
# deuteranopia and tritanopia: six of these hues on one map fall to 12.2 CIEDE2000
# under protanopia (blue against the reddish purple) and 10.9 under tritanopia,
# well inside the range where two dot colours read as one. Four is the largest
# subset of the palette that keeps every pair at least 15 apart under all three
# dichromacies *and* every dot at least 25 from the land fill -- which is what
# rules out the palette's own yellow, at 16.3 against a near-white ground.
OVERLAY_COLOURS = ["#0072b2", "#d55e00", "#56b4e9", "#000000"]

# The common family names to draw, as the maintainer gave them, in that order.
# They are written here without the definite article because `family_key` pools
# `الطرابلسي` with `طرابلسي` anyway; what the figure prints is whichever
# spelling the register uses more often, with the split stated underneath.
#
# All 31 resolve in the 2024 register, across three orders of magnitude --
# `عبيدي` at 62,447 holders down to `صنهاجي` at 291 -- so the sheets state the
# dot value they share and a small name simply draws few dots. A name that does
# not resolve is reported and skipped rather than silently dropped.
# Patronymic prefixes. A surname beginning with one of these is a father's name
# doing duty as a family name, so the automatic frequency set skips it; the
# named list above still draws one if it asks. `بو` is deliberately not here:
# `بوعزيزي` is a family name, not a patronymic.
PATRONYMIC_PREFIXES = ("بن", "ابن", "ولد")

NAMED_COMMON = [
    "طرابلسي", "همامي", "عياري", "دريدي", "جلاصي", "مثلوثي", "وسلاتي",
    "يعقوبي", "ماجري", "مرزوقي", "فرشيشي", "عرفاوي", "برهومي", "قاسمي",
    "حمروني", "خميري", "مهذبي", "نفزي", "رياحي", "زغبي", "عكرمي", "لواتي",
    "هواري", "صنهاجي", "عبيدي", "ورغي", "تليلي", "هميسي", "ذوادي", "بجاوي",
    "هيشري",
]

# A dot map wants enough dots to show texture and few enough that a city does
# not become one solid blob. Measured on the commonest name on the map
# (Abidi, 61,869 voters): at 2,400 dots Greater Tunis reads as dense, not solid.
TARGET_DOTS = 2400
DOT_VALUES = (1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000)

# The registry's own date, as the seed. Nothing about the figures depends on
# this number being anything in particular; what matters is that it is fixed.
SEED = 20240706

TOL_NATIONAL = 0.002      # same simplification the imada choropleths use
TOL_ZOOM = 0.0004

AMIRI = "/usr/share/fonts/opentype/fonts-hosny-amiri/Amiri-Regular.ttf"

# Layout. The map is flushed right and the gutter on the left carries the
# title, the counts, the dot key and the zoom panel.
GUTTER = 2.05


# ---- the surnames ---------------------------------------------------------
def family_key(surname_norm):
    """Pool a surname with its own article variant.

    `العبيدي` and `عبيدي` are one family name; so are `القاسمي` and `قاسمي`.
    The registry prints whichever the voter's card carries, and mapping the two
    apart would draw half a family twice. The article is stripped only where
    something recognisable is left, so `الله` in a compound survives.
    """
    s = " ".join(ar_norm(surname_norm or "").split())
    if s.startswith("ال") and len(s) > 3:
        s = s[2:]
    return s


def read_csv(path):
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def pooled_national():
    """National (domestic + diaspora) voters per pooled family, from the metrics.

    Used only to pick which surnames are worth drawing. Everything a figure
    prints is recomputed from the imada table, which is what the map is drawn
    from and which excludes the diaspora for want of geometry.
    """
    total = collections.Counter()
    spelling = collections.defaultdict(collections.Counter)
    with gzip.open(METRICS_GZ, "rt", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            key = family_key(row["surname_norm"])
            if not key:
                continue
            n = int(row["national_voters"])
            total[key] += n
            spelling[key][ar_norm(row["surname_norm"])] += n
    return total, {k: c.most_common(1)[0][0] for k, c in spelling.items()}


def imada_counts(keys):
    """Per-imada voter counts for a set of pooled families.

    Returns the counts keyed by adm4 p-code, plus what had to be left off the
    map: the diaspora, which has no geometry, and the handful of registry
    imadas the bridge could not resolve.
    """
    xw = {(r["governorate_ar"], r["constituency_ar"], r["imada_ar"]): r
          for r in read_csv(XW)}
    counts = collections.defaultdict(collections.Counter)
    variants = collections.defaultdict(collections.Counter)
    diaspora = collections.Counter()
    unplaced = collections.Counter()
    with gzip.open(IMADA_GZ, "rt", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            key = family_key(row["surname_norm"])
            if key not in keys:
                continue
            n = int(row["voter_count"])
            variants[key][ar_norm(row["surname_norm"])] += n
            if row["is_diaspora"] == "1":
                diaspora[key] += n
                continue
            hit = xw.get((row["governorate"], row["constituency"], row["imada"]))
            if hit is None:
                unplaced[key] += n
                continue
            counts[key][hit["adm4_pcode"]] += n
    return counts, variants, diaspora, unplaced


def centre_counts(keys):
    """Per-polling-centre counts, for the zoom panels."""
    xw = {(r["governorate_ar"], r["constituency_ar"], r["imada_ar"]): r
          for r in read_csv(XW)}
    out = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
    with gzip.open(CENTER_GZ, "rt", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["is_diaspora"] == "1":
                continue
            key = family_key(row["surname_norm"])
            if key not in keys:
                continue
            hit = xw.get((row["governorate"], row["constituency"], row["imada"]))
            if hit is None:
                continue
            out[key][hit["adm4_pcode"]][row["polling_center"]] += int(row["voter_count"])
    return out


def dispersion(counter):
    """HHI and Shannon entropy of one family over the imadas it occupies."""
    total = sum(counter.values())
    if total <= 0:
        return 0.0, 0.0
    shares = [v / total for v in counter.values()]
    hhi = sum(s * s for s in shares)
    ent = -sum(s * math.log(s) for s in shares if s > 0)
    return hhi, ent


# ---- geometry -------------------------------------------------------------
class Geography:
    """The admin4 mesh, projected once and reused by every figure."""

    def __init__(self, tol=TOL_NATIONAL):
        self.props = {}
        self.paths = {}
        for f in load_layer("tun_admin4.geojson"):
            p = f["properties"]
            path = feature_path(f["geometry"], tol)
            if path is None:
                continue
            self.paths[p["adm4_pcode"]] = path
            self.props[p["adm4_pcode"]] = p
        self.gov_paths, self.gov_extent = [], {}
        for f in load_layer("tun_admin2.geojson"):
            path = feature_path(f["geometry"], tol * 2)
            if path is None:
                continue
            self.gov_paths.append(path)
            self.gov_extent[f["properties"]["adm2_name1"]] = path.get_extents()
        self._fallback = 0

    def by_governorate(self, gov_ar):
        return [c for c, p in self.props.items() if p["adm2_name1"] == gov_ar]

    def points(self, pcode, n, stream=0, path=None):
        """`n` points scattered uniformly inside one imada.

        Rejection sampling against the polygon itself rather than a disc around
        its centroid, because imadas are not discs: the southern ones are long
        desert strips and a disc would put dots in the next governorate. Seeded
        from the p-code and the stream, so the same imada draws the same points
        for the same surname on every rebuild, and different points for
        different surnames -- which is what keeps the overlay from stacking six
        surnames on one mark.
        """
        if n <= 0:
            return np.empty((0, 2))
        path = path if path is not None else self.paths[pcode]
        rng = np.random.default_rng(
            [SEED, stream, int.from_bytes(pcode.encode(), "little") % (2 ** 31)])
        (x0, y0), (x1, y1) = path.get_extents().get_points()
        got = []
        have = 0
        for _ in range(24):
            batch = max(64, int((n - have) * 4))
            cand = np.column_stack([rng.uniform(x0, x1, batch),
                                    rng.uniform(y0, y1, batch)])
            inside = cand[path.contains_points(cand)]
            if len(inside):
                got.append(inside)
                have += len(inside)
            if have >= n:
                break
        if have < n:
            # A sliver too thin to hit by rejection. Its centroid stands in for
            # the rest, which is visible as a stack rather than a scatter.
            self._fallback += 1
            p = self.props[pcode]
            cx, cy = albers([float(p["center_lon"])], [float(p["center_lat"])])
            pad = np.column_stack([np.repeat(cx, n - have), np.repeat(cy, n - have)])
            got.append(pad)
        return np.vstack(got)[:n]


def dot_value(total):
    """A round number of voters per dot, aiming at `TARGET_DOTS` dots."""
    want = total / float(TARGET_DOTS)
    for v in DOT_VALUES:
        if v >= want:
            return v
    return DOT_VALUES[-1]


def dots_per_unit(counts, dv):
    """Dots per imada: the count divided by the dot value, rounded at a half.

    A unit holding less than half a dot's worth draws nothing, which every
    figure states as its floor. Rounding up instead would put a mark on all
    2,069 imadas for any common name and the map would say only that Tunisia
    is inhabited.
    """
    out = {}
    for pcode, v in counts.items():
        n = int(v // dv) + (1 if (v % dv) * 2 >= dv else 0)
        if n:
            out[pcode] = n
    return out


# ---- Arabic labels --------------------------------------------------------
_FONT_WARNED = []


def arabic_image(text, colour=INK, px=190):
    """The surname, shaped and rendered, as an RGBA array.

    matplotlib does not shape Arabic -- it has no HarfBuzz -- so a label set
    through it comes out as unjoined letters in the wrong order, which is worse
    than no Arabic at all. Pillow built against Raqm does shape it, so the label
    is rendered there at high resolution and placed as an image. Returns None
    where the font is missing, and the caller falls back to Latin.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
        if not os.path.exists(AMIRI):
            raise FileNotFoundError(AMIRI)
        font = ImageFont.truetype(AMIRI, px, layout_engine=ImageFont.Layout.RAQM)
    except Exception as exc:                                  # pragma: no cover
        if not _FONT_WARNED:
            _FONT_WARNED.append(True)
            print(f"  note: Arabic labels disabled ({exc}); "
                  f"apt-get install -y fonts-hosny-amiri")
        return None
    pad = px // 3
    canvas = Image.new("RGBA", (px * len(text) + 4 * pad, px * 2 + 2 * pad),
                       (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.text((canvas.width - pad, pad), text, font=font,
              fill=matplotlib.colors.to_hex(colour), anchor="ra",
              direction="rtl", language="ar")
    return np.asarray(canvas.crop(canvas.getbbox()))


def place_arabic(ax, text, xy, height_pt, colour=INK, ha="left"):
    """Put a shaped Arabic label on the axes at a given cap height in points."""
    arr = arabic_image(text, colour)
    if arr is None:
        return False
    img = OffsetImage(arr, zoom=height_pt / arr.shape[0], resample=True)
    box = AnnotationBbox(img, xy, xycoords="axes fraction", frameon=False,
                         box_alignment=(0.0 if ha == "left" else 1.0, 1.0),
                         pad=0.0, annotation_clip=False)
    ax.add_artist(box)
    return True


# ---- drawing --------------------------------------------------------------
def base(ax, geo, pcodes=None, mesh_lw=0.10, gov_lw=0.55):
    """The land: the imada mesh, with the governorates drawn over it.

    When `pcodes` names a subset -- a zoom panel on one governorate -- the
    extent is taken from those units alone. Letting autoscale see the national
    governorate outlines instead put one governorate's dots in a frame the size
    of the country, which is how the first zoom panel came out four millimetres
    wide.
    """
    ax.set_aspect("equal")
    ax.set_axis_off()
    ax.set_facecolor(SURFACE)
    paths = ([geo.paths[c] for c in pcodes] if pcodes
             else list(geo.paths.values()))
    ax.add_collection(PathCollection(paths, facecolors=LAND, edgecolors=MESH,
                                     linewidths=mesh_lw, alpha=0.85, zorder=1))
    if gov_lw > 0:
        ax.add_collection(PathCollection(geo.gov_paths, facecolors="none",
                                         edgecolors=GOV_LINE,
                                         linewidths=gov_lw, zorder=2))
    if pcodes:
        xs = [p.get_extents().get_points() for p in paths]
        x0 = min(e[0][0] for e in xs); x1 = max(e[1][0] for e in xs)
        y0 = min(e[0][1] for e in xs); y1 = max(e[1][1] for e in xs)
        pad = 0.03 * max(x1 - x0, y1 - y0)
        ax.set_xlim(x0 - pad, x1 + pad)
        ax.set_ylim(y0 - pad, y1 + pad)
    else:
        ax.autoscale_view()


def scatter(ax, xy, colour=DOT, size=1.3, alpha=0.62, zorder=4):
    if len(xy):
        ax.scatter(xy[:, 0], xy[:, 1], s=size, c=colour, linewidths=0,
                   alpha=alpha, zorder=zorder)


def imada_dots(geo, counts, dv, stream):
    """Every dot for one surname at imada resolution."""
    per = dots_per_unit(counts, dv)
    chunks = [geo.points(pcode, n, stream=stream) for pcode, n in sorted(per.items())]
    xy = np.vstack(chunks) if chunks else np.empty((0, 2))
    return xy, sum(per.values()), len(per)


def centre_dots(geo, per_centre, counts, dv, stream, pcodes, tol=TOL_ZOOM):
    """Dots for one surname at polling-centre resolution, inside given imadas.

    Each centre is given an anchor inside its imada and its dots land in a disc
    around it, sized so the discs of one imada's centres tile it rather than
    overlap. The anchor is arbitrary -- no coordinate for a polling centre
    exists in any ISIE file -- so what this shows is that a surname sits in one
    centre out of six, never which one.
    """
    fine = {}
    for f in load_layer("tun_admin4.geojson"):
        code = f["properties"]["adm4_pcode"]
        if code in pcodes:
            p = feature_path(f["geometry"], tol)
            if p is not None:
                fine[code] = p
    out = []
    drawn = 0
    for pcode in sorted(pcodes):
        centres = per_centre.get(pcode)
        if not centres:
            # No centre breakdown: fall back to the imada's own count.
            n = dots_per_unit({pcode: counts.get(pcode, 0)}, dv).get(pcode, 0)
            if n:
                out.append(geo.points(pcode, n, stream=stream,
                                      path=fine.get(pcode)))
                drawn += n
            continue
        path = fine.get(pcode, geo.paths[pcode])
        anchors = geo.points(pcode, len(centres), stream=stream + 7919, path=path)
        (x0, y0), (x1, y1) = path.get_extents().get_points()
        radius = 0.32 * math.hypot(x1 - x0, y1 - y0) / max(math.sqrt(len(centres)), 1.0)
        for i, (name, v) in enumerate(sorted(centres.items())):
            n = dots_per_unit({name: v}, dv).get(name, 0)
            if not n:
                continue
            # crc32, not hash(): Python salts string hashing per process, so a
            # rebuild in a new interpreter would have moved every centre's dots.
            rng = np.random.default_rng(
                [SEED, stream, i, zlib.crc32(name.encode("utf-8"))])
            ang = rng.uniform(0, 2 * math.pi, n)
            rad = radius * np.sqrt(rng.uniform(0, 1, n))
            pts = np.column_stack([anchors[i, 0] + rad * np.cos(ang),
                                   anchors[i, 1] + rad * np.sin(ang)])
            keep = path.contains_points(pts)
            pts[~keep] = anchors[i]
            out.append(pts)
            drawn += n
    xy = np.vstack(out) if out else np.empty((0, 2))
    return xy, drawn


# ---- one surname, one figure ---------------------------------------------
class Gutter:
    """A left column that stacks text, keys and panels without colliding.

    Everything in the gutter is positioned in axes fractions, and an axes
    fraction is not a font size: the first version advanced the cursor by
    hand-tuned constants and the seven-line statistics block printed straight
    through the line after it. This converts points to fractions once, from the
    axes' own height, so a block of `n` lines advances by exactly `n` lines.
    """

    def __init__(self, fig, ax, x=0.012, top=0.985):
        self.fig, self.ax, self.x, self.y = fig, ax, x, top
        box = ax.get_position()
        self.height_pt = fig.get_size_inches()[1] * 72.0 * box.height

    def frac(self, points):
        return points / self.height_pt

    def text(self, body, size=7.2, colour=INK_2, weight=None, gap=0.55,
             lead=1.42):
        self.ax.text(self.x, self.y, body, transform=self.ax.transAxes,
                     fontsize=size, color=colour, va="top", ha="left",
                     fontweight=weight or "normal", linespacing=lead)
        lines = body.count("\n") + 1
        self.y -= self.frac(size * lead * lines + size * gap)
        return self.y

    def arabic(self, body, height_pt=20.0, colour=INK, gap=6.0):
        if place_arabic(self.ax, body, (self.x, self.y), height_pt, colour):
            self.y -= self.frac(height_pt + gap)
        return self.y

    def space(self, points):
        self.y -= self.frac(points)
        return self.y

    def dots(self, dv, n_dots, colour=DOT, size=7.5):
        """A row of three dots beside the value one of them carries."""
        y = self.y - self.frac(size * 0.55)
        self.ax.scatter([self.x + 0.008, self.x + 0.020, self.x + 0.032],
                        [y, y, y], transform=self.ax.transAxes, s=7.0,
                        c=colour, linewidths=0, alpha=0.9, zorder=6,
                        clip_on=False)
        label = f"1 dot = {dv:,} voter{'s' if dv > 1 else ''}"
        if n_dots:
            label += f"   ({n_dots:,} dots)"
        self.ax.text(self.x + 0.048, y, label, transform=self.ax.transAxes,
                     fontsize=size, color=INK, va="center", ha="left")
        self.y -= self.frac(size * 2.0)
        return self.y


def variant_note(variants):
    """How the two spellings of one family name split, in words not glyphs.

    The pooled spellings differ by the definite article and by nothing else --
    everything below that (tashkeel, tatweel, hamza carriers) is already folded
    before the fold happens here. So the split can be stated without printing
    Arabic through matplotlib, which cannot shape it.
    """
    with_art = sum(n for s, n in variants if s.startswith("ال"))
    without = sum(n for s, n in variants if not s.startswith("ال"))
    if not with_art or not without:
        return ""
    return (f"pooled: {with_art:,} written with the definite\n"
            f"article, {without:,} without")


def national_figure(geo, fam, stats, per_centre, out_dir):
    """One surname: the country in dots, with its home governorate blown up."""
    dv = dot_value(stats["mapped"])
    xy, n_dots, n_units = imada_dots(geo, stats["counts"], dv, stats["stream"])

    fig, ax = plt.subplots(figsize=(7.6, 8.4))
    base(ax, geo)
    scatter(ax, xy)
    x0, x1 = ax.get_xlim()
    ax.set_xlim(x1 - GUTTER * (x1 - x0), x1)

    g = Gutter(fig, ax)
    g.arabic(stats["display"], 22.0)
    g.text(translit(stats["display"]), size=13.0, colour=INK, weight="bold",
           gap=0.25)
    g.text("registered voters bearing this family name,\n"
           "2024 ISIE voter register (6 July 2024)", size=7.4, gap=1.1)
    g.text("\n".join([
        f"{stats['mapped']:,} voters on the map",
        f"{stats['share']:.3f}% of the electorate on the map",
        f"present in {len(stats['counts']):,} of "
        f"{stats['n_mapped_imadas']:,} mapped imadas",
        f"{stats['top_imada_share']:.1f}% of them in one imada:",
        f"{stats['top_imada']}",
        f"top governorate: {stats['top_gov']} ({stats['top_gov_share']:.1f}%)",
        f"HHI {stats['hhi']:.4f}   spatial entropy {stats['entropy']:.2f}",
    ]), size=7.6, colour=INK, gap=1.0)

    note = variant_note(stats["variants"])
    if note:
        g.text(note, size=6.6, gap=0.8)
    if stats["diaspora"] or stats["unplaced"]:
        g.text(f"off the map: {stats['diaspora']:,} registered abroad\n"
               f"+ {stats['unplaced']:,} in unmatched imadas", size=6.6, gap=1.0)

    g.dots(dv, n_dots)
    if dv >= 4:
        # The gap between presence and dots is the dot value's doing, and it can
        # be wide: Abidi is in 1,513 imadas and 529 of them hold the 25 voters a
        # dot needs. Saying only one of the two numbers misstates the other.
        g.text(f"{n_units:,} imadas hold the {math.ceil(dv / 2)} voters a dot\n"
               f"needs; the rest carry none", size=6.6, gap=1.4)

    # The zoom panel, at polling-centre resolution.
    gov = stats["top_gov_ar"]
    pcodes = [c for c in geo.by_governorate(gov) if c in stats["counts"]]
    if pcodes:
        g.text(f"{stats['top_gov']}, by polling centre", size=8.0, colour=INK,
               weight="bold", gap=0.4)
        zdv = dot_value(max(sum(stats["counts"][c] for c in pcodes), 1))
        top, height = g.y, 0.30
        iax = ax.inset_axes([0.012, top - height, 0.40, height])
        base(iax, geo, pcodes=geo.by_governorate(gov), mesh_lw=0.25, gov_lw=0.0)
        zxy, zdots = centre_dots(geo, per_centre, stats["counts"], zdv,
                                 stats["stream"], pcodes)
        scatter(iax, zxy, size=2.4, alpha=0.72)
        # The panel's own key sits beside it rather than under it: under it is
        # where the figure's footer already is, and the two printed through
        # each other on the first render.
        ax.scatter([0.435, 0.447, 0.459], [top - g.frac(5.0)] * 3,
                   transform=ax.transAxes, s=7.0, c=DOT, linewidths=0,
                   alpha=0.9, zorder=6, clip_on=False)
        ax.text(0.474, top - g.frac(5.0),
                f"1 dot = {zdv:,} voter{'s' if zdv > 1 else ''}",
                transform=ax.transAxes, fontsize=6.8, color=INK, va="center",
                ha="left")
        ax.text(0.435, top - g.frac(18.0),
                f"({zdots:,} dots)\n\n"
                "the dots cluster by\npolling centre: the\n"
                "split between centres\nis data, but a centre's\n"
                "own position is not\nrecorded in any ISIE\n"
                "file, so each one is\ngiven an arbitrary\n"
                "anchor inside its imada",
                transform=ax.transAxes, fontsize=6.2, color=INK_2, va="top",
                ha="left", linespacing=1.5)
        g.y = top - height

    ax.text(0.012, 0.012,
            "Dots are scattered at random inside the imada that holds them: the count per\n"
            "imada is data, the position within it is not. Boundaries: OCHA COD-AB admin4\n"
            "(2,084 imadas). Counts: ISIE preliminary voter register, 6 July 2024.",
            transform=ax.transAxes, fontsize=6.0, color=INK_2, va="bottom",
            ha="left", linespacing=1.5)

    stem = os.path.join(out_dir, f"{slug(stats['display'])}_dots")
    made = save_figure(fig, stem, formats=("pdf", "png"))
    plt.close(fig)
    return made, dv, n_dots, n_units


# ---- composites and the overlay ------------------------------------------
def composite(geo, families, stats_by, out_dir, stem, title, subtitle, cols=6,
              dv=None):
    """One sheet, one dot value, several surnames -- so the panels compare.

    Six columns rather than four, because Tunisia projects to an aspect of 2.14
    and a panel wide enough to hold a label beside the map wastes two thirds of
    itself on empty page. The labels therefore sit *above* each panel, where
    they cannot print through the country.

    `dv` is passed in when a set runs across more than one sheet, so that panels
    compare across the sheets and not only within one: the named list is 31
    names over three sheets, and a dot value computed per sheet would have made
    sheet 3 a different unit from sheet 1 while looking identical.
    """
    rows = int(math.ceil(len(families) / cols))
    dv = dv or dot_value(max(stats_by[k]["mapped"] for k in families))
    fig, axes = plt.subplots(rows, cols, figsize=(1.85 * cols, 4.7 * rows))
    axes = np.atleast_1d(axes).ravel()
    for ax in axes[len(families):]:
        ax.set_axis_off()
    for ax, key in zip(axes, families):
        st = stats_by[key]
        base(ax, geo, mesh_lw=0.05, gov_lw=0.30)
        xy, n_dots, _ = imada_dots(geo, st["counts"], dv, st["stream"])
        scatter(ax, xy, size=0.9, alpha=0.62)
        place_arabic(ax, st["display"], (0.0, 1.165), 11.0)
        ax.text(0.0, 1.052, translit(st["display"]), transform=ax.transAxes,
                fontsize=9.0, color=INK, va="bottom", ha="left",
                fontweight="bold")
        ax.text(0.0, 1.008,
                f"{st['mapped']:,} voters · {n_dots:,} dots · "
                f"HHI {st['hhi']:.3f}",
                transform=ax.transAxes, fontsize=6.0, color=INK_2,
                va="bottom", ha="left")
    fig.suptitle(title, x=0.008, y=0.995, ha="left", va="top", fontsize=15,
                 color=INK, fontweight="bold")
    fig.text(0.008, 0.968, subtitle, ha="left", va="top", fontsize=8.5,
             color=INK_2, linespacing=1.5)
    fig.text(0.008, 0.010,
             f"Every panel on one scale: 1 dot = {dv:,} voters, so a panel with "
             f"more dots holds more voters. Dots fall at random inside the imada "
             f"that holds them.\nCounts: ISIE preliminary voter register, "
             f"6 July 2024. Boundaries: OCHA COD-AB admin4.",
             ha="left", va="bottom", fontsize=6.6, color=INK_2, linespacing=1.5)
    fig.tight_layout(rect=(0.0, 0.032, 1.0, 0.945))
    made = save_figure(fig, os.path.join(out_dir, stem))
    plt.close(fig)
    return made, dv


def overlay(geo, families, stats_by, out_dir, stem):
    """The most concentrated surnames on one map, each in its own colour."""
    dv = dot_value(max(stats_by[k]["mapped"] for k in families))
    fig, ax = plt.subplots(figsize=(7.6, 8.4))
    base(ax, geo)
    drawn = []
    for i, key in enumerate(families):
        st = stats_by[key]
        colour = OVERLAY_COLOURS[i % len(OVERLAY_COLOURS)]
        xy, n_dots, n_units = imada_dots(geo, st["counts"], dv, st["stream"])
        scatter(ax, xy, colour=colour, size=2.2, alpha=0.80, zorder=4 + i)
        drawn.append((colour, st, len(st["counts"]), n_dots))
    x0, x1 = ax.get_xlim()
    ax.set_xlim(x1 - GUTTER * (x1 - x0), x1)

    g = Gutter(fig, ax)
    g.text(f"{len(families)} names, {len(families)} clusters", size=13.0,
           colour=INK, weight="bold", gap=0.3)
    g.text("the most spatially concentrated family names\n"
           "in the 2024 register, each in its own colour,\n"
           "on one map", size=7.4, gap=1.4)
    for colour, st, n_units, n_dots in drawn:
        y = g.y
        ax.scatter([0.020], [y - g.frac(6.0)], transform=ax.transAxes, s=16,
                   c=colour, linewidths=0, zorder=6, clip_on=False)
        ax.text(0.040, y - g.frac(6.0), translit(st["display"]),
                transform=ax.transAxes, fontsize=8.4, color=INK, va="center",
                ha="left", fontweight="bold")
        place_arabic(ax, st["display"], (0.245, y + g.frac(1.5)), 11.0)
        g.space(15.0)
        g.text(f"{st['mapped']:,} voters · {n_units} imadas · "
               f"{st['top_gov']}", size=6.4, gap=1.5)
    g.dots(dv, 0)
    g.text("Colours are four of the eight Okabe-Ito hues, a palette\n"
           "built to stay separable under red-green and blue-yellow\n"
           "colour blindness; tools/check_dot_palette.py asserts that\n"
           "it does, on these four and against this ground.", size=6.4)

    ax.text(0.012, 0.012,
            "Where a name is concentrated is where its holders are registered in 2024:\n"
            "a family that stayed, one that was resettled together and one that migrated\n"
            "together all look alike here. Dots fall at random inside the imada that holds\n"
            "them. Counts: ISIE preliminary voter register, 6 July 2024. Boundaries: OCHA\n"
            "COD-AB admin4.",
            transform=ax.transAxes, fontsize=6.0, color=INK_2, va="bottom",
            ha="left", linespacing=1.5)
    made = save_figure(fig, os.path.join(out_dir, stem))
    plt.close(fig)
    return made, dv


# ---- assembly -------------------------------------------------------------
def build_stats(keys, display, geo):
    counts, variants, diaspora, unplaced = imada_counts(set(keys))
    stats = {}
    for key in sorted(keys):
        c = counts[key]
        mapped = sum(c.values())
        if not mapped:
            continue
        hhi, ent = dispersion(c)
        top_pcode, top_n = c.most_common(1)[0]
        p = geo.props[top_pcode]
        by_gov = collections.Counter()
        for pcode, v in c.items():
            by_gov[geo.props[pcode]["adm2_name"]] += v
        top_gov, top_gov_n = by_gov.most_common(1)[0]
        top_gov_ar = next(geo.props[pc]["adm2_name1"] for pc in c
                          if geo.props[pc]["adm2_name"] == top_gov)
        var = variants[key].most_common()
        stats[key] = {
            "key": key,
            "n_mapped_imadas": 0,
            "display": display[key],
            "counts": c,
            "mapped": mapped,
            "hhi": hhi,
            "entropy": ent,
            "top_imada": f"{p['adm2_name']} — {p['adm4_name']}",
            "top_imada_share": 100.0 * top_n / mapped,
            "top_gov": top_gov,
            "top_gov_ar": top_gov_ar,
            "top_gov_share": 100.0 * top_gov_n / mapped,
            "diaspora": diaspora[key],
            "unplaced": unplaced[key],
            "variants": var,
            # The random stream a surname draws on is its own name, not its
            # rank in whatever set this invocation happened to select: keying
            # it to the rank meant `--set common --top 1` drew a name's dots in
            # different places than `--set all` did, and the claim that a
            # rebuild puts every dot back would have been false.
            "stream": zlib.crc32(key.encode("utf-8")) % (2 ** 31),
        }
    return stats


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--set", choices=["common", "concentrated", "sheets", "all"],
                    default="all")
    ap.add_argument("--top", type=int, default=0,
                    help="how many surnames in the chosen set (default: 24 "
                         "common, 16 concentrated)")
    ap.add_argument("--min-common-voters", type=int, default=20000,
                    help="every non-patronymic family name with at least this "
                         "many holders is drawn alongside the named list")
    ap.add_argument("--min-voters", type=int, default=3000,
                    help="floor for the concentrated set; below it a family's "
                         "HHI is noise")
    args = ap.parse_args()
    if not os.path.exists(ARCHIVE):
        sys.exit(f"missing {ARCHIVE}; run tools/fetch_boundaries.py")
    if not os.path.exists(XW):
        sys.exit(f"missing {XW}; run tools/bridge_surname_imadas.py")

    n_common = args.top if (args.top and args.set == "common") else len(NAMED_COMMON)
    n_conc = args.top if (args.top and args.set == "concentrated") else 16

    print("pooling surnames ...")
    national, spelling = pooled_national()
    common, unknown = [], []
    for name in NAMED_COMMON[:n_common]:
        key = family_key(name)
        if key not in national:
            unknown.append(name)
        elif key not in common:
            common.append(key)
    for name in unknown:
        print(f"  not in the register, skipped: {name}")
    # Everything the register itself puts above the floor, patronymics aside,
    # so the set is not only what someone thought to list.
    frequent = [k for k, v in national.most_common()
                if v >= args.min_common_voters
                and k.split()[0] not in PATRONYMIC_PREFIXES
                and k not in set(common)]
    print(f"  {len(frequent)} more above {args.min_common_voters:,} holders "
          f"(patronymics excluded)")
    common += frequent
    pool = [k for k, v in national.items()
            if v >= args.min_voters and k not in set(common)]
    print(f"  {len(national):,} pooled families; {len(common)} named; "
          f"{len(pool):,} others above {args.min_voters:,} voters")

    print("reading the imada table ...")
    geo = Geography()
    cand_stats = build_stats(set(common) | set(pool), spelling, geo)
    conc = sorted((k for k in pool if k in cand_stats),
                  key=lambda k: -cand_stats[k]["hhi"])[:n_conc]
    chosen = [k for k in common if k in cand_stats] + conc
    # Both denominators a figure prints come from the crosswalk, which is what
    # the map can actually hold: the imadas the bridge resolved, and the
    # registered voters living in them. The share used to divide by the sum of
    # the *candidate* surnames instead, which is not an electorate at all and
    # made every name look about twice as common as it is.
    bridged = read_csv(XW)
    n_mapped = len({r["adm4_pcode"] for r in bridged})
    electorate = sum(int(r["registry_voters"]) for r in bridged)
    for key in chosen:
        cand_stats[key]["share"] = 100.0 * cand_stats[key]["mapped"] / electorate
        cand_stats[key]["n_mapped_imadas"] = n_mapped

    out_dir = figure_dir(FAMILY)
    print("reading the polling-centre table ...")
    per_centre = centre_counts(set(chosen))

    index, made_all = [], []
    want_common = args.set in ("common", "all")
    want_conc = args.set in ("concentrated", "all")
    singles = ([k for k in chosen if k in set(common)] if want_common else []) + \
              (conc if want_conc else [])
    for key in singles:
        st = cand_stats[key]
        made, dv, n_dots, n_units = national_figure(
            geo, key, st, per_centre.get(key, {}), out_dir)
        made_all += made
        index.append({
            "surname": st["display"],
            "latin": translit(st["display"]),
            "set": "common" if key in set(common) else "concentrated",
            "voters_mapped": st["mapped"],
            "mapped_electorate_share_pct": f"{st['share']:.4f}",
            "imadas_present": len(st["counts"]),
            "imadas_with_a_dot": n_units,
            "hhi_concentration": f"{st['hhi']:.6f}",
            "spatial_entropy": f"{st['entropy']:.4f}",
            "top_governorate": st["top_gov"],
            "top_imada": st["top_imada"],
            "top_imada_share_pct": f"{st['top_imada_share']:.2f}",
            "diaspora_voters": st["diaspora"],
            "unplaced_voters": st["unplaced"],
            "dot_value": dv,
            "dots_drawn": n_dots,
            "figure": f"maps/{FAMILY}/{slug(st['display'])}_dots.pdf",
        })
        print(f"  {translit(st['display']):<16} {st['mapped']:>7,} voters  "
              f"1 dot = {dv:>3}  {n_dots:>5,} dots  "
              f"{len(st['counts']):>4} imadas")

    if args.set in ("sheets", "all"):
        named = [k for k in chosen if k in set(common)]
        # One dot value for the whole named set, not one per sheet, so a panel
        # on sheet 3 can be read against a panel on sheet 1.
        shared = dot_value(max(cand_stats[k]["mapped"] for k in named))
        # Split as evenly as the sheets allow rather than filling each to 12:
        # 31 names filled greedily left a third sheet holding a single panel in
        # its second row, which reads as a mistake.
        n_sheets = max(1, int(math.ceil(len(named) / 12.0)))
        per = int(math.ceil(len(named) / float(n_sheets)))
        sheets = [named[i:i + per] for i in range(0, len(named), per)]
        for i, part in enumerate(sheets, 1):
            made, dv = composite(
                geo, part, cand_stats, out_dir, f"composite_common_{i}",
                f"Common Tunisian family names ({i} of {len(sheets)})",
                "registered voters bearing each name, 2024 ISIE register — "
                f"one dot value across all {len(named)} panels of the set",
                dv=shared)
            made_all += made
            print(f"  composite_common_{i}: {len(part)} panels, "
                  f"1 dot = {dv} voters")
        made, dv = composite(
            geo, conc[:12], cand_stats, out_dir, "composite_concentrated",
            "Twelve family names that sit in few places",
            "the most spatially concentrated names in the register "
            f"(≥ {args.min_voters:,} voters), by Herfindahl index over imadas — "
            "concentration is where a name is registered now, not evidence "
            "that its holders never moved")
        made_all += made
        print(f"  composite_concentrated: 1 dot = {dv} voters")
        made, dv = overlay(geo, conc[:len(OVERLAY_COLOURS)], cand_stats,
                           out_dir, "overlay_four_names")
        made_all += made
        print(f"  overlay_four_names: 1 dot = {dv} voters")

    # The index names every figure in the folder, so only a run that drew the
    # whole folder may rewrite it. A partial run used to truncate it to whatever
    # it happened to draw -- three rows after `--set concentrated --top 3`.
    if index and args.set != "all":
        print(f"  (not rewriting {INDEX_OUT}: this run drew "
              f"{len(index)} of the 40 figures)")
    elif index:
        os.makedirs(os.path.dirname(INDEX_OUT), exist_ok=True)
        with open(INDEX_OUT, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(index[0].keys()))
            w.writeheader()
            w.writerows(index)
        made_all.append(INDEX_OUT)

    if geo._fallback:
        print(f"\n  {geo._fallback} imada(s) too thin to scatter into; "
              f"their dots stack on the centroid")
    print(f"\nwrote {len(made_all)} files into maps/{FAMILY}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
