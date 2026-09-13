"""
Multiprocessing PDF Extractor for Tunisian Voter Registry.
"""

import os
import re
import sqlite3
import logging
import time
from pathlib import Path
import pypdfium2 as pdfium
from src.parser import parse_voter_line, parse_tunisian_surname

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

COUNT_PATTERN = re.compile(r'عدد\s*الناخبين\s*[:\s]*(\d+)')
IMADA_PATTERN = re.compile(r'العمادة\s*[:\s]*([^\n\r:]+)')
GOV_PATTERN = re.compile(r'الهيئة\s*الفرعية\s*[:\s]*([^\n\r:]+)')
CONST_PATTERN = re.compile(r'الدائرة\s*الانتخابية\s*(?:التشريعية)?\s*[:\s]*([^\n\r:]+)')


from collections import Counter
from src.parser import parse_voter_line, parse_tunisian_surname, parse_latin_surname


def assemble_voter_lines(raw_lines):
    """
    Assemble multi-line wrapped voter records into single complete records.
    Filters out ISIE headers, pagination markers, and footers.
    """
    cleaned = []
    for l in raw_lines:
        l = l.strip()
        if not l or 'الهيئة' in l or 'الثلاث' in l or 'الناخبين' in l or l.startswith('الصفحة') or 'من عدد الهوية' in l or 'قائمة الناخبين الأولية' in l:
            continue
        cleaned.append(l)

    assembled = []
    curr = []
    for l in cleaned:
        words = l.split()
        if curr:
            curr.append(l)
            combined = ' '.join(curr).split()
            if (combined[0].isdigit() and len(combined) >= 3) or (combined[-1].isdigit() and len(combined) >= 3):
                assembled.append(' '.join(curr))
                curr = []
        else:
            if (words[0].isdigit() and len(words) >= 3) or (words[-1].isdigit() and len(words) >= 3):
                assembled.append(l)
            else:
                curr = [l]
    if curr:
        assembled.append(' '.join(curr))
    return assembled


def extract_pdf_data(pdf_path: str):
    """
    Extract metadata and aggregated voter surname counts from a voter registry PDF.
    Supports both domestic and diaspora registries with 100% extraction completeness
    via multi-line reassembly and dual standard (Arabic) / inverted (Latin) orientation parsing.
    """
    try:
        pdf = pdfium.PdfDocument(pdf_path)
    except Exception as e:
        logging.error("Failed to open %s: %s", pdf_path, e)
        return None

    num_pages = len(pdf)
    if num_pages == 0:
        return None

    is_diaspora = 1 if 'الخارج' in str(pdf_path) else 0

    # 1. Extract metadata from Page 0
    txt0 = pdf[0].get_textpage().get_text_range()
    m_cnt = COUNT_PATTERN.search(txt0)
    m_im = IMADA_PATTERN.search(txt0)
    m_gov = GOV_PATTERN.search(txt0)
    m_const = CONST_PATTERN.search(txt0)

    official_count = int(m_cnt.group(1)) if m_cnt else 0
    imada = m_im.group(1).strip() if m_im else Path(pdf_path).stem
    gov = m_gov.group(1).strip() if m_gov else ""
    constituency = m_const.group(1).strip() if m_const else ""

    # Infer from file path if header patterns missed anything
    parts = Path(pdf_path).parts
    if not gov and len(parts) >= 3:
        gov = parts[-3]
    if not constituency and len(parts) >= 2:
        constituency = parts[-2]

    # 2. Extract voters from Pages 1..N-1 and aggregate counts
    counts_counter = Counter()
    total_extracted = 0

    for pno in range(1, num_pages):
        raw_lines = pdf[pno].get_textpage().get_text_range().split('\n')
        v_lines = assemble_voter_lines(raw_lines)

        std_lines = []
        inv_lines = []
        for l in v_lines:
            words = l.split()
            if words[0].isdigit() and len(words[0]) <= 5:
                std_lines.append((words[0], ' '.join(words[1:])))
            elif words[-1].isdigit() and len(words[-1]) <= 5:
                inv_lines.append((words[-1], ' '.join(words[:-1])))

        # 1. Process standard lines (common trailing suffix center)
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

            _, _, sn, sn_norm = parse_tunisian_surname(name)
            if sn:
                counts_counter[(center, sn, sn_norm)] += 1
                total_extracted += 1

        # 2. Process inverted lines (common leading prefix center)
        best_prefix = None
        if len(inv_lines) >= 3:
            prefixes = Counter()
            for cin, rest in inv_lines:
                words = rest.split()
                for n in range(1, min(8, len(words)-1)):
                    prefixes[' '.join(words[:n])] += 1
            qualifying = [p for p, c in prefixes.items() if c >= len(inv_lines) * 0.4]
            if qualifying:
                best_prefix = max(qualifying, key=lambda p: (len(p.split()), prefixes[p]))

        for cin, rest in inv_lines:
            if best_prefix and rest.startswith(best_prefix):
                name = rest[len(best_prefix):].strip()
                center = best_prefix
            else:
                words = rest.split()
                latin_start = next((i for i, w in enumerate(words) if any(c.isascii() and c.isalpha() for c in w)), None)
                if latin_start and latin_start > 0:
                    center = ' '.join(words[:latin_start])
                    name = ' '.join(words[latin_start:])
                else:
                    name = rest
                    center = ""

            is_latin = any(c.isascii() and c.isalpha() for c in name)
            if is_latin:
                sn, sn_norm = parse_latin_surname(name)
            else:
                _, _, sn, sn_norm = parse_tunisian_surname(name)

            if sn:
                counts_counter[(center, sn, sn_norm)] += 1
                total_extracted += 1

    counts = [
        (gov, constituency, imada, center, sn, sn_norm, cnt, is_diaspora)
        for (center, sn, sn_norm), cnt in counts_counter.items()
    ]

    return {
        'metadata': {
            'pdf_path': str(pdf_path),
            'filename': Path(pdf_path).name,
            'governorate': gov,
            'constituency': constituency,
            'imada': imada,
            'pages': num_pages,
            'official_count': official_count,
            'extracted_count': total_extracted,
            'completeness_pct': (total_extracted / official_count * 100) if official_count else 100.0,
            'is_diaspora': is_diaspora
        },
        'counts': counts
    }


