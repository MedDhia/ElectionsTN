"""Turn the contact-sheet transcripts into a checked readings file.

The transcript is written one station per line while the sheets are read:

    03030210105 s
    01060410202 ms

One character per row of the table, in printed order, trailing blanks omitted:

    s  قيس سعيد        z  العياشي زمال     m  زهير المغزاوي
    .  no representative recorded on this row
    ?  something is written on the row and it cannot be attributed

A row with no representative comes in three visible forms — left blank, filled
with a dash, or struck through with a diagonal — and the first draft of this
protocol coded them apart. It was collapsed after a sheet of trial reading: the
distinction costs most of the reading effort, the three are not reliably
separable at contact-sheet scale, and all three say the same thing about the
question the dataset is for. What is lost is the ability to ask whether a bureau
that struck the table out differs from one that left it blank, and the codebook
says so rather than implying the dataset could answer it.

Transcribing the bureau code beside each reading was the first protocol and it
put a typo class into the data: three codes in the first eighty sheets were
mistyped by one digit, and two of them were *valid codes for other stations*, so
nothing downstream could notice. `pair` removes the hazard by taking only the row
codes, in tile order, and pairing them with the codes the plan already holds for
that sheet — a `-` skips a tile whose crop was not the table. `verify` is the
retrospective form of the same check, comparing a written transcript against its
plan sheet.

Usage:
    python3 tools/reps_readings.py check <transcript.txt>
    python3 tools/reps_readings.py build <transcript.txt> [more.txt ...]
    python3 tools/reps_readings.py pair <sheet> <out.txt> <rowcodes...>
    python3 tools/reps_readings.py rescue <sheet> <out.txt> <rowcodes...>
    python3 tools/reps_readings.py verify
"""
import json, os, sys

OUT = "data/verification/representatives_readings.jsonl"
CODES = set("szm.?")
CANDIDATE = {"s": "saied", "z": "zammel", "m": "maghzaoui"}


def parse(paths):
    """{bureau_code: rows} from one or more transcripts, later files winning."""
    out, dupes = {}, 0
    for path in paths:
        for n, line in enumerate(open(path, encoding="utf-8"), 1):
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) != 2:
                raise ValueError(f"{path}:{n}: expected 'code rows', got {line!r}")
            code, rows = parts
            if not code.isdigit():
                raise ValueError(f"{path}:{n}: {code!r} is not a bureau code")
            if not 1 <= len(rows) <= 3 or set(rows) - CODES:
                raise ValueError(f"{path}:{n}: {rows!r} is not one to three row codes")
            rows = rows.ljust(3, ".")
            if code in out and out[code] != rows:
                dupes += 1
            out[code] = rows
    return out, dupes


def build(paths):
    readings, dupes = parse(paths)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        for code in sorted(readings):
            rows = readings[code]
            fh.write(json.dumps({
                "bureau_code": code,
                "rows": list(rows),
                "n_representatives": sum(1 for c in rows if c in CANDIDATE),
                "per_candidate": {v: sum(1 for c in rows if CANDIDATE.get(c) == v)
                                  for v in ("saied", "zammel", "maghzaoui")},
                "unattributed": rows.count("?"),
            }, ensure_ascii=False) + "\n")
    print(f"{len(readings)} stations -> {OUT}"
          + (f" ({dupes} re-read differently, later reading kept)" if dupes else ""))


def check(paths):
    readings, dupes = parse(paths)
    from collections import Counter
    per_row = Counter()
    for rows in readings.values():
        per_row.update(rows)
    print(f"{len(readings)} stations, {dupes} conflicting re-reads")
    print("row codes:", dict(per_row))
    n = Counter(sum(1 for c in r if c in CANDIDATE) for r in readings.values())
    print("representatives per station:", dict(sorted(n.items())))


PLAN = ".cache/reps_plan.csv"


def _plan_sheets():
    import csv
    out = {}
    for r in csv.DictReader(open(PLAN, encoding="utf-8")):
        out.setdefault(int(r["sheet"]), []).append(r["bureau_code"])
    return out


def pair(args):
    """Write a transcript by pairing row codes with the plan's own bureau codes."""
    sheet, out_path = int(args[0]), args[1]
    codes = "".join(args[2:]).split(",") if "," in "".join(args[2:]) else args[2:]
    codes = [c for c in codes if c]
    ref = _plan_sheets()[sheet]
    if len(codes) != len(ref):
        raise SystemExit(f"sheet {sheet} has {len(ref)} tiles, got {len(codes)} row codes")
    with open(out_path, "w", encoding="utf-8") as fh:
        for code, rows in zip(ref, codes):
            if rows == "-":
                continue
            fh.write(f"{code} {rows}\n")
    kept = sum(1 for c in codes if c != "-")
    print(f"sheet {sheet}: {kept} stations -> {out_path}"
          + (f" ({len(codes) - kept} tiles skipped)" if kept != len(codes) else ""))


RESCUE_ORDER = ".cache/reps_rescue/order.txt"


def rescue(args):
    """Pair row codes with a rescue sheet's own order, as `pair` does for a plan.

    The mis-framed stations are read off a page-anchored window rather than a
    contact-sheet tile, so their order comes from the window renderer instead of
    the plan; the retyping hazard is the same one, and so is the fix.
    """
    sheet, out_path = int(args[0]), args[1]
    codes = [c for c in args[2:] if c]
    ref = [l.split()[1] for l in open(RESCUE_ORDER, encoding="utf-8")
           if l.split()[0] == str(sheet)]
    if len(codes) != len(ref):
        raise SystemExit(f"rescue sheet {sheet} has {len(ref)} tiles, "
                         f"got {len(codes)} row codes")
    with open(out_path, "w", encoding="utf-8") as fh:
        for code, rows in zip(ref, codes):
            if rows == "-":
                continue
            fh.write(f"{code} {rows}\n")
    kept = sum(1 for c in codes if c != "-")
    print(f"rescue {sheet}: {kept} stations -> {out_path}"
          + (f" ({len(codes) - kept} unreadable)" if kept != len(codes) else ""))


def verify(_args):
    """Check every x-series transcript's codes against its plan sheet."""
    import glob, re
    sheets = _plan_sheets()
    bad = 0
    for path in sorted(glob.glob(".cache/reps_transcripts/x*.txt")):
        m = re.search(r"x(\d{4})\.txt$", path)
        if not m:
            continue
        mine = [l.split()[0] for l in open(path, encoding="utf-8")
                if l.split("#", 1)[0].strip()]
        ref = sheets.get(int(m.group(1)), [])
        extra = [c for c in mine if c not in ref]
        if extra:
            bad += 1
            print(f"{path}: codes not in plan sheet -> {extra}")
    print(f"{bad} transcripts with codes outside their plan sheet")


if __name__ == "__main__":
    {"check": check, "build": build, "pair": pair, "rescue": rescue,
     "verify": verify}[sys.argv[1]](sys.argv[2:])
