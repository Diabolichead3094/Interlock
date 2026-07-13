#!/usr/bin/env python3
"""One command: a folder of new call .txt files -> scored batch -> dashboard.

    python3 scripts/new_batch.py /path/to/new_txt_folder
    python3 scripts/new_batch.py calls_july/ --name 2026-07-14 --deploy

Steps (fail-fast, all idempotent — re-run the same command to resume):
  1. stage    copy *.txt into batches/<name>/raw/
  2. parse    -> batches/<name>/calls.jsonl (abort on parse failures)
  3. gate     re-validate the judge against the 18 golden calls (Pass B only,
              ~$10); ABORT the batch if overall agreement < 99% or terminal-
              state agreement < 18/18 — the yardstick moved, don't spend
  4. score    two-pass judge over the batch (checkpointed, parallel) + sweep
  5. analyze  -> batches/<name>/results/summary.json
  6. contain  transfer-containment pass + sweep
  7. report   regenerate report/final_report.html with baseline deltas vs the
              previous batch (auto-detected); copy to batches/<name>/dashboard.html
  8. deploy   (--deploy only) rebuild deploy/index.html and push to Vercel

Cost guide: ~$1.3/call for judging + ~$0.35 per transfer-offer call for
containment + $10 gate. A 400-call batch ≈ $600 and ~2-2.5 h at 8 workers.
Safe to interrupt: re-running skips everything already scored.
"""
import argparse
import csv
import datetime
import glob
import json
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
GOLDEN_CSV = os.path.join(ROOT, "labels", "golden_labels.csv")
ROOT_FACTS = os.path.join(ROOT, "results", "facts.jsonl")
BATCHES = os.path.join(ROOT, "batches")

GATE_MIN_OVERALL = 99.0


def banner(step, msg):
    print("\n" + "=" * 72 + "\n== %s  %s\n" % (step, msg) + "=" * 72)


def run(cmd, capture=False):
    """Run a pipeline stage; stream output live unless capture=True."""
    print("$ " + " ".join(os.path.relpath(c, ROOT) if os.path.isabs(c) else c
                          for c in cmd))
    if capture:
        p = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
        print(p.stdout, end="")
        if p.returncode != 0:
            print(p.stderr, end="")
            raise SystemExit("stage failed: %s" % " ".join(cmd))
        return p.stdout
    p = subprocess.run(cmd, cwd=ROOT)
    if p.returncode != 0:
        raise SystemExit("stage failed: %s" % " ".join(cmd))
    return None


def count_lines(path):
    if not os.path.exists(path):
        return 0
    with open(path, encoding="utf-8") as f:
        return sum(1 for l in f if l.strip())


def golden_ids():
    with open(GOLDEN_CSV, encoding="utf-8", newline="") as f:
        return {r["Call_ID"].strip() for r in csv.DictReader(f) if r.get("Call_ID")}


def resolve_baseline(choice, batch_dir):
    if choice == "none":
        return None
    if choice != "auto":
        return choice
    others = sorted(d for d in glob.glob(os.path.join(BATCHES, "*"))
                    if os.path.isdir(d) and os.path.abspath(d) != os.path.abspath(batch_dir)
                    and os.path.exists(os.path.join(d, "results", "scores.jsonl")))
    if others:
        return os.path.join(others[-1], "results")   # most recent other batch
    if os.path.exists(os.path.join(ROOT, "results", "scores.jsonl")):
        return os.path.join(ROOT, "results")          # batch zero
    return None


