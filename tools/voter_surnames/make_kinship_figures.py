#!/usr/bin/env python3
"""
Generate publication-grade PNG and PDF figures for the Tunisian Kinship & Family Networks.
"""

import os
import sys
import gzip
import csv
from collections import defaultdict
import numpy as np

# Set writable matplotlib cache dir
os.environ["MPLCONFIGDIR"] = "/tmp/mpl_config"

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.lines import Line2D
import networkx as nx

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NETWORKS_DIR = os.path.join(BASE_DIR, "data", "voter_surnames_2024", "networks")
DOCS_FIG_DIR = os.path.join(BASE_DIR, "docs", "figures")
os.makedirs(DOCS_FIG_DIR, exist_ok=True)
os.makedirs(NETWORKS_DIR, exist_ok=True)

# Transliteration helper if available
sys.path.insert(0, os.path.join(BASE_DIR, "tools"))
try:
    from arabic_translit import transliterate
except ImportError:
    def transliterate(s):
        return s

# Styling constants
BG_COLOR = "#0f172a"      # Deep slate navy
TEXT_LIGHT = "#f8fafc"
TEXT_MUTED = "#94a3b8"
TEXT_ACCENT = "#38bdf8"
GRID_COLOR = "#334155"

# Palette for the primary communities
COMMUNITY_PALETTE = {
    1: ("#38bdf8", "Sahel Coastal Network"),
    2: ("#f43f5e", "Sfaxian Commercial & Urban Clans"),
    3: ("#10b981", "Southern Maritime (Gabes/Medenine)"),
    4: ("#fbbf24", "Central-West Steppes (Fraichiche/Hammama)"),
    5: ("#a855f7", "Southern Saharan (Nefzaoua/Beni Zid)"),
    6: ("#06b6d4", "Bizerte & Mogods Northern Lineages"),
    7: ("#ec4899", "Kairouan & Jlass Heartland"),
    8: ("#84cc16", "Northwest Medjerda & Tellian Clans"),
    10: ("#f97316", "Northwest High Plains (Ouled Ayar)")
}
DEFAULT_COLOR = "#64748b"

print("=" * 70)
print("GENERATING KINSHIP NETWORK PNG FIGURES")
print("=" * 70)

# -------------------------------------------------------------------------
# Load Node and Edge Data
# -------------------------------------------------------------------------
nodes_path = os.path.join(NETWORKS_DIR, "kinship_nodes.csv.gz")
edges_path = os.path.join(NETWORKS_DIR, "kinship_edges.csv.gz")

