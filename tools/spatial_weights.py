"""Queen contiguity weights from the boundary rings, without a GIS stack.

Why this exists separately
--------------------------
Both cluster analyses need the same thing -- who borders whom -- and neither
should carry its own copy. `make_clusters.py` uses these weights for the
spatial lag in Moran's I and Getis-Ord Gi*; the regionalisation uses the same
adjacency as the connectivity constraint that keeps a region contiguous. One
definition, so the two families cannot disagree about the map's topology.

How contiguity is derived
-------------------------
There is no shapely or libpysal here, and none is needed: the COD-AB rings are
topologically clean, so **two units are neighbours when they share a ring
vertex**. That is queen contiguity by construction (queen = touching at a
vertex or along an edge; rook would require two consecutive shared vertices).

The check that this is sound is the resulting degree distribution, because a
planar partition has a mean degree approaching 6 and nothing else does. Both
levels land there:

- delegation (264 units): min 0, median 5, mean 5.26, max 11
- imada (2,084 units): min 0, median 6, mean 5.85, max 17

The minimum is 0 because of the islands below, not because matching failed.

A vertex-matching failure would show up as a collapse toward zero, not as a
plausible-looking distribution, so this is a real check rather than a formality.
Coordinates are compared at 7 decimal places (about 1 cm at this latitude): the
rings share exact doubles, and rounding only guards against a last-bit
difference surviving the JSON round trip.

Islands, and why they are bridged rather than dropped
-----------------------------------------------------
A share map has no opinion about islands, but a *spatial* statistic does: a unit
with no neighbours has an undefined spatial lag, row-standardising a zero row
divides by zero, and Ward under a connectivity constraint cannot merge across a
gap, so c components silently force at least c regions.

And the problem is not isolated units -- it is disconnected **components**. The
Djerba delegations border each other perfectly well; what they do not border is
Tunisia. Measured, not assumed:

- delegation (264): 3 components -- mainland 260, Djerba 3 (Houmt Souk, Midoun,
  Ajim), Kerkennah 1.
- imada (2,084): 5 components -- mainland 2,049, Djerba 24, Kerkennah 9, and two
  single-unit islands, L'Ile de la Galite (Bizerte) and Melita (Sfax).

So each non-mainland component is joined to the growing mainland by the **single
shortest centroid link** available, which is the minimum intervention that makes
the graph connected: one imposed edge per island group, not k per island unit.
Those links land on the real crossings -- Ajim to El Jourf at 10.1 km is the
Djerba ferry, Kerkennah to Sfax at 26.7 km the boat -- which is corroboration
that the rule is picking geography rather than an artefact.

Every bridge is returned by name and distance, because it is an analyst's
decision imposed on the data rather than something the geometry said. The units
at a bridge's endpoints are flagged so no figure presents their spatial
statistic as if it rested on observed adjacency: Kerkennah's "neighbourhood" is
one delegation across 27 km of sea. Dropping them instead would silently delete
a delegation from a national map, which is worse.

Restricting to units that have a result opens the same wound again: the imada
layer has 2,084 units and 2,042 results, so removing the 42 gaps can strand a
unit whose every neighbour was a gap. `subset` reports those separately.
"""

import collections
import math

import numpy as np
from scipy import sparse
from scipy.spatial import cKDTree

VERTEX_PRECISION = 7


def queen_adjacency(features, precision=VERTEX_PRECISION):
    """Neighbour sets by shared ring vertex, indexed by position in `features`.

    Returns a list of sets. A MultiPolygon's parts are all attributed to the one
    unit, so a two-part delegation is one node rather than two.
    """
    owners = collections.defaultdict(set)
    for i, f in enumerate(features):
        geom = f["geometry"]
        polys = (geom["coordinates"] if geom["type"] == "MultiPolygon"
                 else [geom["coordinates"]])
        for poly in polys:
            for ring in poly:
                for x, y in ring:
                    owners[(round(x, precision), round(y, precision))].add(i)
    adj = [set() for _ in features]
    for shared in owners.values():
        if len(shared) > 1:
            for a in shared:
                adj[a] |= shared - {a}
    return adj


