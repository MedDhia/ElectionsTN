# Tunisian Voter Surnames: Nationwide Geospatial Dataset (2024 ISIE Registry)

Comprehensive, granular dataset of Tunisian voter surnames extracted from the official **ISIE (Instance Supérieure Indépendante pour les Élections)** voter registry (*قائمات الناخبين الأولية*), dated July 6, 2024.

The dataset covers **all 24 domestic governorates** and **10 diaspora consular constituencies** down to the **Imada (*عمادة*)** and **Polling Center (*مركز إقتراع*)** levels, representing **9,738,408 registered voters** across **2,163 official registry documents** with **99.85% overall extraction completeness**.

---

## 1. Summary Statistics

| Metric | Domestic | Diaspora (*الخارج*) | Worldwide Total |
| :--- | :--- | :--- | :--- |
| **Official Electorate (ISIE Header Total)** | 9,134,854 | 618,353 | **9,753,207** |
| **Extracted Voters** | 9,121,540 | 616,868 | **9,738,408** |
| **Extraction Completeness** | **99.85%** | **99.76%** | **99.85%** |
| **Registry Documents (PDFs)** | 2,082 | 81 | **2,163** |
| **Constituencies / Governorates** | 24 Governorates / 151 Delegations | 10 Foreign Districts | **34 Constituencies** |
| **Unique Imadas / Consular Districts** | 2,082 | 81 | **2,163** |
| **Unique Polling Centers / Stations** | 9,852 centers | 721 foreign desks | **43,059** registered stations |
| **Distinct Surnames (Arabic & Latin)** | — | — | **123,328** |
| **Imada-Surname Distribution Rows** | 1,670,395 | 179,038 | **1,849,433** (`.csv.gz`) |
| **Polling Center-Surname Rows** | 2,442,108 | 194,105 | **2,636,213** (`.csv.gz`) |
| **Total Storage Size (Gzipped Tables)** | — | — | **~47 MB** |

---

## 2. Directory & File Structure

```
data/voter_surnames_2024/
├── README.md                          # Comprehensive documentation & codebook
├── extraction_manifest_national.csv   # Per-PDF audit trail (2,163 PDFs, page counts, official vs extracted)
├── surnames_by_imada.csv.gz           # Granular Imada/District surname counts, shares, and local ranks
├── surnames_by_polling_center.csv.gz  # Physical polling station resolution counts and facility shares
└── surnames_spatial_metrics.csv.gz    # Nationwide surname concentration metrics (HHI, entropy, top imada)
```

Pipeline source code is available in `tools/voter_surnames/`:
- `extractor.py`: High-performance PDF parser with adaptive suffix detection, wrapped line reassembly, and dual-orientation parsing.
- `parser.py`: Arabic normalization, Latin name sanitization, and patronymic decomposition.
- `aggregate.py`: Streaming aggregation, rank calculation, and spatial dispersion metrics (HHI, Shannon Entropy).
- `run_national.py`: Multiprocessing orchestration runner.

---

## 3. Dataset Schemas

### A. `surnames_by_imada.csv.gz` (1,849,433 rows)
*The primary table for geographical, demographic, historical, and political sociology research at the municipal/sub-district level.*

| Column | Type | Description |
| :--- | :--- | :--- |
| `surname` | `str` | Extracted surname / family name (Arabic, or Latin for foreign-registered voters) |
| `surname_norm` | `str` | Normalized string (unified alefs, stripped tashkeel, standard taa marbuta) |
| `governorate` | `str` | Governorate (*ولاية*) or Diaspora Country/Zone (*الدوائر الانتخابية بالخارج*) |
| `constituency` | `str` | Electoral Constituency / Delegation (*الدائرة الانتخابية*) |
| `imada` | `str` | Imada (*العمادة*) or Consular District |
| `voter_count` | `int` | Number of registered voters bearing this surname in the imada |
| `imada_total_voters` | `int` | Total registered voters in the imada |
| `surname_share` | `float` | Percentage of the imada electorate bearing this surname (0–100%) |
| `imada_rank` | `int` | Rank of this surname within the imada (1 = most common family name in the imada) |
| `is_diaspora` | `int` | Boolean flag (1 = Diaspora registry, 0 = Domestic registry) |

