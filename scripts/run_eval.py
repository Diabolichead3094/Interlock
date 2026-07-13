#!/usr/bin/env python3
"""Two-pass Mia evaluation harness.

For each call in data/calls.jsonl:
  Pass A  prompts/extract.md + call JSON  -> claude -p (JSON output) -> facts JSON
  Pass B  prompts/judge.md + transcript + facts -> claude -p          -> judge JSON

Validation (per pass, retry once on any failure, then log to results/errors.log):
  Pass A: dict, call_id matches, all 12 template keys present.
  Pass B: dict, call_id matches, all 8 criteria with Pass/Fail/NA, terminal_state
          one of five ids, failure_codes from the frozen registry, outcome codes
          (DROP_OFF, CUT_TRANSCRIPT) force terminal_state=failed, clean states
          carry no outcome code, DROP_OFF and CUT_TRANSCRIPT never together.

Outputs append to results/facts.jsonl and results/scores.jsonl with checkpointing:
reruns skip call_ids already in scores.jsonl; calls with facts but no score reuse
the stored facts and run Pass B only.

Usage:  python3 scripts/run_eval.py [--limit N] [--golden] [--model MODEL]
"""
import argparse
import concurrent.futures
import csv
import datetime
import json
import os
import subprocess
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lint_golden_labels import load_registry  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CALLS = os.path.join(ROOT, "data", "calls.jsonl")
EXTRACT_MD = os.path.join(ROOT, "prompts", "extract.md")
JUDGE_MD = os.path.join(ROOT, "prompts", "judge.md")
RUBRIC = os.path.join(ROOT, "rubric", "rubric.yaml")
GOLDEN_CSV = os.path.join(ROOT, "labels", "golden_labels.csv")
RESULTS = os.path.join(ROOT, "results")
FACTS_OUT = os.path.join(RESULTS, "facts.jsonl")
SCORES_OUT = os.path.join(RESULTS, "scores.jsonl")
ERRORS_LOG = os.path.join(RESULTS, "errors.log")

CLAUDE_TIMEOUT = 300  # seconds per claude call
IO_LOCK = threading.Lock()     # guards jsonl/log appends and prints
STATS_LOCK = threading.Lock()  # guards shared counters

FACTS_KEYS = {
    "call_id", "intents", "name", "links", "guidance_claims", "transfer",
    "callback", "decline", "prices_stated_by_mia", "actions_claimed_by_mia",
    "ends_mid_sentence", "evidence_turns",
}
JUDGE_KEYS = {"call_id", "intents", "terminal_state", "criteria",
              "failure_codes", "rationale"}
CRITERIA = ["identity", "intent_class", "terminal_correct", "scope",
            "dropoff", "transfer_hygiene", "callback_quality", "kb_fidelity"]
VERDICTS = {"Pass", "Fail", "NA"}
TERMINAL_IDS = {"resolved", "transferred", "callback", "declined", "failed"}
OUTCOME_CODES = {"DROP_OFF", "CUT_TRANSCRIPT"}


class PassError(Exception):
    """One failed attempt of a pass; carries a reason and the raw output."""
    def __init__(self, reason, raw=""):
        super().__init__(reason)
        self.reason = reason
        self.raw = raw


def run_claude(prompt, model):
    """One headless claude call. Returns (result_text, cost_usd) or raises PassError."""
    cmd = ["claude", "-p", "--output-format", "json",
           "--tools", "", "--no-session-persistence"]
    if model:
        cmd += ["--model", model]
    try:
        proc = subprocess.run(cmd, input=prompt, capture_output=True,
                              text=True, timeout=CLAUDE_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise PassError("claude timed out after %ds" % CLAUDE_TIMEOUT)
    if proc.returncode != 0:
        raise PassError("claude exit %d" % proc.returncode,
                        proc.stderr or proc.stdout)
    try:
        env = json.loads(proc.stdout)
    except (json.JSONDecodeError, ValueError):
        raise PassError("envelope not JSON", proc.stdout)
    cost = env.get("total_cost_usd") or 0.0
    if env.get("is_error") or env.get("subtype") != "success":
        err = PassError("envelope error subtype=%r" % env.get("subtype"),
                        str(env.get("result", "")))
        err.cost = cost  # count spend even on a failed attempt
        raise err
    return env.get("result", ""), cost


def repair_brackets(doc):
    """Append the closers for any brackets left open outside strings.

    Rescues the judge's recurring glitch of dropping a closing brace (e.g. the
    one that ends the criteria object). Only APPENDS closers at the end; the
    semantic validators still gate the result, so a bad repair cannot slip
    an invalid record through.
    """
    stack, in_str, esc = [], False, False
    for ch in doc:
        if esc:
            esc = False
        elif ch == "\\":
            esc = True
        elif in_str:
            if ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]" and stack and ch == stack[-1]:
            stack.pop()
    return doc + ('"' if in_str else "") + "".join(reversed(stack))