nodes = {}
with gzip.open(nodes_path, "rt", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        s = r["surname_norm"]
        nodes[s] = {
            "name": r["surname_arabic"],
            "cid": int(r["community_id"]),
            "clabel": r["community_label"],
            "voters": int(r["national_voters"]),
            "gov": r["top_governorate"],
            "imada": r["top_imada"],
            "degree": int(r["degree"]),
            "weighted_degree": float(r["weighted_degree"]),
            "betweenness": float(r["betweenness_centrality"]),
            "pagerank": float(r["pagerank"])
        }

G = nx.Graph()
for s, d in nodes.items():
    G.add_node(s, **d)

with gzip.open(edges_path, "rt", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        u, v = r["source"], r["target"]
        if u in nodes and v in nodes:
            G.add_edge(u, v, weight=float(r["similarity_weight"]))

print(f"Loaded graph: {G.number_of_nodes():,} nodes, {G.number_of_edges():,} edges.")

# -------------------------------------------------------------------------
# Figure 1: Nationwide Kinship Network Overview
# -------------------------------------------------------------------------
print("[1/4] Generating Figure 1: Kinship Network Overview...")

# Filter to top core components / nodes with degree >= 3 for clean layout
core_nodes = [n for n, d in G.nodes(data=True) if d["degree"] >= 4]
subG = G.subgraph(core_nodes)

# Compute layout
pos = nx.spring_layout(subG, weight="weight", k=0.18, iterations=70, seed=42)

fig, ax = plt.subplots(figsize=(16, 12), facecolor=BG_COLOR)
ax.set_facecolor(BG_COLOR)

# Draw edges
edge_weights = [d["weight"] for _, _, d in subG.edges(data=True)]
nx.draw_networkx_edges(
    subG, pos, ax=ax,
    alpha=0.15,
    width=0.8,
    edge_color="#475569"
)

# Draw nodes by community
for cid, (color, label) in COMMUNITY_PALETTE.items():
    comm_nodes = [n for n, d in subG.nodes(data=True) if d["cid"] == cid]
    if not comm_nodes:
        continue
    sizes = [np.clip(np.sqrt(subG.nodes[n]["voters"]) * 2.2, 20, 320) for n in comm_nodes]
    nx.draw_networkx_nodes(
        subG, pos, nodelist=comm_nodes, ax=ax,
        node_color=color, node_size=sizes, alpha=0.85,
        edgecolors="#0f172a", linewidths=0.6, label=label
    )

# Other smaller communities
other_nodes = [n for n, d in subG.nodes(data=True) if d["cid"] not in COMMUNITY_PALETTE]
if other_nodes:
    sizes = [np.clip(np.sqrt(subG.nodes[n]["voters"]) * 2.2, 15, 200) for n in other_nodes]
    nx.draw_networkx_nodes(
        subG, pos, nodelist=other_nodes, ax=ax,
        node_color=DEFAULT_COLOR, node_size=sizes, alpha=0.4,
        edgecolors="#0f172a", linewidths=0.5, label="Other Localized Lineages"
    )

# Label prominent hubs (top 35 by degree/voters)
labeled_nodes = sorted(subG.nodes(), key=lambda n: subG.nodes[n]["degree"] * np.log10(subG.nodes[n]["voters"]), reverse=True)[:35]
for n in labeled_nodes:
    x, y = pos[n]
    name_ar = subG.nodes[n]["name"]
    name_lat = transliterate(n)
    lbl = f"{name_ar} ({name_lat})" if name_lat != name_ar else name_ar
    ax.text(
        x, y + 0.015, lbl,
        fontsize=8.5, fontweight="bold", color=TEXT_LIGHT,
        ha="center", va="bottom",
        bbox=dict(boxstyle="round,pad=0.2", facecolor="#1e293b", edgecolor="#475569", alpha=0.85)
    )

# Title & Subtitle
ax.text(
    0.03, 0.96, "Tunisian Kinship & Clan Co-Occurrence Network (2024)",
    transform=ax.transAxes, fontsize=18, fontweight="bold", color=TEXT_ACCENT, va="top"
)
ax.text(
    0.03, 0.93, "Spatial affinities across 2,163 Imadas based on the official ISIE voter registry | 7.8M voters indexed",
    transform=ax.transAxes, fontsize=11, color=TEXT_MUTED, va="top"
)

# Legend
legend = ax.legend(
    loc="lower right", facecolor="#1e293b", edgecolor="#334155",
    fontsize=9, labelcolor=TEXT_LIGHT, framealpha=0.9, title="Sociological Clan Clusters",
    title_fontsize=10
)
legend.get_title().set_color(TEXT_ACCENT)

ax.axis("off")
plt.tight_layout()

f1_png = os.path.join(DOCS_FIG_DIR, "kinship_network_overview.png")
f1_net_png = os.path.join(NETWORKS_DIR, "kinship_network_overview.png")
plt.savefig(f1_png, dpi=300, bbox_inches="tight", facecolor=BG_COLOR)
plt.savefig(f1_net_png, dpi=300, bbox_inches="tight", facecolor=BG_COLOR)
plt.close()
print(f"  -> Saved: {f1_png}")

# -------------------------------------------------------------------------
# Figure 2: The Sfaxian Commercial & Urban Clan Core
# -------------------------------------------------------------------------
print("[2/4] Generating Figure 2: Sfaxian Clan Core Network...")

sfax_nodes = [n for n, d in G.nodes(data=True) if d["cid"] == 2]
sfaxG = G.subgraph(sfax_nodes)

fig, ax = plt.subplots(figsize=(14, 11), facecolor=BG_COLOR)
ax.set_facecolor(BG_COLOR)

pos_sfax = nx.spring_layout(sfaxG, weight="weight", k=0.25, iterations=80, seed=123)

# Edges colored by weight
edges, weights = zip(*nx.get_edge_attributes(sfaxG, "weight").items())
nx.draw_networkx_edges(
    sfaxG, pos_sfax, ax=ax,
    alpha=0.35, width=[w * 3.5 for w in weights],
    edge_color="#f43f5e"
)

sizes = [np.clip(np.sqrt(sfaxG.nodes[n]["voters"]) * 4.5, 50, 600) for n in sfaxG.nodes()]
nx.draw_networkx_nodes(
    sfaxG, pos_sfax, ax=ax,
    node_color="#f43f5e", node_size=sizes, alpha=0.9,
    edgecolors="#ffffff", linewidths=1.2
)

# Label all Sfaxian nodes with >= 1000 voters or top degrees
for n in sfaxG.nodes():
    d = sfaxG.nodes[n]
    if d["voters"] >= 1200 or d["degree"] >= 90:
        x, y = pos_sfax[n]
        name_ar = d["name"]
        name_lat = transliterate(n)
        lbl = f"{name_ar}\n({name_lat})"
        ax.text(
            x, y, lbl,
            fontsize=8, fontweight="bold", color="#ffffff",
            ha="center", va="center",
            bbox=dict(boxstyle="round,pad=0.25", facecolor="#1e293b", edgecolor="#f43f5e", alpha=0.9)
        )

ax.text(
    0.04, 0.95, "The Sfaxian Commercial & Urban Clan Network",
    transform=ax.transAxes, fontsize=17, fontweight="bold", color="#f43f5e", va="top"
)
ax.text(
    0.04, 0.915, "126 tightly endogamous surnames | 213,972 registered voters | Highest network density in Tunisia",
    transform=ax.transAxes, fontsize=10.5, color=TEXT_MUTED, va="top"
)

ax.axis("off")
plt.tight_layout()

f2_png = os.path.join(DOCS_FIG_DIR, "kinship_network_sfax_core.png")
f2_net_png = os.path.join(NETWORKS_DIR, "kinship_network_sfax_core.png")
plt.savefig(f2_png, dpi=300, bbox_inches="tight", facecolor=BG_COLOR)
plt.savefig(f2_net_png, dpi=300, bbox_inches="tight", facecolor=BG_COLOR)
plt.close()
print(f"  -> Saved: {f2_png}")

# -------------------------------------------------------------------------
# Figure 3: Regional Clan Networks (Multi-Panel Comparison)
# -------------------------------------------------------------------------
print("[3/4] Generating Figure 3: Regional Multi-Panel Comparison...")

target_comms = [
    (2, "Sfaxian Urban Network", "#f43f5e"),
    (1, "Sahel Coastal Network", "#38bdf8"),
    (4, "Central-West (Fraichiche/Hammama)", "#fbbf24"),
    (7, "Kairouan & Jlass Heartland", "#ec4899"),
    (8, "Northwest Tellian & Medjerda", "#84cc16"),
    (5, "Southern Saharan (Nefzaoua/Djerba)", "#a855f7")
]

fig, axes = plt.subplots(2, 3, figsize=(18, 12), facecolor=BG_COLOR)
axes = axes.flatten()

for idx, (cid, title, col) in enumerate(target_comms):
    ax = axes[idx]
    ax.set_facecolor("#1e293b")
    
    comm_nodes = [n for n, d in G.nodes(data=True) if d["cid"] == cid]
    sub = G.subgraph(comm_nodes)
    
    if len(sub) > 0:
        p = nx.spring_layout(sub, weight="weight", k=0.3, iterations=50, seed=42)
        nx.draw_networkx_edges(sub, p, ax=ax, alpha=0.25, width=1.0, edge_color=col)
        nsizes = [np.clip(np.sqrt(sub.nodes[n]["voters"]) * 3.0, 30, 400) for n in sub.nodes()]
        nx.draw_networkx_nodes(sub, p, ax=ax, node_color=col, node_size=nsizes, alpha=0.85, edgecolors="#0f172a")
        
        # Label top 4 anchor surnames
        top4 = sorted(sub.nodes(), key=lambda n: sub.nodes[n]["voters"], reverse=True)[:4]
        for tn in top4:
            x, y = p[tn]
            name_ar = sub.nodes[tn]["name"]
            ax.text(x, y + 0.04, name_ar, fontsize=8, fontweight="bold", color="#ffffff", ha="center",
                    bbox=dict(boxstyle="round,pad=0.15", facecolor=BG_COLOR, edgecolor=col, alpha=0.85))
            
    tot_v = sum(G.nodes[n]["voters"] for n in comm_nodes)
    ax.set_title(f"{title}\n({len(comm_nodes)} families | {tot_v:,} voters)", fontsize=11, fontweight="bold", color=col, pad=8)
    ax.axis("off")

plt.suptitle("Regional Clan & Kinship Subgraphs Across Tunisia", fontsize=16, fontweight="bold", color=TEXT_ACCENT, y=0.98)
plt.tight_layout()

f3_png = os.path.join(DOCS_FIG_DIR, "kinship_regional_multi_panel.png")
f3_net_png = os.path.join(NETWORKS_DIR, "kinship_regional_multi_panel.png")
plt.savefig(f3_png, dpi=300, bbox_inches="tight", facecolor=BG_COLOR)
plt.savefig(f3_net_png, dpi=300, bbox_inches="tight", facecolor=BG_COLOR)
plt.close()
print(f"  -> Saved: {f3_png}")

# -------------------------------------------------------------------------
# Figure 4: Centrality Distribution: Bridge Families vs. Clan Hubs
# -------------------------------------------------------------------------
print("[4/4] Generating Figure 4: Centrality Scatter & Bridge Families...")

fig, ax = plt.subplots(figsize=(13, 9), facecolor=BG_COLOR)
ax.set_facecolor("#1e293b")

degrees_list = [d["degree"] for _, d in G.nodes(data=True)]
betweenness_list = [d["betweenness"] for _, d in G.nodes(data=True)]
voters_list = [d["voters"] for _, d in G.nodes(data=True)]
cids = [d["cid"] for _, d in G.nodes(data=True)]
node_names = list(G.nodes())

colors = [COMMUNITY_PALETTE.get(c, (DEFAULT_COLOR, ""))[0] for c in cids]

scatter = ax.scatter(
    degrees_list, betweenness_list,
    s=[np.clip(np.sqrt(v) * 1.8, 15, 350) for v in voters_list],
    c=colors, alpha=0.75, edgecolors="#0f172a", linewidth=0.6
)

# Label top bridge families (high betweenness)
bridge_nodes = sorted(G.nodes(), key=lambda n: G.nodes[n]["betweenness"], reverse=True)[:8]
for bn in bridge_nodes:
    d = G.nodes[bn]
    x, y = d["degree"], d["betweenness"]
    lbl = f"{d['name']} ({transliterate(bn)})"
    ax.annotate(
        lbl, (x, y), xytext=(x + 2, y + 0.0012),
        fontsize=8.5, fontweight="bold", color="#38bdf8",
        arrowprops=dict(arrowstyle="->", color="#38bdf8", lw=0.8),
        bbox=dict(boxstyle="round,pad=0.2", facecolor=BG_COLOR, edgecolor="#38bdf8", alpha=0.9)
    )

# Label top degree clan hubs
hub_nodes = sorted(G.nodes(), key=lambda n: G.nodes[n]["degree"], reverse=True)[:5]
for hn in hub_nodes:
    d = G.nodes[hn]
    x, y = d["degree"], d["betweenness"]
    lbl = f"{d['name']} ({transliterate(hn)})"
    ax.annotate(
        lbl, (x, y), xytext=(x - 18, y + 0.0018),
        fontsize=8.5, fontweight="bold", color="#f43f5e",
        arrowprops=dict(arrowstyle="->", color="#f43f5e", lw=0.8),
        bbox=dict(boxstyle="round,pad=0.2", facecolor=BG_COLOR, edgecolor="#f43f5e", alpha=0.9)
    )

ax.set_xlabel("Degree Centrality (Number of Co-localized Allied Families)", fontsize=11, color=TEXT_LIGHT, labelpad=10)
ax.set_ylabel("Betweenness Centrality (Inter-Regional Bridge Score)", fontsize=11, color=TEXT_LIGHT, labelpad=10)
ax.set_title("Tunisian Family Centrality: Inter-Regional Bridge Families vs. Dense Clan Hubs",
             fontsize=14, fontweight="bold", color=TEXT_ACCENT, pad=15)

ax.grid(True, linestyle="--", alpha=0.2, color=GRID_COLOR)
ax.tick_params(colors=TEXT_MUTED)
for spine in ax.spines.values():
    spine.set_color(GRID_COLOR)

# Annotations explaining the quadrants
ax.text(0.03, 0.92, "High Betweenness (Bridge Families):\nConnecting distinct geographic corridors",
        transform=ax.transAxes, fontsize=9.5, color="#38bdf8", bbox=dict(boxstyle="round", facecolor=BG_COLOR, alpha=0.8))
ax.text(0.70, 0.20, "High Degree (Clan Hubs):\nDense, cohesive local alliances (e.g. Sfax)",
        transform=ax.transAxes, fontsize=9.5, color="#f43f5e", bbox=dict(boxstyle="round", facecolor=BG_COLOR, alpha=0.8))

plt.tight_layout()

f4_png = os.path.join(DOCS_FIG_DIR, "kinship_centrality_distribution.png")
f4_net_png = os.path.join(NETWORKS_DIR, "kinship_centrality_distribution.png")
plt.savefig(f4_png, dpi=300, bbox_inches="tight", facecolor=BG_COLOR)
plt.savefig(f4_net_png, dpi=300, bbox_inches="tight", facecolor=BG_COLOR)
plt.close()
print(f"  -> Saved: {f4_png}")

print("\nAll 4 publication PNG figures generated successfully!")
print("=" * 70)