### B. `surnames_by_polling_center.csv.gz` (2,636,213 rows)
*Ultra-granular resolution at the physical polling station level (primary school, youth center, sports complex, consulate).*

| Column | Type | Description |
| :--- | :--- | :--- |
| `surname` | `str` | Extracted surname |
| `surname_norm` | `str` | Normalized surname string |
| `governorate` | `str` | Governorate or Diaspora Zone |
| `constituency` | `str` | Constituency / Delegation |
| `imada` | `str` | Imada or Consular District |
| `polling_center` | `str` | Official name of the polling facility (*مركز الإقتراع*) |
| `voter_count` | `int` | Voters with this surname registered at this facility |
| `center_total_voters` | `int` | Total voters registered at this facility |
| `surname_share` | `float` | Percentage share of this surname at this specific facility (0–100%) |
| `is_diaspora` | `int` | Boolean flag (1 = Diaspora, 0 = Domestic) |

### C. `surnames_spatial_metrics.csv.gz` (123,328 rows)
*Nationwide surname concentration metrics, spatial entropy, and geographic centers of gravity across all 123,328 distinct surnames.*

| Column | Type | Description |
| :--- | :--- | :--- |
| `surname` | `str` | Extracted surname |
| `surname_norm` | `str` | Normalized surname |
| `national_voters` | `int` | Total registered voters bearing this surname worldwide |
| `national_share` | `float` | Percentage of the total registered electorate |
| `imadas_present` | `int` | Number of distinct imadas/districts where this surname appears |
| `top_governorate` | `str` | Governorate with the highest voter count for this surname |
| `top_imada` | `str` | Imada with the highest absolute voter count (Format: `[Governorate] - [Imada]`) |
| `top_imada_share_pct` | `float` | Percentage of this surname's national electorate concentrated in its single top imada |
| `hhi_concentration` | `float` | Herfindahl-Hirschman Index across imadas ($\sum s_i^2$, where 1.0 = 100% concentrated in one imada) |
| `spatial_entropy` | `float` | Shannon Spatial Entropy ($-\sum p_i \ln(p_i)$, higher = widely dispersed geographically) |

### D. `extraction_manifest_national.csv` (2,163 rows)
*Complete audit trail verifying the parsing completeness and metadata for each official ISIE PDF.*

| Column | Type | Description |
| :--- | :--- | :--- |
| `pdf_path` | `str` | Source PDF path |
| `filename` | `str` | PDF file name |
| `governorate` | `str` | Governorate parsed from header Page 0 |
| `constituency` | `str` | Constituency parsed from header |
| `imada` | `str` | Imada parsed from header |
| `pages` | `int` | Total page count |
| `official_count` | `int` | Official registered voter count certified on Page 0 |
| `extracted_count` | `int` | Actual parsed voter count across data pages |
| `completeness_pct` | `float` | Extraction completeness percentage ($(\text{extracted} / \text{official}) \times 100$) |
| `is_diaspora` | `int` | Boolean flag (1 = Diaspora, 0 = Domestic) |

---

## 4. Methodological Innovations & Pipeline Architecture

1. **Wrapped Record Line Assembly**:
   In complex layouts and multi-column extractions, long voter names often wrap across physical line breaks. The pipeline implements an adaptive lookahead buffer that merges continuation lines back into single complete records before field tokenization.

2. **Dual-Orientation Token Parsing**:
   - **Domestic standard (Arabic)**: `[3-digit CIN] [Voter Full Name] [Polling Center]`
   - **Inverted diaspora/Latin**: `[Polling Center] [Voter Full Name] [3-digit CIN / Passport]`
   The parser detects token directionality and correctly anchors the national identity number, patronymic chain, and voting center.

