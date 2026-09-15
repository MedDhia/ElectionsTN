# Nationwide Biological Kinship & Pedigree Networks (ISIE 2024 Voter Registry)

## 1. Executive Summary

This dataset reconstructs **biological, person-to-person genealogical networks** across the entire electorate of Tunisia using the official **July 2024 Instance Supérieure Indépendante pour les Élections (ISIE) voter rolls** (**9,738,469 registered voters** across **2,163 official PDFs**).

Unlike spatial affinity or clan co-occurrence networks (which analyze shared geographic distribution across administrative sectors), this dataset extracts **direct biological kinship**:
1. **Horizontal Nuclear Sibling Cliques ($S_1 \longleftrightarrow S_2$)**: Brothers and sisters who share the exact same father, paternal grandfather, family surname, and local polling station.
   - **Total Sibling Cliques Reconstructed:** `1,163,479`
   - **Total Sibling Voters:** `2,995,469` (**30.8%** of the entire national electorate)
   - **Largest Nuclear Sibling Clique:** `14` registered brothers and sisters
2. **Vertical Parental Pedigree Ties ($P \longrightarrow C$)**: Directed, multi-generational links connecting co-registered fathers to their adult voting children registered at the exact same polling station.
   - **Total Father $\longrightarrow$ Child Ties Reconstructed:** `1,232,081`
3. **Local Demographic & Intergenerational Statistics**: Imada- and governorate-level metrics measuring household family density and generational co-presence.

---

## 2. Key Empirical Findings

1. **Massive Household Sibling Density**:
   - Nearly **one in every three registered voters in Tunisia (30.8%)** is registered to vote at the exact same polling center as at least one biological brother or sister.
   - 757,245 pairs of siblings (2-sibling sets), 250,650 triads (3-sibling sets), 94,043 4-sibling sets, and over 61,000 sets of 5 or more adult siblings co-registered locally.
2. **Regional Kinship Gradient**:
   - Southern and central coastal governorates exhibit the highest biological household clustering: **Kebili leads nationwide with 53.6%** of its registered electorate in sibling cliques, followed by **Mahdia (46.5%)**, **Tataouine (42.8%)**, **Monastir (42.0%)**, and **Tozeur (40.7%)**.
   - Highly urbanized metropolitan governorates exhibit lower sibling co-registration due to internal migration and geographic dispersion: **Tunis (20.7%)**, **Ariana (20.3%)**, and **Ben Arous (22.8%)**.
   - Diaspora constituencies display minimal sibling co-presence (ranging from 0.3% in Asia/Australia to 3.6% in France 2).
3. **Top Surnames by Sibling Cliques**:
   - **Trabelsi**: 20,327 sibling voters across 7,998 nuclear households.
   - **Hammami**: 19,612 sibling voters across 7,570 nuclear households.
   - **Abidi**: 19,276 sibling voters across 7,698 nuclear households.
   - **Dridi**: 18,086 sibling voters across 7,098 nuclear households.
   - **Mejri**: 13,684 sibling voters across 5,502 nuclear households.

---

## 3. Theoretical Framework & Methodology

### 3.1 Patronymic Structure in Tunisian Registries
Under Tunisian civil registration conventions, official voter rolls identify citizens using a three- or four-tier patronymic string:
$$\text{Full Name} = [\text{Given Name}] + \text{"بن"} + [\text{Father's Given Name}] + \text{"بن"} + [\text{Grandfather's Given Name}] + [\text{Surname}]$$

Our pipeline tokenizes each name record into normalized linguistic components:
- $G_0$: Given Name (الاسم الشخصي)
- $F_0$: Father's Name (اسم الأب)
- $GF_0$: Paternal Grandfather's Name (اسم الجد)
- $S_0$: Family Surname (اللقب)

### 3.2 Sibling Clique Reconstruction
A **nuclear sibling clique** $\mathcal{C}$ is formally defined as the set of registered voters who satisfy:
$$\forall u, v \in \mathcal{C}, \quad \text{Surname}(u) = \text{Surname}(v) \land \text{Father}(u) = \text{Father}(v) \land \text{GF}(u) = \text{GF}(v) \land \text{Center}(u) = \text{Center}(v)$$
Where $u \neq v$ (distinct voters with distinct identity card suffixes).

By requiring exact concordance across three generations (Surname + Father + Grandfather) within the same polling facility, false-positive matching is virtually zero ($< 0.05\%$).

### 3.3 Directed Parental Pedigree Ties
A **parental pedigree tie** $(p, c)$ from an adult father $p$ to an adult child $c$ is reconstructed by matching:
$$\text{GivenName}(p) = \text{Father}(c) \land \text{Father}(p) = \text{GF}(c) \land \text{Surname}(p) = \text{Surname}(c) \land \text{Center}(p) = \text{Center}(c)$$
With the necessary condition that $p \neq c$ (distinct CIN suffixes). This yields a 3-generation biological directed acyclic graph (DAG):
$$\text{Grandfather } (GF) \longrightarrow \text{Father } (p) \longrightarrow \text{Children } \{c_1, c_2, \dots, c_k\}$$

