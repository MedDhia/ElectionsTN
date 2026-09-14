# Patronymic name changes under Bourguiba (JORT, 1965-1966)

Every surname change that the *Journal Officiel de la République Tunisienne*
printed by name, extracted from the presidential decrees that enacted them:
**18,593 people**, **2,115 family dossiers**, **1,361 distinct
`ancien nom -> nouveau nom` pairs**, across **73 decrees** and **10 governorates**.

Source: the French edition of the JORT, via the full mirror at
[jort.tn](https://www.jort.tn) (`lake.jort.tn` for facsimile PDFs,
`ocr.jort.tn` for the OCR text layer).

---

## 1. The legal instrument

Law 59-53 obliges every Tunisian to acquire a patronymic name and creates a
**commission locale du nom patronymique** in each délégation. The commissions
decide; a presidential decree signed Habib Bourguiba makes those decisions
binding; the JORT prints the resulting table, column for column:

`N° de dossier | NOUVEAU NOM | ANCIEN NOM | PRÉNOM | date, lieu et n° d'acte de naissance`

| Text | Date | Object |
|---|---|---|
| Loi 59-53 | 26 May 1959 | Makes a patronymic compulsory; creates the local commissions (founding text) |
| Loi 59-101 | 1 Sept. 1959 | Extends the article 2 deadline |
| Décret-loi 62-5 | 10 March 1962 | Completes 59-53 (who chooses when a family has no male ascendant) |
| Loi 62-11 | 24 April 1962 | Ratifies décret-loi 62-5 |
| Loi 85-81 | 11 Aug. 1985 | Patronymic for children of unknown filiation or abandoned |

## 2. Coverage — read this before using the data

142 texts on the patronymic name were located across 1959-1985. The **name lists
themselves were printed in the main gazette only between September 1965 and
August 1966**:

| Publication regime | Texts | Names recoverable |
|---|---|---|
| Lists printed in the JORT main edition | **73 decrees** | **yes — 18,593 people** |
| "publiés sur l'original" (from decree 66-314, Aug. 1966) | 15 decrees | no — never printed |
| Separate "Nom Patronymique" edition (from decree 67-383, Nov. 1967) | 44 decrees | no — edition not digitised |
| Framework laws | 10 | n/a |

From decree 66-314 the gazette notes only that the lists are "published on the
original" — the signed copy alone carries the names. From decree 67-383 they move
to a separate JORT edition titled *Nom Patronymique*, which exists neither on
iort.tn nor in the mirror; the main edition keeps only a summary line pointing at
its issue number. The Arabic edition is not OCR'd either.

**These 18,593 people are therefore the visible window, not the total number of
name changes.** Treat the governorate distribution the same way: Le Kef and
Médenine dominate because their commissions happened to report during that
eleven-month printing window, not because name changes concentrated there.

## 3. Files

```
data/jort_name_changes_1965_1966/
├── README.md
├── jort_noms_individus.csv.gz      18,593 rows — one row per person
├── jort_noms_familles.csv           2,115 rows — one row per dossier (family)
├── jort_paires_noms.csv             1,361 rows — distinct old -> new pairs
├── jort_decrets.csv                    73 rows — the decrees actually exploited
├── jort_textes_catalogue.csv          142 rows — every text located, with its publication regime
└── figures/
    ├── sankey_noms_jort.png         flow diagram, light (2800 × 2296)
    ├── sankey_noms_jort_sombre.png  flow diagram, dark
    ├── sankey_noms_jort.html        interactive version (filters, table view)
    └── sankey_data.js               data payload for the page
```

Pipeline in `tools/jort_name_changes/`:
- `download_corpus.py` — mirrors the French JORT OCR text, 1959-1975 (1,046 issues)
- `parse_decrees.py` — locates decree blocks, parses both table formats, resolves continuation rows
- `export_tables.py` — cleans, normalises place names, writes the four CSV levels
- `build_catalogue.py` — sweeps the corpus for every patronymic-name text and its publication regime
- `render_figures.js` — renders the Sankey to PNG in both themes (Playwright)

## 4. Codebook

### `jort_noms_individus.csv.gz` — one row per person
| Field | Description |
|---|---|
| `annee`, `numero_jort` | Year and issue number of the gazette |
| `decret_no` | Decree number, e.g. `65-448` |
| `decret_date` | Date of the decree |
| `gouvernorat`, `delegation` | Governorate and délégation of the commission |
| `commission_dates` | Date(s) of the local commission sittings the decree approves |
| `dossier` | Dossier number as printed; shared by all members of one family |
| `ancien_nom` | Surname before the change |
| `nouveau_nom` | Surname after the change |
| `prenom` | Given name |
| `naissance` | Date of birth, as printed |
| `lieu_acte` | Remaining printed cells (place of birth, birth-record number) |
| `pdf` | Facsimile of the source issue |

### `jort_noms_familles.csv` — one row per dossier
Same identifiers, plus `nb_personnes` (people in the dossier) and `prenoms`
(their given names, `;`-separated). A dossier is one family changing one name.

### `jort_paires_noms.csv` — distinct pairs
`ancien_nom`, `nouveau_nom`, `nb_dossiers`, `nb_personnes`. 930 distinct old
names, 863 distinct new names.

### `jort_decrets.csv` — the 73 exploited decrees
Adds `dates_commission` and `nb_personnes` extracted per decree.

### `jort_textes_catalogue.csv` — all 142 texts
`type` (LOI / DECRET-LOI / DECRET), `numero`, `date`, `objet`, and
`listes_publiees` — the publication regime from the table in §2, which says
whether names are recoverable for that text.

## 5. What the data shows

The replaced names are overwhelmingly **collective and tribal designations**,
substituted by individualised family patronyms. `Charni` (1,773 people) splits
into eleven separate surnames; `Jebari -> Naimi` alone covers 369 people in 22
dossiers; `Boughanmi` fragments into `Souihi`, `Othmani`, `Zidi`, `Hmaidi` and
more. The 1959 law's practical effect, visible row by row, is the conversion of
tribal affiliation into civil-registry surnames.

## 6. Provenance and known limits

- Corpus: 1,046 French JORT issues, 1959-1975, plus 1985/059.
- Decree blocks are anchored on `Par décret N° … du … :` followed by
  *"Sont approuvées les décisions de la commission locale du nom patronymique"*.
- Two printed formats coexist: ruled tables (1965 – May 1966) and inline lists
  `dossier — nouveau — ancien (prénom) date — lieu — acte` (from JORT 1966/023).
  Continuation rows (dashes) inherit the current dossier and names, as in the
  original layout.
- Validation: 10 randomly drawn rows checked line by line against the source
  text, 10/10 exact; 6 questionable cells in 18,593 (0.03%).
- This is OCR. Decree numbers and toponyms retain residual errors (`63-545` for
  `65-545`, `Benguerdano` for Ben Guerdane). Person-name columns are clean
  tabular fields and are markedly more reliable. Every row carries a `pdf` link
  back to the facsimile for verification.
- Governorate and délégation labels are normalised (`Medenine`/`Médenin:` ->
  `Médenine`, `Nabcul` -> `Nabeul`); a few blank governorate cells are inferred
  from the délégation.
