"""Standing check on what the elite-network figures may be read to say.

A force-directed picture always looks like it has neighbourhoods, because the
algorithm's job is to put connected things near each other. Whether those
clumps *mean* anything is a separate question, and it is the question a reader
of `docs/figures/elite_network*.png` will silently answer yes to unless told
otherwise. So the claim the figures' caption makes — that the alliance network
is a hub-dominated web rather than a set of intermarrying blocs — is measured
here rather than asserted, and measured against the only fair comparison: the
same families with the same number of marriages each, wired at random.

Two statistics, each against 50 degree-preserving rewirings of the observed
graph (double-edge swaps, which keep every family's number of allies exactly):

**Global clustering.** If families married into circles, family A's two allies
would often be allied to each other. Observed closure is 1.0x the null on the
whole network and 1.2x inside the core — the triangles that exist are the ones
the degree sequence forces.

**Modularity.** If the elite split into blocs, a community partition would find
them and score well above a random graph with the same degrees. Inside the
core it scores +0.039 above null — z=+1.9, inside the noise of the null. On
the whole network the excess is +0.027 at z=+11: statistically obvious,
substantively nothing, and it comes from the hundreds of detached fragments
rather than from any division of the elite.

The community detection is one round of local moving (Louvain's first phase,
no aggregation), which understates modularity — but it understates it equally
for the observed graph and for its nulls, and the comparison is the point.

Truncation cuts both ways and is the honest caveat: the export lost rows, lost
ties remove triangles, so the observed closure is a floor. It would have to be
several times higher to change the reading.

Reads only published files. Exits non-zero on a violation, like the audits
already in the repo.
"""
import collections
import csv
import random
import statistics
import sys

EDGES = "data/rodovid/family_alliances.csv"
NODES = "data/rodovid/family_nodes.csv"

REWIRINGS = 50
SWAP_PASSES = 10
SEED = 0
CORE_K = 5

# What the figures and the README are allowed to be read as saying: ceilings on
# how far the observed graph may beat its own null before "no blocs" stops
# being the right description.
#
# Closure is tested as a ratio, because its null has a tight spread and the
# question is one of size: are there several times more triangles than the
# degree sequence forces, or the same number?
#
# Modularity is tested two ways, because a partition of a graph this size
# scores well above zero on pure noise and the two graphs fail differently.
# On the whole network the excess is statistically obvious and substantively
# nothing (+0.027, z=+11) — it comes from the hundreds of small detached
# fragments, each of which is trivially its own "community". So that one is
# held to an absolute excess. Inside the core, where a bloc would actually
# mean something, the excess is within the noise of the null itself, so that
# one is held to a z-score.
MAX_CLUSTERING_RATIO = 1.5
MAX_MODULARITY_EXCESS = 0.05
MAX_MODULARITY_Z = 3.0


def read_edges(path=EDGES):
    with open(path, encoding="utf-8") as fh:
        return [(r["family_a"], r["family_b"]) for r in csv.DictReader(fh)]


def neighbours(edges):
    nb = collections.defaultdict(set)
    for a, b in edges:
        nb[a].add(b)
        nb[b].add(a)
    return nb


def k_core(edges, k):
    nb = {n: set(v) for n, v in neighbours(edges).items()}
    thin = [n for n in sorted(nb) if len(nb[n]) < k]
    while thin:
        n = thin.pop()
        if n not in nb:
            continue
        for m in nb.pop(n):
            nb[m].discard(n)
            if len(nb[m]) < k:
                thin.append(m)
    return set(nb)


def clustering(nb):
    """Global clustering: closed triples over all triples."""
    closed = triples = 0
    for node in sorted(nb):
        ns = sorted(nb[node])
        for i, a in enumerate(ns):
            for b in ns[i + 1:]:
                triples += 1
                if b in nb[a]:
                    closed += 1
    return closed / triples if triples else 0.0


def modularity(nb, seed=SEED, rounds=12):
    """Louvain's first phase, then the modularity of the partition it finds."""
    nodes = sorted(nb)
    community = {n: i for i, n in enumerate(nodes)}
    degree = {n: len(nb[n]) for n in nodes}
    two_m = sum(degree.values())
    total = collections.defaultdict(float)
    for n in nodes:
        total[community[n]] += degree[n]

    rng = random.Random(seed)
    order = list(nodes)
    for _ in range(rounds):
        moved = 0
        rng.shuffle(order)
        for n in order:
            home = community[n]
            total[home] -= degree[n]
            links = collections.Counter(community[m] for m in nb[n])
            best, gain = home, links[home] - total[home] * degree[n] / two_m
            for c, w in sorted(links.items()):
                g = w - total[c] * degree[n] / two_m
                if g > gain + 1e-12:
                    best, gain = c, g
            community[n] = best
            total[best] += degree[n]
            moved += best != home
        if not moved:
            break

    inside = collections.defaultdict(float)
    strength = collections.defaultdict(float)
    for n in nodes:
        strength[community[n]] += degree[n]
        for m in nb[n]:
            if community[m] == community[n]:
                inside[community[n]] += 1
    return sum(inside[c] / two_m - (strength[c] / two_m) ** 2 for c in strength)