def main():
    ap = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("txt_folder", help="folder containing the new *.txt transcripts")
    ap.add_argument("--name", default=datetime.date.today().isoformat(),
                    help="batch name (default: today's date)")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--baseline", default="auto", metavar="auto|DIR|none",
                    help="results dir for ▲▼ deltas (default auto = previous batch)")
    ap.add_argument("--skip-gate", action="store_true",
                    help="skip golden re-validation (NOT recommended)")
    ap.add_argument("--deploy", action="store_true",
                    help="after the report, rebuild deploy/index.html and push to Vercel")
    ap.add_argument("--limit", type=int, default=None,
                    help="score at most N calls (testing)")
    ap.add_argument("--model", default=None, help="claude --model override")
    args = ap.parse_args()

    batch = os.path.join(BATCHES, args.name)
    raw, results = os.path.join(batch, "raw"), os.path.join(batch, "results")
    gate = os.path.join(batch, "gate")
    calls_jsonl = os.path.join(batch, "calls.jsonl")
    passthru = (["--model", args.model] if args.model else [])
    limit = (["--limit", str(args.limit)] if args.limit is not None else [])

    # -- 1. stage ------------------------------------------------------------
    banner("1/8 stage", "batches/%s" % args.name)
    src = sorted(glob.glob(os.path.join(args.txt_folder, "*.txt")))
    if not src:
        raise SystemExit("no .txt files in %s" % args.txt_folder)
    os.makedirs(raw, exist_ok=True)
    copied = 0
    for p in src:
        dst = os.path.join(raw, os.path.basename(p))
        if not os.path.exists(dst):
            shutil.copyfile(p, dst)
            copied += 1
    names = [os.path.splitext(os.path.basename(p))[0] for p in src]
    if len(set(names)) != len(names):
        raise SystemExit("duplicate call_ids in the input folder")
    print("staged %d file(s) (%d newly copied) -> %s"
          % (len(src), copied, os.path.relpath(raw, ROOT)))

    # -- 2. parse -------------------------------------------------------------
    banner("2/8 parse", "raw .txt -> calls.jsonl")
    run([sys.executable, os.path.join(SCRIPTS, "parse.py"),
         "--raw", raw, "--out", calls_jsonl])
    n_parsed = count_lines(calls_jsonl)
    if n_parsed != len(src):
        raise SystemExit("parse failures: %d file(s) did not parse — fix before scoring"
                         % (len(src) - n_parsed))

    # -- 3. golden gate --------------------------------------------------------
    if args.skip_gate:
        banner("3/8 gate", "SKIPPED (--skip-gate)")
        gate_line = "skipped"
    else:
        banner("3/8 gate", "judge re-validation vs 18 golden calls (Pass B only)")
        os.makedirs(gate, exist_ok=True)
        gate_facts = os.path.join(gate, "facts.jsonl")
        if not os.path.exists(gate_facts):
            gids = golden_ids()
            with open(ROOT_FACTS, encoding="utf-8") as fin, \
                 open(gate_facts, "w", encoding="utf-8") as fout:
                for line in fin:
                    if line.strip() and json.loads(line)["call_id"] in gids:
                        fout.write(line)
            print("seeded %d golden facts (Pass A reused, only Pass B re-runs)"
                  % count_lines(gate_facts))
        n_golden = len(golden_ids())
        for attempt in range(3):   # main run + up to 2 sweeps for JSON glitches
            run([sys.executable, os.path.join(SCRIPTS, "run_eval.py"), "--golden",
                 "--results", gate, "--workers", str(args.workers if attempt == 0 else 2)]
                + passthru)
            if count_lines(os.path.join(gate, "scores.jsonl")) >= n_golden:
                break
        out = run([sys.executable, os.path.join(SCRIPTS, "compare.py"),
                   "--scores", os.path.join(gate, "scores.jsonl")], capture=True)
        m = re.search(r"OVERALL\s+(\d+)/(\d+)\s+([\d.]+)%", out)
        j = re.search(r"joined on Call_ID:\s+(\d+)", out)
        t = re.search(r"TERMINAL-STATE AGREEMENT\s*\n=+\n\s+(\d+)/(\d+)", out)
        overall = float(m.group(3)) if m else 0.0
        joined = int(j.group(1)) if j else 0
        term_ok = t and t.group(1) == t.group(2)
        gate_line = "criterion %.1f%%, terminal %s/%s, %d/%d golden scored" % (
            overall, t.group(1) if t else "?", t.group(2) if t else "?",
            joined, n_golden)
        if overall < GATE_MIN_OVERALL or not term_ok or joined < n_golden:
            raise SystemExit(
                "\nGATE FAILED (%s). The judge no longer matches the golden labels —\n"
                "do NOT spend on this batch. Investigate prompts/judge.md or model drift."
                % gate_line)
        print("\nGATE PASSED: %s" % gate_line)

    # -- 4. score ---------------------------------------------------------------
    banner("4/8 score", "two-pass judge, %d workers" % args.workers)
    run([sys.executable, os.path.join(SCRIPTS, "run_eval.py"),
         "--calls", calls_jsonl, "--results", results,
         "--workers", str(args.workers)] + passthru + limit)
    if count_lines(os.path.join(results, "scores.jsonl")) < (args.limit or n_parsed):
        print("\n-- sweep: retrying stragglers")
        run([sys.executable, os.path.join(SCRIPTS, "run_eval.py"),
             "--calls", calls_jsonl, "--results", results, "--workers", "2"]
            + passthru + limit)
    n_scored = count_lines(os.path.join(results, "scores.jsonl"))
    target = args.limit or n_parsed
    if n_scored < target:
        print("WARNING: %d/%d scored after sweep — see %s/errors.log; "
              "re-run this command to retry" % (n_scored, target, results))

    # -- 5. analyze ---------------------------------------------------------------
    banner("5/8 analyze", "aggregates -> summary.json")
    run([sys.executable, os.path.join(SCRIPTS, "analyze.py"), "--results", results])

    # -- 6. containment -------------------------------------------------------------
    banner("6/8 containment", "unsolicited-transfer pass")
    for w in (str(args.workers), "2"):   # main run + one sweep
        run([sys.executable, os.path.join(SCRIPTS, "containment.py"),
             "--calls", calls_jsonl, "--results", results,
             "--workers", w] + passthru)

    # -- 7. report --------------------------------------------------------------------
    baseline = resolve_baseline(args.baseline, batch)
    banner("7/8 report", "dashboard%s" % (
        " with deltas vs " + os.path.relpath(baseline, ROOT) if baseline else ""))
    cmd = [sys.executable, os.path.join(SCRIPTS, "build_report.py"),
           "--calls", calls_jsonl, "--results", results,
           "--out", os.path.join(ROOT, "report", "final_report.html")]
    if baseline:
        cmd += ["--baseline", baseline]
    run(cmd)
    shutil.copyfile(os.path.join(ROOT, "report", "final_report.html"),
                    os.path.join(batch, "dashboard.html"))

    # -- 8. deploy ---------------------------------------------------------------------
    if args.deploy:
        banner("8/8 deploy", "Vercel production")
        dcmd = [sys.executable, os.path.join(SCRIPTS, "build_report.py"),
                "--calls", calls_jsonl, "--results", results,
                "--out", os.path.join(ROOT, "deploy", "index.html")]
        if baseline:
            dcmd += ["--baseline", baseline]
        run(dcmd)
        vercel = shutil.which("vercel")
        if vercel:
            subprocess.run([vercel, "deploy", "--prod", "--yes"],
                           cwd=os.path.join(ROOT, "deploy"))
        else:
            print("vercel CLI not found — run manually: cd deploy && vercel deploy --prod")
    else:
        banner("8/8 deploy", "skipped (pass --deploy to publish)")

    # -- batch card ------------------------------------------------------------------------
    summ = json.load(open(os.path.join(results, "summary.json")))
    cont = json.load(open(os.path.join(results, "containment.json")))
    print("\n" + "#" * 72)
    print("BATCH %s COMPLETE" % args.name)
    print("#" * 72)
    print("calls scored      : %d" % summ["n_calls"])
    print("golden gate       : %s" % gate_line)
    print("terminal states   : " + "  ".join(
        "%s %d" % (k, v["count"]) for k, v in summ["terminal_states"].items()))
    print("fully clean       : %d (%.1f%%)" % (summ["calls_fully_clean"]["count"],
                                               summ["calls_fully_clean"]["pct"]))
    print("critical fails    : %d (%.1f%%)"
          % (summ["calls_failing_any_critical_criterion"]["count"],
             summ["calls_failing_any_critical_criterion"]["pct"]))
    print("transfer nudges   : %d flagged (%s containable transfers)"
          % (cont["flagged_total"]["count"], cont["flagged_transferred"]["count"]))
    print("dashboard         : report/final_report.html  (+ %s)"
          % os.path.relpath(os.path.join(batch, "dashboard.html"), ROOT))
    print("baseline          : %s" % (os.path.relpath(baseline, ROOT) if baseline else "none"))


if __name__ == "__main__":
    main()
