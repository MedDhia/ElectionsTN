# -*- coding: utf-8 -*-
import re, glob, os, csv, json, collections

NUMS = re.compile(r"[0-9]{2}\s*-\s*[0-9]+")
REF = re.compile(
    r"(LOIS?|D[EÉ]CRETS?)\s+(?:N[°ºo]s?\.?\s*)?((?:[0-9]{2}-[0-9]+)(?:\s*(?:,|et|à)\s*(?:N[°ºo]s?\s*)?[0-9]{2}?-?[0-9]+)*)"
    r"\s*,?\s*du\s+([0-9]{1,2}(?:er)?\s+[A-Za-zÀ-ÿ]+\s+[0-9]{4})\s*,?\s*([^\n]{0,260})", re.I)

rows = []
# A. decrees whose name tables were printed in the main JORT (parsed)
dec = json.load(open("decrees.json"))
cnt = collections.Counter()
for r in json.load(open("records.json")):
    cnt[(r["annee"], r["numero_jort"], r["decret_no"])] += 1
for b in dec:
    rows.append(dict(
        annee=b["year"], numero_jort=b["issue"], type="DECRET", numero=b["decret_no"],
        date=b["decret_date"],
        objet=f"Nom patronymique — délégation de {b['delegation']} (gouvernorat de {b['gouvernorat']})",
        listes_publiees="oui (JORT édition principale)",
        nb_personnes_extraites=cnt.get((b["year"], b["issue"], b["decret_no"]), 0),
        pdf=f"https://lake.jort.tn/journal-officiel/fr/{b['year']}/{b['issue']}.pdf"))

known = {(r["type"], r["numero"]) for r in rows}

# B. every other reference to a nom-patronymique text in 1959-1975 + the 1985 law
for p in sorted(glob.glob("md/*.md")):
    base = os.path.basename(p)[:-3]
    y, iss = int(base[:4]), base[5:8]
    txt = open(p, encoding="utf-8", errors="replace").read()
    for m in REF.finditer(txt):
        tail = re.sub(r"\s+", " ", m.group(4)).strip(" .|")
        if "patronymique" not in tail.lower():
            continue
        if tail.lower().startswith(("rendant obligatoire",)) and m.group(1).upper().startswith("LOI") is False:
            pass
        nums = "/".join(re.sub(r"\s+", "", n) for n in NUMS.findall(m.group(2)))
        typ = "LOI" if m.group(1).upper().startswith("LOI") else "DECRET"
        if (typ, nums) in known:
            continue
        known.add((typ, nums))
        low = tail.lower()
        if "sur l'original" in low:
            pub = "non (publiées sur l'original)"
        elif "édition nom patr" in low or "de l'édition" in low:
            pub = "non (édition spéciale « Nom Patronymique », absente du miroir)"
        elif typ == "DECRET":
            # OCR truncated the summary line before the parenthetical naming the
            # regime. These all post-date the printing window, so the names are
            # not in the main edition either way.
            pub = "non (régime non précisé au sommaire)"
        else:
            pub = "s.o. / texte-cadre"
        rows.append(dict(annee=y, numero_jort=iss, type=typ, numero=nums, date=re.sub(r"\s+"," ",m.group(3)),
                         objet=tail[:200], listes_publiees=pub, nb_personnes_extraites=0,
                         pdf=f"https://lake.jort.tn/journal-officiel/fr/{y}/{iss}.pdf"))


# --- corrections manuelles (artefacts OCR / citations hors sujet) ---
DROP = {("LOI","50-53"), ("LOI","58-27"), ("LOI","59-53")}  # doublons OCR de la loi 59-53
rows = [r for r in rows if not (r["type"],r["numero"]) in DROP or r["annee"]==1959 and r["numero_jort"]=="028"]
rows = [r for r in rows if (r["type"],r["numero"]) not in {("LOI","50-53"),("LOI","58-27")}]
for r in rows:
    if r["numero"] == "62-5": r["type"] = "DECRET-LOI"
CADRES = {
 "59-53": "Loi rendant obligatoire l'acquisition par chaque Tunisien d'un nom patronymique (texte fondateur)",
 "59-101": "Prorogation du délai de l'article 2 de la loi 59-53",
 "62-5": "Décret-loi complétant la loi 59-53 (choix du nom quand la famille ne compte que des femmes)",
 "62-11": "Loi ratifiant le décret-loi 62-5",
 "85-81": "Attribution d'un nom patronymique aux enfants de filiation inconnue ou abandonnés",
}
for r in rows:
    if r["numero"] in CADRES:
        r["objet"] = CADRES[r["numero"]]; r["listes_publiees"] = "s.o. / texte-cadre"
rows.sort(key=lambda r: (r["annee"], r["numero_jort"], r["numero"]))
cols = ["annee","numero_jort","type","numero","date","objet","listes_publiees","nb_personnes_extraites","pdf"]
with open("jort_textes_catalogue.csv","w",newline="",encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(rows)

print("total textes:", len(rows))
c = collections.Counter(r["listes_publiees"] for r in rows)
for k, v in c.items(): print(f"  {v:>3}  {k}")
print()
print("Lois-cadres:")
for r in rows:
    if r["type"] == "LOI": print("  ", r["annee"], r["numero"], r["date"], "|", r["objet"][:100])
print()
print("Décrets avec listes nominatives exploitables:",
      sum(1 for r in rows if r["nb_personnes_extraites"]),
      "| personnes:", sum(r["nb_personnes_extraites"] for r in rows))
