#!/usr/bin/env python3
"""
Nationwide Biological Kinship Extraction Engine (2024 ISIE Registry)
====================================================================
Parses the official ISIE voter lists across all 2,163 PDFs to reconstruct:
1. Horizontal Sibling Cliques (brothers & sisters in nuclear households)
2. Vertical Parental Ties (directed Father -> Child pedigree links)
3. Imada-level household demographic statistics
"""

import os
import sys
import time
import gzip
import csv
import re
from pathlib import Path
from collections import defaultdict, Counter
from multiprocessing import Pool, cpu_count

import pypdfium2 as pdfium

# Add project root to sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(BASE_DIR, "tools"))
sys.path.insert(0, "/Users/mohameddhiahammami/.gemini/antigravity/scratch/TunisiaVoterSurnames")

from src.parser import parse_tunisian_surname, normalize_arabic, parse_voter_line
from src.extractor import assemble_voter_lines

try:
    from arabic_translit import translit
except ImportError:
    def translit(s):
        return s

# Common Latin spellings
CURATED_LATIN = {
    "الطرابلسي": "Trabelsi", "الدريدي": "Dridi", "الهمامي": "Hammami", "بن محمد": "Ben Mohamed",
    "الجلاصي": "Jlassi", "الماجري": "Mejri", "بن علي": "Ben Ali", "العبيدي": "Abidi",
    "الرياحي": "Riahi", "العياري": "Ayari", "الجبالي": "Jebali", "الغربي": "Gharbi",
    "بن صالح": "Ben Salah", "بن احمد": "Ben Ahmed", "المثلوثي": "Mathlouthi", "الزواري": "Zouari",
    "العكرمي": "Akremi", "البجاوي": "Bejaoui", "المرزوقي": "Marzouki", "غربال": "Ghorbel",
    "الهنتاتي": "Hentati", "الحشيشة": "Hachicha", "قوبعة": "Koubaa", "الفخفاخ": "Fakhfakh",
    "المصمودي": "Masmoudi", "الطريقي": "Triki", "اللوز": "Ellouze", "العش": "El Euch",
    "عبدالناظر": "Abdennadher", "العمدوني": "Amdouni", "رويس": "Rouis", "بسباس": "Besbes",
    "الزيتوني": "Ezzitouni", "مسعودي": "Messaoudi", "خضراوي": "Khadhraoui", "الحامدي": "Hamdi",
    "بوعلي": "Bouali", "سعيدي": "Saidi", "سلطاني": "Soltani", "سعيداني": "Saidani"
}

def to_latin(name):
    c = name.strip()
    if c in CURATED_LATIN:
        return CURATED_LATIN[c]
    if c.startswith("ال") and c[2:] in CURATED_LATIN:
        return CURATED_LATIN[c[2:]]
    res = translit(c)
    return res if res else c

def extract_patronymic_tokens(patronymic):
    tokens = [t for t in patronymic.split() if t not in ('بن', 'ابن', 'بنت')]
    father = tokens[0] if tokens else ''
    gf = ' '.join(tokens[1:]) if len(tokens) > 1 else ''
    return father, gf


