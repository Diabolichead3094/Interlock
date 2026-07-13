#!/usr/bin/env python3
"""Corpus-wide aggregation of judge scores.

Reads results/scores.jsonl (+ facts.jsonl, errors.log, rubric registry) and
produces results/summary.json plus a console summary:

  - terminal-state distribution
  - behavioral failure-code rates (CUT_TRANSCRIPT excluded, reported separately
    per the frozen rubric ruling) with severity rollup
  - per-criterion Pass/Fail/NA rates and critical-criterion failure rate
  - per-intent counts and terminal-state outcomes vs the decision table
  - failure-code co-occurrence pairs
  - worst calls (most critical codes)
  - pipeline health (errors.log summary)

Usage:  python3 scripts/analyze.py
"""
import json
import os
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lint_golden_labels import CRITERION_COLS  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCORES = os.path.join(ROOT, "results", "scores.jsonl")
ERRORS = os.path.join(ROOT, "results", "errors.log")
RUBRIC = os.path.join(ROOT, "rubric", "rubric.yaml")
SUMMARY_OUT = os.path.join(ROOT, "results", "summary.json")

TERMINAL_IDS = ["resolved", "transferred", "callback", "declined", "failed"]
OUTCOME_CODES = {"DROP_OFF", "CUT_TRANSCRIPT"}
CRITICAL_CRITERIA = ["identity", "intent_class", "terminal_correct", "scope",
                     "dropoff", "kb_fidelity"]

# decision table, mirrored from the frozen rubric (rubric/rubric.yaml)
DECISION_TABLE = {
    "lockout": {"resolved", "transferred"},
    "service_timing": {"resolved"},
    "payment": {"resolved"},
    "data_upload": {"resolved"},
    "removal": {"transferred", "resolved"},
    "quote": {"resolved", "transferred"},
    "holiday_coordination": {"resolved"},
    "bypass_legal": {"declined"},
    "operator_request": {"transferred"},
    "other": {"resolved", "transferred", "declined"},
}
# callback is a valid landing for ANY intent (global rule); failed never valid.


def code_severities(path):
    """{code: severity} parsed from the rubric registry (outcome + process)."""
    text = open(path, encoding="utf-8").read()
    fc = text.split("failure_codes:", 1)[1]
    fc = re.split(r"^\s*nursery:", fc, flags=re.M)[0]
    out = {}
    for m in re.finditer(
            r"-\s*code:\s*([A-Z_]+)\s*\n\s*severity:\s*([a-z-]+)", fc):
        out[m.group(1)] = m.group(2)
    return out


def pct(n, d):
    return round(100.0 * n / d, 1) if d else 0.0