def extract_json(text):
    """Pull the JSON object out of model text (tolerates markdown fences/prose)."""
    if "```" in text:
        parts = text.split("```")
        for part in parts[1:]:  # fenced blocks are the odd segments
            body = part[4:] if part.startswith("json") else part
            if "{" in body:
                text = body
                break
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise PassError("no JSON object in output", text)
    doc = text[start:end + 1]
    try:
        return json.loads(doc)
    except (json.JSONDecodeError, ValueError) as e:
        try:
            return json.loads(repair_brackets(doc))
        except (json.JSONDecodeError, ValueError):
            raise PassError("output JSON parse error: %s" % e, text)


def validate_facts(obj, call_id):
    if not isinstance(obj, dict):
        raise PassError("facts is not an object")
    if obj.get("call_id") != call_id:
        raise PassError("facts call_id %r != %r" % (obj.get("call_id"), call_id))
    missing = FACTS_KEYS - obj.keys()
    if missing:
        raise PassError("facts missing keys: %s" % ", ".join(sorted(missing)))


def normalize_judge(obj):
    """Hoist root-level keys that a dropped brace misfiled inside criteria.

    The judge's recurring truncation glitch omits the brace closing the
    criteria object, so bracket repair parses failure_codes/rationale as
    criteria members. Relocation is unambiguous: those keys are never
    criteria. Mutates and returns obj; validate_judge still gates the result.
    """
    crit = obj.get("criteria")
    if isinstance(crit, dict):
        for key in ("failure_codes", "rationale"):
            if key not in obj and key in crit:
                obj[key] = crit.pop(key)
    return obj


def validate_judge(obj, call_id, registry):
    if not isinstance(obj, dict):
        raise PassError("judge output is not an object")
    if obj.get("call_id") != call_id:
        raise PassError("judge call_id %r != %r" % (obj.get("call_id"), call_id))
    missing = JUDGE_KEYS - obj.keys()
    if missing:
        raise PassError("judge missing keys: %s" % ", ".join(sorted(missing)))

    crit = obj.get("criteria")
    if not isinstance(crit, dict):
        raise PassError("criteria is not an object")
    for c in CRITERIA:
        entry = crit.get(c)
        if not isinstance(entry, dict) or entry.get("verdict") not in VERDICTS:
            raise PassError("criterion %s verdict invalid: %r"
                            % (c, entry.get("verdict") if isinstance(entry, dict) else entry))

    state = obj.get("terminal_state")
    if state not in TERMINAL_IDS:
        raise PassError("terminal_state invalid: %r" % state)

    codes = obj.get("failure_codes")
    if not isinstance(codes, list) or not all(isinstance(x, str) for x in codes):
        raise PassError("failure_codes is not a list of strings")
    unknown = [x for x in codes if x not in registry]
    if unknown:
        raise PassError("failure_codes not in registry: %s" % ", ".join(unknown))
    outcome = OUTCOME_CODES & set(codes)
    if outcome and state != "failed":
        raise PassError("outcome code %s requires terminal_state=failed, got %r"
                        % ("/".join(sorted(outcome)), state))
    if len(outcome) == 2:
        raise PassError("DROP_OFF and CUT_TRANSCRIPT are mutually exclusive")


def log_error(call_id, pass_name, reason, raw):
    snippet = " ".join(str(raw)[:300].split())
    line = "%s | %s | pass %s | %s | %s\n" % (
        datetime.datetime.now().isoformat(timespec="seconds"),
        call_id, pass_name, reason, snippet)
    with IO_LOCK:
        with open(ERRORS_LOG, "a", encoding="utf-8") as f:
            f.write(line)
        print("  ✗ %s pass %s FAILED after retry: %s (logged)"
              % (call_id, pass_name, reason))


def attempt_pass(pass_name, call_id, prompt, model, validator):
    """Run one pass with up to 2 attempts. Returns (obj, cost) or (None, cost)."""
    cost = 0.0
    for attempt in (1, 2):
        try:
            text, c = run_claude(prompt, model)
            cost += c
            obj = extract_json(text)
            validator(obj)
            return obj, cost
        except PassError as e:
            cost += getattr(e, "cost", 0.0)
            if attempt == 1:
                with IO_LOCK:
                    print("  ! %s pass %s attempt 1 failed (%s), retrying"
                          % (call_id, pass_name, e.reason))
            else:
                log_error(call_id, pass_name, e.reason, e.raw)
    return None, cost


