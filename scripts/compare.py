#!/usr/bin/env python3
"""Compare judge scores against the golden labels.

Joins results/scores.jsonl with labels/golden_labels.csv on Call_ID and prints:
  1. join summary (golden rows, scored rows, joined; unscored golden ids)
  2. per-criterion agreement percentages (exact Pass/Fail/NA match)
  3. criterion mismatches with both verdicts and call ids
  4. terminal-state agreement (golden display names mapped to judge ids)
  5. failure-code overlap: per-call sets side by side, exact-set-match rate,
     micro precision/recall/F1, and a per-code count table

Usage:  python3 scripts/compare.py [--scores FILE]
"""
import argparse
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lint_golden_labels import CRITERION_COLS  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLDEN_CSV = os.path.join(ROOT, "labels", "golden_labels.csv")
SCORES = os.path.join(ROOT, "results", "scores.jsonl")

STATE_MAP = {
    "Resolved by Mia": "resolved",
    "Transferred": "transferred",
    "Callback captured": "callback",
    "Declined & redirected": "declined",
    "Failed": "failed",
}


def hr(title):
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--scores", default=SCORES, metavar="FILE",
                    help="scores jsonl to compare (default: results/scores.jsonl)")
    args = ap.parse_args()

    with open(GOLDEN_CSV, encoding="utf-8", newline="") as f:
        golden = {row["Call_ID"].strip(): row
                  for row in csv.DictReader(f) if row.get("Call_ID", "").strip()}

    if not os.path.exists(args.scores):
        raise SystemExit("no %s — run scripts/run_eval.py first" % args.scores)
    scores = {}
    with open(args.scores, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rec = json.loads(line)
                scores[rec["call_id"]] = rec  # last occurrence wins

    joined = sorted(set(golden) & set(scores))
    unscored = sorted(set(golden) - set(scores))

    hr("JOIN SUMMARY")
    print("golden rows: %d   scored calls: %d   joined on Call_ID: %d"
          % (len(golden), len(scores), len(joined)))
    if unscored:
        print("golden ids with no score: %s" % ", ".join(unscored))
    if not joined:
        raise SystemExit("nothing to compare")

    # --- 2 & 3: per-criterion agreement + mismatches -----------------------
    agree = {c: 0 for c in CRITERION_COLS}
    mismatches = []
    for cid in joined:
        for c in CRITERION_COLS:
            g = golden[cid][c].strip()
            j = scores[cid]["criteria"][c]["verdict"]
            if g == j:
                agree[c] += 1
            else:
                mismatches.append((cid, c, g, j))

    hr("PER-CRITERION AGREEMENT (exact Pass/Fail/NA match, n=%d)" % len(joined))
    for c in CRITERION_COLS:
        print("  %-18s %2d/%2d  %6.1f%%"
              % (c, agree[c], len(joined), 100.0 * agree[c] / len(joined)))
    overall = sum(agree.values())
    total = len(joined) * len(CRITERION_COLS)
    print("  %-18s %2d/%2d  %6.1f%%"
          % ("OVERALL", overall, total, 100.0 * overall / total))

    hr("CRITERION MISMATCHES (%d)" % len(mismatches))
    if not mismatches:
        print("  ✓ none")
    for cid, c, g, j in mismatches:
        print("  ✗ %-20s %-18s golden=%-4s judge=%s" % (cid, c, g, j))

    # --- 4: terminal-state agreement ---------------------------------------
    ts_agree, ts_miss = 0, []
    for cid in joined:
        g = STATE_MAP.get(golden[cid]["Terminal_State"].strip(),
                          golden[cid]["Terminal_State"].strip())
        j = scores[cid]["terminal_state"]
        if g == j:
            ts_agree += 1
        else:
            ts_miss.append((cid, g, j))

    hr("TERMINAL-STATE AGREEMENT")
    print("  %d/%d  %.1f%%" % (ts_agree, len(joined), 100.0 * ts_agree / len(joined)))
    for cid, g, j in ts_miss:
        print("  ✗ %-20s golden=%-12s judge=%s" % (cid, g, j))

    # --- 5: failure-code overlap --------------------------------------------
    hr("FAILURE-CODE OVERLAP")
    exact = 0
    tp = fp = fn = 0
    per_code = {}  # code -> [golden_count, judge_count, both_count]
    for cid in joined:
        gset = {t.strip() for t in golden[cid]["Failure_Code"].split(",")
                if t.strip()}
        jset = set(scores[cid]["failure_codes"])
        both = gset & jset
        tp += len(both)
        fp += len(jset - gset)
        fn += len(gset - jset)
        for code in gset | jset:
            row = per_code.setdefault(code, [0, 0, 0])
            row[0] += code in gset
            row[1] += code in jset
            row[2] += code in both
        mark = "✓" if gset == jset else "✗"
        if gset == jset:
            exact += 1
        print("  %s %-20s golden={%s}  judge={%s}%s"
              % (mark, cid,
                 ",".join(sorted(gset)) or "-",
                 ",".join(sorted(jset)) or "-",
                 "" if gset == jset else
                 "  diff: +%s -%s" % (",".join(sorted(jset - gset)) or "∅",
                                      ",".join(sorted(gset - jset)) or "∅")))

    print("\n  exact set match: %d/%d  %.1f%%"
          % (exact, len(joined), 100.0 * exact / len(joined)))
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    print("  micro precision %.3f   recall %.3f   F1 %.3f   (TP=%d FP=%d FN=%d)"
          % (prec, rec, f1, tp, fp, fn))

    print("\n  %-22s %6s %6s %6s" % ("code", "golden", "judge", "both"))
    for code in sorted(per_code):
        g, j, b = per_code[code]
        print("  %-22s %6d %6d %6d" % (code, g, j, b))


if __name__ == "__main__":
    main()
