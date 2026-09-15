# -*- coding: utf-8 -*-
import re, os, json, glob

DASHES = "—–‒‐‑-"

def clean(s):
    return re.sub(r"\s+", " ", s or "").strip().strip(" .")

def isdash(s):
    s = (s or "").strip()
    return s == "" or all(c in DASHES + " ." for c in s)

PAGE_MARK = re.compile(r"^\s*(<!--\s*page:\d+\s*-->|-{3,}|\d{1,4})\s*$")
PAGE_HEAD = re.compile(r"JOURNAL\s+OFFICIEL\s+DE\s+LA\s+REPUBLIQUE", re.I)

def normalize(txt):
    out = []
    for ln in txt.split("\n"):
        if PAGE_MARK.match(ln) or PAGE_HEAD.search(ln):
            continue
        out.append(ln)
    return "\n".join(out)

DECREE_RE = re.compile(
    r"Par\s+d[ée]crets?\s+N[°ºo]s?\.?\s*([0-9]{2}\s*-\s*[0-9.]+"
    r"(?:\s*(?:et|à|,)\s*(?:N[°ºo]\s*)?[0-9]{2}\s*-\s*[0-9.]+)*)"
    r"[,\s]*du\s+([0-9]{1,2}(?:er)?\s+[A-Za-zéûôêà]+\s+[0-9]{4})", re.I)

# section terminators (a new rubric in the gazette)
STOP_RE = re.compile(
    r"^(?:#{1,6}\s*)?(ANNONCES|AVIS\s+ET\s+COMMUNICATIONS|MOUVEMENT|LISTE\s+D|SITUATION|CONCOURS|"
    r"NOMINATION|MARCHE|CHANGEMENT|TABLEAU|ARR[EÊ]T[EÉ]|D[EÉ]CRET|LOI\s|MINIST|SECRETARIAT|"
    r"PROMOTION|INTEGRATION|RECRUTEMENT|DEMISSION|CESSATION|D[EÉ]TACHEMENT)", re.I)

INTRO_RE = re.compile(
    r"commission\s+locale\s+d\w*\s*(?:la\s+)?nom\s+patronymique\s+de\s+la\s+D[ée]l[ée]gation\s+"
    r"d[eu']?\s*(.{2,60}?)\s*[.,]?\s*\(\s*Gouvern\w+\s+d[eu']?\s*([^)]{2,60}?)\s*\)\s*[.,]?\s*"
    r"en\s+date\s+d\w*\s*(.{0,300}?)\s*[.,]?\s*relatives?", re.I | re.S)
# looser fallbacks
DELEG_RE = re.compile(r"D[ée]l[ée]gation\s+d[eu']?\s*(.{2,60}?)\s*[.,]?\s*\(", re.I | re.S)
GOUV_RE = re.compile(r"\(\s*Gouvern\w+\s+d[eu']?\s*([^)]{2,60}?)\s*\)", re.I)
DATES_RE = re.compile(r"en\s+date\s+d\w*\s*(.{0,300}?)\s*[.,]?\s*relatives?", re.I | re.S)

INLINE_RE = re.compile(
    r"^\s*([0-9][0-9./]*)\s*[" + DASHES + r"]\s*([^" + DASHES + r"]{2,60}?)\s*[" + DASHES +
    r"]\s*([^(]{2,60}?)\s*\(([^)]{1,60})\)\s*(.*)$")

HEADER_TOKENS = ("NUMERO", "NOUVEAU", "ANCIEN", "PRENOM", "NAISSANCE", "DE L'ACTE", "LIEU")

def blocks_for(path):
    raw = open(path, encoding="utf-8", errors="replace").read()
    txt = normalize(raw)
    year, issue = os.path.basename(path)[:-3].split("_")
    anchors = list(DECREE_RE.finditer(txt))
    res = []
    for k, m in enumerate(anchors):
        nxt = anchors[k + 1].start() if k + 1 < len(anchors) else len(txt)
        seg = txt[m.end():nxt]
        head = seg[:1500]
        if "commission locale" not in head.lower() or "patronymique" not in head.lower():
            continue
        # truncate at a new rubric heading
        body_lines = []
        started = False
        for ln in seg.split("\n"):
            s = ln.strip()
            if started and s and not s.startswith("|") and STOP_RE.match(s):
                break
            body_lines.append(ln)
            if s.startswith("|"):
                started = True
        body = "\n".join(body_lines)
        im = INTRO_RE.search(head)
        if im:
            deleg, gouv, cdates = im.group(1), im.group(2), im.group(3)
        else:
            d = DELEG_RE.search(head); g = GOUV_RE.search(head); c = DATES_RE.search(head)
            deleg = d.group(1) if d else ""
            gouv = g.group(1) if g else ""
            cdates = c.group(1) if c else ""
        res.append(dict(
            year=int(year), issue=issue,
            decret_no="/".join(re.sub(r"\s+", "", n) for n in re.findall(r"[0-9]{2}\s*-\s*[0-9.]+", m.group(1))),
            decret_date=clean(m.group(2)),
            delegation=clean(deleg), gouvernorat=clean(gouv),
            commission_dates=clean(cdates), body=body))
    return res

