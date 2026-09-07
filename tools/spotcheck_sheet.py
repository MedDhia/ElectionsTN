"""Render an audit sheet: what the dataset says, beside the form it came from.

Every check in this project is the pipeline checking itself. The identities are
the form's own arithmetic, the words channel is another reader I wrote, and the
`reading == "vision"` rows were read by the same eye that then verified them.
None of that is independent. The only audit that is, is a person opening a few
scans and comparing them to the published row.

This makes that cheap. It picks a spread of vision-read stations — across
governorates, across station sizes, and deliberately including rows the words
channel disagreed with — crops the block that carries the candidate rows, their
Arabic words and both totals, and prints the published values beside it.

What to check, per station: the three candidate digits, the total in `(ق)`, and
that the Arabic words beside each candidate say the same number as the digits.
Anything that does not match is a real error in the dataset, not a flagging
question, and worth telling me about.

Two pools, because they answer different questions and mixing them hides both:

- `--pool corrected` — the rows this project **overruled the pipeline on** by
  hand. These are the highest-stakes claims in the dataset: each one asserts the
  published value was wrong and states a different one. If I misread a scan while
  "correcting" it, this is where the damage is.
- `--pool untouched` — vision-read rows nothing has since revised. The ordinary
  case, and the one that says whether the reading is sound in general.

Usage: python3 tools/spotcheck_sheet.py [--pool corrected|untouched] [--n 10]
"""
import argparse, csv, json, os, random, sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

RESULTS = "data/pv_presidential_2024.csv"
UPRIGHT = ".cache/pv_upright"
BOX = (0.0, 0.38, 0.72, 0.84)   # candidate rows, their words, and both totals
WIDE = 1500
CAND = ("zammel", "maghzaoui", "saied")


def as_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def crop(img):
    h, w = img.shape[:2]
    x0, y0, x1, y1 = BOX
    return img[int(h * y0):int(h * y1), int(w * x0):int(w * x1)]


def scale(im, width=WIDE):
    h, w = im.shape[:2]
    if not w or not h:
        return None
    return cv2.resize(im, (width, max(1, int(round(h * width / w)))),
                      interpolation=cv2.INTER_CUBIC)


def panel(r, width):
    """The published row, printed large enough to read against the scan."""
    lines = [
        f"{r['bureau_code']}   {r['governorate']} / {r['delegation']}",
        "",
        f"  Zammel    {r['zammel'] or '-':>6}",
        f"  Maghzaoui {r['maghzaoui'] or '-':>6}",
        f"  Saied     {r['saied'] or '-':>6}",
        f"  --------------------",
        f"  valid     {r['valid'] or '-':>6}      (q) {r['q_declared'] or '-'}",
        "",
        f"  words agree: {'yes' if r['split_corroborated'] == '1' else 'NO' if r['split_corroborated'] == '0' else 'not read'}"
        f"     reading: {r['reading']}",
    ]
    im = np.full((34 * len(lines) + 20, width, 3), 250, np.uint8)
    for i, line in enumerate(lines):
        cv2.putText(im, line, (14, 32 + i * 34), cv2.FONT_HERSHEY_SIMPLEX,
                    0.78, (20, 20, 20), 2)
    cv2.line(im, (0, im.shape[0] - 2), (width, im.shape[0] - 2), (120, 120, 120), 2)
    return im


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", choices=["corrected", "untouched"],
                    default="untouched")
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default=".cache/spotcheck")
    a = ap.parse_args()

    revised = set()
    for f in ("data/verification/split_errors.jsonl",
              "data/verification/papers_contradictions.jsonl"):
        if os.path.exists(f):
            revised |= {json.loads(l)["bureau_code"]
                        for l in open(f, encoding="utf-8")}

    rows = [r for r in csv.DictReader(open(RESULTS, encoding="utf-8"))
            if r["reading"] == "vision" and r["votes_certified"] == "1"
            and all(r[c] for c in CAND)
            and ((r["bureau_code"] in revised) == (a.pool == "corrected"))
            and os.path.exists(os.path.join(UPRIGHT, f"{r['bureau_code']}.jpg"))]
    print(f"pool '{a.pool}': {len(rows)} candidate stations\n")

    rng = random.Random(a.seed)
    # A spread, not a random draw: small and large stations, several
    # governorates, and some rows the words channel disagreed with — those are
    # where an error is most likely to be hiding.
    # Take from the pools most likely to hide an error first, then fill the rest
    # by station size so the sample is not all one scale. Whatever a pool cannot
    # supply is taken up by the next, so the sheet count is n whenever n rows
    # exist at all.
    tiers = [[r for r in rows if r["split_corroborated"] == "0"],
             [r for r in rows if r["split_corroborated"] not in ("0", "1")],
             [r for r in rows if r["split_corroborated"] == "1"]]
    quota = [max(1, a.n // 4), max(1, a.n // 3), a.n]
    pick, seen = [], set()
    for tier, k in zip(tiers, quota):
        tier = [r for r in tier if r["bureau_code"] not in seen]
        # `valid` is empty on the rows where the form's (ص) is washed out and
        # its (ق) carries the total, so size falls back to (ق) and then to 0.
        tier.sort(key=lambda r: as_int(r["valid"]) or as_int(r["q_declared"]) or 0)
        if not tier:
            continue
        step = max(1, len(tier) // max(1, min(k, a.n - len(pick))))
        for r in tier[::step]:
            if len(pick) >= a.n:
                break
            pick.append(r)
            seen.add(r["bureau_code"])
        if len(pick) >= a.n:
            break
    # and if the tiers together still fall short, top up from anything left
    for r in rows:
        if len(pick) >= a.n:
            break
        if r["bureau_code"] not in seen:
            pick.append(r)
            seen.add(r["bureau_code"])
    rng.shuffle(pick)

    os.makedirs(a.out, exist_ok=True)
    made = []
    for i, r in enumerate(pick, 1):
        img = cv2.imread(os.path.join(UPRIGHT, f"{r['bureau_code']}.jpg"))
        if img is None:
            continue
        im = scale(crop(img))
        if im is None:
            continue
        tile = np.vstack([panel(r, im.shape[1]), im])
        p = os.path.join(a.out, "spotcheck_%02d_%s.png" % (i, r["bureau_code"]))
        cv2.imwrite(p, tile)
        made.append((p, r))
        print(f"  {p}   {r['zammel']}/{r['maghzaoui']}/{r['saied']} of "
              f"{r['valid']}   words "
              f"{'agree' if r['split_corroborated'] == '1' else 'DISAGREE' if r['split_corroborated'] == '0' else 'not read'}")

    print(f"\n{len(made)} sheets -> {a.out}")
    print("check per station: the three candidate digits, the (ق) total, and "
          "that the Arabic\nwords beside each candidate say the same number as "
          "its digits.")


if __name__ == "__main__":
    main()
