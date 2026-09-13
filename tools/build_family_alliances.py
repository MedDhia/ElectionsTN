"""Marriage alliances between Tunisian elite families.

Collapses the person-level kinship graph in `data/rodovid/` to the family
level, which is the level at which elite alliance is usually read: who marries
whom, how often, and how widely.

A *couple* is two people joined by a SPOUSE tie, or two people recorded as
parents of the same child — the export sometimes carries the children without
the marriage. A couple whose two surnames differ is one *alliance* between two
families; a couple sharing a surname is counted as endogamy instead and stays
off the graph.

Surnames are rodovid's own reduction of the name, and it is a blunt one:
`Mohamed Salah Ben Mrad` reduces to `Mrad`, which is right, but a person
recorded as `Ahmed Ben Ali` with no family name reduces to `Ali`, which makes a
"family" out of a patronymic. Nodes like `Ali`, `Mahmoud`, `Youssef` and `Amor`
are therefore aggregates of unrelated people, and are named as such wherever
these files are read. The large houses — Bey, Mrad, Cherif, Belkhodja,
Darghouth, Miled, Ayed, Lasram — are not affected.

Writes two files, both keyed on the surname as it appears in the export.
"""
import collections
import csv
import re
import sys

SRC_IND = "data/rodovid/tunisian_individuals.csv"
SRC_TIES = "data/rodovid/tunisian_ties.csv"
OUT_NODES = "data/rodovid/family_nodes.csv"
OUT_EDGES = "data/rodovid/family_alliances.csv"


# Not families: rodovid's unresolved wiki link, its unknown-name marker, and
# rows whose surname holds no letter at all. Left in the person-level files,
# kept off the family graph, where they would read as one large house.
PLACEHOLDER = {"Personne", "?"}
HAS_LETTER = re.compile(r"[^\W\d_]", re.UNICODE)


def is_family(name):
    return bool(name) and name not in PLACEHOLDER and bool(HAS_LETTER.search(name))


def load():
    with open(SRC_IND, encoding="utf-8") as fh:
        people = {r["id"]: r for r in csv.DictReader(fh)}
    with open(SRC_TIES, encoding="utf-8") as fh:
        ties = list(csv.DictReader(fh))
    return people, ties


def couples(ties):
    """Every recorded couple: spouses, plus the parents of a shared child."""
    pairs = set()
    parents = collections.defaultdict(set)
    for t in ties:
        if t["edge"] == "SPOUSE":
            pairs.add((min(t["id_from"], t["id_to"]), max(t["id_from"], t["id_to"])))
        elif t["edge"] == "PARENT":
            parents[t["id_to"]].add(t["id_from"])
    for child in sorted(parents):
        ps = sorted(parents[child])
        for i, a in enumerate(ps):
            for b in ps[i + 1:]:
                pairs.add((a, b))
    return sorted(pairs)


def main():
    people, ties = load()
    surname = {pid: r["surname"] for pid, r in people.items()
               if is_family(r["surname"])}
    dropped = len(people) - len(surname)

    alliances = collections.Counter()
    endogamy = collections.Counter()
    for a, b in couples(ties):
        sa, sb = surname.get(a), surname.get(b)
        if not sa or not sb:
            continue
        if sa == sb:
            endogamy[sa] += 1
        else:
            alliances[(min(sa, sb), max(sa, sb))] += 1

    size = collections.Counter(s for s in surname.values() if s)
    marriages = collections.Counter()
    allies = collections.defaultdict(set)
    for (a, b), w in alliances.items():
        marriages[a] += w
        marriages[b] += w
        allies[a].add(b)
        allies[b].add(a)

    families = sorted(size, key=lambda s: (-marriages[s], -size[s], s))
    with open(OUT_NODES, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["family", "people", "marriages", "allies", "endogamous"])
        for f in families:
            w.writerow([f, size[f], marriages[f], len(allies[f]), endogamy[f]])

    with open(OUT_EDGES, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["family_a", "family_b", "marriages"])
        for (a, b), n in sorted(alliances.items(), key=lambda kv: (-kv[1], kv[0])):
            w.writerow([a, b, n])

    print("families: %d, of which %d marry outside the surname (%d people "
          "carry no usable surname and are off the graph)"
          % (len(families), sum(1 for f in families if marriages[f]), dropped))
    print("alliances: %d family pairs, %d marriages; %d marriages within a surname"
          % (len(alliances), sum(alliances.values()), sum(endogamy.values())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