def main():
    severities = code_severities(RUBRIC)

    scores = {}
    with open(SCORES, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rec = json.loads(line)
                scores[rec["call_id"]] = rec
    n = len(scores)

    # --- terminal states ----------------------------------------------------
    ts_counts = Counter(s["terminal_state"] for s in scores.values())

    # --- failure codes ------------------------------------------------------
    code_counts = Counter()
    calls_with_code = defaultdict(list)
    for cid, s in sorted(scores.items()):
        for c in set(s["failure_codes"]):
            code_counts[c] += 1
            calls_with_code[c].append(cid)
    cut_count = code_counts.get("CUT_TRANSCRIPT", 0)
    behavioral = {c: v for c, v in code_counts.items() if c != "CUT_TRANSCRIPT"}
    sev_rollup = Counter()
    for c, v in behavioral.items():
        sev_rollup[severities.get(c, "?")] += v
    calls_any_behavioral = sum(
        1 for s in scores.values()
        if set(s["failure_codes"]) - {"CUT_TRANSCRIPT"})
    calls_clean = sum(1 for s in scores.values() if not s["failure_codes"])

    # --- criteria -----------------------------------------------------------
    crit_table = {}
    for c in CRITERION_COLS:
        vc = Counter(s["criteria"][c]["verdict"] for s in scores.values())
        crit_table[c] = {"Pass": vc.get("Pass", 0), "Fail": vc.get("Fail", 0),
                         "NA": vc.get("NA", 0)}
    calls_critical_fail = sum(
        1 for s in scores.values()
        if any(s["criteria"][c]["verdict"] == "Fail" for c in CRITICAL_CRITERIA))

    # --- intents & decision table -------------------------------------------
    intent_counts = Counter()
    intent_state = defaultdict(Counter)
    invalid_landings = []
    for cid, s in sorted(scores.items()):
        state = s["terminal_state"]
        multi_intent = len(s["intents"]) > 1
        for it in s["intents"]:
            intent_counts[it] += 1
            intent_state[it][state] += 1
            valid = DECISION_TABLE.get(it, set()) | {"callback"}
            # global rule: a transfer serving all requests of a multi-intent
            # call is a valid landing for every one of them (rubric, 040)
            if multi_intent and state == "transferred":
                continue
            if state != "failed" and state not in valid:
                invalid_landings.append(
                    {"call_id": cid, "intent": it, "state": state})

    # --- co-occurrence (behavioral codes) ------------------------------------
    cooc = Counter()
    for s in scores.values():
        cs = sorted(set(s["failure_codes"]) - {"CUT_TRANSCRIPT"})
        for i in range(len(cs)):
            for j in range(i + 1, len(cs)):
                cooc[(cs[i], cs[j])] += 1

    # --- worst calls ----------------------------------------------------------
    def crit_count(s):
        return sum(1 for c in set(s["failure_codes"])
                   if severities.get(c) == "critical")
    worst = sorted(scores.values(),
                   key=lambda s: (-crit_count(s), -len(set(s["failure_codes"])),
                                  s["call_id"]))
    worst = [{"call_id": s["call_id"], "terminal_state": s["terminal_state"],
              "codes": sorted(set(s["failure_codes"])),
              "critical_codes": crit_count(s)}
             for s in worst if s["failure_codes"]][:10]

    # --- pipeline health -------------------------------------------------------
    err_lines = []
    if os.path.exists(ERRORS):
        err_lines = [l.strip() for l in open(ERRORS, encoding="utf-8")
                     if l.strip()]

    summary = {
        "n_calls": n,
        "terminal_states": {t: {"count": ts_counts.get(t, 0),
                                "pct": pct(ts_counts.get(t, 0), n)}
                            for t in TERMINAL_IDS},
        "behavioral_failure_codes": {
            c: {"count": v, "pct_of_calls": pct(v, n),
                "severity": severities.get(c, "?"),
                "calls": calls_with_code[c]}
            for c, v in sorted(behavioral.items(), key=lambda kv: -kv[1])},
        "cut_transcript": {"count": cut_count, "pct_of_calls": pct(cut_count, n),
                           "note": "evidence-only; excluded from behavioral rates",
                           "calls": calls_with_code.get("CUT_TRANSCRIPT", [])},
        "severity_rollup": dict(sev_rollup),
        "calls_with_any_behavioral_code": {
            "count": calls_any_behavioral, "pct": pct(calls_any_behavioral, n)},
        "calls_fully_clean": {"count": calls_clean, "pct": pct(calls_clean, n)},
        "criteria": crit_table,
        "calls_failing_any_critical_criterion": {
            "count": calls_critical_fail, "pct": pct(calls_critical_fail, n)},
        "intents": {it: {"count": v, "states": dict(intent_state[it])}
                    for it, v in intent_counts.most_common()},
        "invalid_landings": invalid_landings,
        "code_cooccurrence": [{"pair": list(p), "count": v}
                              for p, v in cooc.most_common(12)],
        "worst_calls": worst,
        "pipeline_errors_logged": len(err_lines),
    }

    with open(SUMMARY_OUT, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    # --- console summary -------------------------------------------------------
    print("=" * 72)
    print("CORPUS SUMMARY — %d calls  (results/summary.json written)" % n)
    print("=" * 72)
    print("\nTerminal states:")
    for t in TERMINAL_IDS:
        c = ts_counts.get(t, 0)
        print("  %-12s %4d  %5.1f%%  %s" % (t, c, pct(c, n), "█" * int(pct(c, n) / 2)))
    print("\nBehavioral failure codes (CUT_TRANSCRIPT excluded):")
    for c, v in sorted(behavioral.items(), key=lambda kv: -kv[1]):
        print("  %-22s %4d  %5.1f%% of calls  [%s]"
              % (c, v, pct(v, n), severities.get(c, "?")))
    print("  %-22s %4d  %5.1f%% of calls  [evidence-only, separate]"
          % ("CUT_TRANSCRIPT", cut_count, pct(cut_count, n)))
    print("\nCriteria (Pass / Fail / NA):")
    for c in CRITERION_COLS:
        t = crit_table[c]
        print("  %-18s %4d / %3d / %3d   fail rate %.1f%% of applicable"
              % (c, t["Pass"], t["Fail"], t["NA"],
                 pct(t["Fail"], t["Pass"] + t["Fail"])))
    print("\nCalls fully clean: %d (%.1f%%)   with any behavioral code: %d (%.1f%%)"
          % (calls_clean, pct(calls_clean, n),
             calls_any_behavioral, pct(calls_any_behavioral, n)))
    print("Calls failing ≥1 critical criterion: %d (%.1f%%)"
          % (calls_critical_fail, pct(calls_critical_fail, n)))
    print("\nIntents:")
    for it, v in intent_counts.most_common():
        states = ", ".join("%s:%d" % kv for kv in intent_state[it].most_common())
        print("  %-22s %4d   %s" % (it, v, states))
    if invalid_landings:
        print("\nInvalid landings (non-failed state outside decision table):")
        for r in invalid_landings:
            print("  %(call_id)s  %(intent)s → %(state)s" % r)
    print("\nTop code co-occurrences:")
    for item in cooc.most_common(8):
        print("  %-40s %d" % (" + ".join(item[0]), item[1]))
    print("\nWorst calls (by critical codes):")
    for w in worst:
        print("  %-22s %-12s %s" % (w["call_id"], w["terminal_state"],
                                    ",".join(w["codes"])))


if __name__ == "__main__":
    main()
