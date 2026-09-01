"""Undo any page swap that cost a bureau a block it was already publishing.

`pick_page` ranks candidate pages by how well they register against the
counting-record layout. That is a geometry signal, not a legibility one, and the
two come apart: bureau 23030110103 has a page that fits at 0.94 and certifies
nothing beside a page that fits worse and certifies the whole votes block. On the
bureaux with no reading at all there is nothing to lose, but about one swap in
five lands on a bureau already publishing a papers or ballots account, and a
better-fitting page that reads worse would drop it without saying so.

So this compares the dataset against the one committed before the rerun, finds
every bureau that now certifies strictly fewer blocks, rebuilds the page that
bureau used to use, and keeps whichever of the two certifies more. Rebuilding
goes back through the original scan and the masthead chooser, so it reproduces
the old page rather than reading it from a backup — an imperfect reproduction
can only fail to help here, never publish something wrong, because the winner is
decided by what the form's own identities vouch for.

Usage: python3 tools/confirm_pages.py [--before HEAD] [--workers 3]
"""
import argparse, csv, io, os, subprocess, sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

RESULTS = "data/pv_presidential_2024.csv"
MANIFEST = ".cache/pv_all_manifest.csv"
UPRIGHT = ".cache/pv_upright"
BLOCKS = ("votes_certified", "papers_certified", "ballots_certified")


def blocks_of(row):
    return {b for b in BLOCKS if row.get(b) == "1"}


def committed(ref):
    """The dataset as of `ref`, so the comparison is against what was published."""
    out = subprocess.run(["git", "show", f"{ref}:{RESULTS}"],
                         capture_output=True, check=True).stdout.decode("utf-8")
    return {r["bureau_code"]: r for r in csv.DictReader(io.StringIO(out))}


def rebuild(code, man):
    """The page this bureau used before pick_page, back through the old chooser."""
    from extract_pvs import _load_best_page, LONG_EDGE
    src = man.get(code)
    if not src or not os.path.exists(src):
        return None
    try:
        page, _deg, _score = _load_best_page(src)
    except Exception:
        return None
    if page is None:
        return None
    img = cv2.cvtColor(np.array(page.convert("RGB")), cv2.COLOR_RGB2BGR)
    h, w = img.shape[:2]
    if max(h, w) > LONG_EDGE:
        f = LONG_EDGE / max(h, w)
        img = cv2.resize(img, (max(1, round(w * f)), max(1, round(h * f))),
                         interpolation=cv2.INTER_AREA)
    return img


def certified(img, predict):
    from decode_all import read_image, BLOCKS as FIELD_BLOCKS
    got = read_image(img, predict)
    if not got:
        return set(), None
    cert = set(got["certified"])
    return {name for name, fields in FIELD_BLOCKS.items()
            if set(fields) <= cert}, got


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", default="HEAD",
                    help="git ref holding the dataset to compare against")
    a = ap.parse_args()

    import torch
    from digit_model import Net, predict_proba
    torch.set_num_threads(os.cpu_count() or 4)
    net = Net()
    net.load_state_dict(torch.load(".cache/digit_cnn.pt", map_location="cpu"))
    net.eval()
    predict = lambda X: predict_proba(net, X)

    was = committed(a.before)
    now = {r["bureau_code"]: r for r in csv.DictReader(open(RESULTS, encoding="utf-8"))}
    man = {r["bureau_code"]: r["local_path"]
           for r in csv.DictReader(open(MANIFEST, encoding="utf-8"))}

    lost = [c for c, r in now.items()
            if blocks_of(was.get(c, {})) - blocks_of(r)]
    print(f"{len(lost)} bureaux certify fewer blocks than before the rerun",
          flush=True)

    restored = 0
    for code in lost:
        old = rebuild(code, man)
        if old is None:
            print(f"  {code}: cannot rebuild the previous page", flush=True)
            continue
        cur = cv2.imread(os.path.join(UPRIGHT, f"{code}.jpg"))
        old_blocks, _ = certified(old, predict)
        new_blocks, _ = certified(cur, predict) if cur is not None else (set(), None)
        if len(old_blocks) > len(new_blocks):
            cv2.imwrite(os.path.join(UPRIGHT, f"{code}.jpg"), old,
                        [cv2.IMWRITE_JPEG_QUALITY, 92])
            restored += 1
            print(f"  {code}: restored, {sorted(old_blocks)} beats "
                  f"{sorted(new_blocks)}", flush=True)
        else:
            print(f"  {code}: kept, {sorted(new_blocks)} against "
                  f"{sorted(old_blocks)} — the loss is not the page swap",
                  flush=True)

    print(f"\nrestored the previous page for {restored} of {len(lost)}")
    if restored:
        print("re-run tools/decode_all.py for those bureaux")


if __name__ == "__main__":
    main()
