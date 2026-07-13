#!/usr/bin/env python3
"""Pass C: transfer-containment classification.

Candidates: calls where Pass A found a transfer offered/attempted AND the judge
did not classify an operator_request intent (the caller didn't open by asking
for a human). Each candidate runs through prompts/containment.md; results are
validated (enums, call_id, verbatim-substring evidence quotes, offer-turn
citation) with retry-once + errors.log, checkpointed in
results/containment.jsonl. Aggregates land in results/containment.json.

Usage:  python3 scripts/containment.py [--limit N] [--workers N] [--model M]
"""
import argparse
import concurrent.futures
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from run_eval import (run_claude, extract_json, PassError, load_jsonl_map,  # noqa: E402
                      append_jsonl, log_error, IO_LOCK, STATS_LOCK)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CALLS = os.path.join(ROOT, "data", "calls.jsonl")
FACTS = os.path.join(ROOT, "results", "facts.jsonl")
SCORES = os.path.join(ROOT, "results", "scores.jsonl")
PROMPT_MD = os.path.join(ROOT, "prompts", "containment.md")
OUT_JSONL = os.path.join(ROOT, "results", "containment.jsonl")
OUT_JSON = os.path.join(ROOT, "results", "containment.json")

BUCKETS = {"resolved_then_nudged", "containable_but_transferred",
           "partially_containable", "justified_transfer", "caller_requested"}
FLAGGED = {"resolved_then_nudged", "containable_but_transferred",
           "partially_containable"}
CONTAINABLE = {"yes", "partial", "no"}


def validate(obj, cid, turns):
    if not isinstance(obj, dict):
        raise PassError("not an object")
    if obj.get("call_id") != cid:
        raise PassError("call_id %r != %r" % (obj.get("call_id"), cid))
    if obj.get("bucket") not in BUCKETS:
        raise PassError("bucket invalid: %r" % obj.get("bucket"))
    if obj.get("containable") not in CONTAINABLE:
        raise PassError("containable invalid: %r" % obj.get("containable"))
    if obj.get("caller_requested_human") and obj["bucket"] != "caller_requested":
        raise PassError("caller_requested_human=true but bucket %r" % obj["bucket"])
    ev = obj.get("evidence")
    if not isinstance(ev, list) or (obj["bucket"] != "caller_requested" and not ev):
        raise PassError("evidence missing")
    cited = set()
    for e in ev:
        t = e.get("turn")
        if not isinstance(t, int) or not (0 <= t < len(turns)):
            raise PassError("evidence turn %r out of range" % t)
        q = e.get("quote", "")
        if not q or q not in turns[t]["text"]:
            raise PassError("quote not verbatim in turn %s: %r" % (t, q[:60]))
        cited.add(t)
    fo = obj.get("first_offer_turn")
    if obj["bucket"] in FLAGGED:
        if not isinstance(fo, int) or fo not in cited:
            raise PassError("flagged bucket must cite first_offer_turn (%r)" % fo)


def process(call, facts, prompt_md, model, total, stats):
    cid = call["call_id"]
    inp = (prompt_md
           + "\n\nCALL TRANSCRIPT:\n" + json.dumps(call, ensure_ascii=False)
           + "\n\nEXTRACTED FACTS:\n" + json.dumps(facts, ensure_ascii=False))
    cost, obj = 0.0, None
    for attempt in (1, 2):
        try:
            text, c = run_claude(inp, model)
            cost += c
            cand = extract_json(text)
            validate(cand, cid, call["turns"])
            obj = cand
            break
        except PassError as e:
            cost += getattr(e, "cost", 0.0)
            if attempt == 1:
                with IO_LOCK:
                    print("  ! %s pass C attempt 1 failed (%s), retrying"
                          % (cid, e.reason))
            else:
                log_error(cid, "C", e.reason, e.raw)
    with STATS_LOCK:
        stats["cost"] += cost
        stats["done"] += 1
        done = stats["done"]
        if obj is None:
            stats["errors"] += 1
    if obj is None:
        return
    append_jsonl(OUT_JSONL, obj)
    with IO_LOCK:
        print("[%d/%d] %s → %s" % (done, total, cid, obj["bucket"]))


