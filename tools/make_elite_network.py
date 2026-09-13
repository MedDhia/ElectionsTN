"""The marriage network of Tunisian elite families.

Three figures over `data/rodovid/family_alliances.csv`, all from the same
layout code and the same palette as the maps.

  elite_network        every family that marries outside its own surname:
                       1,853 nodes, 3,642 alliances. The field, with the thirty
                       widest-married houses named and, around the edge, the
                       955 families that married into it exactly once.
  elite_network_core   the 5-core: the families left when everyone with fewer
                       than five allies *inside the core* is stripped away,
                       repeatedly, until no one else can be. 236 families, each
                       named where its neighbours leave room. The 6-core is
                       empty, so this is the deepest core the network has — not
                       a threshold chosen for the picture.
  elite_network_null   that same core beside a degree-preserving rewiring of
                       itself. A force layout always looks like it has
                       neighbourhoods; this is what says whether they mean
                       anything. `tools/audit_alliances.py` measures what the
                       panels show: closure 1.2x its null, modularity z=+1.9.

One quantity carries both node channels: marriages into other families, as
area and as position on the documented blue ramp. A node is dark and large for
the same reason, so the key is a single row of growing, darkening circles and
there is nothing to cross-reference. Edge width is the number of marriages
between that pair.

Layout is ForceAtlas2-style: repulsion scaled by degree, LinLog attraction
along edges weighted by the number of marriages, gravity toward the centre,
and a closing pass that repels by drawn radius so nodes stop covering each
other. It starts from a sunflower spiral ordered by degree — no random seed
anywhere — so a rerun reproduces the figure byte for byte, which is how every
other figure in this repo is checked.

Labels are placed by measured extent: candidates are tried in descending order
of marriages and one is dropped when its box would touch a box already placed.
Nothing is nudged by hand.
"""
import collections
import csv
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import PathCollection
from matplotlib.path import Path
from matplotlib.patheffects import withStroke

from audit_alliances import rewire
from make_maps import CMAP, INK, INK_2, SURFACE, save_figure

EDGES_CSV = "data/rodovid/family_alliances.csv"
OUT_DIR = "docs/figures"

EDGE_INK = "#9b9992"          # alliances recede; the nodes carry the reading
CORE_K = 5                    # the deepest non-empty core; asserted in main()
NULL_SEED = 0                 # the seed audit_alliances.py rewires with

SOURCE = ("Source: rodovid.org genealogies, filtered to Tunisian families by "
          "tools/build_rodovid_elites.py, collapsed to families by "
          "tools/build_family_alliances.py. Surnames are rodovid's own "
          "reduction of the name, so patronymic nodes (Ali, Mahmoud, Youssef) "
          "aggregate unrelated people. The export is truncated at 65,535 rows: "
          "every count here is a floor.")


# ---- the data ------------------------------------------------------------

def read_alliances():
    with open(EDGES_CSV, encoding="utf-8") as fh:
        return [(r["family_a"], r["family_b"], int(r["marriages"]))
                for r in csv.DictReader(fh)]


def k_core(edges, k):
    """Families left when everyone with fewer than k allies inside is stripped."""
    adjacent = collections.defaultdict(set)
    for a, b, _ in edges:
        adjacent[a].add(b)
        adjacent[b].add(a)
    thin = [n for n in sorted(adjacent) if len(adjacent[n]) < k]
    while thin:
        n = thin.pop()
        if n not in adjacent:
            continue
        for m in adjacent.pop(n):
            adjacent[m].discard(n)
            if len(adjacent[m]) < k:
                thin.append(m)
    return set(adjacent)


class Graph:
    """The arrays every stage below reads: nodes, ends, weights, degree.

    `marriages` is summed from this graph's own edges rather than read from
    `family_nodes.csv`. On the observed network the two are the same number by
    construction; on a rewired one they are not, and a node has to be drawn at
    the size the graph it is drawn in gives it.
    """

    def __init__(self, edges):
        self.families = sorted({f for e in edges for f in e[:2]})
        index = {f: i for i, f in enumerate(self.families)}
        self.n = len(self.families)
        self.edges = edges
        self.ends = np.array([(index[a], index[b]) for a, b, _ in edges])
        self.weights = np.array([w for _, _, w in edges], dtype=float)
        self.degree = np.zeros(self.n)
        self.marriages = np.zeros(self.n)
        for a, b, w in edges:
            self.degree[index[a]] += 1
            self.degree[index[b]] += 1
            self.marriages[index[a]] += w
            self.marriages[index[b]] += w


# ---- the layout ----------------------------------------------------------

