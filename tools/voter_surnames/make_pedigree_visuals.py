#!/usr/bin/env python3
"""
Nationwide Biological Kinship Network Visualizer
================================================
Generates publication-quality figures (100% Latin typography) from:
- household_sibling_cliques.csv.gz
- parental_pedigree_ties.csv.gz
- kinship_demographic_stats.csv
"""

import os
import sys
import gzip
import csv
from pathlib import Path
from collections import Counter, defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np
import pandas as pd

# Set clean Latin typography styling
plt.rcParams['font.family'] = 'DejaVu Sans'
plt.rcParams['font.size'] = 10
plt.rcParams['axes.titlesize'] = 13
plt.rcParams['axes.labelsize'] = 11
plt.rcParams['xtick.labelsize'] = 9
plt.rcParams['ytick.labelsize'] = 9
plt.rcParams['figure.titlesize'] = 15

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(BASE_DIR, "tools"))
from arabic_translit import translit

KINSHIP_DIR = os.path.join(BASE_DIR, "data", "voter_surnames_2024", "kinship")
FIG_DIR = os.path.join(KINSHIP_DIR, "figures")
os.makedirs(FIG_DIR, exist_ok=True)

GOV_LATIN = {
    "أريانة": "Ariana", "باجة": "Beja", "بن عروس": "Ben Arous", "بنزرت": "Bizerte",
    "تطاوين": "Tataouine", "توزر": "Tozeur", "تونس": "Tunis", "جندوبة": "Jendouba",
    "زغوان": "Zaghouan", "سليانة": "Siliana", "سوسة": "Sousse", "سيدي بوزيد": "Sidi Bouzid",
    "صفاقس": "Sfax", "قابس": "Gabes", "قبلي": "Kebili", "القصرين": "Kasserine",
    "قفصة": "Gafsa", "القيروان": "Kairouan", "الكاف": "Le Kef", "مدنين": "Medenine",
    "المنستير": "Monastir", "منوبة": "Manouba", "المهدية": "Mahdia", "نابل": "Nabeul",
    "ألمانيا": "Germany (Diaspora)", "فرنسا 1": "France 1 (Diaspora)", "فرنسا 2": "France 2 (Diaspora)",
    "فرنسا 3": "France 3 (Diaspora)", "إيطاليا": "Italy (Diaspora)", "باقي الدول": "Other Countries (Diaspora)",
    "الدول العربية": "Arab Countries (Diaspora)", "باقي الدول الأوروبية": "Rest of Europe (Diaspora)",
    "الأمريكيتان": "Americas (Diaspora)", "افريقيا": "Africa (Diaspora)", "اسيا وأستراليا": "Asia & Australia (Diaspora)"
}


def clean_latin(s):
    if not s:
        return ""
    s_str = str(s).strip()
    # If already Latin (contains ASCII letters), return cleaned s
    if any('a' <= ch.lower() <= 'z' for ch in s_str):
        return s_str
    s_str = s_str.replace("م إبتدائية", "Primary School").replace("إبتدائية", "Primary School")
    s_str = s_str.replace("معهد", "Lyceum").replace("إعدادية", "Prep School")
    res = translit(s_str)
    return res if res else s_str