def load_jsonl_map(path):
    """{call_id: record} from a jsonl file; last occurrence wins; {} if absent."""
    out = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rec = json.loads(line)
                    out[rec["call_id"]] = rec
    return out


def append_jsonl(path, rec):
    with IO_LOCK:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())


def golden_ids():
    with open(GOLDEN_CSV, encoding="utf-8", newline="") as f:
        return {row["Call_ID"].strip() for row in csv.DictReader(f) if row.get("Call_ID")}


def process_call(call, total, prompts, registry, model, facts_done, stats):
    """Full A→B chain for one call. Thread-safe; returns nothing (updates stats)."""
    extract_prompt, judge_prompt = prompts
    cid = call["call_id"]
    call_json = json.dumps(call, ensure_ascii=False)

    # Pass A (reuse checkpointed facts if present)
    facts = facts_done.get(cid)
    reused = facts is not None
    if not reused:
        facts, cost = attempt_pass(
            "A", cid, extract_prompt + "\n\n" + call_json, model,
            lambda o: validate_facts(o, cid))
        with STATS_LOCK:
            stats["cost"] += cost
        if facts is None:
            with STATS_LOCK:
                stats["errors"] += 1
                stats["done"] += 1
            return
        append_jsonl(FACTS_OUT, facts)
        with STATS_LOCK:
            stats["facts"] += 1

    # Pass B
    judge_input = (judge_prompt
                   + "\n\nCALL TRANSCRIPT:\n" + call_json
                   + "\n\nEXTRACTED FACTS:\n" + json.dumps(facts, ensure_ascii=False))
    score, cost = attempt_pass("B", cid, judge_input, model,
                               lambda o: validate_judge(normalize_judge(o),
                                                        cid, registry))
    with STATS_LOCK:
        stats["cost"] += cost
        stats["done"] += 1
        done = stats["done"]
        if score is None:
            stats["errors"] += 1
        else:
            stats["scores"] += 1
    if score is None:
        return
    append_jsonl(SCORES_OUT, score)
    codes = ",".join(score["failure_codes"]) or "-"
    with IO_LOCK:
        print("[%d/%d] %s → %s (%s)%s"
              % (done, total, cid, score["terminal_state"], codes,
                 "  [facts reused]" if reused else ""))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--limit", type=int, default=None, metavar="N",
                    help="process at most N not-yet-scored calls")
    ap.add_argument("--golden", action="store_true",
                    help="only call_ids present in labels/golden_labels.csv")
    ap.add_argument("--model", default=None,
                    help="pass through to claude --model (default: CLI default)")
    ap.add_argument("--workers", type=int, default=1, metavar="N",
                    help="parallel claude calls (default 1 = sequential)")
    args = ap.parse_args()

    extract_prompt = open(EXTRACT_MD, encoding="utf-8").read()
    judge_prompt = open(JUDGE_MD, encoding="utf-8").read()
    registry = set(load_registry(RUBRIC))
    print("Registry: %d codes" % len(registry))

    with open(CALLS, encoding="utf-8") as f:
        calls = [json.loads(line) for line in f if line.strip()]
    if args.golden:
        wanted = golden_ids()
        calls = [c for c in calls if c["call_id"] in wanted]
        print("--golden: %d of %d golden call_ids found in calls.jsonl"
              % (len(calls), len(wanted)))

    os.makedirs(RESULTS, exist_ok=True)
    facts_done = load_jsonl_map(FACTS_OUT)
    scores_done = load_jsonl_map(SCORES_OUT)

    todo = [c for c in calls if c["call_id"] not in scores_done]
    skipped = len(calls) - len(todo)
    if args.limit is not None:
        todo = todo[:args.limit]
    print("Calls: %d selected, %d already scored (skipped), %d to run, %d worker(s)\n"
          % (len(calls), skipped, len(todo), args.workers))

    stats = {"cost": 0.0, "facts": 0, "scores": 0, "errors": 0, "done": 0}
    prompts = (extract_prompt, judge_prompt)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(process_call, call, len(todo), prompts,
                               registry, args.model, facts_done, stats)
                   for call in todo]
        for fut in concurrent.futures.as_completed(futures):
            fut.result()  # surface unexpected exceptions

    print("\nDone. facts written: %d, scores written: %d, errors: %d, "
          "skipped (already scored): %d"
          % (stats["facts"], stats["scores"], stats["errors"], skipped))
    print("Cumulative claude cost: $%.4f" % stats["cost"])
    if stats["errors"]:
        print("See %s" % os.path.relpath(ERRORS_LOG, ROOT))


if __name__ == "__main__":
    main()
