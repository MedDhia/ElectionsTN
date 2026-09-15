"""From the tribe's nineteenth-century ground to where its name is registered.

What is being compared
----------------------
Two things that were never meant to be joined, and the join is a hypothesis
rather than a fact.

On one side, the sheets: the 1853 Pellissier and 1881 Lasailly maps of the
Regency in the MapsTN collection, and Martel's 1965 sketch of 1881, each of
which prints tribe names in letterspaced capitals across the ground the tribe
held. MapsTN read every label, placed it on the ground, and gave each tribe the
largest ellipse that holds all of its own labels and no other tribe's. Those
tables are copied under `data/sources/mapstn/` and that ellipse is what this
tool calls the tribe's **historical ground**. It is not a boundary: no sheet in
that collection draws one.

On the other side, the register: the 2024 ISIE voter register counts every
registered voter's family name by imada. A Tunisian family name is very often
a *nisba*, the adjective of belonging formed from a tribe, a fraction or an
eponym: the Hammama's member is a Hammami, the Zlass's a Jlassi, the Ouled
Ayar's an Ayari. `data/tribal_surname_crosswalk.csv` pairs each tribe the
sheets place with the nisba the register carries, says how the one derives from
the other, and grades the link. Only pairs graded high or medium are drawn;
the generic patronymics (Saidi, Khelifi, Yaacoubi) are listed and left out,
because mapping them would map a given name and not a tribe.

What a figure shows
-------------------
For one tribe: its ground as a filled ellipse, the label centres each sheet
printed (one marker per cartographer), and every registered voter bearing the
nisba as a dot inside the imada that holds them. Arrows run from the centre of
the ground to the largest concentrations of the name more than 25 km from it,
sized by voters. The gutter states how much of the name is registered inside
the ground, within 25 km of it, and beyond; how far its centre of gravity has
moved and in which direction; and where the largest concentrations beyond are.

Three readings the figures do not support, stated on every one of them
----------------------------------------------------------------------
**A nisba is a name, not a membership card.** Every Hammami was not a Hammama
and the register cannot say which were. A holder outside the ground may be a
migrant, a descendant of one, or someone whose name has another origin
entirely: Trabelsi means Tripolitan and Abidi may derive from Abid. The
crosswalk grades each pair and the grade is printed.

**The ground is the largest reading of the sheets, not a territory.** It is
bounded by neighbouring names, so a tribe with no neighbour for a hundred
kilometres gets a huge ellipse and a tribe hemmed in by names gets a small
one. Where two sheets put a name 200 km apart the ellipse joins them, and
those tribes (Riah, Ouled Sdira, Ouled Khiar, Souassi) are drawn dashed.

**A concentration is where a name is registered in 2024, not a route.** The
arrows join a nineteenth-century centre to a twenty-first-century one and
say nothing about when anyone moved, or whether the movement was one family's
or a century's. Tunisia's twentieth century moved people towards Tunis, the
Sahel and Sfax, and every figure here shows that pull; it does not show its
mechanism.

Outputs:
    maps/tribes/<latin>_mobility.{pdf,png}     one per tribe
    maps/tribes/composite_tribes_<n>.{pdf,png} up to twelve to a sheet
    maps/tribes/overview_displacement.{pdf,png,svg}
    maps/tribes/overview_retention.{pdf,png,svg}
    data/tribal_mobility.csv                   one row per tribe
    data/tribal_mobility_destinations.csv      one row per tribe x governorate

Usage:
    python3 tools/make_tribal_mobility.py
    python3 tools/make_tribal_mobility.py --only Hammama Zlass
"""

import argparse
import collections
import csv
import math
import os
import sys
import textwrap
import zlib

import matplotlib
matplotlib.use("Agg")
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch
from shapely import transform as shp_transform
from shapely.geometry import Point, Polygon, shape

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from make_maps import (ARCHIVE, INK, INK_2, RAMP, SURFACE, albers, figure_dir,
                       load_layer, save_figure)
from make_surname_dots import (DOT, GUTTER, XW, Geography, Gutter, base,
                               dot_value, family_key, imada_counts, imada_dots,
                               place_arabic, read_csv, scatter)

FAMILY = "tribes"
SRC = "data/sources/mapstn"
XWALK = "data/tribal_surname_crosswalk.csv"
OUT_STATS = "data/tribal_mobility.csv"
OUT_DEST = "data/tribal_mobility_destinations.csv"

# The inks MapsTN gives each cartographer, kept so a reader of both repositories
# sees the same sheet in the same colour. The ground itself takes the 1853 ink.
SHEET_INK = {"1853 Pellissier": "#a5642a",
             "1881 Lasailly": "#2f5f8f",
             "1881 Martel (1965)": "#4a7c59"}
SHEET_MARK = {"1853 Pellissier": "s", "1881 Lasailly": "^",
              "1881 Martel (1965)": "D"}
GROUND = SHEET_INK["1853 Pellissier"]
ARROW = "#0b0b0b"