def candidates():
    calls = {json.loads(l)["call_id"]: json.loads(l) for l in open(CALLS)}
    facts = load_jsonl_map(FACTS)
    scores = load_jsonl_map(SCORES)
    out = []
    for cid in sorted(scores):
        tr = facts.get(cid, {}).get("transfer", {})
        if not (tr.get("offered") or tr.get("attempted")):
            continue
        if "operator_request" in scores[cid].get("intents", []):
            continue
        out.append((calls[cid], facts[cid], scores[cid]["terminal_state"]))
    return out, len(scores)


def aggregate(cands, n_scored):
    recs = load_jsonl_map(OUT_JSONL)
    state_by_cid = {c["call_id"]: st for c, _, st in cands}
    buckets, citations = {}, []
    for cid, r in sorted(recs.items()):
        buckets.setdefault(r["bucket"], []).append(cid)
        if r["bucket"] in FLAGGED:
            citations.append({
                "call_id": cid, "bucket": r["bucket"],
                "terminal_state": state_by_cid.get(cid),
                "first_offer_turn": r.get("first_offer_turn"),
                "evidence": r["evidence"], "reason": r.get("reason", "")})
    flagged = sorted(set().union(*[set(buckets.get(b, [])) for b in FLAGGED]))
    transferred_flagged = [c for c in flagged
                           if state_by_cid.get(c) == "transferred"]
    summary = {
        "n_scored_calls": n_scored,
        "n_transfer_offered_or_attempted": 168,
        "n_candidates": len(cands),
        "n_classified": len(recs),
        "buckets": {b: {"count": len(v), "calls": v}
                    for b, v in sorted(buckets.items(), key=lambda kv: -len(kv[1]))},
        "flagged_total": {"count": len(flagged),
                          "pct_of_corpus": round(100.0 * len(flagged) / n_scored, 1),
                          "calls": flagged},
        "flagged_transferred": {
            "count": len(transferred_flagged),
            "pct_of_127_transferred": round(100.0 * len(transferred_flagged) / 127, 1)},
        "citations": citations,
    }
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--limit", type=int, default=None, metavar="N")
    ap.add_argument("--workers", type=int, default=1, metavar="N")
    ap.add_argument("--model", default=None)
    args = ap.parse_args()

    prompt_md = open(PROMPT_MD, encoding="utf-8").read()
    cands, n_scored = candidates()
    done_map = load_jsonl_map(OUT_JSONL)
    todo = [(c, f) for c, f, _ in cands if c["call_id"] not in done_map]
    if args.limit is not None:
        todo = todo[:args.limit]
    print("Candidates: %d total, %d already classified, %d to run, %d worker(s)\n"
          % (len(cands), len(done_map), len(todo), args.workers))

    stats = {"cost": 0.0, "errors": 0, "done": 0}
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = [pool.submit(process, c, f, prompt_md, args.model, len(todo), stats)
                for c, f in todo]
        for fut in concurrent.futures.as_completed(futs):
            fut.result()

    print("\nDone. classified: %d, errors: %d, cost this run: $%.4f"
          % (stats["done"] - stats["errors"], stats["errors"], stats["cost"]))

    s = aggregate(cands, n_scored)
    print("\nBuckets:")
    for b, v in s["buckets"].items():
        print("  %-28s %3d" % (b, v["count"]))
    print("Flagged total: %d (%.1f%% of corpus); flagged transferred: %d "
          "(%.1f%% of the 127 transfers)"
          % (s["flagged_total"]["count"], s["flagged_total"]["pct_of_corpus"],
             s["flagged_transferred"]["count"],
             s["flagged_transferred"]["pct_of_127_transferred"]))
    print("Wrote results/containment.json")


if __name__ == "__main__":
    main()
