#!/usr/bin/env python3
"""
Tunisian Family & Kinship Network Mapping Engine
================================================
Constructs a spatial co-occurrence kinship graph across Tunisia's 2,163 Imadas,
detects regional and tribal clan confederation clusters via Louvain modularity,
computes network centrality (bridging vs. core families), cross-links with
senior state elites, and outputs graph datasets and an interactive D3.js visualizer.
"""

import gzip
import csv
import json
import time
import os
from collections import defaultdict
import numpy as np
import scipy.sparse as sp
import networkx as nx
from networkx.algorithms.community import louvain_communities

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMADA_PATH = os.path.join(BASE_DIR, "data", "processed", "surnames_by_imada.csv.gz")
NETWORKS_DIR = os.path.join(BASE_DIR, "data", "processed", "networks")
ELITE_PERSONS_PATH = "/Users/mohameddhiahammami/.gemini/antigravity/scratch/EliteNetworksTN/data/processed/persons.csv.gz"

os.makedirs(NETWORKS_DIR, exist_ok=True)

print("=" * 70)
print("TUNISIAN KINSHIP NETWORK MAPPING ENGINE")
print("=" * 70)
start_time = time.time()

# -------------------------------------------------------------------------
# Step 1: Ingest & Filter Imada Data
# -------------------------------------------------------------------------
print("[1/5] Ingesting Imada dataset and indexing domestic surnames...")

surname_voters = defaultdict(int)
surname_top_imada = {}
surname_top_imada_max = defaultdict(int)
surname_gov_counts = defaultdict(lambda: defaultdict(int))
surname_raw_names = {}