def rows_from_body(body):
    out, lines, i = [], body.split("\n"), 0
    while i < len(lines):
        s = lines[i].strip()
        if s.startswith("|"):
            buf = s
            while not buf.rstrip().endswith("|") and i + 1 < len(lines):
                nx = lines[i + 1].strip()
                if nx.startswith("|") or nx == "":
                    break
                buf += " " + nx; i += 1
            i += 1
            inner = buf.strip().strip("|")
            if re.fullmatch(r"[\s|:-]*", inner):
                continue
            cells = [clean(c) for c in inner.split("|")]
            if len(cells) < 3:
                continue
            up = " ".join(cells).upper()
            if any(t in up for t in HEADER_TOKENS):
                continue
            out.append(("pipe", cells))
            continue
        m = INLINE_RE.match(s)
        if m:
            out.append(("inline", [clean(m.group(g)) for g in (1, 2, 3, 4, 5)]))
        i += 1
    return out

NAME_OK = re.compile(r"[A-Za-zÀ-ÿ]{2,}")
DATE_RE = re.compile(r"(\d{1,2}(?:er)?[\s-]+(?:[A-Za-zÀ-ÿ]+|\d{1,2})[\s-]+\d{2,4})")

def build():
    recs, blocks = [], []
    for path in sorted(glob.glob("md/*.md")):
        for b in blocks_for(path):
            n_before = len(recs)
            last = {"d": "", "n": "", "a": ""}
            for kind, cells in rows_from_body(b["body"]):
                if kind == "pipe":
                    dossier, nouveau, ancien = cells[0], cells[1], cells[2]
                    prenom = cells[3] if len(cells) > 3 else ""
                    rest = " | ".join(cells[4:])
                else:
                    dossier, nouveau, ancien, prenom, rest = cells
                if isdash(dossier): dossier = last["d"]
                else: last["d"] = dossier
                if isdash(nouveau): nouveau = last["n"]
                else: last["n"] = nouveau
                if isdash(ancien): ancien = last["a"]
                else: last["a"] = ancien
                if not (NAME_OK.search(nouveau) and NAME_OK.search(ancien) and NAME_OK.search(prenom)):
                    continue
                rest_flat = " ".join(cells[4:]) if kind == "pipe" else rest
                rest_flat = re.sub(r"\s+", " ", rest_flat)
                dm = DATE_RE.search(rest_flat)
                recs.append(dict(
                    annee=b["year"], numero_jort=b["issue"],
                    decret_no=b["decret_no"], decret_date=b["decret_date"],
                    delegation=b["delegation"], gouvernorat=b["gouvernorat"],
                    commission_dates=b["commission_dates"],
                    dossier=dossier, ancien_nom=ancien, nouveau_nom=nouveau,
                    prenom=prenom, naissance=dm.group(1) if dm else "",
                    lieu_acte=rest,
                    pdf=f"https://lake.jort.tn/journal-officiel/fr/{b['year']}/{b['issue']}.pdf"))
            bb = {k: v for k, v in b.items() if k != "body"}
            bb["n_records"] = len(recs) - n_before
            blocks.append(bb)
    return recs, blocks

if __name__ == "__main__":
    recs, blocks = build()
    json.dump(recs, open("records.json", "w"), ensure_ascii=False, indent=1)
    json.dump(blocks, open("decrees.json", "w"), ensure_ascii=False, indent=1)
    print("decrees:", len(blocks), " records:", len(recs))
    print("issues:", len({(b['year'], b['issue']) for b in blocks}))
    print("families:", len({(r['annee'], r['numero_jort'], r['decret_no'], r['dossier']) for r in recs}))
    for b in blocks:
        print(f"  {b['year']}/{b['issue']} decret {b['decret_no']:<12} {b['decret_date']:<18} "
              f"{b['delegation'][:26]:<26} {b['gouvernorat'][:22]:<22} n={b['n_records']}")