NEAR_KM = 25.0          # the ring around the ground that counts as spillover
MIN_VOTERS = 1000       # below this a distribution is a handful of households
PROMINENT_PCT = 5.0     # a name at this share of an imada's electorate stands out
N_DEST = 6              # arrows drawn per figure
DEST_MIN_SHARE = 2.0    # ... and only to governorates holding this much of the name

# MapsTN's own flat km-space, reproduced exactly so its ellipses land where it
# drew them: one scale for longitude at 34.5 N, one for latitude.
KM_PER_DEG_LAT = 110.574
LAT0 = 34.5
KM_PER_DEG_LON = 111.320 * math.cos(math.radians(LAT0))

COMPASS = ["E", "NE", "N", "NW", "W", "SW", "S", "SE"]


def to_km(lon, lat):
    return np.asarray(lon, dtype=float) * KM_PER_DEG_LON, \
        np.asarray(lat, dtype=float) * KM_PER_DEG_LAT


def to_deg(x, y):
    return np.asarray(x) / KM_PER_DEG_LON, np.asarray(y) / KM_PER_DEG_LAT


def bearing(dx, dy):
    """Eight-point compass direction of a displacement in km."""
    ang = math.degrees(math.atan2(dy, dx)) % 360.0
    return COMPASS[int((ang + 22.5) // 45.0) % 8]


# ---- the sheets -----------------------------------------------------------
class Ground:
    """One tribe's ellipse, in MapsTN's km-space and on the Albers map."""

    def __init__(self, row):
        self.tribe = row["tribe"]
        self.lon, self.lat = float(row["lon"]), float(row["lat"])
        cx, cy = to_km(self.lon, self.lat)
        self.centre = np.array([float(cx), float(cy)])
        self.a = float(row["major_km"]) / 2.0
        self.b = float(row["minor_km"]) / 2.0
        th = math.radians(float(row["angle_deg"]))
        self.R = np.array([[math.cos(th), -math.sin(th)],
                           [math.sin(th), math.cos(th)]])
        self.area = float(row["area_sqkm"])
        self.flagged = int(row["encloses_other_tribes"] or 0) > 0
        self.encloses = row["encloses"]
        self.sources = row["sources_named"]
        self.printed = row["printed_as"]
        t = np.linspace(0, 2 * math.pi, 241)
        ring = self.centre + (self.R @ np.vstack([self.a * np.cos(t),
                                                 self.b * np.sin(t)])).T
        self.polygon = Polygon(ring)
        lon, lat = to_deg(ring[:, 0], ring[:, 1])
        x, y = albers(lon, lat)
        self.xy = np.column_stack([x, y])
        self.centre_xy = np.array(albers([self.lon], [self.lat])).ravel()

    def distance_km(self, xk, yk):
        """0 inside the ellipse, else the distance to its edge."""
        return np.array([self.polygon.distance(Point(x, y))
                         for x, y in zip(xk, yk)])

    def share_in(self, country):
        return self.polygon.intersection(country).area / self.polygon.area


def read_grounds():
    return {r["tribe"]: Ground(r) for r in read_csv(os.path.join(SRC, "tribal_spread.csv"))}


def read_labels():
    """Every placed label, by tribe: (sheet, printed, lon, lat)."""
    out = collections.defaultdict(list)
    for r in read_csv(os.path.join(SRC, "tribal_territories.csv")):
        sheet = "1853 Pellissier" if r["year"] == "1853" else "1881 Lasailly"
        out[r["tribe"] or r["label_as_printed"]].append(
            (sheet, r["label_as_printed"], float(r["lon"]), float(r["lat"])))
    for r in read_csv(os.path.join(SRC, "martel_1965_tribes.csv")):
        out[r["tribe"]].append(("1881 Martel (1965)", r["label_as_printed"],
                                float(r["lon"]), float(r["lat"])))
    return out


def tunisia_km():
    """The country in km-space, to say how much of a ground the register can see."""
    feats = load_layer("tun_admin0.geojson")
    geom = shape(feats[0]["geometry"])
    return shp_transform(geom, lambda c: np.column_stack(to_km(c[:, 0], c[:, 1])))


# ---- the register ---------------------------------------------------------
def imada_electorate():
    """Registered voters per admin4 p-code, from the crosswalk."""
    out = collections.Counter()
    for r in read_csv(XW):
        out[r["adm4_pcode"]] += int(r["registry_voters"])
    return out


def wrap(text, width=48):
    return "\n".join(textwrap.wrap(text, width))


def analyse(pair, ground, counts, geo, electorate, country):
    """Everything one figure prints, and one row of the table."""
    pcodes = sorted(counts)
    n = np.array([counts[c] for c in pcodes], dtype=float)
    mapped = int(n.sum())
    lon = np.array([float(geo.props[c]["center_lon"]) for c in pcodes])
    lat = np.array([float(geo.props[c]["center_lat"]) for c in pcodes])
    xk, yk = to_km(lon, lat)
    d = ground.distance_km(xk, yk)

    inside = float(n[d == 0].sum())
    near = float(n[(d > 0) & (d <= NEAR_KM)].sum())
    far = float(n[d > NEAR_KM].sum())

    # The electorate of the imadas the ground covers, so the name's weight
    # there can be stated as one voter in so many.
    el_in = sum(electorate[c] for c, dd in zip(pcodes, d) if dd == 0)
    el_in += sum(v for c, v in electorate.items()
                 if c not in counts and ground.polygon.contains(
                     Point(*to_km(float(geo.props[c]["center_lon"]),
                                  float(geo.props[c]["center_lat"])))))
    prominence = inside / el_in if el_in else 0.0

    # Centre of gravity and its displacement from the historical centre.
    cx, cy = (n * xk).sum() / n.sum(), (n * yk).sum() / n.sum()
    dx, dy = cx - ground.centre[0], cy - ground.centre[1]
    disp = math.hypot(dx, dy)
    clon, clat = to_deg(cx, cy)

    order = np.argsort(d)
    cum = np.cumsum(n[order]) / n.sum()
    d_median = float(d[order][np.searchsorted(cum, 0.5)])

    # Imadas where the name stands out, inside and outside the ground.
    prom_in = prom_out = 0
    for c, dd in zip(pcodes, d):
        if electorate[c] and 100.0 * counts[c] / electorate[c] >= PROMINENT_PCT:
            if dd == 0:
                prom_in += 1
            else:
                prom_out += 1

    # Destinations: governorates holding the name beyond the near ring, with
    # the centre of gravity of those holders as the arrow's end.
    by_gov = collections.defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])
    for c, v, dd, x, y in zip(pcodes, n, d, xk, yk):
        g = geo.props[c]["adm2_name"]
        by_gov[g][0] += v
        if dd > NEAR_KM:
            acc = by_gov[g]
            acc[1] += v
            acc[2] += v * x
            acc[3] += v * y
    dests = []
    for g, (tot, farv, sx, sy) in by_gov.items():
        share_far = 100.0 * farv / mapped
        dests.append({
            "governorate": g, "voters": int(tot), "share_pct": 100.0 * tot / mapped,
            "voters_beyond_ring": int(farv), "share_beyond_ring_pct": share_far,
            "lon": float(to_deg(sx / farv, 0)[0]) if farv else "",
            "lat": float(to_deg(0, sy / farv)[1]) if farv else "",
        })
    dests.sort(key=lambda r: -r["voters_beyond_ring"])
    arrows = [r for r in dests
              if r["share_beyond_ring_pct"] >= DEST_MIN_SHARE][:N_DEST]

    return {
        "tribe": ground.tribe,
        "surname": pair["surname_ar"],
        "surname_alt": pair["surname_alt_ar"],
        "latin": pair["latin"],
        "confidence": pair["confidence"],
        "derivation": pair["derivation"],
        "note": pair["note"],
        "sheets": ground.sources,
        "printed_as": ground.printed,
        "ground_area_sqkm": int(ground.area),
        "ground_share_in_tunisia_pct": round(100.0 * ground.share_in(country), 1),
        "ground_flagged": int(ground.flagged),
        "ground_lon": ground.lon, "ground_lat": ground.lat,
        "voters_mapped": mapped,
        "inside_pct": 100.0 * inside / mapped,
        "near_pct": 100.0 * near / mapped,
        "beyond_pct": 100.0 * far / mapped,
        "electorate_inside": int(el_in),
        "one_in": (el_in / inside) if inside else float("inf"),
        "prominent_imadas_inside": prom_in,
        "prominent_imadas_outside": prom_out,
        "centroid_lon": round(float(clon), 4), "centroid_lat": round(float(clat), 4),
        "displacement_km": disp, "direction": bearing(dx, dy),
        "median_km_from_ground": d_median,
        "imadas_present": len(pcodes),
        "dests": dests, "arrows": arrows,
        "counts": counts,
    }


