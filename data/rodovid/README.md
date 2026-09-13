# Rodovid — Tunisian elite genealogies

A crawl of [rodovid.org](https://rodovid.org) seeded on Tunisian elite families,
filtered down to the Tunisians. Two files describe the people and the kinship
between them; a third holds everyone the filter removed, so the call can be
checked rather than taken on trust.

| file | rows | what |
|---|---|---|
| `tunisian_individuals.csv` | 37,819 | people classified as Tunisian, with the evidence for each |
| `tunisian_ties.csv` | 23,565 | parent, sibling and spouse ties where both ends are Tunisian |
| `excluded_individuals.csv` | 27,716 | everyone removed, with the same evidence columns |
| `source/rodovid_individuals.csv.gz` | 65,535 | the `Individuals` sheet of the source workbook, verbatim |
| `source/rodovid_ties.csv.gz` | 65,535 | the `Ties` sheet, verbatim |

Rebuild everything with `python3 tools/build_rodovid_elites.py` — stdlib only,
about fifteen seconds, byte-identical on every run.

The two files under `source/` are the workbook's own sheets, dumped to CSV once
and committed so the build needs no Excel reader:

```python
import pandas as pd                                        # needs pandas, xlrd
for sheet, out in [("Individuals", "rodovid_individuals.csv.gz"),
                   ("Ties", "rodovid_ties.csv.gz")]:
    pd.read_excel("RodovidData234862.xls", sheet).to_csv(
        "data/rodovid/source/" + out, index=False, lineterminator="\n",
        compression={"method": "gzip", "mtime": 0})
```

## What the source is, and what was wrong with it

The source is `RodovidData234862.xls`, an export of a rodovid.org crawl seeded
on Tunisian families. Crawls follow marriages, and this one overran its
subject: alongside the Tunisian families the export carries French aristocratic
and industrial lineages (Polignac, La Rochefoucauld, Prouvost, Tiberghien),
German, Russian, Danish and Swedish royalty, the Ottoman house and its Abkhaz
and Circassian beys, the London Rothschild–Montefiore connection, and Egyptian
and Persian court families. Slightly more than four rows in ten had nothing to
do with Tunisia.

**The export is truncated.** Both sheets came out of Excel at exactly 65,535
data rows — the BIFF8 row limit — so both were cut, not merely the larger one.
Two consequences: 3,872 people are referenced by a tie but have no row of their
own, and 22,857 of the Tunisians kept here have no surviving tie at all, which
is a property of the export rather than of the families. Anything computed on
the kinship graph is a lower bound. A re-export in `.xlsx` would lift the cap.

## How the filter works

Nothing is hand-listed. Each of the 65,535 people is scored on four signals,
each in [-1, 1], positive for Tunisian:

| signal | weight | what it reads |
|---|---|---|
| `sig_place` | 2.0 / 1.5 | Tunisian toponyms and beylical offices in the person's own `INFO` against foreign countries, capitals and dynastic seats, plus the script the name is written in |
| `sig_name` | 1.2 | a character n-gram Naive Bayes model over `FULLNAME` |
| `sig_family` | 1.0 | the place evidence of everyone *else* sharing the surname |
| `sig_network` | 1.5 | the direct evidence of relatives one and two steps away in the kinship graph |

A person is kept when the weighted sum is positive (above 0.1 — a record with
no signal at all is not evidence of a Tunisian).

The name model is trained on the 13,242 people the place signal already
labels, and scores 0.966 on a held-out fifth, printed on every run. It is what
carries the 26,000-odd rows whose own record names no place, and it is why
`sig_name` and the seeding place evidence should not be read as independent.

Tunisian place evidence is weighted more heavily than foreign (2.0 against
1.5) because the evidence is asymmetric: the crawl was seeded on Tunisians, so
a Tunisian record routinely names Istanbul, Paris or Rome — study, exile,
Ottoman ancestry, a Turco-Tunisian mamluk line — while a European or Ottoman
record has no reason to name Sousse.

### Columns

| column | meaning |
|---|---|
| `id` | rodovid person id, unique, the key `tunisian_ties.csv` joins on |
| `fullname`, `surname`, `gender` | as exported; `surname` is rodovid's own reduction of the name |
| `score` | the weighted sum; rows are written in descending order |
| `confidence` | `high` (\|score\| ≥ 1.5), `medium` (≥ 0.5), `low` (below) |
| `sig_place`, `sig_name`, `sig_family`, `sig_network` | the four signals, before weighting |
| `degree` | ties in the export, before filtering |
| `married_in` | kept, but the person's own name and record are foreign — a foreign spouse inside a Tunisian family (68 rows) |
| `tunisia_link` | excluded, but the record names a Tunisian place (8 rows) |
| `info` | the source `INFO` field, verbatim: births, deaths, marriages, offices, schooling |

Both flags mark the cases where the signals disagree, which are the ones worth
a look. `tunisia_link` is mostly protectorate France — Roger Seydoux, résident
général; Baron Rodolphe d'Erlanger of Sidi Bou Saïd; a British vice-consul —
people whose lives ran through Tunisia but whose families are European.

Because every signal is written out, the threshold can be moved without
rerunning anything: a stricter set is `confidence == "high"` (32,320 people),
and rows the filter dropped at `score` just below zero are the top of
`excluded_individuals.csv`.

## What it kept, and what it dropped

Across twenty well-known Tunisian elite families — Bourguiba, Ben Ali, Mzali,
Nouira, Chenik, Caïd Essebsi, Ghannouchi, Materi, Ben Ammar, Belkhodja,
Khaznadar, Baccouche, Sfar, Zarrouk, Trabelsi, Saied, Mestiri, Lasram,
Djellouli, Ben Achour — all 2,906 rows are kept.

Of the export's largest single lineage cluster, 10,670 people of French and
European descent, 115 are kept: the Tunisians the crawl reached through it,
among them Ahmed Ben Salah and Hamed Karoui, both of whom would have been lost
to a filter that worked cluster by cluster rather than person by person.

Kept, correctly, on Tunisian evidence despite European names: the Italian and
Maltese families of Tunis — Tortorici, Vignale, Mascaro, Spiteri, Muscat,
Miceli, Raffo. Dropped, correctly, on foreign evidence despite Arabic names:
the Egyptian pashas, the Hejaz and Persian courts, the Ottoman and Abkhaz beys.

The kept graph has 23,565 ties — 13,215 parent, 6,234 sibling, 4,116 spouse —
over 14,962 people; the remaining 22,857 are isolated by the truncation. Its largest
connected component holds 4,189 people. The people carry 3,249 distinct
surnames; 20,757 are recorded male, 16,676 female, 386 unrecorded.

## Known limits

- **Truncation**, above: the kinship graph is partial, and both sheets are cut.
- **The low band.** 437 kept rows score below 0.5, most of them bare names with
  no record and no surviving tie, where only the name model has anything to
  say. Treat them as a maybe, not a finding.
- **Arabic names outside Tunisia** are the hardest case. Where the record names
  Cairo, Istanbul or Tehran, or the family is attested elsewhere, they are
  dropped correctly; a bare Arabic name with no record and no ties can be kept
  on the name alone, and an Afghan and an Egyptian or two are in the file.
- **Colonial France in Tunisia** is a definitional question the filter answers
  one way: someone French by family and Tunisian only by posting or birthplace
  is excluded, and flagged `tunisia_link` when the record says so.
- **`sig_family` is surname-based**, so it is weak for surnames that are common
  across the Arab world and for the 193 kept rows whose name survives only as a
  `Personne:<id>` wiki link.
- **Rodovid is a user-edited wiki.** Coverage follows what contributors chose to
  enter: deep on a few Tunis families, thin elsewhere, and dates and offices are
  as reliable as whoever typed them. This is a relational map of who is related
  to whom, not a biographical source.