def rewire(edges, rng, passes=SWAP_PASSES):
    """Double-edge swaps: every family keeps its exact number of allies."""
    pairs = [list(e) for e in edges]
    present = {(a, b) for a, b in edges} | {(b, a) for a, b in edges}
    for _ in range(passes * len(pairs)):
        i, j = rng.randrange(len(pairs)), rng.randrange(len(pairs))
        (a, b), (c, d) = pairs[i], pairs[j]
        if len({a, b, c, d}) < 4 or (a, d) in present or (c, b) in present:
            continue
        present -= {(a, b), (b, a), (c, d), (d, c)}
        present |= {(a, d), (d, a), (c, b), (b, c)}
        pairs[i], pairs[j] = [a, d], [c, b]
    return [tuple(p) for p in pairs]


def compare(name, edges, check, modularity_rule):
    nb = neighbours(edges)
    observed = (clustering(nb), modularity(nb))
    rng = random.Random(SEED)
    null = [(clustering(neighbours(r)), modularity(neighbours(r)))
            for r in (rewire(edges, rng) for _ in range(REWIRINGS))]

    print("  %s: %d families, %d alliances" % (name, len(nb), len(edges)))
    summary = []
    for i, label in enumerate(("clustering", "modularity")):
        values = [v[i] for v in null]
        mean = statistics.mean(values)
        sd = statistics.pstdev(values) or 1e-12
        ratio = observed[i] / mean if mean else float("inf")
        z = (observed[i] - mean) / sd
        print("    %-11s observed %.4f   null %.4f (sd %.4f)   %.2fx  z=%+.1f"
              % (label, observed[i], mean, sd, ratio, z))
        summary.append((observed[i], mean, ratio, z))

    _, _, ratio, _ = summary[0]
    check(ratio <= MAX_CLUSTERING_RATIO,
          "%s: closure is %.2fx its degree-preserving null (ceiling %.2f), so "
          "the figure shows a web and not a set of circles"
          % (name, ratio, MAX_CLUSTERING_RATIO))

    obs, mean, _, z = summary[1]
    if modularity_rule == "excess":
        check(obs - mean <= MAX_MODULARITY_EXCESS,
              "%s: modularity is %+.3f above its null (ceiling %+.3f), small "
              "enough that the partition is not finding blocs"
              % (name, obs - mean, MAX_MODULARITY_EXCESS))
    else:
        check(z <= MAX_MODULARITY_Z,
              "%s: modularity is z=%+.1f against its null (ceiling %+.1f), "
              "inside the noise of the null itself"
              % (name, z, MAX_MODULARITY_Z))


def main():
    failures, passed = [], [0]

    def check(ok, message):
        if ok:
            passed[0] += 1
        else:
            failures.append(message)
            print("  FAIL  %s" % message)

    edges = read_edges()
    with open(NODES, encoding="utf-8") as fh:
        nodes = list(csv.DictReader(fh))

    nb = neighbours(edges)
    check(not k_core(edges, CORE_K + 1),
          "the %d-core is empty, so the %d-core the figure draws is the "
          "deepest the network has" % (CORE_K + 1, CORE_K))
    check(len(k_core(edges, CORE_K)) == 236,
          "the %d-core holds the 236 families the caption claims" % CORE_K)

    once = sum(1 for n in nb if len(nb[n]) == 1)
    check(once == 955, "955 families married into the field exactly once")
    print("  %d of %d families have exactly one allied family" % (once, len(nb)))

    widest = max(nodes, key=lambda r: int(r["allies"]))
    check(widest["family"] == "Bey" and int(widest["allies"]) == 160,
          "the beylical house is the widest-married, at 160 allied families")

    compare("whole network", edges, check, modularity_rule="excess")
    core = k_core(edges, CORE_K)
    compare("the 5-core", [e for e in edges if e[0] in core and e[1] in core],
            check, modularity_rule="z")

    print("%d checks run" % (len(failures) + passed[0]))
    if failures:
        print("\n%d check(s) failed" % len(failures))
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