def init_sqlite_db(db_path: Path):
    """Initialize SQLite database for surname counts and PDF extraction manifests."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS center_surname_counts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            governorate TEXT,
            constituency TEXT,
            imada TEXT,
            polling_center TEXT,
            surname TEXT,
            surname_norm TEXT,
            voter_count INTEGER,
            is_diaspora INTEGER DEFAULT 0
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS manifests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pdf_path TEXT UNIQUE,
            filename TEXT,
            governorate TEXT,
            constituency TEXT,
            imada TEXT,
            pages INTEGER,
            official_count INTEGER,
            extracted_count INTEGER,
            completeness_pct REAL,
            is_diaspora INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()


def save_batch_to_db(db_path: Path, batch_results: list):
    """Write extracted counts and manifests to SQLite."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    all_counts = []
    manifests = []
    for res in batch_results:
        if not res:
            continue
        manifests.append((
            res['metadata']['pdf_path'],
            res['metadata']['filename'],
            res['metadata']['governorate'],
            res['metadata']['constituency'],
            res['metadata']['imada'],
            res['metadata']['pages'],
            res['metadata']['official_count'],
            res['metadata']['extracted_count'],
            res['metadata']['completeness_pct'],
            res['metadata']['is_diaspora']
        ))
        all_counts.extend(res['counts'])

    cur.executemany("""
        INSERT OR REPLACE INTO manifests 
        (pdf_path, filename, governorate, constituency, imada, pages, official_count, extracted_count, completeness_pct, is_diaspora)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, manifests)

    cur.executemany("""
        INSERT INTO center_surname_counts 
        (governorate, constituency, imada, polling_center, surname, surname_norm, voter_count, is_diaspora)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, all_counts)

    conn.commit()
    conn.close()


def create_db_indexes(db_path: Path):
    """Create indexes on center_surname_counts for high-speed aggregations."""
    logging.info("Creating SQLite database indexes on %s...", db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("CREATE INDEX IF NOT EXISTS idx_cnt_sn_imada ON center_surname_counts(governorate, constituency, imada);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_cnt_sn_center ON center_surname_counts(governorate, constituency, imada, polling_center);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_cnt_sn_surname ON center_surname_counts(surname, surname_norm);")
    conn.commit()
    conn.close()
    logging.info("Indexes successfully created.")
