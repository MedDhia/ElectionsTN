"""
Aggregations and Geospatial Metrics for Extracted Voter Surnames.
"""

import sqlite3
import csv
import gzip
import math
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def build_imada_aggregation(db_path: Path, out_path: Path):
    """
    Generate surnames_by_imada.csv.gz:
    Columns: surname, surname_norm, governorate, constituency, imada, voter_count, imada_total_voters, surname_share, imada_rank, is_diaspora
    """
    logging.info("Building Imada aggregation from %s...", db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    imada_totals = {}
    imada_surnames = {}
    imada_diaspora = {}

    for row in cur.execute("SELECT governorate, constituency, imada, surname, surname_norm, voter_count, is_diaspora FROM center_surname_counts WHERE surname != ''"):
        gov, const, im, sn, sn_norm, cnt, dias = row
        im_key = (gov, const, im)
        imada_totals[im_key] = imada_totals.get(im_key, 0) + cnt
        imada_diaspora[im_key] = dias
        if im_key not in imada_surnames:
            imada_surnames[im_key] = {}
        sn_key = (sn, sn_norm)
        imada_surnames[im_key][sn_key] = imada_surnames[im_key].get(sn_key, 0) + cnt

    conn.close()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(out_path, "wt", encoding="utf-8", newline="") as f_out:
        writer = csv.writer(f_out)
        writer.writerow([
            "surname", "surname_norm", "governorate", "constituency",
            "imada", "voter_count", "imada_total_voters", "surname_share", "imada_rank", "is_diaspora"
        ])
        count = 0
        for im_key in sorted(imada_surnames.keys()):
            gov, const, im = im_key
            tot = imada_totals[im_key]
            dias = imada_diaspora.get(im_key, 0)
            sorted_sns = sorted(imada_surnames[im_key].items(), key=lambda x: x[1], reverse=True)
            for rank, ((sn, sn_norm), cnt) in enumerate(sorted_sns, 1):
                share = round((cnt / tot) * 100.0, 4) if tot else 0.0
                writer.writerow([sn, sn_norm, gov, const, im, cnt, tot, share, rank, dias])
                count += 1

    logging.info("Saved %d imada surname rows to %s", count, out_path)
    return count


def build_polling_center_aggregation(db_path: Path, out_path: Path):
    """
    Generate surnames_by_polling_center.csv.gz:
    Columns: surname, surname_norm, governorate, constituency, imada, polling_center, voter_count, center_total_voters, surname_share, is_diaspora
    """
    logging.info("Building Polling Center aggregation...")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    center_totals = {}
    for row in cur.execute("SELECT governorate, constituency, imada, polling_center, voter_count FROM center_surname_counts"):
        key = (row[0], row[1], row[2], row[3])
        center_totals[key] = center_totals.get(key, 0) + row[4]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(out_path, "wt", encoding="utf-8", newline="") as f_out:
        writer = csv.writer(f_out)
        writer.writerow([
            "surname", "surname_norm", "governorate", "constituency",
            "imada", "polling_center", "voter_count", "center_total_voters", "surname_share", "is_diaspora"
        ])
        count = 0
        for row in cur.execute("SELECT surname, surname_norm, governorate, constituency, imada, polling_center, voter_count, is_diaspora FROM center_surname_counts WHERE surname != ''"):
            sn, sn_norm, gov, const, im, center, cnt, dias = row
            tot = center_totals.get((gov, const, im, center), cnt)
            share = round((cnt / tot) * 100.0, 4) if tot else 0.0
            writer.writerow([sn, sn_norm, gov, const, im, center, cnt, tot, share, dias])
            count += 1

    conn.close()
    logging.info("Saved %d polling center surname rows to %s", count, out_path)
    return count


def build_spatial_metrics(db_path: Path, out_path: Path):
    """
    Generate surnames_spatial_metrics.csv.gz:
    Columns: surname, surname_norm, national_voters, national_share, imadas_present, top_governorate, top_imada, top_imada_share_pct, hhi_concentration, spatial_entropy
    """
    logging.info("Calculating Spatial Concentration Metrics (HHI & Entropy)...")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    surname_data = {}
    total_national_voters = 0

    for row in cur.execute("SELECT surname, surname_norm, governorate, imada, voter_count FROM center_surname_counts WHERE surname != ''"):
        sn, sn_norm, gov, im, cnt = row
        total_national_voters += cnt
        key = (sn, sn_norm)
        if key not in surname_data:
            surname_data[key] = {
                'total': 0,
                'imadas': {},
                'govs': {}
            }
        surname_data[key]['total'] += cnt
        im_key = (gov, im)
        surname_data[key]['imadas'][im_key] = surname_data[key]['imadas'].get(im_key, 0) + cnt
        surname_data[key]['govs'][gov] = surname_data[key]['govs'].get(gov, 0) + cnt

    conn.close()

    metrics = []
    for (sn, sn_norm), d in surname_data.items():
        tot = d['total']
        num_imadas = len(d['imadas'])

        # Top imada
        top_im_key = max(d['imadas'], key=d['imadas'].get)
        top_im_count = d['imadas'][top_im_key]
        top_gov, top_im = top_im_key
        top_im_share = round((top_im_count / tot) * 100.0, 3)

        # Top gov
        top_gov_name = max(d['govs'], key=d['govs'].get)

        # HHI & Entropy
        hhi = 0.0
        entropy = 0.0
        for cnt in d['imadas'].values():
            p = cnt / tot
            hhi += p ** 2
            if p > 0:
                entropy -= p * math.log(p)

        national_share = round((tot / (total_national_voters or 1)) * 100.0, 5)

        metrics.append((
            sn, sn_norm, tot, national_share, num_imadas,
            top_gov_name, f"{top_gov} - {top_im}", top_im_share,
            round(hhi, 5), round(entropy, 4)
        ))

    metrics.sort(key=lambda x: x[2], reverse=True)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(out_path, "wt", encoding="utf-8", newline="") as f_out:
        writer = csv.writer(f_out)
        writer.writerow([
            "surname", "surname_norm", "national_voters", "national_share", "imadas_present",
            "top_governorate", "top_imada", "top_imada_share_pct", "hhi_concentration", "spatial_entropy"
        ])
        for row in metrics:
            writer.writerow(row)

    logging.info("Saved %d spatial metrics rows to %s", len(metrics), out_path)
    return len(metrics)