def components(adj):
    """Connected components as a list of index lists, largest first.

    The regionalisation needs this: Ward under a connectivity constraint cannot
    merge across components, so c components force at least c regions and a
    requested k below that silently returns something else.
    """
    seen = set()
    out = []
    for start in range(len(adj)):
        if start in seen:
            continue
        stack, comp = [start], []
        seen.add(start)
        while stack:
            u = stack.pop()
            comp.append(u)
            for v in adj[u]:
                if v not in seen:
                    seen.add(v)
                    stack.append(v)
        out.append(sorted(comp))
    return sorted(out, key=len, reverse=True)


def bridge_components(adj, xy, names):
    """Join every non-mainland component to the mainland by its shortest link.

    Mutates `adj` and returns one (i, j, name_i, name_j, km) per bridge, with
    positional indices rather than names: imada names repeat across
    governorates, so matching a bridge back by name could flag the wrong unit.
    Components are
    absorbed largest-first, so a small island nearer another island than the
    mainland still ends up in one connected graph.

    One edge per component is deliberate. A kNN fallback applied per isolated
    unit would give Kerkennah two or three mainland "neighbours" and hide that
    its entire spatial context is imposed; one named edge cannot be mistaken for
    observed adjacency.
    """
    comps = components(adj)
    if len(comps) == 1:
        return []
    connected = set(comps[0])
    log = []
    for comp in comps[1:]:
        pool = np.fromiter(connected, dtype=int)
        tree = cKDTree(xy[pool])
        dist, idx = tree.query(xy[comp], k=1)
        h = int(np.argmin(dist))
        i, j = int(comp[h]), int(pool[int(np.atleast_1d(idx)[h])])
        adj[i].add(j)
        adj[j].add(i)
        log.append((i, j, names[i], names[j],
                    round(float(np.atleast_1d(dist)[h]), 1)))
        connected |= set(comp)
    return log


def bridged_units(bridge_log):
    """Positions whose adjacency includes an imposed edge, for flagging."""
    return sorted({i for b in bridge_log for i in b[:2]})


def subset(adj, keep):
    """Adjacency restricted to `keep` (a list of indices), reindexed to 0..m-1.

    Returns (new_adj, stranded) where `stranded` lists positions in the new
    indexing whose every neighbour was dropped. Those are reported, not
    silently row-standardised into a division by zero.
    """
    pos = {old: new for new, old in enumerate(keep)}
    new_adj = [set() for _ in keep]
    for old in keep:
        for nb in adj[old]:
            if nb in pos:
                new_adj[pos[old]].add(pos[nb])
    stranded = [i for i in range(len(keep)) if not new_adj[i]]
    return new_adj, stranded


def row_standardised(adj):
    """Sparse row-standardised W. Each row sums to 1, so the lag Wz is a mean
    of the neighbours' values and Moran's I reduces to z'Wz / z'z."""
    n = len(adj)
    rows, cols, vals = [], [], []
    for i, nbs in enumerate(adj):
        if not nbs:
            raise ValueError(f"unit {i} has no neighbours; row-standardising "
                             "it would divide by zero -- connect or drop it "
                             "first, and say which in the log")
        w = 1.0 / len(nbs)
        for j in nbs:
            rows.append(i)
            cols.append(j)
            vals.append(w)
    return sparse.csr_matrix((vals, (rows, cols)), shape=(n, n))


def degree_summary(adj):
    """(min, median, mean, max, n_isolated) -- the sanity check on contiguity."""
    d = sorted(len(a) for a in adj)
    n = len(d)
    return (d[0], d[n // 2], sum(d) / n, d[-1], sum(1 for x in d if x == 0))


def centroids_km(lats, lons):
    """Centroids in kilometres, for the island fallback only.

    Equirectangular about the data's own mean latitude. Distances here decide
    which unit an island borrows as a neighbour, over tens of kilometres, so the
    projection's accuracy is irrelevant to the outcome; using `albers` from
    make_maps would drag a rendering dependency into a pure-geometry module.
    """
    lat = np.asarray(lats, dtype=float)
    lon = np.asarray(lons, dtype=float)
    lat0 = math.radians(float(lat.mean()))
    return np.column_stack([111.32 * math.cos(lat0) * lon, 110.57 * lat])
