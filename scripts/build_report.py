#!/usr/bin/env python3
"""Generate the interactive dashboard from pipeline outputs.

Reads calls + scores (+ facts, containment when present) and injects a single
DATA object into report/template.html, producing a self-contained HTML file
with drill-down: counts → call lists → full transcripts with cited turns
highlighted. Narrative text (recommendation cards, scoreboard targets) comes
from report/narrative.json — edit that file, never the output.

Usage:
  python3 scripts/build_report.py
  python3 scripts/build_report.py --calls data/calls.jsonl --results results \\
      --out report/final_report.html --baseline path/to/previous/results
"""
import argparse
import datetime
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze import code_severities  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUBRIC = os.path.join(ROOT, "rubric", "rubric.yaml")
TEMPLATE = os.path.join(ROOT, "report", "template.html")
NARRATIVE = os.path.join(ROOT, "report", "narrative.json")

# fixed slot per entity (color follows the entity across runs) and fixed arc
# order (validated adjacency: blue, orange, aqua, yellow, violet)
STATE_SLOTS = [("transferred", 1), ("failed", 2), ("callback", 3),
               ("resolved", 4), ("declined", 5)]
STATE_COLS = [s for s, _ in STATE_SLOTS]
CRITICAL_CRITERIA = ["identity", "intent_class", "terminal_correct", "scope",
                     "dropoff", "kb_fidelity"]


def jmap(path):
    out = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    r = json.loads(line)
                    out[r["call_id"]] = r
    return out


def aggregates(scores, severities):
    """Everything countable, from scores alone (shared with --baseline)."""
    n = len(scores)
    codes = Counter()
    for s in scores.values():
        for c in set(s["failure_codes"]):
            codes[c] += 1
    clean = sum(1 for s in scores.values() if not s["failure_codes"])
    beh_fail = [c for c, s in scores.items() if s["terminal_state"] == "failed"
                and "CUT_TRANSCRIPT" not in s["failure_codes"]]
    crit_fail = sum(1 for s in scores.values() if any(
        s["criteria"][k]["verdict"] == "Fail" for k in CRITICAL_CRITERIA))
    return {
        "n": n,
        "codes": {c: v for c, v in codes.items()},
        "kpis": {
            "n": n,
            "clean_n": clean, "clean_pct": round(100.0 * clean / n),
            "beh_fail_n": len(beh_fail),
            "beh_fail_pct": round(100.0 * len(beh_fail) / n),
            "cut_n": codes.get("CUT_TRANSCRIPT", 0),
            "crit_fail_n": crit_fail,
            "crit_fail_pct": round(100.0 * crit_fail / n),
            "scope_fails": sum(1 for s in scores.values()
                               if s["criteria"]["scope"]["verdict"] == "Fail"),
            "critical_criteria": CRITICAL_CRITERIA,
        },
    }