# ---- drawing --------------------------------------------------------------
def draw_ground(ax, ground, lw=1.0, alpha=0.20, zorder=3):
    ax.fill(ground.xy[:, 0], ground.xy[:, 1], facecolor=GROUND, alpha=alpha,
            edgecolor="none", zorder=zorder)
    ax.plot(np.append(ground.xy[:, 0], ground.xy[0, 0]),
            np.append(ground.xy[:, 1], ground.xy[0, 1]), color=GROUND, lw=lw,
            ls=(0, (3, 2)) if ground.flagged else "-", zorder=zorder + 0.5)


def draw_labels(ax, labels, size=26, zorder=6):
    for sheet, _, lon, lat in labels:
        x, y = albers([lon], [lat])
        ax.scatter(x, y, marker=SHEET_MARK[sheet], s=size, c=SHEET_INK[sheet],
                   edgecolors="white", linewidths=0.5, zorder=zorder)


def place_labels(ax, ends, texts, gap_px=9.0, px_per_char=4.6):
    """Label positions that do not print through each other.

    Greedy, top to bottom: a label whose box would overlap one already placed
    is pushed down by one line. Done in display pixels, so it has to run after
    the axes have their final extent, which is why `tribe_figure` sets the
    gutter before it draws the arrows.
    """
    ax.apply_aspect()
    tr = ax.transData
    disp = tr.transform(np.asarray(ends, dtype=float))
    pos = disp.copy()
    placed = []
    for i in np.argsort(-disp[:, 1]):
        x, y = disp[i]
        w = px_per_char * len(texts[i])
        moved = True
        while moved:
            moved = False
            for px, py, pw in placed:
                if abs(py - y) < gap_px and x < px + pw and px < x + w:
                    y = py - gap_px
                    moved = True
        placed.append((x, y, w))
        pos[i] = (x, y)
    return tr.inverted().transform(pos), np.abs(pos[:, 1] - disp[:, 1]) > gap_px / 2