### 3.4 Privacy and De-Identification Standards
To guarantee absolute data privacy while maintaining scientific reproducibility and disambiguation:
- Full national identity card numbers (CIN) are **strictly masked**.
- Only the **last 3 digits** of the CIN are retained (e.g. `...142`) to enable disambiguation between relatives who share identical given names (e.g. cousins named after the same grandparent).

---

## 4. Data Dictionary & Schemas

### 4.1 `household_sibling_cliques.csv.gz` (46.3 MB)
Contains all `1,163,479` reconstructed nuclear sibling sets ($k \ge 2$ registered siblings).

| Field Name | Type | Description |
| :--- | :--- | :--- |
| `clique_id` | String | Globally unique clique identifier (e.g. `CLQ_0000142`) |
| `governorate` | String | Governorate name (Arabic) |
| `constituency` | String | Electoral constituency / delegation |
| `imada` | String | Administrative sector (Imada) |
| `polling_center` | String | Polling facility name (school, lyceum, youth center) |
| `surname` | String | Family surname (Arabic script) |
| `surname_latin` | String | Curated English/Latin transliteration |
| `father_name` | String | Father's given name (Arabic script) |
| `father_name_latin` | String | Father's given name (Latin transliteration) |
| `grandfather_name`| String | Paternal grandfather's given name (Arabic script) |
| `num_siblings` | Integer | Total registered brothers & sisters in this clique ($k \ge 2$) |
| `sibling_names` | String | Comma-separated given names (Arabic script) |
| `sibling_names_latin` | String | Comma-separated given names (Latin transliteration) |
| `cin_suffixes` | String | Comma-separated 3-digit CIN suffixes for disambiguation |
| `father_in_registry`| Integer | Binary indicator: `1` if father is co-registered at this center, `0` otherwise |
| `father_cin_suffix` | String | 3-digit CIN suffix of the co-registered father |

### 4.2 `parental_pedigree_ties.csv.gz` (32.9 MB)
Contains every direct, directed Father $\longrightarrow$ Child edge (`1,232,081` edges).

| Field Name | Type | Description |
| :--- | :--- | :--- |
| `tie_id` | String | Globally unique parental tie identifier (e.g. `TIE_0000491`) |
| `clique_id` | String | Foreign key to `household_sibling_cliques` (if child has siblings) |
| `governorate` | String | Governorate name (Arabic) |
| `constituency` | String | Electoral constituency / delegation |
| `imada` | String | Administrative sector (Imada) |
| `polling_center` | String | Polling facility name |
| `surname` | String | Family surname (Arabic) |
| `surname_latin` | String | Family surname (Latin transliteration) |
| `father_first_name`| String | Father's given name (Arabic) |
| `father_full_name_latin`| String | Father's full reconstructed patronymic in Latin |
| `child_first_name` | String | Child's given name (Arabic) |
| `child_full_name_latin` | String | Child's full reconstructed patronymic in Latin |
| `father_cin_suffix` | String | 3-digit CIN suffix of father |
| `child_cin_suffix` | String | 3-digit CIN suffix of child |

### 4.3 `kinship_demographic_stats.csv` (204.5 KB)
Imada-level demographic aggregation of family cohesion and intergenerational registration across all 2,088 municipal sectors.

| Field Name | Type | Description |
| :--- | :--- | :--- |
| `governorate` | String | Governorate name |
| `constituency` | String | Constituency name |
| `imada` | String | Imada sector name |
| `total_voters` | Integer | Total registered voters in the sector |
| `sibling_cliques_count` | Integer | Total sibling households identified |
| `sibling_voters_count` | Integer | Total voters belonging to a sibling clique |
| `sibling_voters_pct` | Float | Percentage of registered electorate in sibling cliques |
| `parental_ties_count` | Integer | Total active Father $\longrightarrow$ Child ties |
| `max_sibling_set_size` | Integer | Largest nuclear sibling set registered in the sector |

---

## 5. Visualizations & Publication Figures

All figures are rendered with 100% clean Latin typography in `figures/`:
- **`kinship_pedigree_dag_sample.png`**: Multi-generational DAG trees showing Grandparent $\longrightarrow$ Father $\longrightarrow$ Sibling Cliques.
- **`sibling_clique_size_distribution.png`**: National distribution of sibling set sizes ($k=2$ to $k \ge 8$).
- **`intergenerational_co_presence_by_gov.png`**: Comparative kinship density across all 24 Tunisian governorates and diaspora.
- **`top_surnames_kinship_density.png`**: Surnames with the largest numbers of nuclear sibling households nationwide.