def sunflower(n, order):
    """Deterministic start: a phyllotactic spiral, densest families innermost."""
    pos = np.zeros((n, 2))
    golden = math.pi * (3.0 - math.sqrt(5.0))
    for rank, i in enumerate(order):
        r = math.sqrt(rank + 0.5)
        pos[i] = (r * math.cos(rank * golden), r * math.sin(rank * golden))
    return pos


def layout(graph, radii, iterations=600, gravity=0.15, repulsion=0.05,
           declutter=0.2):
    """ForceAtlas2-style layout. No randomness: same input, same coordinates."""
    n, ends, weights, degree = graph.n, graph.ends, graph.weights, graph.degree
    pos = sunflower(n, sorted(range(n), key=lambda i: (-degree[i], i))) * 3.0
    mass = degree + 1.0
    ia, ib = ends[:, 0], ends[:, 1]
    # The last `declutter` of the run repels by drawn radius rather than by
    # point, which stops large nodes from sitting on top of their neighbours.
    # It also regularises the picture, so the crowded core figure asks for more
    # of it than the open one.
    overlap_from = int(iterations * (1.0 - declutter))

    for step in range(iterations):
        delta = pos[:, None, :] - pos[None, :, :]
        dist = np.sqrt((delta ** 2).sum(-1))
        np.fill_diagonal(dist, np.inf)
        if step >= overlap_from:
            dist = np.maximum(dist - (radii[:, None] + radii[None, :]), 0.01)
        force = repulsion * mass[:, None] * mass[None, :] / dist ** 2
        disp = (force[:, :, None] * delta).sum(1)

        # LinLog attraction: the pull grows with the log of distance, not with
        # distance, so a densely married set contracts while the single links
        # between such sets are free to stretch. Plain linear attraction pulls
        # everything into one even disc and hides exactly that.
        edge = pos[ia] - pos[ib]
        length = np.sqrt((edge ** 2).sum(-1))[:, None]
        pull = weights[:, None] * np.log1p(length) * edge / np.maximum(length, 1e-9)
        np.add.at(disp, ia, -pull)
        np.add.at(disp, ib, pull)

        centre = pos - pos.mean(0)
        norm = np.sqrt((centre ** 2).sum(-1))[:, None]
        disp -= gravity * mass[:, None] * centre / np.maximum(norm, 1e-9)

        # Cool from a long first stride to a short last one, and cap any single
        # node's move so one hub cannot fling itself out of the frame.
        speed = 0.12 * (1.0 - step / iterations) ** 1.5 + 0.006
        move = np.sqrt((disp ** 2).sum(-1))[:, None]
        pos += disp * np.minimum(1.0, 2.0 / np.maximum(move, 1e-9)) * speed

    return pos - pos.mean(0)


# ---- drawing -------------------------------------------------------------

def arcs(pos, ends, bow):
    """One quadratic Bezier per alliance, bowed off the straight line."""
    a, b = pos[ends[:, 0]], pos[ends[:, 1]]
    span = b - a
    perp = np.stack([-span[:, 1], span[:, 0]], axis=1)
    control = (a + b) / 2.0 + bow * perp
    return [Path(np.array([p, c, q]), [Path.MOVETO, Path.CURVE3, Path.CURVE3])
            for p, c, q in zip(a, control, b)]


def sizes(marriages, top, node_scale, node_floor):
    """Node area. Marriages are long-tailed — the beylical house has 218 and
    the median family in the core has nine — so both channels read a
    compressed scale. On a linear one the picture is pale dots around a single
    dark blob, and the difference between five alliances and twenty, which is
    the difference the figure is for, disappears."""
    share = np.clip(np.asarray(marriages, dtype=float) / top, 0.0, 1.0)
    return node_scale * share ** 0.55 + node_scale * node_floor


def shade(marriages, top):
    """Position on the ramp, on the same compressed scale as node area."""
    return np.clip(np.asarray(marriages, dtype=float) / top, 0.0, 1.0) ** 0.55


def place_labels(ax, fig, items, pad=2.0):
    """Draw labels in priority order, dropping any that would touch another."""
    renderer = fig.canvas.get_renderer()
    placed, drawn = [], 0
    for x, y, text, size, weight, colour in items:
        label = ax.text(x, y, text, fontsize=size, color=colour, ha="center",
                        va="center", fontweight=weight, zorder=6,
                        path_effects=[withStroke(linewidth=2.2,
                                                 foreground=SURFACE)])
        box = label.get_window_extent(renderer).padded(pad)
        if any(box.overlaps(other) for other in placed):
            label.remove()
            continue
        placed.append(box)
        drawn += 1
    return drawn