def draw_arrows(ax, ground, arrows, mapped, label=True):
    """Arrows from the ground's centre to each destination, sized by voters."""
    x0, y0 = ground.centre_xy
    ends, texts = [], []
    for i, r in enumerate(arrows):
        x1, y1 = albers([r["lon"]], [r["lat"]])
        x1, y1 = float(x1[0]), float(y1[0])
        w = 0.5 + 2.6 * r["voters_beyond_ring"] / max(mapped, 1)
        rad = 0.16 if i % 2 == 0 else -0.16
        ax.add_patch(FancyArrowPatch(
            (x0, y0), (x1, y1), connectionstyle=f"arc3,rad={rad}",
            arrowstyle="-|>", mutation_scale=7.0, lw=w, color=ARROW,
            alpha=0.78, shrinkA=2, shrinkB=3, zorder=7))
        ends.append((x1, y1))
        texts.append(f" {r['governorate']} {r['share_beyond_ring_pct']:.0f}%")
    if not (label and ends):
        return
    pos, moved = place_labels(ax, ends, texts)
    for (x1, y1), (x, y), m, t in zip(ends, pos, moved, texts):
        if m:
            ax.plot([x1, x], [y1, y], color=INK_2, lw=0.4, zorder=7.5)
        ax.text(x, y, t, fontsize=5.6, color=INK, va="center", ha="left",
                zorder=8,
                path_effects=[pe.withStroke(linewidth=1.6, foreground=SURFACE)])


def sheet_key(ax, g, labels):
    """Which cartographer printed what, one marker per sheet."""
    seen = collections.OrderedDict()
    for sheet, printed, _, _ in labels:
        seen.setdefault(sheet, []).append(printed)
    for sheet, printed in seen.items():
        y = g.y - g.frac(4.0)
        ax.scatter([g.x + 0.010], [y], transform=ax.transAxes,
                   marker=SHEET_MARK[sheet], s=22, c=SHEET_INK[sheet],
                   edgecolors="white", linewidths=0.5, zorder=6, clip_on=False)
        names = ", ".join(dict.fromkeys(printed))
        ax.text(g.x + 0.030, y, f"{sheet}: {names}", transform=ax.transAxes,
                fontsize=6.4, color=INK_2, va="center", ha="left")
        g.y -= g.frac(10.0)


