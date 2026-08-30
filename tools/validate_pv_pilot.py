"""Validate the pilot PV readings against the form's own internal identities.

The 2024 presidential PV is a self-checking document. Seven constraints can be
tested without any external ground truth:

  1. the bureau code written in the form matches the code in the file path
  2. مطابقة 1 : c - s == 0            (signed voters vs ballots extracted)
  3. م = س + د + ر                    (ballots delivered accounted for)
  4. مطابقة 2 : b - m == 0
  5. ن = ص + ع + ف                    (ballots extracted accounted for)
  6. مطابقة 3 : w - n == 0
  7. sum(candidate votes) == q == ص    (declared votes vs valid ballots)

A reading that satisfies all seven is almost certainly correct: an OCR slip
would have to be compensated by matching slips in three other boxes.

Usage: python3 tools/validate_pv_pilot.py
"""
import csv, json, os
from collections import Counter

SRC = ".cache/pv_pilot/readings.jsonl"
OUT = "data/pv_pilot_2024.csv"
REPORT = ".cache/pv_pilot/validation.txt"


def check(r):
    """Return {constraint: True/False/None}; None where a field was unreadable."""
    def got(*keys):
        return all(r.get(k) is not None for k in keys)

    out = {}
    out["code_matches_path"] = r["code_in_image"] == r["bureau_code"]
    out["match1_c_minus_s"] = (r["c_signed"] - r["s_extracted"] == r["match1"]
                               if got("c_signed", "s_extracted", "match1") else None)
    out["m_equals_s_d_r"] = (r["m_total"] == r["s_extracted"] + r["d_damaged"] + r["r_remaining"]
                             if got("m_total", "s_extracted", "d_damaged", "r_remaining") else None)
    out["match2_b_minus_m"] = (r["b_delivered"] - r["m_total"] == r["match2"]
                               if got("b_delivered", "m_total", "match2") else None)
    out["n_equals_valid_blank_spoilt"] = (
        r["n_total"] == r["valid"] + r["blank"] + r["spoilt"]
        if got("n_total", "valid", "blank", "spoilt") else None)
    out["match3_w_minus_n"] = (r["w_voted"] - r["n_total"] == r["match3"]
                               if got("w_voted", "n_total", "match3") else None)
    votes = r["zammel"] + r["maghzaoui"] + r["saied"]
    out["candidate_sum_equals_q"] = (votes == r["q_declared"] == r["valid"]
                                     if got("q_declared", "valid") else None)
    return out, votes


def main():
    rows = [json.loads(l) for l in open(SRC, encoding="utf-8")]
    results, tally = [], Counter()
    per_constraint = {}

    for r in rows:
        checks, votes = check(r)
        passed = sum(1 for v in checks.values() if v is True)
        testable = sum(1 for v in checks.values() if v is not None)
        failed = [k for k, v in checks.items() if v is False]
        for k, v in checks.items():
            per_constraint.setdefault(k, Counter())[
                "pass" if v is True else ("fail" if v is False else "untestable")] += 1
        tally["all_pass" if not failed and testable == 7 else
              ("partial_untestable" if not failed else "has_failure")] += 1
        results.append({
            **{k: r.get(k) for k in
               ("bureau_code", "governorate", "a_registered", "b_delivered", "c_signed",
                "d_damaged", "r_remaining", "s_extracted", "valid", "blank", "spoilt",
                "w_voted", "q_declared", "zammel", "maghzaoui", "saied")},
            "candidate_sum": votes,
            "turnout_pct": round(100 * r["w_voted"] / r["a_registered"], 2)
                           if r.get("w_voted") and r.get("a_registered") else "",
            "saied_share_pct": round(100 * r["saied"] / votes, 2) if votes else "",
            "checks_passed": passed,
            "checks_testable": testable,
            "checks_failed": ",".join(failed),
            "legibility": r.get("legible", ""),
            "fields_uncertain": r.get("fields_uncertain", ""),
        })

    # Join governorate from the download manifest.
    man = {m["bureau_code"]: m for m in csv.DictReader(open(".cache/pv_pilot/sample.csv", encoding="utf-8"))}
    for row in results:
        src = man.get(row["bureau_code"], {})
        row["governorate"] = src.get("governorate", "")
        row["delegation"] = src.get("delegation", "")
        row["polling_centre"] = src.get("polling_centre", "")

    fields = ["bureau_code", "governorate", "delegation", "polling_centre",
              "a_registered", "b_delivered", "c_signed", "d_damaged", "r_remaining",
              "s_extracted", "valid", "blank", "spoilt", "w_voted", "q_declared",
              "zammel", "maghzaoui", "saied", "candidate_sum", "turnout_pct",
              "saied_share_pct", "checks_passed", "checks_testable", "checks_failed",
              "legibility", "fields_uncertain"]
    os.makedirs("data", exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(results)

    lines = [f"PV pilot validation — {len(rows)} bureaux, 2024 presidential", ""]
    lines.append(f"  fully consistent (7/7 checks pass): {tally['all_pass']}/{len(rows)}")
    lines.append(f"  consistent but some checks untestable: {tally['partial_untestable']}")
    lines.append(f"  at least one check failed: {tally['has_failure']}")
    lines.append("")
    lines.append("  per constraint:")
    for k, c in per_constraint.items():
        lines.append(f"    {k:32s} pass {c['pass']:3d}  fail {c['fail']:3d}  untestable {c['untestable']:3d}")
    lines.append("")
    lines.append(f"  legibility: {dict(Counter(r['legibility'] for r in results))}")
    total_fields = len(rows) * 16
    unread = sum(len(r["fields_uncertain"].split(",")) if r["fields_uncertain"] else 0
                 for r in results)
    lines.append(f"  fields not confidently read: {unread}/{total_fields} "
                 f"({100*unread/total_fields:.1f}%)")
    report = "\n".join(lines)
    open(REPORT, "w", encoding="utf-8").write(report)
    print(report)
    print(f"\nwrote {len(results)} rows -> {OUT}")


if __name__ == "__main__":
    main()
