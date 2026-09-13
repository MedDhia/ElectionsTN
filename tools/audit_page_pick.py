"""Which bureaux had their results read off a page that is not the counting record.

The orient stage used to choose among a bureau's archived pages by masthead OCR
score, and on a poor scan the record's own masthead reads as nothing (see the
comment at the top of `extract_pvs.py`). This re-runs the fixed picker over every
bureau whose archive holds more than one page and compares its answer with the
page already cached, without touching the cache.

Two numbers per bureau. `cached_fit` is how well the page the results were read
from registers against the reference layout, measured **at every rotation**: the
pages this got wrong are the ones whose masthead scored 0, so their orientation
is suspect too, and measuring them upright-only counts a sideways record as a
wrong one. That distinction is not academic -- it moved 8 bureaux out of the
list. `new_fit` is the best any archived page manages.

A low cached fit says the page was wrong. It does not say the numbers are wrong:
the form's arithmetic identities can close on whatever digits a page carries,
which is why 123 of the 125 found this way are certified. The output is a list to
re-read, not a correction.

Usage: python3 tools/audit_page_pick.py <out.json> [workers]
"""
import csv, json, os, sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, 'tools')

def sources():
    seen = defaultdict(set)
    for r in csv.DictReader(open('.cache/pv_all_manifest.csv', encoding='utf-8')):
        if os.path.exists(r['local_path']) and r['bureau_code'] != 'nocode':
            seen[r['bureau_code']].add(r['local_path'])
    return {c: sorted(v) for c, v in seen.items()}

def _one(job):
    import cv2
    import extract_pvs as E
    from pick_page import fit
    code, srcs = job
    # how well the page already cached fits the counting-record layout
    cur = cv2.imread(os.path.join('.cache/pv_upright', f'{code}.jpg'))
    # rotations=True: these are the pages whose masthead scored 0, so the cached
    # image may not be upright, and an unrotated fit would blame the page for
    # what is really a bad turn.
    cached = fit(cur, rotations=True)[0] if cur is not None else 0.0
    try:
        img, deg, score, why = E._pick_page(srcs)
    except Exception as exc:
        return code, {'error': f'{type(exc).__name__}: {exc}'}
    if img is None:
        return code, {'error': 'no readable page'}
    return code, {'cached_fit': round(cached, 4), 'new_fit': why.get('fit'),
                  'src': os.path.basename(why['src']), 'page': why['page'],
                  'deg': deg, 'on': why['decisive'],
                  'pages': why.get('pages', 1)}

if __name__ == '__main__':
    src = sources()
    jobs = [(c, ps) for c, ps in src.items()
            if len(ps) > 1 or any(p.lower().endswith('.pdf') for p in ps)]
    jobs.sort()
    print(f'{len(jobs)} bureaux whose archive holds more than one page', flush=True)
    out = {}
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 8
    with ProcessPoolExecutor(workers) as ex:
        for i, (code, res) in enumerate(ex.map(_one, jobs), 1):
            out[code] = res
            if i % 100 == 0:
                print(f'  {i}/{len(jobs)}', flush=True)
    json.dump(out, open(sys.argv[1], 'w'), indent=1)
    print('wrote', sys.argv[1])