def tribe_figure(geo, ground, labels, st, out_dir):
    dv = dot_value(st["voters_mapped"])
    stream = zlib.crc32(family_key(st["surname"]).encode("utf-8")) % (2 ** 31)
    xy, n_dots, n_units = imada_dots(geo, st["counts"], dv, stream)

    fig, ax = plt.subplots(figsize=(7.6, 8.4))
    base(ax, geo)
    draw_ground(ax, ground)
    scatter(ax, xy)
    draw_labels(ax, labels)
    x0, x1 = ax.get_xlim()
    ax.set_xlim(x1 - GUTTER * (x1 - x0), x1)
    draw_arrows(ax, ground, st["arrows"], st["voters_mapped"])

    g = Gutter(fig, ax)
    g.text(st["tribe"], size=13.0, colour=INK, weight="bold", gap=0.2)
    g.text("the tribe, as the nineteenth-century sheets print it", size=7.0,
           gap=0.5)
    sheet_key(ax, g, labels)
    g.space(4.0)
    g.arabic(st["surname"], 20.0)
    g.text(f"{st['latin']}", size=12.0, colour=INK, weight="bold", gap=0.2)
    g.text("the family name, 2024 ISIE voter register", size=7.0, gap=0.4)
    link = f"{st['derivation']}; link graded {st['confidence']}"
    if st["surname_alt"]:
        link += f"; pooled with a second spelling"
    g.text(wrap(link, 52), size=6.4, gap=1.0)

    weight = (f"inside the ground, 1 voter in {st['one_in']:.0f} bears the name"
              if math.isfinite(st["one_in"]) else
              "inside the ground, no registered voter bears the name")
    g.text("\n".join([
        f"{st['voters_mapped']:,} voters on the map",
        f"{st['inside_pct']:.1f}% registered inside the historical ground",
        f"{st['near_pct']:.1f}% within {NEAR_KM:.0f} km of it, "
        f"{st['beyond_pct']:.1f}% beyond",
        weight,
        f"{PROMINENT_PCT:.0f}%+ of the electorate in "
        f"{st['prominent_imadas_inside']} imadas inside, "
        f"{st['prominent_imadas_outside']} outside",
        f"centre of gravity {st['displacement_km']:.0f} km "
        f"{st['direction']} of the ground's centre",
        f"median holder {st['median_km_from_ground']:.0f} km from the ground",
    ]), size=7.2, colour=INK, gap=1.0)

    if st["arrows"]:
        g.text(f"largest concentrations beyond {NEAR_KM:.0f} km (the arrows):",
               size=6.8, colour=INK, weight="bold", gap=0.3)
        g.text("\n".join(
            f"{r['governorate']}: {r['voters_beyond_ring']:,} "
            f"({r['share_beyond_ring_pct']:.1f}% of the name)"
            for r in st["arrows"]), size=6.8, gap=1.0)
    else:
        g.text(f"no governorate holds {DEST_MIN_SHARE:.0f}% of the name beyond "
               f"{NEAR_KM:.0f} km", size=6.8, gap=1.0)

    g.dots(dv, n_dots)
    notes = []
    if ground.flagged:
        others = ground.encloses.split(" | ")
        listed = ", ".join(others[:3]) + (f" and {len(others) - 3} more"
                                          if len(others) > 3 else "")
        notes.append(f"The sheets disagree on where this tribe was; the "
                     f"ground drawn (dashed) joins their placements and covers "
                     f"{listed}.")
    if st["ground_share_in_tunisia_pct"] < 90:
        notes.append(f"{100 - st['ground_share_in_tunisia_pct']:.0f}% of the "
                     f"ground lies outside Tunisia, where the register cannot "
                     f"see.")
    if st["note"]:
        notes.append(st["note"])
    for note in notes:
        # The footer owns the bottom of the gutter; a note that would run
        # into it is dropped here and survives in the table.
        lines = wrap(note, 54)
        if g.y - g.frac(6.2 * 1.42 * (lines.count("\n") + 1)) < 0.17:
            break
        g.text(lines, size=6.2, gap=0.8)

    ax.text(0.012, 0.012,
            "A nisba is a name, not a membership: not every holder descends from the tribe, and the\n"
            "register cannot say which do. The ground is the largest ellipse the sheets support, bounded\n"
            "by neighbouring names, not a boundary anyone drew (MapsTN, tribal_spread.csv). Dots fall\n"
            "at random inside the imada that holds them. Counts: ISIE register, 6 July 2024; boundaries:\n"
            "OCHA COD-AB admin4.",
            transform=ax.transAxes, fontsize=5.8, color=INK_2, va="bottom",
            ha="left", linespacing=1.5)

    stem = os.path.join(out_dir, f"{st['latin'].lower()}_mobility")
    made = save_figure(fig, stem, formats=("pdf", "png"))
    plt.close(fig)
    return made, dv, n_dots