def build_data(calls_path, results_dir, baseline_dir):
    severities = code_severities(RUBRIC)
    calls = jmap(calls_path)
    scores = jmap(os.path.join(results_dir, "scores.jsonl"))
    containment = jmap(os.path.join(results_dir, "containment.jsonl"))
    missing = sorted(set(calls) - set(scores))
    scored_calls = {c: calls[c] for c in scores}

    agg = aggregates(scores, severities)
    n = agg["n"]

    # states, fixed arc order
    st_counts = Counter(s["terminal_state"] for s in scores.values())
    states = [{"id": sid, "n": st_counts.get(sid, 0), "slot": slot}
              for sid, slot in STATE_SLOTS]

    # failure codes, behavioral desc + cut separate
    codes = [{"c": c, "n": v, "sev": severities.get(c, "?")}
             for c, v in sorted(agg["codes"].items(), key=lambda kv: (-kv[1], kv[0]))
             if c != "CUT_TRANSCRIPT"]
    cut = {"c": "CUT_TRANSCRIPT", "n": agg["codes"].get("CUT_TRANSCRIPT", 0),
           "sev": "evidence"}

    # criteria
    crit_names = list(next(iter(scores.values()))["criteria"].keys())
    criteria = []
    for c in crit_names:
        vc = Counter(s["criteria"][c]["verdict"] for s in scores.values())
        criteria.append({"c": c, "p": vc.get("Pass", 0), "f": vc.get("Fail", 0),
                         "na": vc.get("NA", 0)})

    # intent × state matrix
    im = {}
    for s in scores.values():
        for it in s["intents"]:
            im.setdefault(it, Counter())[s["terminal_state"]] += 1
    intents = [{"i": it, "v": [im[it].get(c, 0) for c in STATE_COLS]}
               for it in sorted(im, key=lambda k: -sum(im[k].values()))]

    # containment block
    cont_block = None
    if containment:
        flagged_buckets = {"resolved_then_nudged", "containable_but_transferred",
                           "partially_containable"}
        flagged = [r for _, r in sorted(containment.items())
                   if r["bucket"] in flagged_buckets]
        n_ct = sum(1 for r in flagged if r["bucket"] == "containable_but_transferred")
        n_rn = sum(1 for r in flagged if r["bucket"] == "resolved_then_nudged")
        n_pc = sum(1 for r in flagged if r["bucket"] == "partially_containable")
        cont_block = {
            "flagged": [{"call_id": r["call_id"], "bucket": r["bucket"],
                         "evidence": r["evidence"], "reason": r.get("reason", "")}
                        for r in flagged],
            "summary": "%d containable transfers · %d resolved-call nudges · %d partial"
                       % (n_ct, n_rn, n_pc),
        }

    # per-call detail for drill-down
    call_detail = {}
    for cid, sc in scores.items():
        call_detail[cid] = {
            "turns": calls[cid]["turns"],
            "score": {k: sc[k] for k in
                      ("intents", "terminal_state", "criteria",
                       "failure_codes", "rationale")},
            "containment": (
                {k: containment[cid][k] for k in ("bucket", "evidence", "reason")}
                if cid in containment else None),
        }

    kpis = agg["kpis"]
    kpis["health"] = ("all %d calls in the batch scored" % n if not missing
                      else "%d call(s) not yet scored" % len(missing))

    baseline = None
    if baseline_dir:
        b_scores = jmap(os.path.join(baseline_dir, "scores.jsonl"))
        if not b_scores:
            raise SystemExit("--baseline: no scores.jsonl in %s" % baseline_dir)
        b = aggregates(b_scores, severities)
        b_cont = jmap(os.path.join(baseline_dir, "containment.jsonl"))
        if b_cont:
            b["kpis"]["nudges"] = sum(
                1 for r in b_cont.values()
                if r["bucket"] in ("resolved_then_nudged",
                                   "containable_but_transferred",
                                   "partially_containable"))
        baseline = {"kpis": b["kpis"], "codes": b["codes"], "n": b["n"]}

    narrative = json.load(open(NARRATIVE, encoding="utf-8"))
    return {
        "meta": {"n": n,
                 "generated": "generated %s from %s"
                 % (datetime.date.today().isoformat(),
                    os.path.relpath(results_dir, ROOT))},
        "kpis": kpis,
        "states": states, "codes": codes, "cut": cut,
        "criteria": criteria, "stateCols": STATE_COLS, "intents": intents,
        "containment": cont_block,
        "narrative": narrative,
        "baseline": baseline,
        "calls": call_detail,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--calls", default=os.path.join(ROOT, "data", "calls.jsonl"))
    ap.add_argument("--results", default=os.path.join(ROOT, "results"))
    ap.add_argument("--out", default=os.path.join(ROOT, "report", "final_report.html"))
    ap.add_argument("--baseline", default=None, metavar="RESULTS_DIR",
                    help="previous run's results dir — renders ▲▼ delta chips")
    args = ap.parse_args()

    data = build_data(args.calls, args.results, args.baseline)
    template = open(TEMPLATE, encoding="utf-8").read()
    marker = "/*__DATA__*/ null"
    if marker not in template:
        raise SystemExit("template placeholder not found")
    html = template.replace(
        marker, json.dumps(data, ensure_ascii=False, separators=(",", ":"))
                    .replace("</", "<\\/"))  # keep </script> safe inside JSON
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html)
    print("Wrote %s  (%.2f MB, %d calls, %d codes%s)"
          % (os.path.relpath(args.out, ROOT), os.path.getsize(args.out) / 1e6,
             data["meta"]["n"], len(data["codes"]),
             ", baseline deltas on" if data["baseline"] else ""))


if __name__ == "__main__":
    main()
