"""Tunisian-elite subset of the Rodovid genealogy export.

The source workbook (`RodovidData234862.xls`, two sheets: `Individuals` and
`Ties`) is a crawl of rodovid.org seeded on Tunisian elite families. Crawls
follow marriages, so the export overran its subject: alongside the Tunisian
families it carries French aristocratic and industrial lineages, German,
Russian and Scandinavian royalty, and the Ottoman house.

This script separates the two. Nothing is hand-listed: every person is scored
on four signals and the threshold is applied uniformly.

  place   places and titles named in the person's own `INFO` field
          (Tunisian toponyms and beylical offices against foreign ones)
  name    a character n-gram Naive Bayes model over `FULLNAME`, trained on
          the people the `place` signal already labels. Held-out accuracy is
          printed on every run (0.972 at the time of writing)
  family  the place evidence of everyone else sharing the surname
  network the scores of relatives within two steps in the kinship graph,
          which is what recovers people whose own row says nothing

A person is kept when the weighted sum is positive. Every component is
written out per person, so the call can be audited or re-thresholded without
re-running anything.

Two flags mark the cases where the signals disagree, because they are the
ones a reader will want to check:

  married_in     kept, but the person's own name and record are foreign —
                 a foreign spouse inside a Tunisian family
  tunisia_link   excluded, but the record names a Tunisian place — mostly
                 French protectorate officials and settlers, born or posted
                 in Tunisia but belonging to European families

Sources are the committed CSV dumps of the two workbook sheets, so the build
runs on stdlib alone. Both sheets came out of Excel at exactly 65,535 rows —
the BIFF8 row limit — so the export is truncated; see the folder README.
"""
import collections
import csv
import gzip
import math
import random
import re
import sys
import unicodedata

SRC_IND = "data/rodovid/source/rodovid_individuals.csv.gz"
SRC_TIES = "data/rodovid/source/rodovid_ties.csv.gz"
OUT_IND = "data/rodovid/tunisian_individuals.csv"
OUT_TIES = "data/rodovid/tunisian_ties.csv"
OUT_EXC = "data/rodovid/excluded_individuals.csv"

# Tunisian toponyms (governorates, cities, Tunis quarters, cemeteries) and the
# vocabulary of the beylical state and its schools, which no foreign record in
# this export uses.
TUNISIAN = re.compile(
    r"Tunis|Tunisie|Tunisia|Tunesien|Tunisien|Sousse|Sfax|Kairouan|Monastir|Mahdia|"
    r"Nabeul|Bizerte|Gab[eè]s|Gafsa|Djerba|Jerba|Zarzis|La Marsa|Carthage|Bardo|"
    r"B[eé]ja|Le Kef|K[eé]libia|Moknine|Hammamet|Ksar Hellal|Menzel|Testour|Zaghouan|"
    r"M[eé]denine|Tataouine|Kasserine|Siliana|Jendouba|Tozeur|K[eé]bili|Sidi Bou Sa|"
    r"Bab Souika|Bab Jedid|Bab El Khadra|Halfaouine|Kerkennah|Soliman|Grombalia|Korba|"
    r"Hammam.?Lif|Rad[eè]s|Ariana|Manouba|La Goulette|Halq El|Djellaz|Sidi Jebali|"
    r"Zitouna|Sadiki|Khaldounia|Destour|Nichan|Beylic|Bey de Tunis|Bey du Camp|"
    r"R[eé]gence de Tunis|Regency of Tunis|Ca[iï]d|Kahia|Mateur|Teboursouk|T[eé]bourba|"
    r"Sbe[iï]tla|Thala|Jemmal|Jammel|Msaken|Ouardanine|Metline|Ghar El Melh|Nefta|"
    r"Douz|Ben Gardane|Tabarka|A[iï]n Draham|Sidi Bouzid|Makthar|Enfidha|Bouficha|"
    r"Sahline|Khniss|Bekalta|Teboulba|Sayada|Lamta|Bembla|Zeramdine|Chebba|Rejiche|"
    r"El Jem|Souassi|Ksour Essef|Salakta|Mornag|Sidi Thabet|Sakiet|Redeyef|Metlaoui|"
    r"Tamerza|Matmata|Zarzouna|Ras Jebel|Utique|Dougga|Sbikha|Haffouz|Ouslatia|"
    r"Nasrallah|Ferryville|Protectorat fran[cç]ais de Tunisie|Sadikien|Alaoui|"
    r"Collège Sadiki|Lyc[eé]e Carnot",
    re.I)