3. **Tunisian Patronymic & Compound Surname Decomposition**:
   Tunisian full names follow the patronymic structure: `[First Name] [بن Father] [بن Grandfather] [Family Surname]`. The parser accurately isolates:
   - Three-word compound surnames (e.g. `بن ضيف الله`, `بن شرف الدين`, `بن الحاج علي`, `بن عبد الكريم`).
   - Two-word suffix compounds ending in `الله` and `الدين` (e.g. `ضيف الله`, `عطاء الله`, `شرف الدين`, `صلاح الدين`).
   - Standard Tunisian family prefixes (`بن`, `بو`, `بل`, `عبد`, `آل`, `سيدي`, `ولد`).

4. **Privacy by Design**:
   In strict adherence to ethical research standards, **zero** individual identity numbers (CINs) or unaggregated voter identities are retained in the analytical tables. All outputs are strictly aggregated demographic distributions.

---

## 5. Quick Start (Python & R)

### Python (pandas)
```python
import pandas as pd

# Load imada-level surname distribution
df = pd.read_csv("data/voter_surnames_2024/surnames_by_imada.csv.gz")

# Query dominant surnames in an imada (e.g., Slouguia, Beja)
slouguia = df[(df["governorate"] == "باجة") & (df["imada"] == "السلوقية")]
print(slouguia.sort_values("voter_count", ascending=False).head(10))

# Load national spatial concentration metrics
metrics = pd.read_csv("data/voter_surnames_2024/surnames_spatial_metrics.csv.gz")

# Surnames with highest spatial concentration (HHI > 0.25 with >= 1,000 voters)
concentrated = metrics[(metrics["hhi_concentration"] > 0.25) & (metrics["national_voters"] >= 1000)]
print(concentrated[["surname", "national_voters", "top_imada", "hhi_concentration"]].head(10))
```

### R (tidyverse)
```r
library(tidyverse)

# Read imada dataset
imada_surnames <- read_csv("data/voter_surnames_2024/surnames_by_imada.csv.gz")

# Find top surname per imada in Sfax
sfax_top <- imada_surnames %>%
  filter(str_detect(governorate, "صفاقس"), imada_rank == 1) %>%
  select(constituency, imada, surname, voter_count, surname_share)

print(sfax_top)
```

---

## 6. Mapping the distributions

The imada table is drawn as dot maps in [`maps/surnames/`](../../maps/surnames):
40 family names, one figure each, plus two twelve-panel sheets and a four-name
overlay. Built by `tools/make_surname_dots.py`; the figures and the numbers
printed on them are indexed in `data/maps/surname_dot_index.csv`.

**The join.** This table names its geography the way the registry PDFs print it
— governorate, electoral constituency, imada, all in Arabic, none of it coded.
The boundaries the maps are drawn on (OCHA COD-AB admin4, 2,084 imadas) carry
`adm4_pcode` and their own Arabic spelling, and nothing joins the two but the
names. `tools/bridge_surname_imadas.py` matches them and writes
`data/surname_imada_crosswalk.csv`: **2,074 of the 2,080 domestic registry
imadas, carrying 99.72% of domestic voters**, onto 2,069 boundary units. The six
it could not resolve — among them `حمام معروف الرياض` in Sousse, which admin4
does not carry under any spelling — and the eight it matched across a one-letter
difference are all written to
`data/verification/surname_imada_bridge.jsonl`, with the score and the
runner-up for each.

**The diaspora has no geometry.** The ten consular constituencies (618,353
registered voters, `is_diaspora = 1`) are not on any map here, by construction,
and each figure prints how many of its own voters that cost it.

**Article variants are pooled for mapping.** `العبيدي` and `عبيدي` are the same
family name written two ways — 33,347 and 29,100 voters in this table — and the
maps pool them on the normalised string with the leading definite article
removed. This table keeps them apart, as the registry printed them; the pooling
happens at draw time and each figure states the split.

**Dot placement carries no sub-imada information.** A dot is a fixed number of
voters, scattered at random inside the imada that holds them. The zoom panel on
each figure uses `surnames_by_polling_center.csv.gz` to cluster dots by polling
centre, which shows *that* a name sits in one centre out of six — but no
coordinate for a polling centre exists in any ISIE file, so where the cluster
falls inside the imada is arbitrary and every figure says so.