def plot_pedigree_dag_samples():
    """Figure 1: Reconstructed Multi-Generational Pedigree DAGs"""
    cliques_path = os.path.join(KINSHIP_DIR, "household_sibling_cliques.csv.gz")
    if not os.path.exists(cliques_path):
        print(f"File not found: {cliques_path}")
        return

    # Pick 3 diverse representative families from major governorates (Sfax, Tunis, Sousse)
    target_govs = ["صفاقس", "تونس", "سوسة", "القيروان", "مدنين"]
    selected = []
    seen_govs = set()
    with gzip.open(cliques_path, "rt", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            gov = r["governorate"]
            if r.get("father_in_registry") == "1" and int(r.get("num_siblings", 0)) >= 3:
                if gov in target_govs and gov not in seen_govs:
                    selected.append(r)
                    seen_govs.add(gov)
                    if len(selected) == 3:
                        break

    if len(selected) < 3:
        with gzip.open(cliques_path, "rt", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                if r.get("father_in_registry") == "1" and int(r.get("num_siblings", 0)) >= 3:
                    if r["governorate"] not in seen_govs:
                        selected.append(r)
                        seen_govs.add(r["governorate"])
                        if len(selected) == 3:
                            break

    fig, axes = plt.subplots(1, 3, figsize=(19, 9.5), dpi=300)
    fig.patch.set_facecolor("#f8fafc")

    for idx, (ax, c) in enumerate(zip(axes, selected)):
        ax.set_facecolor("#ffffff")
        ax.set_xlim(-0.15, 1.15)
        ax.set_ylim(-0.08, 1.15)
        ax.axis("off")

        gov_lat = GOV_LATIN.get(c["governorate"], clean_latin(c["governorate"]))
        const_lat = clean_latin(c["constituency"])
        sn_lat = c["surname_latin"]
        fa_lat = c["father_name_latin"]
        gf_lat = clean_latin(c["grandfather_name"])
        sib_names = [clean_latin(s.strip()) for s in c["sibling_names_latin"].split(",") if s.strip()][:4]
        cins = [s.strip() for s in c["cin_suffixes"].split(",") if s.strip()][:4]
        f_cin = c.get("father_cin_suffix", "N/A")
        center_lat = clean_latin(c["polling_center"])[:30]

        # Title card (positioned with clean spacing)
        ax.text(0.5, 1.10, f"Family #{idx+1}: {sn_lat} Lineage",
                ha="center", va="top", fontsize=13, fontweight="bold", color="#0f172a")
        ax.text(0.5, 1.05, f"Governorate: {gov_lat}  |  Delegation: {const_lat}",
                ha="center", va="top", fontsize=10, color="#475569")

        # Level 0: Grandfather Node (Paternal Root)
        gf_box = patches.FancyBboxPatch((0.15, 0.86), 0.7, 0.12,
                                        boxstyle="round,pad=0.03,rounding_size=0.04",
                                        facecolor="#f1f5f9", edgecolor="#64748b", linewidth=1.5)
        ax.add_patch(gf_box)
        ax.text(0.5, 0.94, "PATERNAL GRANDFATHER (GENERATION 0)", ha="center", va="center", fontsize=8, color="#475569", fontweight="bold")
        ax.text(0.5, 0.89, f"Patronym: {gf_lat} {sn_lat}", ha="center", va="center", fontsize=11, color="#0f172a", fontweight="bold")

        # Arrow GF -> Father
        ax.annotate("", xy=(0.5, 0.73), xytext=(0.5, 0.86),
                    arrowprops=dict(arrowstyle="->", lw=2, color="#64748b", shrinkA=2, shrinkB=2))

        # Level 1: Father Node (Co-registered Adult Voter)
        fa_box = patches.FancyBboxPatch((0.12, 0.54), 0.76, 0.17,
                                        boxstyle="round,pad=0.03,rounding_size=0.04",
                                        facecolor="#eff6ff", edgecolor="#2563eb", linewidth=2)
        ax.add_patch(fa_box)
        ax.text(0.5, 0.65, "FATHER (GENERATION 1 — CO-REGISTERED VOTER)", ha="center", va="center", fontsize=8, color="#1d4ed8", fontweight="bold")
        ax.text(0.5, 0.60, f"{fa_lat} ben {gf_lat} {sn_lat}", ha="center", va="center", fontsize=11, color="#1e3a8a", fontweight="bold")
        ax.text(0.5, 0.55, f"Voter ID CIN Suffix: ...{f_cin}", ha="center", va="center", fontsize=8.5, color="#2563eb")

        # Sibling Nodes Level 2
        n_sibs = len(sib_names)
        x_positions = np.linspace(0.04, 0.96, n_sibs) if n_sibs > 1 else [0.5]

        for xi, sib_name, cin in zip(x_positions, sib_names, cins):
            # Arrow Father -> Child
            ax.annotate("", xy=(xi, 0.35), xytext=(0.5, 0.54),
                        arrowprops=dict(arrowstyle="->", lw=1.5, color="#0284c7", alpha=0.8, shrinkA=2, shrinkB=2))

            # Child Node
            ch_box = patches.FancyBboxPatch((xi - 0.13, 0.16), 0.26, 0.17,
                                            boxstyle="round,pad=0.02,rounding_size=0.03",
                                            facecolor="#ecfdf5", edgecolor="#059669", linewidth=1.5)
            ax.add_patch(ch_box)
            ax.text(xi, 0.28, "CHILD (GEN 2)", ha="center", va="center", fontsize=7, color="#047857", fontweight="bold")
            ax.text(xi, 0.23, f"{sib_name}", ha="center", va="center", fontsize=9.5, color="#064e3b", fontweight="bold")
            ax.text(xi, 0.18, f"CIN: ...{cin}", ha="center", va="center", fontsize=8, color="#059669")

        # Horizontal sibling clique bounding bar
        if n_sibs > 1:
            ax.plot([x_positions[0], x_positions[-1]], [0.10, 0.10], color="#059669", linestyle="--", linewidth=1.5)
            ax.text(0.5, 0.06, f"Nuclear Sibling Clique (k = {c['num_siblings']} registered siblings)",
                    ha="center", va="center", fontsize=9, color="#065f46", fontweight="bold")
            ax.text(0.5, 0.01, f"Facility: {center_lat}...",
                    ha="center", va="center", fontsize=8, color="#64748b")

    plt.suptitle("Official ISIE 2024 Voter Registry — Biological Pedigree DAGs\n(Reconstructed from Patronymic Vectors & Polling Station Co-Presence)",
                 fontsize=15, fontweight="bold", y=0.98, color="#0f172a")
    plt.tight_layout(rect=[0, 0, 1, 0.94])

    out_file = os.path.join(FIG_DIR, "kinship_pedigree_dag_sample.png")
    plt.savefig(out_file, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Saved: {out_file}")


def plot_sibling_size_distribution():
    """Figure 2: Distribution of Nuclear Sibling Clique Sizes Nationwide"""
    cliques_path = os.path.join(KINSHIP_DIR, "household_sibling_cliques.csv.gz")
    if not os.path.exists(cliques_path):
        return

    sizes = Counter()
    with gzip.open(cliques_path, "rt", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            k = int(r["num_siblings"])
            sizes[k] += 1

    total_cliques = sum(sizes.values())
    total_sibling_voters = sum(k * cnt for k, cnt in sizes.items())

    plot_labels = ["2", "3", "4", "5", "6", "7", "8+"]
    counts = [sizes[k] for k in range(2, 8)]
    counts.append(sum(cnt for k, cnt in sizes.items() if k >= 8))

    voter_counts = [k * sizes[k] for k in range(2, 8)]
    voter_counts.append(sum(k * cnt for k, cnt in sizes.items() if k >= 8))

    fig, ax1 = plt.subplots(figsize=(11, 6.5), dpi=300)
    fig.patch.set_facecolor("#ffffff")
    ax1.set_facecolor("#f8fafc")

    x = np.arange(len(plot_labels))
    width = 0.38

    rects1 = ax1.bar(x - width/2, counts, width, label="Sibling Households (Cliques)", color="#2563eb", alpha=0.9, edgecolor="#1d4ed8")
    ax1.set_ylabel("Number of Sibling Cliques", color="#1d4ed8", fontsize=11, fontweight="bold")
    ax1.tick_params(axis="y", labelcolor="#1d4ed8")
    ax1.set_xticks(x)
    ax1.set_xticklabels(plot_labels, fontsize=10, fontweight="bold")
    ax1.set_xlabel("Sibling Clique Size (Number of Brothers & Sisters Registered in Same Polling Center)", fontsize=11, fontweight="bold")
    ax1.set_ylim(0, max(counts) * 1.18)
    ax1.grid(axis="y", linestyle="--", alpha=0.4)

    # Second axis: Total voters in those cliques
    ax2 = ax1.twinx()
    rects2 = ax2.bar(x + width/2, voter_counts, width, label="Total Registered Voters", color="#059669", alpha=0.85, edgecolor="#047857")
    ax2.set_ylabel("Total Registered Sibling Voters", color="#059669", fontsize=11, fontweight="bold")
    ax2.tick_params(axis="y", labelcolor="#059669")
    ax2.set_ylim(0, max(voter_counts) * 1.18)

    # Count labels with proper formatting
    for i, rect in enumerate(rects1):
        h = rect.get_height()
        yoff = 10 if i == 0 else 4
        ax1.annotate(f"{h:,}", xy=(rect.get_x() + rect.get_width() / 2, h),
                     xytext=(0, yoff), textcoords="offset points", ha="center", va="bottom", fontsize=8.5, color="#1e3a8a", fontweight="bold")

    for i, rect in enumerate(rects2):
        h = rect.get_height()
        ax2.annotate(f"{h:,}", xy=(rect.get_x() + rect.get_width() / 2, h),
                     xytext=(0, 4), textcoords="offset points", ha="center", va="bottom", fontsize=8.5, color="#064e3b", fontweight="bold")

    plt.title(f"National Distribution of Nuclear Sibling Clique Sizes\nTotal Sibling Cliques: {total_cliques:,} | Total Sibling Voters: {total_sibling_voters:,} (30.8% of National Electorate)",
              fontsize=13, fontweight="bold", pad=15)

    # Combined legend
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper right", frameon=True, facecolor="#ffffff", edgecolor="#cbd5e1", fontsize=10)

    plt.tight_layout()
    out_file = os.path.join(FIG_DIR, "sibling_clique_size_distribution.png")
    plt.savefig(out_file, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Saved: {out_file}")


def plot_intergenerational_by_gov():
    """Figure 3: Intergenerational and Sibling Co-presence Rates Across 24 Governorates"""
    stats_path = os.path.join(KINSHIP_DIR, "kinship_demographic_stats.csv")
    if not os.path.exists(stats_path):
        return

    df = pd.read_csv(stats_path)
    
    # Map all governorates strictly to Latin
    df["gov_latin"] = df["governorate"].map(lambda x: GOV_LATIN.get(x, clean_latin(x)))
    
    # Filter out empty or placeholder rows
    df = df[df["total_voters"] > 100]

    # Aggregate by governorate
    gov_stats = df.groupby("gov_latin").agg({
        "total_voters": "sum",
        "sibling_voters_count": "sum",
        "parental_ties_count": "sum",
        "sibling_cliques_count": "sum"
    }).reset_index()

    gov_stats["sibling_pct"] = (gov_stats["sibling_voters_count"] / gov_stats["total_voters"]) * 100
    gov_stats["parental_pct"] = (gov_stats["parental_ties_count"] / gov_stats["total_voters"]) * 100

    # Sort by sibling rate ascending for horizontal bar chart
    gov_stats = gov_stats.sort_values("sibling_pct", ascending=True)

    fig, ax = plt.subplots(figsize=(12, 10.5), dpi=300)
    fig.patch.set_facecolor("#ffffff")
    ax.set_facecolor("#f8fafc")

    y = np.arange(len(gov_stats))
    h = 0.38

    b1 = ax.barh(y + h/2, gov_stats["sibling_pct"], h, label="Sibling Voter Co-Presence (% of Electorate in Sibling Sets)", color="#0284c7", edgecolor="#0369a1")
    b2 = ax.barh(y - h/2, gov_stats["parental_pct"], h, label="Parental Linkage Rate (% with Co-Registered Father)", color="#f59e0b", edgecolor="#d97706")

    ax.set_yticks(y)
    ax.set_yticklabels(gov_stats["gov_latin"], fontsize=9.5, fontweight="bold")
    ax.set_xlabel("Percentage of Registered Electorate (%)", fontsize=11, fontweight="bold")
    ax.set_xlim(0, 60)
    ax.set_title("Household Kinship Density Across Tunisia's 24 Governorates & Diaspora\nSibling Co-Presence vs. Co-Registered Father-Child Ties (2024 ISIE Registry)",
                 fontsize=13, fontweight="bold", pad=15)
    ax.grid(axis="x", linestyle="--", alpha=0.5)
    ax.legend(loc="lower right", frameon=True, facecolor="#ffffff", edgecolor="#cbd5e1", fontsize=10)

    # Annotate values
    for rect in b1:
        w = rect.get_width()
        if w > 0:
            ax.annotate(f"{w:.1f}%", xy=(w, rect.get_y() + rect.get_height()/2),
                        xytext=(4, 0), textcoords="offset points", ha="left", va="center", fontsize=8, color="#0369a1", fontweight="bold")

    plt.tight_layout()
    out_file = os.path.join(FIG_DIR, "intergenerational_co_presence_by_gov.png")
    plt.savefig(out_file, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Saved: {out_file}")


def plot_top_surnames_kinship():
    """Figure 4: Surnames with Highest Biological Kinship Density"""
    cliques_path = os.path.join(KINSHIP_DIR, "household_sibling_cliques.csv.gz")
    if not os.path.exists(cliques_path):
        return

    clique_counts = Counter()
    voter_counts = Counter()

    with gzip.open(cliques_path, "rt", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            sn_lat = r["surname_latin"]
            # Exclude non-surname prefixes if isolated
            if sn_lat.upper() in ("BEN", "IBN", "BENT", "OULD"):
                continue
            k = int(r["num_siblings"])
            clique_counts[sn_lat] += 1
            voter_counts[sn_lat] += k

    top20 = clique_counts.most_common(20)
    names = [t[0] for t in top20][::-1]
    c_vals = [t[1] for t in top20][::-1]
    v_vals = [voter_counts[n] for n in names]

    fig, ax = plt.subplots(figsize=(11, 8.5), dpi=300)
    fig.patch.set_facecolor("#ffffff")
    ax.set_facecolor("#f8fafc")

    y = np.arange(len(names))
    h = 0.4

    b1 = ax.barh(y + h/2, c_vals, h, label="Nuclear Sibling Cliques", color="#4f46e5", edgecolor="#3730a3")
    b2 = ax.barh(y - h/2, v_vals, h, label="Total Sibling Voters", color="#10b981", edgecolor="#059669")

    ax.set_yticks(y)
    ax.set_yticklabels(names, fontsize=10, fontweight="bold")
    ax.set_xlabel("Count", fontsize=11, fontweight="bold")
    ax.set_xlim(0, max(v_vals) * 1.14)
    ax.set_title("Top 20 Tunisian Surnames by Reconstructed Nuclear Sibling Households\n(Official 2024 ISIE Voter Registry)",
                 fontsize=13, fontweight="bold", pad=15)
    ax.grid(axis="x", linestyle="--", alpha=0.5)
    ax.legend(loc="lower right", frameon=True, facecolor="#ffffff", edgecolor="#cbd5e1", fontsize=10)

    for rect in b2:
        w = rect.get_width()
        ax.annotate(f"{w:,}", xy=(w, rect.get_y() + rect.get_height()/2),
                    xytext=(4, 0), textcoords="offset points", ha="left", va="center", fontsize=8.5, color="#065f46", fontweight="bold")

    plt.tight_layout()
    out_file = os.path.join(FIG_DIR, "top_surnames_kinship_density.png")
    plt.savefig(out_file, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Saved: {out_file}")


def main():
    print("Generating refined kinship figures with 100% Latin typography...")
    plot_pedigree_dag_samples()
    plot_sibling_size_distribution()
    plot_intergenerational_by_gov()
    plot_top_surnames_kinship()
    print("All refined kinship figures generated successfully!")


if __name__ == "__main__":
    main()