# Countries, capitals, dynastic seats and court vocabulary that place a record
# outside Tunisia. France, Italy, Egypt and the Levant are deliberately absent:
# Tunisian elites studied, served and died there, so those names carry no
# information about origin.
FOREIGN = re.compile(
    r"Allemagne|Deutschland|Germany|Preu[sß]|Prusse|Prussia|Russie|Russia|Russland|"
    r"Saint-P[eé]tersbourg|Sankt Petersburg|Moscou|Moscow|Su[eè]de|Sweden|Sverige|"
    r"Danemark|Denmark|Norv[eè]ge|Norway|Pays-Bas|Netherlands|Autriche|Austria|"
    r"Wien|Vienne \(Autriche\)|Hongrie|Hungary|Budapest|Pologne|Poland|Tch[eè]|Prag|"
    r"Angleterre|England|Londres|London|Royaume-Uni|United Kingdom|[EÉ]cosse|Scotland|"
    r"Irlande|Ireland|Br[eé]sil|Brazil|Portugal|Espagne|Spain|Madrid|Gr[eè]ce|Greece|"
    r"Ath[eè]nes|Roumanie|Romania|Serbie|Serbia|Bulgarie|Bulgaria|Abkhazia|"
    r"G[eé]orgie \(pays\)|Ottoman|Osmanisches|Istanbul|Constantinople|Be[sş]ikta[sş]|"
    r"Dolmabah|Orta[kK][oö]y|Topkap|[EÉ]tats-Unis|United States|USA|New York|"
    r"Empire russe|Russian Empire|Saxe|Sachsen|Bavi[eè]re|Bayern|Hesse|Hessen|"
    r"Brandebourg|Mecklembourg|Wurtemberg|W[uü]rttemberg|Bade-|Holstein|Oldenbourg|"
    r"Berlin|Munich|M[uü]nchen|Dresde|Dresden|Stuttgart|Karlsruhe|Weimar|Potsdam|"
    r"Copenhague|Copenhagen|Stockholm|Oslo|Bratislava|Graz|Bruxelles|Belgique|"
    r"Rio de Janeiro|Japon|Japan|Chine|China|Inde \(|India|Iran|T[eé]h[eé]ran|"
    r"Argentine|Mexique|Mexico|Canada|Australie|Australia|Suisse|Switzerland|"
    r"Gen[eè]ve|Lausanne|Z[uü]rich",
    re.I)

# Scripts that place a record outside the Maghreb on sight. Arabic is absent:
# a fair number of Tunisian rows carry the name in Arabic alongside the Latin
# transliteration.
FOREIGN_SCRIPT = ("CYRILLIC", "GEORGIAN", "GREEK", "ARMENIAN", "HEBREW",
                  "CJK", "HIRAGANA", "KATAKANA", "HANGUL", "THAI", "DEVANAGARI")

# Weights on the four signals. A Tunisian place counts for more than a foreign
# one because the evidence is asymmetric: the crawl was seeded on Tunisians, so
# a Tunisian record routinely names Istanbul, Paris or Rome (study, exile,
# Ottoman ancestry) while a European or Ottoman record has no reason to name
# Sousse. Foreign place evidence therefore argues less strongly than Tunisian.
W_PLACE_TUN, W_PLACE_FOR, W_NAME, W_FAMILY, W_NETWORK = 2.0, 1.5, 1.2, 1.0, 1.5
# Positive, not zero: a record with no signal at all — no place, no informative
# name, no relatives, no namesakes — is not evidence of a Tunisian.
KEEP = 0.1
# Score bands reported as `confidence`.
BANDS = ((1.5, "high"), (0.5, "medium"), (0.0, "low"))
# Two hops of kinship, the second worth 40% of the first.
HOPS = (1.0, 0.4)
NGRAMS = (2, 3, 4)