def process_single_pdf(row):
    """
    Worker function to process one PDF and extract sibling cliques & parental ties.
    """
    pdf_path = row["pdf_path"]
    gov = row["governorate"]
    constituency = row["constituency"]
    imada = row["imada"]

    if not os.path.exists(pdf_path):
        return None

    try:
        doc = pdfium.PdfDocument(pdf_path)
    except Exception:
        return None

    num_pages = len(doc)
    if num_pages <= 1:
        return None

    raw_voters = []
    
    for p in range(1, num_pages):
        try:
            raw_lines = doc[p].get_textpage().get_text_range().split('\n')
        except Exception:
            continue
            
        v_lines = assemble_voter_lines(raw_lines)
        std_lines = []
        inv_lines = []
        
        for l in v_lines:
            w = l.split()
            if not w:
                continue
            if w[0].isdigit() and len(w[0]) <= 5:
                std_lines.append((w[0], ' '.join(w[1:])))
            elif w[-1].isdigit() and len(w[-1]) <= 5:
                inv_lines.append((w[-1], ' '.join(w[:-1])))

        # Find best trailing facility suffix
        best_suffix = None
        if len(std_lines) >= 3:
            suffixes = Counter()
            for cin, rest in std_lines:
                words = rest.split()
                for n in range(2, min(15, len(words))):
                    suffixes[' '.join(words[-n:])] += 1
            qualifying = [s for s, c in suffixes.items() if c >= len(std_lines) * 0.4]
            if qualifying:
                best_suffix = max(qualifying, key=lambda s: (len(s.split()), suffixes[s]))

        for cin, rest in std_lines:
            if best_suffix and rest.endswith(best_suffix):
                name = rest[:-len(best_suffix)].strip()
                center = best_suffix
            else:
                parsed = parse_voter_line(f"{cin} {rest}")
                name = parsed[1] if parsed else rest
                center = parsed[2] if parsed else ""

            fn, pat, sn, sn_norm = parse_tunisian_surname(name)
            fa, gf = extract_patronymic_tokens(pat)
            if fn and sn_norm:
                raw_voters.append({
                    "cin": cin,
                    "first": fn,
                    "first_norm": normalize_arabic(fn),
                    "father": fa,
                    "father_norm": normalize_arabic(fa),
                    "gf": gf,
                    "gf_norm": normalize_arabic(gf),
                    "surname": sn,
                    "surname_norm": sn_norm,
                    "center": center
                })

        # Inverted lines (diaspora / passport)
        for cin, rest in inv_lines:
            parsed = parse_voter_line(f"{cin} {rest}")
            name = parsed[1] if parsed else rest
            center = parsed[2] if parsed else ""
            fn, pat, sn, sn_norm = parse_tunisian_surname(name)
            fa, gf = extract_patronymic_tokens(pat)
            if fn and sn_norm:
                raw_voters.append({
                    "cin": cin,
                    "first": fn,
                    "first_norm": normalize_arabic(fn),
                    "father": fa,
                    "father_norm": normalize_arabic(fa),
                    "gf": gf,
                    "gf_norm": normalize_arabic(gf),
                    "surname": sn,
                    "surname_norm": sn_norm,
                    "center": center
                })

    total_voters = len(raw_voters)
    if total_voters == 0:
        return None

    # Deduplicate exact identical lines if any
    voters = list({(v["cin"], v["first_norm"], v["father_norm"], v["gf_norm"], v["surname_norm"], v["center"]): v for v in raw_voters}.values())

    # -------------------------------------------------------------
    # Adult Men lookup dictionary
    # -------------------------------------------------------------
    men_by_key = defaultdict(list)
    for v in voters:
        men_by_key[(v["first_norm"], v["father_norm"], v["surname_norm"], v["center"])].append(v)

    # -------------------------------------------------------------
    # 1. Reconstruct Sibling Cliques
    # -------------------------------------------------------------
    cliques_dict = defaultdict(list)
    for v in voters:
        if v["father_norm"] and v["gf_norm"]:
            key = (v["surname_norm"], v["father_norm"], v["gf_norm"], v["center"])
            cliques_dict[key].append(v)

    sibling_cliques = []
    sibling_voters_count = 0
    max_sibling_size = 0
    clique_membership = {}  # voter_tuple -> local_clique_idx

    for key, members in cliques_dict.items():
        if len(members) >= 2:
            count = len(members)
            sibling_voters_count += count
            if count > max_sibling_size:
                max_sibling_size = count

            sn_norm, fa_norm, gf_norm, center = key
            sn_raw = members[0]["surname"]
            fa_raw = members[0]["father"]
            gf_raw = members[0]["gf"]
            
            names_ar = ", ".join(m["first"] for m in members)
            names_lat = ", ".join(to_latin(m["first"]) for m in members)
            cins = ", ".join(m["cin"] for m in members)

            # Check if father is in the voter list
            f_key = (fa_norm, gf_norm, sn_norm, center)
            father_candidates = men_by_key.get(f_key, [])
            father_in_reg = 1 if len(father_candidates) > 0 else 0
            father_cin = father_candidates[0]["cin"] if father_candidates else ""

            local_c_idx = len(sibling_cliques)
            for m in members:
                v_key = (m["cin"], m["first_norm"], m["father_norm"], m["gf_norm"], m["surname_norm"], m["center"])
                clique_membership[v_key] = local_c_idx

            sibling_cliques.append({
                "governorate": gov,
                "constituency": constituency,
                "imada": imada,
                "polling_center": center,
                "surname": sn_raw,
                "surname_latin": to_latin(sn_raw),
                "father_name": fa_raw,
                "father_name_latin": to_latin(fa_raw),
                "grandfather_name": gf_raw,
                "num_siblings": count,
                "sibling_names": names_ar,
                "sibling_names_latin": names_lat,
                "cin_suffixes": cins,
                "father_in_registry": father_in_reg,
                "father_cin_suffix": father_cin,
                "local_clique_idx": local_c_idx
            })

    # -------------------------------------------------------------
    # 2. Reconstruct Parental Ties (Father -> Child)
    # -------------------------------------------------------------
    parental_ties = []

    for v in voters:
        f_key = (v["father_norm"], v["gf_norm"], v["surname_norm"], v["center"])
        if f_key in men_by_key:
            for father_rec in men_by_key[f_key]:
                if father_rec["cin"] != v["cin"]:
                    v_key = (v["cin"], v["first_norm"], v["father_norm"], v["gf_norm"], v["surname_norm"], v["center"])
                    local_c_idx = clique_membership.get(v_key, None)

                    parental_ties.append({
                        "governorate": gov,
                        "constituency": constituency,
                        "imada": imada,
                        "polling_center": v["center"],
                        "surname": v["surname"],
                        "surname_latin": to_latin(v["surname"]),
                        "father_first_name": father_rec["first"],
                        "father_full_name_latin": f"{to_latin(father_rec['first'])} ben {to_latin(father_rec['father'])} {to_latin(father_rec['surname'])}",
                        "child_first_name": v["first"],
                        "child_full_name_latin": f"{to_latin(v['first'])} ben {to_latin(v['father'])} {to_latin(v['surname'])}",
                        "father_cin_suffix": father_rec["cin"],
                        "child_cin_suffix": v["cin"],
                        "local_clique_idx": local_c_idx
                    })

    # Summary stats
    imada_stats = {
        "governorate": gov,
        "constituency": constituency,
        "imada": imada,
        "total_voters": total_voters,
        "sibling_cliques_count": len(sibling_cliques),
        "sibling_voters_count": sibling_voters_count,
        "sibling_voters_pct": round((sibling_voters_count / total_voters) * 100, 2) if total_voters else 0.0,
        "parental_ties_count": len(parental_ties),
        "max_sibling_set_size": max_sibling_size
    }

    return imada_stats, sibling_cliques, parental_ties