def render(ax, graph, pos, top, node_scale, node_floor, edge_scale, bow):
    """Edges and nodes of one graph into one axes. Labels come after a draw."""
    ax.set_facecolor(SURFACE)
    ax.set_axis_off()
    ax.set_aspect("equal")
    span = np.abs(pos).max() * 1.04
    ax.set_xlim(-span, span)
    ax.set_ylim(-span, span)

    # Heavier alliances read darker as well as thicker: a pair married ten
    # times should not look like a pair married once. Edges bow slightly, which
    # is what keeps a thousand of them from fusing into one grey wash.
    heavy = (graph.weights / graph.weights.max()) ** 0.7
    rgb = matplotlib.colors.to_rgb(EDGE_INK)
    ax.add_collection(PathCollection(
        arcs(pos, graph.ends, bow), facecolors="none", zorder=1,
        capstyle="round", edgecolors=[(*rgb, 0.14 + 0.50 * h) for h in heavy],
        linewidths=edge_scale * (0.35 + 1.9 * heavy)))

    area = sizes(graph.marriages, top, node_scale, node_floor)
    ax.scatter(pos[:, 0], pos[:, 1], s=area, c=CMAP(shade(graph.marriages, top)),
               linewidths=0.45, edgecolors=SURFACE, zorder=3)
    return area


def label_items(graph, pos, area, top, limit, label_size):
    cut = np.quantile(graph.marriages, 0.92)
    items = []
    for i in np.argsort(-graph.marriages)[:limit]:
        big = graph.marriages[i] >= cut
        items.append((pos[i, 0], pos[i, 1] + math.sqrt(area[i]) * 0.012 + 0.35,
                      graph.families[i], label_size + (1.2 if big else 0.0),
                      "bold" if big else "normal", INK if big else INK_2))
    return items


def key(ax, transform, x0, y0, dx, top, node_scale, node_floor, label_size,
        caption):
    """One row of circles: the same quantity as area and as shade."""
    steps, ladder = [], sorted({v for v in (1, 5, 15, 40, 100, int(top))
                                if v <= top})
    for v in ladder:
        # Two circles a reader cannot tell apart teach nothing: drop a rung
        # that sits within 15% of the maximum, which is the only place the
        # fixed ladder can collide with it.
        if v != ladder[-1] and v > 0.85 * ladder[-1]:
            continue
        steps.append(v)
    for j, v in enumerate(steps):
        ax.scatter([x0 + j * dx], [y0], s=sizes(v, top, node_scale, node_floor),
                   c=[CMAP(shade(v, top))], linewidths=0.45, edgecolors=SURFACE,
                   transform=transform, zorder=6, clip_on=False)
        ax.text(x0 + j * dx, y0 - 0.024, str(v), transform=transform,
                fontsize=label_size, color=INK_2, ha="center", va="top")
    ax.text(x0, y0 + 0.028, caption, transform=transform,
            fontsize=label_size + 0.5, color=INK_2, ha="left", va="bottom")


def frame(fig, ax, title, subtitle, note, top, node_scale, node_floor,
          label_size, key_caption):
    """Title, subtitle, the one key and the source note — all outside the
    axes, in figure coordinates, so the drawing keeps the whole frame and no
    family that lands at the top of the picture shares a line with them."""
    fig.text(0.012, 0.990, title, fontsize=16, color=INK, va="top", ha="left",
             fontweight="bold")
    fig.text(0.012, 0.963, subtitle, fontsize=10.5, color=INK_2, va="top",
             ha="left")
    key(ax, fig.transFigure, 0.014, 0.062, 0.040, top, node_scale, node_floor,
        label_size, key_caption)
    fig.text(0.012, 0.028, SOURCE + "  " + note, fontsize=7.0, color=INK_2,
             va="top", ha="left", wrap=True)


def draw(edges, path, title, subtitle, key_caption, size_in, labels,
         iterations, node_scale, edge_scale, label_size, node_floor=0.10,
         declutter=0.2, bow=0.09):
    graph = Graph(edges)
    top = graph.marriages.max()
    radii = np.sqrt(sizes(graph.marriages, top, node_scale, node_floor)) * 0.012
    pos = layout(graph, radii, iterations=iterations, declutter=declutter)

    # Taller than wide by exactly the margins the frame takes, so the axes box
    # comes out square and an equal-aspect drawing fills it edge to edge.
    fig, ax = plt.subplots(figsize=(size_in, size_in * 1.20))
    fig.subplots_adjust(left=0.012, right=0.988, top=0.930, bottom=0.115)
    fig.patch.set_facecolor(SURFACE)
    area = render(ax, graph, pos, top, node_scale, node_floor, edge_scale, bow)
    fig.canvas.draw()
    shown = place_labels(ax, fig, label_items(graph, pos, area, top,
                                              labels or graph.n, label_size))
    frame(fig, ax, title, subtitle,
          "%d families, %d alliances; %d named." % (graph.n, len(edges), shown),
          top, node_scale, node_floor, label_size, key_caption)
    save_figure(fig, path)
    plt.close(fig)
    print("%s: %d families, %d alliances, %d labels"
          % (path, graph.n, len(edges), shown))


