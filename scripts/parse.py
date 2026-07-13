#!/usr/bin/env python3
"""Parse transcripts/raw/*.txt into data/calls.jsonl (one JSON object per call).

Each turn is a header line followed by its text, e.g.:
    Agent (Mia) at 0.4s:
    Hello. You're speaking with Mia, a virtual assistant.

Speaker mapping:
    Agent (Mia)     -> agent_mia
    Agent (Human)   -> agent_human
    Customer        -> customer
    Unknown (<id>)  -> agent_human   # raw diarization IDs; by content they are human agents

Rules:
  * Turn order is preserved.
  * Tokens like [CUSTOMER_NAME], [REDACTED], [SENSITIVE_CONTENT], [PHONE_NUMBER] are kept verbatim.
  * Blank lines are skipped.
  * Tolerates files that begin mid-sentence (text before the first header is dropped, since it
    can't be attributed) or end mid-sentence (a trailing fragment/empty body is kept as-is).

Output object shape (one JSON line per call):
    {"call_id": "<filename without .txt>", "turns": [{"t": <float seconds>, "speaker": <str>, "text": <str>}, ...]}
"""
import argparse
import glob
import json
import os
import re
import statistics

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "transcripts", "raw")
OUT = os.path.join(ROOT, "data", "calls.jsonl")

HEADER = re.compile(r"^(.+?) at (\d+(?:\.\d+)?)s:$")
SPEAKER_MAP = {
    "Agent (Mia)": "agent_mia",
    "Agent (Human)": "agent_human",
    "Customer": "customer",
}
UNKNOWN = re.compile(r"^Unknown \(\d+\)$")


def map_speaker(label):
    if label in SPEAKER_MAP:
        return SPEAKER_MAP[label]
    if UNKNOWN.match(label):
        return "agent_human"
    return None  # unmapped -> caller treats the file as a failure


def parse_file(path):
    """Return (turns, error): turns is a list of {t, speaker, text}; error is None or a reason str."""
    turns = []
    cur = None
    for raw_line in open(path, encoding="utf-8").read().split("\n"):
        line = raw_line.strip()
        if not line:
            continue  # skip blank lines
        m = HEADER.match(line)
        if m:
            speaker = map_speaker(m.group(1))
            if speaker is None:
                return None, "unmapped speaker %r" % m.group(1)
            cur = {"t": float(m.group(2)), "speaker": speaker, "text": ""}
            turns.append(cur)
        elif cur is not None:
            # body text for the current turn (join multi-line bodies with a space)
            cur["text"] = (cur["text"] + " " + line) if cur["text"] else line
        # else: text before the first header (begins mid-sentence) -> unattributable, drop it
    if not turns:
        return None, "no turns parsed"
    return turns, None


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--raw", default=RAW, metavar="DIR",
                    help="directory of *.txt transcripts (default: transcripts/raw)")
    ap.add_argument("--out", default=OUT, metavar="FILE",
                    help="output jsonl (default: data/calls.jsonl)")
    ap.add_argument("--show", nargs="*", default=[], metavar="CALL_ID",
                    help="pretty-print these calls in full after parsing")
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.raw, "*.txt")))
    parsed = []    # list of (call_id, turns)
    failures = []  # list of (call_id, reason)
    for path in files:
        call_id = os.path.splitext(os.path.basename(path))[0]
        turns, err = parse_file(path)
        if err:
            failures.append((call_id, err))
        else:
            parsed.append((call_id, turns))

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        for call_id, turns in parsed:
            f.write(json.dumps({"call_id": call_id, "turns": turns}, ensure_ascii=False) + "\n")

    turn_counts = [len(t) for _, t in parsed]
    print("Wrote %s" % os.path.relpath(args.out, ROOT))
    print("total files : %d" % len(files))
    print("total parsed: %d" % len(parsed))
    if failures:
        print("failures    : %d -> %s"
              % (len(failures), ", ".join("%s (%s)" % f for f in failures)))
    else:
        print("failures    : 0")
    if turn_counts:
        print("turns/call  : min=%d  median=%g  max=%d"
              % (min(turn_counts), statistics.median(turn_counts), max(turn_counts)))

    # pretty-print requested calls in full (opt-in via --show)
    by_id = dict(parsed)
    for cid in args.show:
        print("\n" + "=" * 78)
        turns = by_id.get(cid)
        if turns is None:
            print("%s: NOT PARSED" % cid)
            continue
        print("%s  —  %d turns" % (cid, len(turns)))
        print("=" * 78)
        for tn in turns:
            print("[%7.1fs] %-12s %s" % (tn["t"], tn["speaker"], tn["text"]))


if __name__ == "__main__":
    main()