with gzip.open(IMADA_PATH, "rt", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for r in reader:
        if r.get("is_diaspora") in ("1", "True", True):
            continue
        s_norm = r["surname_norm"]
        v = int(r["voter_count"])
        gov = r["governorate"]
        im = f"{gov} - {r['imada']}"
        
        surname_voters[s_norm] += v
        surname_gov_counts[s_norm][gov] += v
        surname_raw_names[s_norm] = r["surname"]
        
        if v > surname_top_imada_max[s_norm]:
            surname_top_imada_max[s_norm] = v
            surname_top_imada[s_norm] = im

# Filter to domestic surnames with >= 300 voters
SUBSTANTIAL_THRESHOLD = 300
surnames = sorted([s for s, v in surname_voters.items() if v >= SUBSTANTIAL_THRESHOLD])
s_idx = {s: i for i, s in enumerate(surnames)}
print(f"  -> Indexed {len(surnames):,} domestic surnames (>= {SUBSTANTIAL_THRESHOLD} voters).")
print(f"  -> Coverage: {sum(surname_voters[s] for s in surnames):,} voters.")

# -------------------------------------------------------------------------
# Step 2: Build Sparse Spatial Matrix & Pairwise Cosine Graph
# -------------------------------------------------------------------------
print("[2/5] Constructing sparse spatial matrix and computing cosine affinities...")

imada_ids = {}
rows, cols, data = [], [], []

with gzip.open(IMADA_PATH, "rt", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for r in reader:
        if r.get("is_diaspora") in ("1", "True", True):
            continue
        s_norm = r["surname_norm"]
        if s_norm not in s_idx:
            continue
        im_key = f"{r['governorate']}__{r['imada']}"
        if im_key not in imada_ids:
            imada_ids[im_key] = len(imada_ids)
        
        rows.append(s_idx[s_norm])
        cols.append(imada_ids[im_key])
        data.append(float(r["surname_share"]))

X = sp.csr_matrix((data, (rows, cols)), shape=(len(surnames), len(imada_ids)))
print(f"  -> Sparse matrix shape: {X.shape}, Non-zeros: {X.nnz:,}")

# Row normalization for cosine similarity
norms = sp.linalg.norm(X, axis=1)
norms[norms == 0] = 1.0
inv_norms = sp.diags(1.0 / np.array(norms).flatten())
X_norm = inv_norms.dot(X)

# Pairwise cosine similarity
Sim = X_norm.dot(X_norm.T).tocoo()

# Build NetworkX Graph
G = nx.Graph()
for s in surnames:
    gov = max(surname_gov_counts[s].items(), key=lambda x: x[1])[0]
    G.add_node(s,
               raw_name=surname_raw_names[s],
               voters=surname_voters[s],
               top_imada=surname_top_imada[s],
               top_gov=gov)

SIMILARITY_THRESHOLD = 0.45
for i, j, v in zip(Sim.row, Sim.col, Sim.data):
    if i < j and v >= SIMILARITY_THRESHOLD:
        G.add_edge(surnames[i], surnames[j], weight=float(v))

print(f"  -> Kinship graph built: {G.number_of_nodes():,} nodes, {G.number_of_edges():,} edges (threshold >= {SIMILARITY_THRESHOLD}).")

# -------------------------------------------------------------------------
# Step 3: Louvain Community Detection & Sociological Cluster Labeling
# -------------------------------------------------------------------------
print("[3/5] Detecting clan communities & assigning regional labels...")

communities = louvain_communities(G, weight="weight", seed=42)
sorted_comms = sorted(communities, key=len, reverse=True)
print(f"  -> Detected {len(sorted_comms)} kinship communities.")

def label_community(comm_surnames):
    gov_counts = defaultdict(int)
    for s in comm_surnames:
        gov_counts[G.nodes[s]["top_gov"]] += 1
    total_nodes = len(comm_surnames)
    top_gov, top_cnt = max(gov_counts.items(), key=lambda x: x[1])
    pct = (top_cnt / total_nodes) * 100

    # Regional groupings
    sahel_count = sum(gov_counts[g] for g in ["سوسة", "المنستير", "المهدية"])
    south_count = sum(gov_counts[g] for g in ["مدنين", "تطاوين", "قابس", "قبلي"])
    northwest_count = sum(gov_counts[g] for g in ["باجة", "جندوبة", "الكاف", "سليانة"])
    centerwest_count = sum(gov_counts[g] for g in ["القصرين", "سيدي بوزيد"])
    grand_tunis_count = sum(gov_counts[g] for g in ["تونس", "أريانة", "بن عروس", "منوبة"])

    if top_gov == "صفاقس" and pct >= 40:
        return "Sfaxian Lineages & Commercial Clans (صفاقس)"
    elif sahel_count / total_nodes >= 0.45:
        return "Sahel Coastal Kinship Network (الساحل: سوسة، المنستير، المهدية)"
    elif top_gov == "القيروان" and pct >= 35:
        return "Kairouan & Jlass Tribal Heartland (القيروان - جلاص)"
    elif centerwest_count / total_nodes >= 0.40:
        return "Central-West High Steppes (القصرين وسيدي بوزيد - فراشيش وهمامة)"
    elif northwest_count / total_nodes >= 0.40:
        return "Northwest Medjerda & Tellian Clans (الشمال الغربي - عمدون وعيار)"
    elif south_count / total_nodes >= 0.40:
        return "Southern Saharan & Maritime Clans (الجنوب - جربة وبني زيد ونفزاوة)"
    elif top_gov == "بنزرت" and pct >= 35:
        return "Bizerte & Mogods Northern Lineages (بنزرت والمقاعد)"
    elif top_gov == "نابل" and pct >= 35:
        return "Cap Bon Peninsula Lineages (الوطن القبلي - نابل)"
    elif grand_tunis_count / total_nodes >= 0.45:
        return "Greater Tunis & Peri-Urban Lineages (إقليم تونس الكبرى)"
    else:
        return f"{top_gov} Regional Clan Cluster"

node_community = {}
comm_metadata = []

for cid, comm in enumerate(sorted_comms):
    comm_id = cid + 1
    label = label_community(comm)
    tot_voters = sum(G.nodes[s]["voters"] for s in comm)
    top_surnames = sorted(comm, key=lambda s: G.nodes[s]["voters"], reverse=True)[:5]
    
    for s in comm:
        node_community[s] = (comm_id, label)
        
    comm_metadata.append({
        "community_id": comm_id,
        "community_label": label,
        "surname_count": len(comm),
        "total_voters": tot_voters,
        "top_surnames": ", ".join(top_surnames)
    })

# Centrality metrics
print("  -> Computing network centrality metrics (degree, pagerank, betweenness)...")
degrees = dict(G.degree())
weighted_degrees = dict(G.degree(weight="weight"))
pageranks = nx.pagerank(G, weight="weight")

# Fast betweenness on connected components or k-samples
betweenness = nx.betweenness_centrality(G, weight="weight", k=min(300, len(G)))

# -------------------------------------------------------------------------
# Step 4: Cross-Link with Senior State Elites (EliteNetworksTN)
# -------------------------------------------------------------------------
print("[4/5] Cross-linking with historical state elite registry...")

elite_surname_counts = defaultdict(int)
if os.path.exists(ELITE_PERSONS_PATH):
    with gzip.open(ELITE_PERSONS_PATH, "rt", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            name = r.get("name") or ""
            parts = name.strip().split()
            if parts:
                last_token = parts[-1].lower()
                elite_surname_counts[last_token] += 1
    print(f"  -> Loaded senior state appointees across {len(elite_surname_counts):,} Latin surname stems.")
else:
    print("  -> Elite persons dataset not found; skipping elite linkage.")

# -------------------------------------------------------------------------
# Step 5: Export Data Tables & Interactive D3 Visualizer
# -------------------------------------------------------------------------
print("[5/5] Exporting datasets and generating interactive visualizer...")

# A. Nodes CSV
nodes_out = os.path.join(NETWORKS_DIR, "kinship_nodes.csv.gz")
with gzip.open(nodes_out, "wt", encoding="utf-8", newline="") as f:
    writer = csv.writer(f)
    writer.writerow([
        "surname_norm", "surname_arabic", "community_id", "community_label",
        "national_voters", "top_governorate", "top_imada",
        "degree", "weighted_degree", "betweenness_centrality", "pagerank"
    ])
    for s in surnames:
        cid, clabel = node_community.get(s, (0, "Unassigned"))
        writer.writerow([
            s,
            G.nodes[s]["raw_name"],
            cid,
            clabel,
            G.nodes[s]["voters"],
            G.nodes[s]["top_gov"],
            G.nodes[s]["top_imada"],
            degrees.get(s, 0),
            round(weighted_degrees.get(s, 0.0), 3),
            round(betweenness.get(s, 0.0), 6),
            round(pageranks.get(s, 0.0), 6)
        ])
print(f"  -> Saved nodes table: {nodes_out}")

# B. Edges CSV
edges_out = os.path.join(NETWORKS_DIR, "kinship_edges.csv.gz")
with gzip.open(edges_out, "wt", encoding="utf-8", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["source", "target", "similarity_weight", "source_community", "target_community", "is_intra_community"])
    for u, v, d in G.edges(data=True):
        c_u = node_community.get(u, (0, ""))[0]
        c_v = node_community.get(v, (0, ""))[0]
        writer.writerow([
            u, v, round(d["weight"], 4), c_u, c_v, int(c_u == c_v)
        ])
print(f"  -> Saved edges table: {edges_out}")

# C. Community Summary CSV
comm_out = os.path.join(NETWORKS_DIR, "community_summary.csv")
with open(comm_out, "w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["community_id", "community_label", "surname_count", "total_voters", "top_surnames"])
    writer.writeheader()
    writer.writerows(comm_metadata[:25])
print(f"  -> Saved community summary: {comm_out}")

# D. GEXF Export (for Gephi)
gexf_out = os.path.join(NETWORKS_DIR, "kinship_network.gexf")
nx.set_node_attributes(G, {s: node_community[s][0] for s in G.nodes()}, "community_id")
nx.set_node_attributes(G, {s: node_community[s][1] for s in G.nodes()}, "community_label")
nx.write_gexf(G, gexf_out)
print(f"  -> Saved Gephi GEXF file: {gexf_out}")

# E. Generate Standalone Interactive D3.js Network HTML
print("  -> Generating interactive HTML network viewer...")

# Filter graph for visualization: top 600 nodes with highest degrees & their edges
top_vis_nodes = set(sorted(G.nodes(), key=lambda s: degrees.get(s, 0), reverse=True)[:500])
subG = G.subgraph(top_vis_nodes)

nodes_json = []
for s in subG.nodes():
    cid, clabel = node_community[s]
    nodes_json.append({
        "id": s,
        "name": G.nodes[s]["raw_name"],
        "voters": G.nodes[s]["voters"],
        "gov": G.nodes[s]["top_gov"],
        "imada": G.nodes[s]["top_imada"],
        "community": cid,
        "label": clabel,
        "degree": degrees[s]
    })

edges_json = []
for u, v, d in subG.edges(data=True):
    edges_json.append({
        "source": u,
        "target": v,
        "weight": round(d["weight"], 3)
    })

vis_data = json.dumps({"nodes": nodes_json, "links": edges_json}, ensure_ascii=False)

html_template = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Tunisian Kinship & Clan Networks Explorer (2024)</title>
<script src="https://d3js.org/d3.v7.min.js"></script>
<style>
  body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #f8fafc; overflow: hidden; }}
  #header {{ position: absolute; top: 16px; left: 16px; z-index: 10; background: rgba(15, 23, 42, 0.85); backdrop-filter: blur(8px); padding: 16px 20px; border-radius: 12px; border: 1px solid #334155; max-width: 420px; }}
  h1 {{ margin: 0 0 6px 0; font-size: 18px; font-weight: 700; color: #38bdf8; }}
  p {{ margin: 0 0 10px 0; font-size: 12px; color: #94a3b8; line-height: 1.4; }}
  .search-box {{ width: 100%; padding: 8px 12px; border-radius: 6px; border: 1px solid #475569; background: #1e293b; color: #f8fafc; font-size: 13px; box-sizing: border-box; }}
  .search-box:focus {{ outline: none; border-color: #38bdf8; }}
  #stats {{ font-size: 11px; color: #64748b; margin-top: 8px; }}
  #tooltip {{ position: absolute; display: none; background: rgba(15, 23, 42, 0.95); border: 1px solid #38bdf8; border-radius: 8px; padding: 12px; font-size: 12px; pointer-events: none; z-index: 20; max-width: 280px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }}
  .tooltip-title {{ font-size: 15px; font-weight: bold; color: #38bdf8; margin-bottom: 4px; }}
  .tooltip-row {{ margin: 3px 0; color: #cbd5e1; }}
  .tooltip-label {{ color: #94a3b8; font-size: 11px; }}
  svg {{ width: 100vw; height: 100vh; cursor: grab; }}
  svg:active {{ cursor: grabbing; }}
  .link {{ stroke-opacity: 0.35; transition: stroke-opacity 0.2s; }}
  .node circle {{ stroke: #0f172a; stroke-width: 1.5px; transition: transform 0.2s, stroke-width 0.2s; }}
  .node text {{ font-size: 10px; fill: #e2e8f0; pointer-events: none; text-shadow: 0 1px 3px rgba(0,0,0,0.9); }}
</style>
</head>
<body>

<div id="header">
  <h1>Tunisian Kinship & Clan Networks</h1>
  <p>Spatial co-occurrence graph across 2,163 Imadas from the 2024 ISIE Voter Registry. Nodes represent family surnames; links connect kin groups co-concentrated in the same localities.</p>
  <input type="text" id="search" class="search-box" placeholder="Search surname (e.g. الزواري, كمون, مسعودي)..." />
  <div id="stats">Displaying top 500 core lineage hubs and kinship ties</div>
</div>

<div id="tooltip"></div>
<svg id="network"></svg>

<script>
const data = {vis_data};

const width = window.innerWidth;
const height = window.innerHeight;

const svg = d3.select("#network")
  .attr("viewBox", [-width / 2, -height / 2, width, height]);

const g = svg.append("g");

// Zoom & Pan
const zoom = d3.zoom()
  .scaleExtent([0.15, 6])
  .on("zoom", (event) => g.attr("transform", event.transform));
svg.call(zoom);

// Color Palette by Community
const colorPalette = [
  "#38bdf8", "#f43f5e", "#10b981", "#fbbf24", "#a855f7",
  "#f97316", "#06b6d4", "#ec4899", "#84cc16", "#6366f1",
  "#14b8a6", "#e11d48", "#8b5cf6", "#d97706", "#22c55e"
];
const color = (cid) => colorPalette[(cid - 1) % colorPalette.length];

// Force Simulation
const simulation = d3.forceSimulation(data.nodes)
  .force("link", d3.forceLink(data.links).id(d => d.id).distance(d => 120 * (1.1 - d.weight)).strength(0.6))
  .force("charge", d3.forceManyBody().strength(-180))
  .force("center", d3.forceCenter(0, 0))
  .force("collision", d3.forceCollide().radius(d => Math.sqrt(d.voters) * 0.12 + 6));

// Links
const link = g.append("g")
  .selectAll("line")
  .data(data.links)
  .join("line")
  .attr("class", "link")
  .attr("stroke", "#475569")
  .attr("stroke-width", d => Math.max(1, d.weight * 3));

// Nodes
const node = g.append("g")
  .selectAll(".node")
  .data(data.nodes)
  .join("g")
  .attr("class", "node")
  .call(d3.drag()
    .on("start", dragstarted)
    .on("drag", dragged)
    .on("end", dragended));

node.append("circle")
  .attr("r", d => Math.max(4.5, Math.min(22, Math.sqrt(d.voters) * 0.12)))
  .attr("fill", d => color(d.community));

node.append("text")
  .attr("dx", d => Math.max(4.5, Math.sqrt(d.voters) * 0.12) + 4)
  .attr("dy", 3)
  .text(d => d.name);

// Tooltip
const tooltip = d3.select("#tooltip");

node.on("mouseover", (event, d) => {{
  tooltip.style("display", "block")
    .html(`
      <div class="tooltip-title">${{d.name}} (${{d.id}})</div>
      <div class="tooltip-row"><span class="tooltip-label">Registered Voters:</span> <b>${{d.voters.toLocaleString()}}</b></div>
      <div class="tooltip-row"><span class="tooltip-label">Clan Cluster:</span> ${{d.label}}</div>
      <div class="tooltip-row"><span class="tooltip-label">Dominant Governorate:</span> ${{d.gov}}</div>
      <div class="tooltip-row"><span class="tooltip-label">Top Imada:</span> ${{d.imada}}</div>
      <div class="tooltip-row"><span class="tooltip-label">Allied Kin Surnames:</span> ${{d.degree}}</div>
    `);
  
  // Highlight connected
  link.attr("stroke-opacity", l => (l.source.id === d.id || l.target.id === d.id) ? 0.9 : 0.08)
      .attr("stroke", l => (l.source.id === d.id || l.target.id === d.id) ? "#38bdf8" : "#475569");
}})
.on("mousemove", (event) => {{
  tooltip.style("left", (event.pageX + 15) + "px").style("top", (event.pageY - 25) + "px");
}})
.on("mouseout", () => {{
  tooltip.style("display", "none");
  link.attr("stroke-opacity", 0.35).attr("stroke", "#475569");
}});

// Search highlight
d3.select("#search").on("input", function() {{
  const query = this.value.trim().toLowerCase();
  if (!query) {{
    node.select("circle").attr("opacity", 1).attr("stroke-width", 1.5);
    node.select("text").attr("opacity", 1);
    link.attr("stroke-opacity", 0.35);
    return;
  }}
  node.select("circle")
    .attr("opacity", d => (d.name.includes(query) || d.id.includes(query) || d.label.includes(query)) ? 1 : 0.15)
    .attr("stroke", d => (d.name.includes(query) || d.id.includes(query)) ? "#fff" : "#0f172a")
    .attr("stroke-width", d => (d.name.includes(query) || d.id.includes(query)) ? 3 : 1.5);
  
  node.select("text")
    .attr("opacity", d => (d.name.includes(query) || d.id.includes(query)) ? 1 : 0.2);
}});

// Simulation Tick
simulation.on("tick", () => {{
  link
    .attr("x1", d => d.source.x)
    .attr("y1", d => d.source.y)
    .attr("x2", d => d.target.x)
    .attr("y2", d => d.target.y);

  node.attr("transform", d => `translate(${{d.x}},${{d.y}})`);
}});

function dragstarted(event, d) {{
  if (!event.active) simulation.alphaTarget(0.3).restart();
  d.fx = d.x;
  d.fy = d.y;
}}

function dragged(event, d) {{
  d.fx = event.x;
  d.fy = event.y;
}}

function dragended(event, d) {{
  if (!event.active) simulation.alphaTarget(0);
  d.fx = null;
  d.fy = null;
}}
</script>
</body>
</html>
"""

html_out = os.path.join(NETWORKS_DIR, "interactive_family_network.html")
with open(html_out, "w", encoding="utf-8") as f:
    f.write(html_template)
print(f"  -> Saved interactive network visualization: {html_out}")

print(f"\nCompleted in {time.time() - start_time:.2f} seconds!")
print("=" * 70)
