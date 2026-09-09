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

Usage:
    python3 tools/reps_readings.py check <transcript.txt>
    python3 tools/reps_readings.py build <transcript.txt> [more.txt ...]
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
                "candidates": sorted({CANDIDATE[c] for c in rows if c in CANDIDATE}),
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


if __name__ == "__main__":
    {"check": check, "build": build}[sys.argv[1]](sys.argv[2:])