def read_gz(path):
    with gzip.open(path, "rt", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def foreign_script(name):
    for ch in name:
        if ch.isalpha():
            block = unicodedata.name(ch, "")
            if block.startswith(FOREIGN_SCRIPT):
                return True
    return False


def grams(name):
    s = " " + name.lower() + " "
    return [s[i:i + k] for k in NGRAMS for i in range(len(s) - k + 1)]


def train_name_model(labelled, seed=0):
    """Char n-gram Naive Bayes. Returns (scorer, held-out accuracy)."""
    pos = sorted(n for n, y in labelled if y)
    neg = sorted(n for n, y in labelled if not y)
    rng = random.Random(seed)
    rng.shuffle(pos)
    rng.shuffle(neg)
    cut_p, cut_n = int(len(pos) * .8), int(len(neg) * .8)
    train = [(n, 1) for n in pos[:cut_p]] + [(n, 0) for n in neg[:cut_n]]
    test = [(n, 1) for n in pos[cut_p:]] + [(n, 0) for n in neg[cut_n:]]

    def fit(data):
        cnt = (collections.Counter(), collections.Counter())
        tot = [0, 0]
        docs = [0, 0]
        for name, y in data:
            g = grams(name)
            cnt[y].update(g)
            tot[y] += len(g)
            docs[y] += 1
        vocab = set(cnt[0]) | set(cnt[1])
        lp = math.log(docs[1] / docs[0])
        v = len(vocab)

        def score(name):
            s = lp
            for g in grams(name):
                if g in vocab:
                    s += (math.log((cnt[1][g] + .5) / (tot[1] + .5 * v))
                          - math.log((cnt[0][g] + .5) / (tot[0] + .5 * v)))
            return s
        return score

    held = fit(train)
    acc = sum((held(n) > 0) == bool(y) for n, y in test) / len(test)
    return fit(train + test), acc


def squash(x, scale):
    return math.tanh(x / scale)


def main():
    individuals = read_gz(SRC_IND)
    ties = read_gz(SRC_TIES)

    people = {}
    for r in individuals:
        pid = r["ID"].strip()
        if not pid:
            continue
        people[pid] = {
            "id": pid,
            "fullname": (r.get("FULLNAME") or "").strip(),
            "surname": (r.get("SURNAME") or "").strip(),
            "gender": (r.get("GENDER") or "").strip(),
            "info": (r.get("INFO") or "").strip(),
        }

    # 1. place evidence from the person's own record, plus the script the name
    #    is written in
    for p in people.values():
        tun = bool(TUNISIAN.search(p["info"]))
        for_ = bool(FOREIGN.search(p["info"])) or foreign_script(p["fullname"])
        p["place"] = 1.0 if tun else (-1.0 if for_ else 0.0)

    # 2. name model, trained on the people place evidence already separates
    labelled = [(p["fullname"], p["place"] > 0) for p in people.values()
                if p["place"] and p["fullname"]]
    name_score, accuracy = train_name_model(labelled)
    print("name model: %d training names, held-out accuracy %.3f"
          % (len(labelled), accuracy))
    for p in people.values():
        p["name"] = squash(name_score(p["fullname"]), 40.0) if p["fullname"] else 0.0

    # 3. family: place evidence of everyone else carrying the surname
    fam = collections.defaultdict(lambda: [0, 0])
    for p in people.values():
        if p["surname"] and p["place"]:
            fam[p["surname"]][0 if p["place"] > 0 else 1] += 1
    for p in people.values():
        tun, for_ = fam.get(p["surname"], (0, 0))
        if p["place"] > 0:
            tun -= 1
        elif p["place"] < 0:
            for_ -= 1
        n = tun + for_
        p["family"] = ((tun - for_) / n) * min(1.0, n / 3.0) if n > 0 else 0.0

    # 4. network: direct evidence of relatives, two hops out
    adjacency = collections.defaultdict(set)
    for t in ties:
        a, b = t["ID_FROM"].strip(), t["ID_TO"].strip()
        if a in people and b in people and a != b:
            adjacency[a].add(b)
            adjacency[b].add(a)

    def place_term(p):
        return (W_PLACE_TUN if p["place"] > 0 else W_PLACE_FOR) * p["place"]

    direct = {pid: place_term(p) + W_NAME * p["name"] + W_FAMILY * p["family"]
              for pid, p in people.items()}
    for pid, p in people.items():
        seen = {pid}
        frontier = {pid}
        num = den = 0.0
        for weight in HOPS:
            frontier = {n for f in frontier for n in adjacency[f]} - seen
            if not frontier:
                break
            seen |= frontier
            # sorted, so the float sum does not depend on set iteration order
            for n in sorted(frontier, key=int):
                num += weight * squash(direct[n], 2.0)
                den += weight
        p["network"] = num / den if den else 0.0
        p["degree"] = len(adjacency[pid])

    for p in people.values():
        p["score"] = (place_term(p) + W_NAME * p["name"]
                      + W_FAMILY * p["family"] + W_NETWORK * p["network"])
        p["tunisian"] = p["score"] > KEEP
        p["confidence"] = next(lab for edge, lab in BANDS if abs(p["score"]) >= edge)
        # foreign spouse inside a Tunisian family: kept on its ties alone
        p["married_in"] = (p["tunisian"] and p["place"] <= 0 and p["name"] < -0.5
                           and p["family"] <= 0)
        # European family with a Tunisian record: colonial officials, settlers
        p["tunisia_link"] = (not p["tunisian"]) and p["place"] > 0

    kept = {pid for pid, p in people.items() if p["tunisian"]}
    print("individuals: %d kept, %d excluded (of %d)"
          % (len(kept), len(people) - len(kept), len(people)))
    print("  %d kept by marriage into a Tunisian family"
          % sum(p["married_in"] for p in people.values()))
    print("  %d excluded despite a Tunisian place in the record"
          % sum(p["tunisia_link"] for p in people.values()))
    bands = collections.Counter(p["confidence"] for p in people.values() if p["tunisian"])
    print("  kept by confidence: " + ", ".join("%s %d" % (lab, bands[lab])
                                               for _, lab in BANDS))

    # written column -> key on the person record
    cols = {"id": "id", "fullname": "fullname", "surname": "surname",
            "gender": "gender", "score": "score", "confidence": "confidence",
            "sig_place": "place", "sig_name": "name", "sig_family": "family",
            "sig_network": "network", "degree": "degree",
            "married_in": "married_in", "tunisia_link": "tunisia_link",
            "info": "info"}

    def row(p, columns=cols):
        out = {c: p[k] for c, k in columns.items()}
        for c in ("score", "sig_place", "sig_name", "sig_family", "sig_network"):
            out[c] = round(out[c], 4)
        for c in ("married_in", "tunisia_link"):
            if c in out:
                out[c] = "1" if out[c] else "0"
        return out

    def write(path, rows, columns):
        with open(path, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, columns, lineterminator="\n")
            w.writeheader()
            w.writerows(rows)

    order = sorted(people.values(), key=lambda p: (-p["score"], int(p["id"])))
    excluded_cols = {c: k for c, k in cols.items() if c != "married_in"}
    write(OUT_IND, [row(p) for p in order if p["tunisian"]], list(cols))
    write(OUT_EXC, [row(p, excluded_cols) for p in order if not p["tunisian"]],
          list(excluded_cols))

    # ties with both ends kept, deduplicated (the export lists some twice, and
    # sibling and spouse edges appear from both sides)
    seen = set()
    edges = []
    for t in ties:
        a, b = t["ID_FROM"].strip(), t["ID_TO"].strip()
        if a not in kept or b not in kept:
            continue
        edge = t["EDGE"].strip()
        key = (a, b, edge) if edge == "PARENT" else (min(a, b), max(a, b), edge)
        if key in seen:
            continue
        seen.add(key)
        edges.append({"id_from": a, "from": t["FROM"].strip(), "edge": edge,
                      "to": t["TO"].strip(), "id_to": b})
    edges.sort(key=lambda e: (int(e["id_from"]), e["edge"], int(e["id_to"])))
    write(OUT_TIES, edges, ["id_from", "from", "edge", "to", "id_to"])
    print("ties: %d kept (%d rows read, both ends Tunisian and deduplicated)"
          % (len(edges), len(ties)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