def draw_null(edges, path, title, subtitle, iterations, node_scale,
              edge_scale, label_size):
    """The core beside a degree-preserving rewiring of itself.

    Same families, same number of allies each, marriages dealt at random —
    the comparison `tools/audit_alliances.py` scores. Both panels run the same
    layout at the same settings, so any difference in how clumped they look is
    a difference in the graphs and not in the drawing.
    """
    weight = {(min(a, b), max(a, b)): w for a, b, w in edges}
    rng = random.Random(NULL_SEED)
    swapped = rewire([(a, b) for a, b, _ in edges], rng)
    # The rewiring moves which pair a marriage joins, not how many there are:
    # the weights travel with the edges, in the order the swaps left them.
    null_edges = [(a, b, w) for (a, b), w in
                  zip(swapped, (weight[(min(a, b), max(a, b))]
                                for a, b, _ in edges))]

    panels = [("observed", Graph(edges)),
              ("the same families, marriages rewired at random",
               Graph(null_edges))]
    top = max(p[1].marriages.max() for p in panels)

    fig, axes = plt.subplots(1, 2, figsize=(17.0, 9.2))
    fig.patch.set_facecolor(SURFACE)
    for ax, (caption, graph) in zip(axes, panels):
        radii = np.sqrt(sizes(graph.marriages, top, node_scale, 0.10)) * 0.012
        pos = layout(graph, radii, iterations=iterations)
        area = render(ax, graph, pos, top, node_scale, 0.10, edge_scale, 0.09)
        fig.canvas.draw()
        shown = place_labels(ax, fig, label_items(graph, pos, area, top, 14,
                                                  label_size))
        ax.text(0.5, 1.012, caption, transform=ax.transAxes, fontsize=10.5,
                color=INK_2, va="bottom", ha="center")
        print("  %s: %d labels" % (caption, shown))

    fig.suptitle(title, x=0.008, y=0.992, ha="left", va="top", fontsize=16,
                 color=INK, fontweight="bold")
    fig.text(0.008, 0.955, subtitle, ha="left", va="top", fontsize=10.5,
             color=INK_2, linespacing=1.5)
    key(axes[0], fig.transFigure, 0.010, 0.085, 0.026, top, node_scale, 0.10,
        label_size, "marriages inside the core")
    fig.text(0.008, 0.030,
             SOURCE + "  %d families and %d alliances in each panel."
             % (panels[0][1].n, len(edges)),
             ha="left", va="top", fontsize=7.0, color=INK_2, wrap=True)
    fig.subplots_adjust(left=0.004, right=0.996, top=0.865, bottom=0.075,
                        wspace=0.01)
    save_figure(fig, path)
    plt.close(fig)
    print("%s: two panels" % path)


def main():
    edges = read_alliances()
    os.makedirs(OUT_DIR, exist_ok=True)

    assert not k_core(edges, CORE_K + 1), "a deeper core exists; CORE_K is stale"
    core = k_core(edges, CORE_K)
    core_edges = [e for e in edges if e[0] in core and e[1] in core]

    draw(edges, f"{OUT_DIR}/elite_network",
         "Marriage alliances among Tunisian elite families",
         "A node is a family, an edge one or more marriages between two of "
         "them. The thirty widest-married houses are named; the corona is the "
         "955 families that married into the field exactly once.",
         "marriages into other families",
         size_in=14.0, labels=30, iterations=500, node_scale=120.0,
         edge_scale=0.85, label_size=9.0, node_floor=0.045, declutter=0.10,
         bow=0.06)

    draw(core_edges, f"{OUT_DIR}/elite_network_core",
         "The core of the alliance network",
         "The 5-core: strip every family with fewer than five allies inside, "
         "repeat until none is left to strip. The 6-core is empty, so this is "
         "as deep as the network goes.",
         "marriages inside the core",
         size_in=13.0, labels=None, iterations=700, node_scale=300.0,
         edge_scale=1.35, label_size=7.0)

    draw_null(core_edges, f"{OUT_DIR}/elite_network_null",
              "The core, and the same core wired at random",
              "Elite families here marry widely rather than into circles. The "
              "observed core closes only 1.2x as many triangles as a random "
              "graph giving every family the same number of allies, and "
              "scores z=+1.9 on modularity against it — inside the noise of\n"
              "the null itself. Both panels run the same layout at the same "
              "settings, so any difference in how clumped they look is a "
              "difference in the graphs. Measured by tools/audit_alliances.py.",
              iterations=700, node_scale=300.0, edge_scale=1.35, label_size=7.0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