def composite(geo, grounds, labels, results, out_dir, stem, title, cols=6):
    rows = int(math.ceil(len(results) / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(1.85 * cols, 4.7 * rows))
    axes = np.atleast_1d(axes).ravel()
    for ax in axes[len(results):]:
        ax.set_axis_off()
    for ax, st in zip(axes, results):
        ground = grounds[st["tribe"]]
        dv = dot_value(st["voters_mapped"])
        stream = zlib.crc32(family_key(st["surname"]).encode("utf-8")) % (2 ** 31)
        xy, n_dots, _ = imada_dots(geo, st["counts"], dv, stream)
        base(ax, geo, mesh_lw=0.05, gov_lw=0.30)
        draw_ground(ax, ground, lw=0.7)
        scatter(ax, xy, size=0.9, alpha=0.62)
        draw_labels(ax, labels[st["tribe"]], size=9, zorder=6)
        draw_arrows(ax, ground, st["arrows"][:3], st["voters_mapped"], label=False)
        ax.text(0.0, 1.10, st["tribe"], transform=ax.transAxes, fontsize=8.0,
                color=INK, va="bottom", ha="left", fontweight="bold")
        place_arabic(ax, st["surname"], (1.0, 1.094), 9.0, ha="right")
        ax.text(0.0, 1.052, st["latin"], transform=ax.transAxes, fontsize=7.4,
                color=INK_2, va="bottom", ha="left")
        ax.text(0.0, 1.008,
                f"{st['voters_mapped']:,} voters · 1 dot = {dv} · "
                f"{st['inside_pct']:.0f}% inside",
                transform=ax.transAxes, fontsize=5.6, color=INK_2,
                va="bottom", ha="left")
    fig.suptitle(title, x=0.008, y=0.995, ha="left", va="top", fontsize=15,
                 color=INK, fontweight="bold")
    fig.text(0.008, 0.968,
             "the tribe's ground as the 1853, 1881 and Martel sheets place it (ellipse and "
             "label markers), every 2024 registered voter bearing its nisba (dots),\n"
             "and the three largest concentrations beyond 25 km (arrows). Each panel "
             "carries its own dot value, so panels show geography and do not compare "
             "counts.",
             ha="left", va="top", fontsize=8.0, color=INK_2, linespacing=1.5)
    fig.text(0.008, 0.010,
             "A nisba is a name, not a membership. The ground is the largest ellipse "
             "the sheets support, bounded by neighbouring names (MapsTN); dashed where "
             "the sheets disagree.\nDots fall at random inside their imada. Counts: "
             "ISIE register, 6 July 2024. Boundaries: OCHA COD-AB admin4.",
             ha="left", va="bottom", fontsize=6.4, color=INK_2, linespacing=1.5)
    fig.tight_layout(rect=(0.0, 0.032, 1.0, 0.935))
    made = save_figure(fig, os.path.join(out_dir, stem), formats=("pdf", "png"))
    plt.close(fig)
    return made


RETAIN_BINS = [(40.0, RAMP[6], "40% or more registered inside the ground"),
               (15.0, RAMP[4], "15 to 40%"),
               (0.0, RAMP[2], "under 15%")]


def retain_colour(pct):
    for lo, colour, _ in RETAIN_BINS:
        if pct >= lo:
            return colour
    return RETAIN_BINS[-1][1]


def overview_displacement(geo, grounds, results, out_dir):
    """Every tribe at once: from the ground's centre to the name's centre of gravity."""
    fig, ax = plt.subplots(figsize=(7.6, 8.4))
    base(ax, geo)
    for st in results:
        ground = grounds[st["tribe"]]
        draw_ground(ax, ground, lw=0.45, alpha=0.06, zorder=2.5)
    vmax = max(st["voters_mapped"] for st in results)
    ends, texts = [], []
    for st in sorted(results, key=lambda s: -s["voters_mapped"]):
        ground = grounds[st["tribe"]]
        x0, y0 = ground.centre_xy
        x1, y1 = albers([st["centroid_lon"]], [st["centroid_lat"]])
        x1, y1 = float(x1[0]), float(y1[0])
        lw = 0.7 + 2.3 * math.sqrt(st["voters_mapped"] / vmax)
        ax.add_patch(FancyArrowPatch(
            (x0, y0), (x1, y1), arrowstyle="-|>", mutation_scale=7.0, lw=lw,
            color=retain_colour(st["inside_pct"]), alpha=0.9, shrinkA=0,
            shrinkB=0, zorder=6))
        ax.scatter([x0], [y0], marker="o", s=14, c=SURFACE, edgecolors=GROUND,
                   linewidths=0.9, zorder=7)
        ends.append((x0, y0))
        texts.append(f" {st['tribe']}")
    x0, x1 = ax.get_xlim()
    ax.set_xlim(x1 - GUTTER * (x1 - x0), x1)
    pos, moved = place_labels(ax, ends, texts, gap_px=7.0, px_per_char=3.6)
    for (ex, ey), (x, y), m, t in zip(ends, pos, moved, texts):
        if m:
            ax.plot([ex, x], [ey, y], color=INK_2, lw=0.35, zorder=7.5)
        ax.text(x, y, t, fontsize=4.9, color=INK, va="center", ha="left",
                zorder=8,
                path_effects=[pe.withStroke(linewidth=1.4, foreground=SURFACE)])

    g = Gutter(fig, ax)
    g.text("From the tribe's ground to\nthe name's centre of gravity", size=12.5,
           colour=INK, weight="bold", gap=0.4)
    g.text(f"{len(results)} tribes the nineteenth-century sheets place, each\n"
           f"paired with the family name derived from it in the\n"
           f"2024 voter register", size=7.4, gap=1.2)
    g.text("Each arrow starts at the centre of the tribe's ground\n"
           "(the pale ellipses, as MapsTN reads the 1853, 1881\n"
           "and Martel sheets) and ends at the voter-weighted\n"
           "centre of gravity of the name in 2024. Width follows\n"
           "the number of voters bearing the name.", size=6.8, gap=1.2)
    g.text("colour: share of the name registered inside its ground",
           size=6.8, colour=INK, weight="bold", gap=0.4)
    for lo, colour, label in RETAIN_BINS:
        y = g.y - g.frac(4.0)
        ax.plot([g.x, g.x + 0.030], [y, y], transform=ax.transAxes, color=colour,
                lw=2.2, solid_capstyle="butt", clip_on=False, zorder=6)
        ax.text(g.x + 0.040, y, label, transform=ax.transAxes, fontsize=6.6,
                color=INK_2, va="center", ha="left")
        g.y -= g.frac(10.0)
    g.space(6.0)
    top = sorted(results, key=lambda s: -s["displacement_km"])[:6]
    g.text("furthest moved centres", size=6.8, colour=INK, weight="bold", gap=0.4)
    g.text("\n".join(f"{s['tribe']} → {s['latin']}: {s['displacement_km']:.0f} km "
                     f"{s['direction']}, {s['inside_pct']:.0f}% inside"
                     for s in top), size=6.4, gap=1.0)
    stay = sorted(results, key=lambda s: -s["inside_pct"])[:6]
    g.text("most still inside the ground", size=6.8, colour=INK, weight="bold",
           gap=0.4)
    g.text("\n".join(f"{s['tribe']} → {s['latin']}: {s['inside_pct']:.0f}% inside, "
                     f"{s['displacement_km']:.0f} km {s['direction']}"
                     for s in stay), size=6.4, gap=1.0)
    ax.text(0.012, 0.012,
            "A centre of gravity is a mean, so a name split between its ground and Tunis has its centre on\n"
            "the road between them where nobody lives. The arrow is a summary of a distribution, not a\n"
            "route, and a nisba is a name, not a membership. Grounds: MapsTN tribal_spread.csv; counts:\n"
            "ISIE register, 6 July 2024; boundaries: OCHA COD-AB.",
            transform=ax.transAxes, fontsize=5.8, color=INK_2, va="bottom",
            ha="left", linespacing=1.5)
    made = save_figure(fig, os.path.join(out_dir, "overview_displacement"))
    plt.close(fig)
    return made


def overview_retention(results, out_dir):
    """One bar per tribe: inside the ground, within 25 km, beyond."""
    rows = sorted(results, key=lambda s: (s["inside_pct"], s["near_pct"]))
    n = len(rows)
    fig, ax = plt.subplots(figsize=(7.6, 0.19 * n + 1.9))
    y = np.arange(n)
    inside = np.array([s["inside_pct"] for s in rows])
    near = np.array([s["near_pct"] for s in rows])
    beyond = np.array([s["beyond_pct"] for s in rows])
    kw = dict(height=0.72, edgecolor=SURFACE, linewidth=0.8)
    ax.barh(y, inside, color=RAMP[6], label="inside the ground", **kw)
    ax.barh(y, near, left=inside, color=RAMP[3],
            label=f"within {NEAR_KM:.0f} km of it", **kw)
    ax.barh(y, beyond, left=inside + near, color=RAMP[1], label="beyond", **kw)
    ax.set_yticks(y)
    ax.set_yticklabels([f"{s['tribe']}  ·  {s['latin']}" for s in rows],
                       fontsize=6.6, color=INK)
    for yi, s in zip(y, rows):
        ax.text(101.0, yi, f"{s['inside_pct']:.0f}%   {s['voters_mapped']:,}",
                fontsize=6.0, color=INK_2, va="center", ha="left")
    ax.set_xlim(0, 100)
    ax.set_ylim(-0.7, n - 0.3)
    ax.set_xlabel("share of the name's registered voters, 2024 (%)", fontsize=7.2,
                  color=INK_2)
    ax.tick_params(axis="x", labelsize=6.6, colors=INK_2, length=2.0, width=0.5)
    ax.tick_params(axis="y", length=0)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(INK_2)
    ax.spines["bottom"].set_linewidth(0.5)
    ax.grid(axis="x", color="#e4e3df", lw=0.5, zorder=0)
    ax.set_axisbelow(True)
    ax.text(101.0, n - 0.1, "inside   voters", fontsize=6.0, color=INK_2,
            va="bottom", ha="left")
    ax.legend(loc="lower right", bbox_to_anchor=(1.0, 1.005), ncol=3,
              fontsize=6.6, frameon=False, handlelength=1.4, handleheight=0.8,
              columnspacing=1.2)
    fig.suptitle("How much of each tribe's name is still registered on its "
                 "nineteenth-century ground", x=0.01, y=0.995, ha="left",
                 va="top", fontsize=11.5, color=INK, fontweight="bold")
    fig.text(0.01, 0.962,
             f"{n} tribes placed by the 1853, 1881 and Martel sheets, each paired "
             "with its nisba in the 2024 register, sorted by the share inside. The ground is "
             "the largest ellipse the sheets support,\nso a tribe hemmed in by "
             "neighbouring names has a small ground and reads as dispersed; a tribe "
             "alone in its quarter has a large one and reads as settled.",
             ha="left", va="top", fontsize=6.8, color=INK_2, linespacing=1.5)
    fig.text(0.01, 0.006,
             "A nisba is a name, not a membership. Grounds: MapsTN "
             "tribal_spread.csv. Counts: ISIE register, 6 July 2024, domestic "
             "voters with a resolved imada.",
             ha="left", va="bottom", fontsize=6.0, color=INK_2)
    fig.tight_layout(rect=(0.0, 0.02, 1.0, 0.925))
    made = save_figure(fig, os.path.join(out_dir, "overview_retention"))
    plt.close(fig)
    return made


# ---- assembly -------------------------------------------------------------
STAT_COLUMNS = [
    "tribe", "surname", "surname_alt", "latin", "confidence", "derivation",
    "sheets", "printed_as", "ground_lon", "ground_lat", "ground_area_sqkm",
    "ground_share_in_tunisia_pct", "ground_flagged", "voters_mapped",
    "imadas_present", "inside_pct", "near_pct", "beyond_pct",
    "electorate_inside", "one_in", "prominent_imadas_inside",
    "prominent_imadas_outside", "centroid_lon", "centroid_lat",
    "displacement_km", "direction", "median_km_from_ground",
    "top_destination", "top_destination_pct", "dot_value", "dots_drawn",
    "figure", "note",
]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", nargs="*", default=None,
                    help="draw these tribes only (the tables are still rewritten "
                         "in full only when everything is drawn)")
    ap.add_argument("--min-voters", type=int, default=MIN_VOTERS)
    args = ap.parse_args()
    if not os.path.exists(ARCHIVE):
        sys.exit(f"missing {ARCHIVE}; run tools/fetch_boundaries.py")

    grounds = read_grounds()
    labels = read_labels()
    pairs = [r for r in read_csv(XWALK) if r["drawn"] == "1"]
    missing = [r["tribe"] for r in pairs if r["tribe"] not in grounds]
    if missing:
        sys.exit(f"crosswalk names tribes with no ground: {missing}")
    if args.only:
        pairs = [r for r in pairs if r["tribe"] in set(args.only)]

    print("reading the register ...")
    keys = {}
    for r in pairs:
        names = [r["surname_ar"]] + [s for s in r["surname_alt_ar"].split("|") if s]
        keys[r["tribe"]] = [family_key(s) for s in names]
    counts_by_key, _, diaspora, unplaced = imada_counts(
        {k for ks in keys.values() for k in ks})

    geo = Geography()
    electorate = imada_electorate()
    country = tunisia_km()
    out_dir = figure_dir(FAMILY)

    results = []
    for r in pairs:
        counts = collections.Counter()
        for k in keys[r["tribe"]]:
            counts.update(counts_by_key.get(k, {}))
        if sum(counts.values()) < args.min_voters:
            print(f"  {r['tribe']}: {sum(counts.values())} voters, below the floor")
            continue
        st = analyse(r, grounds[r["tribe"]], counts, geo, electorate, country)
        st["diaspora"] = sum(diaspora[k] for k in keys[r["tribe"]])
        st["unplaced"] = sum(unplaced[k] for k in keys[r["tribe"]])
        results.append(st)

    made = []
    for st in results:
        m, dv, n_dots = tribe_figure(geo, grounds[st["tribe"]], labels[st["tribe"]],
                                     st, out_dir)
        made += m
        st["dot_value"], st["dots_drawn"] = dv, n_dots
        st["figure"] = f"maps/{FAMILY}/{st['latin'].lower()}_mobility.pdf"
        print(f"  {st['tribe']:<18} {st['latin']:<11} {st['voters_mapped']:>7,} "
              f"voters  {st['inside_pct']:5.1f}% inside  {st['near_pct']:5.1f}% near  "
              f"moved {st['displacement_km']:4.0f} km {st['direction']:<2}")

    if not args.only:
        by_size = sorted(results, key=lambda s: -s["voters_mapped"])
        n_sheets = max(1, int(math.ceil(len(by_size) / 12.0)))
        per = int(math.ceil(len(by_size) / float(n_sheets)))
        for i in range(n_sheets):
            part = by_size[i * per:(i + 1) * per]
            made += composite(geo, grounds, labels, part, out_dir,
                              f"composite_tribes_{i + 1}",
                              f"Tribes and their family names ({i + 1} of {n_sheets})")
        made += overview_displacement(geo, grounds, results, out_dir)
        made += overview_retention(results, out_dir)

        with open(OUT_STATS, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=STAT_COLUMNS, extrasaction="ignore")
            w.writeheader()
            for st in sorted(results, key=lambda s: -s["voters_mapped"]):
                row = dict(st)
                for k in ("inside_pct", "near_pct", "beyond_pct", "displacement_km",
                          "median_km_from_ground"):
                    row[k] = f"{st[k]:.1f}"
                row["one_in"] = f"{st['one_in']:.0f}" if math.isfinite(st["one_in"]) else ""
                row["top_destination"] = st["arrows"][0]["governorate"] if st["arrows"] else ""
                row["top_destination_pct"] = (f"{st['arrows'][0]['share_beyond_ring_pct']:.1f}"
                                              if st["arrows"] else "")
                w.writerow(row)
        with open(OUT_DEST, "w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["tribe", "latin", "governorate", "voters", "share_pct",
                        "voters_beyond_ring", "share_beyond_ring_pct", "arrow_drawn"])
            for st in sorted(results, key=lambda s: -s["voters_mapped"]):
                drawn = {a["governorate"] for a in st["arrows"]}
                for d in sorted(st["dests"], key=lambda d: -d["voters"]):
                    w.writerow([st["tribe"], st["latin"], d["governorate"], d["voters"],
                                f"{d['share_pct']:.1f}", d["voters_beyond_ring"],
                                f"{d['share_beyond_ring_pct']:.1f}",
                                int(d["governorate"] in drawn)])
        made += [OUT_STATS, OUT_DEST]
    else:
        print(f"  (not rewriting {OUT_STATS}: partial run)")

    if geo._fallback:
        print(f"\n  {geo._fallback} imada(s) too thin to scatter into; "
              f"their dots stack on the centroid")
    print(f"\nwrote {len(made)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