def main():
    print("=" * 75, flush=True)
    print("STARTING NATIONWIDE BIOLOGICAL KINSHIP EXTRACTION (8 WORKERS)", flush=True)
    print("=" * 75, flush=True)
    t_start = time.time()

    manifest_path = os.path.join(BASE_DIR, "data", "voter_surnames_2024", "extraction_manifest_national.csv")
    out_dir = os.path.join(BASE_DIR, "data", "voter_surnames_2024", "kinship")
    os.makedirs(out_dir, exist_ok=True)

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = list(csv.DictReader(f))

    total_files = len(manifest)
    print(f"Loaded manifest: {total_files:,} official registry PDFs.", flush=True)

    cliques_out = os.path.join(out_dir, "household_sibling_cliques.csv.gz")
    parents_out = os.path.join(out_dir, "parental_pedigree_ties.csv.gz")
    stats_out = os.path.join(out_dir, "kinship_demographic_stats.csv")

    n_workers = min(8, cpu_count())
    print(f"Launching pool with {n_workers} worker processes...", flush=True)

    tot_voters = 0
    tot_cliques = 0
    tot_sib_voters = 0
    tot_parent_ties = 0

    clique_fields = [
        "clique_id", "governorate", "constituency", "imada", "polling_center",
        "surname", "surname_latin", "father_name", "father_name_latin",
        "grandfather_name", "num_siblings", "sibling_names", "sibling_names_latin",
        "cin_suffixes", "father_in_registry", "father_cin_suffix"
    ]
    parent_fields = [
        "tie_id", "clique_id", "governorate", "constituency", "imada", "polling_center",
        "surname", "surname_latin", "father_first_name", "father_full_name_latin",
        "child_first_name", "child_full_name_latin", "father_cin_suffix", "child_cin_suffix"
    ]
    stats_fields = [
        "governorate", "constituency", "imada", "total_voters",
        "sibling_cliques_count", "sibling_voters_count", "sibling_voters_pct",
        "parental_ties_count", "max_sibling_set_size"
    ]

    with gzip.open(cliques_out, "wt", encoding="utf-8", newline="") as f_clq, \
         gzip.open(parents_out, "wt", encoding="utf-8", newline="") as f_par, \
         open(stats_out, "w", encoding="utf-8", newline="") as f_stat:

        writer_clq = csv.DictWriter(f_clq, fieldnames=clique_fields)
        writer_clq.writeheader()

        writer_par = csv.DictWriter(f_par, fieldnames=parent_fields)
        writer_par.writeheader()

        writer_stat = csv.DictWriter(f_stat, fieldnames=stats_fields)
        writer_stat.writeheader()

        processed_count = 0
        clique_seq = 0
        tie_seq = 0

        with Pool(n_workers) as pool:
            for res in pool.imap_unordered(process_single_pdf, manifest, chunksize=4):
                if res is None:
                    continue
                stats, cliques, ties = res

                processed_count += 1
                tot_voters += stats["total_voters"]
                tot_cliques += stats["sibling_cliques_count"]
                tot_sib_voters += stats["sibling_voters_count"]
                tot_parent_ties += stats["parental_ties_count"]

                writer_stat.writerow(stats)

                # Assign globally unique clique IDs and build local mapping
                local_to_global_clq = {}
                for c in cliques:
                    clique_seq += 1
                    gid = f"CLQ_{clique_seq:07d}"
                    local_c_idx = c.pop("local_clique_idx", None)
                    if local_c_idx is not None:
                        local_to_global_clq[local_c_idx] = gid
                    c["clique_id"] = gid
                    writer_clq.writerow(c)

                for t in ties:
                    tie_seq += 1
                    t["tie_id"] = f"TIE_{tie_seq:07d}"
                    local_c_idx = t.pop("local_clique_idx", None)
                    t["clique_id"] = local_to_global_clq.get(local_c_idx, "")
                    writer_par.writerow(t)

                if processed_count % 100 == 0 or processed_count == total_files:
                    elapsed = time.time() - t_start
                    rate = tot_voters / elapsed if elapsed else 0
                    print(f"[{processed_count:,}/{total_files:,}] {tot_voters:,} voters processed | {tot_cliques:,} sibling cliques | {tot_parent_ties:,} parental ties ({rate:,.0f} voters/sec)", flush=True)

    total_time = time.time() - t_start
    print("\n" + "=" * 75, flush=True)
    print(f"EXTRACTION COMPLETE IN {total_time/60:.2f} MINUTES!", flush=True)
    print(f"Total Voters Processed:     {tot_voters:,}", flush=True)
    print(f"Total Sibling Cliques:      {tot_cliques:,} ({tot_sib_voters:,} sibling voters, {tot_sib_voters/tot_voters*100:.1f}% of electorate)", flush=True)
    print(f"Total Father->Child Ties:   {tot_parent_ties:,}", flush=True)
    print(f"Output files:", flush=True)
    print(f"  -> {cliques_out} ({os.path.getsize(cliques_out)/(1024*1024):.1f} MB)", flush=True)
    print(f"  -> {parents_out} ({os.path.getsize(parents_out)/(1024*1024):.1f} MB)", flush=True)
    print(f"  -> {stats_out} ({os.path.getsize(stats_out)/1024:.1f} KB)", flush=True)
    print("=" * 75, flush=True)

if __name__ == "__main__":
    main()
