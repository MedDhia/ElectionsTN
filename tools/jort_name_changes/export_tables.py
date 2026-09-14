# -*- coding: utf-8 -*-
import json, csv, re, collections
DASHES = "—–‒‐‑-"
def tidy(s):
    s = re.sub(r"\s+", " ", s or "").strip()
    s = s.strip(DASHES + " .,;:")
    return re.sub(r"\s+", " ", s).strip()


GOUV = {"medenine":"Médenine","medenin":"Médenine","médenin":"Médenine","medecine":"Médenine",
        "médecine":"Médenine","nabcul":"Nabeul","nabeul":"Nabeul","gabes":"Gabès","gabès":"Gabès",
        "kef":"Le Kef","le kef":"Le Kef","kasserine":"Kasserine","bizerte":"Bizerte","sousse":"Sousse",
        "kairouan":"Kairouan","gafsa":"Gafsa","tunis et banlieue":"Tunis et Banlieue","tunis":"Tunis et Banlieue"}
DELEG = {"tedjerouine":"Tédjerouine","tadjerouine":"Tédjerouine","benguerdano":"Ben Guerdane",
         "benguerdane":"Ben Guerdane","’el guetar":"El Guetar","el guetar":"El Guetar",
         "shiba":"Sbiba","sbiba":"Sbiba","kelibia":"Kélibia","kélibia":"Kélibia",
         "tunis et ban issue":"Tunis et Banlieue","tunis et banlieue":"Tunis et Banlieue",
         "el-hammamet":"Hammamet","ras-djebel":"Ras Djebel","menzel temime":"Menzel Temime"}
# gouvernorat inféré à partir de la délégation quand la cellule OCR est vide
DEL2GOUV = {"Ben Guerdane":"Médenine","Sbiba":"Kasserine","Sbiba ":"Kasserine","Nabeul":"Nabeul",
            "Remada":"Médenine","Mareth":"Gabès","Médenine":"Médenine","Zarzis":"Médenine"}
def normgouv(g, d):
    k = re.sub(r"[^a-zà-ÿ ]","",(g or "").lower()).strip()
    v = GOUV.get(k, (g or "").strip(" :.,"))
    if not v: v = DEL2GOUV.get(d, "")
    return v
def normdel(d):
    k = (d or "").lower().strip()
    return DELEG.get(k, (d or "").strip(" :.,"))

recs = json.load(open("records.json"))
decs = json.load(open("decrees.json"))
for r in recs:
    r["ancien_nom"] = tidy(r["ancien_nom"])
    r["nouveau_nom"] = tidy(r["nouveau_nom"])
    r["prenom"] = tidy(r["prenom"])
    r["dossier"] = tidy(r["dossier"]).replace(" ", "")
    r["lieu_acte"] = tidy(r["lieu_acte"])
    r["delegation"] = normdel(r["delegation"])
    r["gouvernorat"] = normgouv(r["gouvernorat"], r["delegation"])
recs = [r for r in recs if r["ancien_nom"] and r["nouveau_nom"]]

cols = ["annee","numero_jort","decret_no","decret_date","gouvernorat","delegation",
        "commission_dates","dossier","ancien_nom","nouveau_nom","prenom","naissance","lieu_acte","pdf"]
with open("jort_noms_individus.csv","w",newline="",encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore"); w.writeheader(); w.writerows(recs)

# family / dossier level
fam = {}
for r in recs:
    k = (r["annee"], r["numero_jort"], r["decret_no"], r["dossier"], r["ancien_nom"], r["nouveau_nom"])
    e = fam.setdefault(k, dict(annee=r["annee"], numero_jort=r["numero_jort"], decret_no=r["decret_no"],
                               decret_date=r["decret_date"], gouvernorat=r["gouvernorat"],
                               delegation=r["delegation"], dossier=r["dossier"],
                               ancien_nom=r["ancien_nom"], nouveau_nom=r["nouveau_nom"],
                               nb_personnes=0, prenoms=[], pdf=r["pdf"]))
    e["nb_personnes"] += 1
    if r["prenom"]: e["prenoms"].append(r["prenom"])
fams = list(fam.values())
for e in fams: e["prenoms"] = "; ".join(e["prenoms"])
fcols = ["annee","numero_jort","decret_no","decret_date","gouvernorat","delegation","dossier",
         "ancien_nom","nouveau_nom","nb_personnes","prenoms","pdf"]
with open("jort_noms_familles.csv","w",newline="",encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=fcols, extrasaction="ignore"); w.writeheader(); w.writerows(fams)

# unique surname pairs
pair = collections.Counter((e["ancien_nom"], e["nouveau_nom"]) for e in fams)
ppl = collections.Counter()
for e in fams: ppl[(e["ancien_nom"], e["nouveau_nom"])] += e["nb_personnes"]
with open("jort_paires_noms.csv","w",newline="",encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["ancien_nom","nouveau_nom","nb_dossiers","nb_personnes"])
    for (a,n),c in pair.most_common(): w.writerow([a,n,c,ppl[(a,n)]])

with open("jort_decrets.csv","w",newline="",encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["annee","numero_jort","decret_no","decret_date","gouvernorat",
                                   "delegation","dates_commission","nb_personnes","pdf"])
    byd = collections.Counter((r["annee"],r["numero_jort"],r["decret_no"]) for r in recs)
    for b in decs:
        k=(b["year"],b["issue"],b["decret_no"])
        w.writerow([b["year"],b["issue"],b["decret_no"],b["decret_date"],b["gouvernorat"],
                    b["delegation"],b["commission_dates"],byd.get(k,0),
                    f"https://lake.jort.tn/journal-officiel/fr/{b['year']}/{b['issue']}.pdf"])

print("individus:",len(recs))
print("dossiers (familles):",len(fams))
print("paires ancien->nouveau uniques:",len(pair))
print("anciens noms distincts:",len({a for a,_ in pair}))
print("nouveaux noms distincts:",len({n for _,n in pair}))
print()
print("Top 15 paires:")
for (a,n),c in pair.most_common(15): print(f"   {a:<22} -> {n:<22} {c} dossiers / {ppl[(a,n)]} pers.")
