# Mia Voice-Agent Evaluation — Final Report

**Date:** 2026-07-13 · **Corpus:** 200 calls (`data/calls.jsonl`) · **Rubric:** frozen v1
**Judge:** two-pass Claude pipeline (judge prompt v1.1, calibrated at **99.3%** criterion
agreement / **100%** terminal-state agreement against 18 human golden labels)
**Companion dashboard:** `report/final_report.html` · **Raw verdicts:** `results/scores.jsonl`

---

## 1. Executive summary

| | |
|---|---|
| **Calls fully clean** (no failure code of any kind) | **84 / 200 (42%)** |
| **Calls with ≥1 behavioral failure code** | 100 / 200 (50%) |
| **Calls failing ≥1 critical criterion** | 32 / 200 (16%) |
| **True behavioral failure-to-land rate** | **4 / 200 (2%)** |
| Transcripts cut mid-flow (evidence problem, not agent failure) | 28 / 200 (14%) |

**The headline:** Mia lands calls. Of 32 `failed` terminal states, **28 are
CUT_TRANSCRIPT** — the recording ends mid-flow, outcome unknowable — and only **4 calls
(2%)** genuinely failed to land (028, 093, 160, 195). Scope discipline is near-perfect
(1 violation in 200 calls) and the identity gate holds in 95% of calls.

**The cost:** conversational quality. **STATE_ECHO fires in 34% of all calls** — Mia
re-asks questions that were already answered — and the context-grounding family
(CONTEXT_IGNORED + WRONG_GUIDANCE, 21 calls) includes the corpus's signature defect:
**negation inversion**, where a caller's "No" is processed as a yes.

**New in this revision — containment leak:** a dedicated transfer-containment pass
(§6) found **11 calls (5.5%)** where Mia offered a human transfer that nobody asked
for on a need she could resolve herself — including **7 of the 127 transfers (5.5%)**
that should have been contained, each one billing avoidable human-agent time.

## 2. Methodology

```
200 raw transcripts → parse.py → calls.jsonl
  Pass A: extract.md + call  → claude headless → facts.jsonl   (literal facts)
  Pass B: judge.md + transcript + facts → claude → scores.jsonl (rubric verdicts)
  Validation: 8 criteria ∈ {Pass,Fail,NA} · 5 terminal states · 16-code registry ·
              outcome-code/state consistency · retry-once + bracket-repair fallback
```

Judge trustworthiness was established before the corpus run, against 18 human-labeled
golden calls:

| Gate | judge v1 | judge v1.1 (used for corpus) |
|---|---|---|
| Criterion agreement (144 verdicts) | 95.1% | **99.3%** |
| Terminal-state agreement | 18/18 | **18/18** |
| Failure-code micro F1 | 0.905 | 0.905 |
| Calibration anchors (028/042, 044/045, 065, 039) | 4/4 | 4/4 |

All 200 calls scored; 0 lost (14 transient JSON glitches auto-recovered via retry,
checkpointed re-run, or bracket repair). Total judge spend ≈ **$231**.

## 3. Where calls land

| Terminal state | Calls | % | Note |
|---|---|---|---|
| transferred | 127 | 63.5% | success state by design — human picked up |
| failed | 32 | 16.0% | 28 evidence-cuts + **4 behavioral** |
| callback | 22 | 11.0% | number captured + confirmed |
| resolved | 18 | 9.0% | answered fully in-call |
| declined | 1 | 0.5% | out-of-scope refused cleanly |

Six landings sit outside the frozen decision table and are flagged for label review
(080/112/162 payment→transferred, 125 service_timing→transferred, 097 lockout→declined,
197 data_upload→transferred).

## 4. Failure codes (behavioral — CUT_TRANSCRIPT excluded per rubric)

| Code | Severity | Calls | % of corpus |
|---|---|---|---|
| STATE_ECHO | minor | **68** | **34.0%** |
| MULTI_Q | minor | 23 | 11.5% |
| CONTEXT_IGNORED | major | 15 | 7.5% |
| ID_SKIPPED | critical | 7 | 3.5% |
| WRONG_GUIDANCE | critical | 6 | 3.0% |
| CB_NO_CONFIRM | major | 4 | 2.0% |
| ID_INVALID | critical | 3 | 1.5% |
| BYPASS_ENGAGED | critical | 1 | 0.5% |
| WRONG_TEAM | major | 1 | 0.5% |
| *CUT_TRANSCRIPT (evidence-only, reported separately)* | — | *28* | *14.0%* |

Never sighted in 200 calls: DROP_OFF, PRICE_QUOTED, ACTION_OVERSTEP, CB_DATE_PROMISED,
HALLUCINATED_POLICY, AFTER_HOURS_TRANSFER — six of the sixteen registry codes, including
four of the highest-severity overstep/accuracy codes. **Mia's forbidden-zone discipline
is excellent; her conversation-state discipline is not.**

Top co-occurrences: MULTI_Q+STATE_ECHO (10), CONTEXT_IGNORED+STATE_ECHO (6) — the flow
defects travel together.

## 5. Criterion scorecard

| Criterion | Pass | Fail | NA | Fail rate (of applicable) |
|---|---|---|---|---|
| identity (critical) | 190 | 10 | 0 | 5.0% |
| intent_class (critical) | 136 | 9 | 55 | 6.2% |
| terminal_correct (critical) | 165 | 7 | 28 | 4.1% |
| scope (critical, zero-tol) | 199 | **1** | 0 | **0.5%** |
| dropoff (critical, zero-tol) | 172 | **0** | 28 | **0.0%** |
| transfer_hygiene (major) | 158 | 1 | 41 | 0.6% |
| callback_quality (major) | 22 | 4 | 174 | **15.4%** |
| kb_fidelity (critical) | 112 | 9 | 79 | 7.4% |

The zero-tolerance criteria are effectively clean. The standout risk is
**callback_quality: 15.4% of callback flows fail** — and callback is the safety net
that catches failed transfers and closed-office calls.

## 6. Containment analysis: unsolicited transfer nudging (new)

**Trigger:** reviewer observation, corroborated by the golden label comment on 041
("Mia is unnecessarily nudging for human transfer"). **Method:** all 168 calls where
Pass A recorded a transfer offer/attempt were prescreened to 87 candidates (caller
never opened with an operator request), then a dedicated classifier pass (Pass C,
`prompts/containment.md`) judged each against Mia's capability zone with the designed
transfer flows excluded (bypass decline-redirects, permanent-lockout specialist
routing, with-notice removals, failed-transfer fallbacks). Every quote below is
**mechanically verified verbatim** against the cited transcript turn.

| Bucket | Calls | Meaning |
|---|---|---|
| justified_transfer | 71 | need genuinely required a human or a designed flow |
| **containable_but_transferred** | **7** | in-scope need, yet the call left Mia's hands |
| caller_requested | 5 | caller did ask for a human mid-call (prescreen refinement) |
| **resolved_then_nudged** | **3** | call resolved; the offer was pure friction |
| **partially_containable** | **1** | containable part escalated before being attempted |

**Flagged: 11/200 calls (5.5% of corpus) · 7/127 transfers (5.5%) were containable.**

The signature move is a trailing *"Would you like to speak with customer support as
well?"* **after the need is already resolved** — present in 7 of the 11 flags. When
the caller politely accepts, a contained call converts into a paid human interaction:
041 and 149 are near-identical resolved flows, but 041's caller said *"No. Thank you."*
(stayed resolved) while 149's said yes (became a transfer).

Evidence exemplars (full set: `results/containment.json`):

| Call | Turn | Verbatim evidence |
|---|---|---|
| 041 (resolved_then_nudged) | 10→14 | "Sent you a text with the hub link to check your end date." → *"Would you like to speak with customer support as well?"* → caller: "No. Thank you." |
| 149 (containable→transferred) | 10→14 | same flow, nudge accepted → *"I'll get you over to our customer support team now."* |
| 092 (containable, ended failed) | 1→4 | caller: "A medium recall." → Mia, without attempting the documented recall flow: *"Would you like me to connect you to our customer support team now?"* |
| 154 (partially containable) | 10→25 | Mia at t10: *"I'll connect you with a specialist…"* — the **human** then answers with policy Mia knew: *"additional seven days. So you've got till close of business next Thursday, June 25."* |
| 197 (containable→transferred) | 10→25 | grace-window question → instant *"I'll get you over to our customer support team now…"*; human's answer was again the seven-day policy |
| 180 (containable→transferred) | 10→20 | payment handled via Mia's own link at t10, then *"Would you like to speak with customer support as well?"* |

**Rubric note:** TRANSFER_NUDGE is hereby a candidate **nursery pattern** (11 sightings
— well past the 3-sighting graduation bar for rubric v2). The frozen v1 rubric is
untouched; this analysis lives beside it.

## 7. Top 4 recommendations

---

### TASK 1 — Make Mia act on what the caller actually said

**Priority:** P0 · **Owner:** Dialog/NLU + prompt engineering

**The problem, in plain words:** in 21 calls (about 1 in 10), Mia's next move
contradicted something the caller had *just told her*. The worst version: the caller
says **"No"** and Mia carries on as if they said yes. In 028 she read a phone number
back, the caller said "No", and she replied *"Perfect. I've noted your details"* —
keeping the wrong number. In 035 the caller said *"I have NOT received one"* and Mia
thanked him *"for confirming you've received your completion notice."* In 065 the
caller confirmed the serious type of lockout and Mia gave the advice for the mild
type — the caller had to correct her.

**What to do about it:** before Mia acts on any answer, sort it into *yes / no /
unclear* — "no" and "unclear" always mean ask again, never proceed. And once the
caller has confirmed a fact (which lockout type, whether the notice arrived), keep it
in memory for the whole call so her advice can't contradict it. Test the fix by
replaying calls 028, 035, 065 and 073.

**How we'll know it worked:** on a fresh 200-call run, ≤ 3 calls carry these codes
(today: 21), and zero "No-treated-as-Yes" events on the 18 golden calls.

---

### TASK 2 — Stop Mia repeating questions that were already answered

**Priority:** P1 · **Owner:** Voice-agent flow/state-machine engineering

**The problem, in plain words:** in **1 of every 3 calls**, Mia re-asks something the
caller already answered — usually asking "are you ready to be connected?" again right
after the caller said yes (040, 042, 099), and in one case re-asking for a name that
had just been given (044). When a caller talks over her, she restarts her whole
message from the beginning instead of picking up where she left off (043). It makes
her sound broken and stretches out every call.

**What to do about it:** once an answer is in, mark that question as done so it can't
fire again; when the caller interrupts, continue the sentence — don't start over.

**How we'll know it worked:** STATE_ECHO falls from 34% of calls to 10% or less, and
the 18 golden calls show zero repeated consent questions.

---

### TASK 3 — Always capture the caller's name before doing anything

**Priority:** P1 · **Owner:** Voice-agent flow engineering

**The problem, in plain words:** in 10 calls Mia either never asked who was calling
before sending links or transferring (7 calls, e.g. 084, 111), or accepted something
that obviously wasn't a name and moved on anyway (3 calls, e.g. 066, 146). The
frustrating part: she already knows the right behavior — in call 039 she noticed a
garbled answer, politely queried it, and asked again. It just isn't enforced
everywhere.

**What to do about it:** make the name a hard gate — links, transfers and callbacks
simply cannot happen until a plausible name is captured. If the answer doesn't look
like a name, ask one more time, exactly like call 039 did.

**How we'll know it worked:** zero identity failures on a fresh run (today: 10).

---

### TASK 4 — Don't offer a human when Mia already solved it ⭐ NEW

**Priority:** P1 · **Owner:** Voice-agent flow/prompt engineering

**The problem, in plain words:** Mia has a habit of finishing a call she just solved
with *"Would you like to speak with customer support as well?"* — an offer nobody
asked for. Polite callers say yes, and a call Mia handled becomes a human handoff
that costs agent time. We flagged 11 such calls: 7 became transfers she could have
kept, 3 stayed resolved but carried the pointless offer, 1 was mixed. The cleanest
proof is the pair 041/149 — two nearly identical solved calls, where 041's caller
said "No. Thank you." (call stayed resolved) and 149's said yes (call became a
transfer). And twice (154, 197), the human who took the handoff answered with the
exact seven-day policy Mia already knows.

**What to do about it:** only offer a human when the caller asks, when the task is
genuinely beyond her (payments, bookings, prices, unlock codes, legal), or when the
designed flow requires it. After solving the request, say goodbye — drop the trailing
offer. For policy questions she can answer, answer first and escalate only if that
didn't help.

**How we'll know it worked:** flagged nudges drop from 11 to ≤ 2 on a fresh run
(re-run `scripts/containment.py`); the share of transferred calls falls without
failed calls rising.

---

**Watch items (below top-4 threshold):** callback confirmation robustness
(CB_NO_CONFIRM — only 4 sightings but 15.4% of the flows where it can occur; fold into
Task 2's polarity work) · MULTI_Q compound questions (23 calls; style guide + prompt
fix) · CUT_TRANSCRIPT 14% is a **platform/telephony** recording-pipeline issue, not an
agent defect — route to the platform team to determine whether recordings clip or calls
genuinely drop.

## 8. How we'll know the fixes worked

**The eval built for this report is itself the measurement instrument.** The rubric is
frozen, the judge is calibrated against human labels (99.3% agreement), and every step
is scripted and checkpointed — so the same yardstick can be laid against Mia before
and after any change. The loop:

1. **Freeze the yardstick.** Rubric v1 and judge v1.1 don't change between
   measurements. Before each measurement run, re-check the judge against the 18
   golden calls (`python3 scripts/compare.py`) — agreement must stay ≥ 99%. If the
   yardstick moved, fix that first; never compare scores from different judges.
2. **Ship one fix, then collect a fresh batch of ~200 calls.** The existing 200
   transcripts are recordings of *old* behavior — they can prove a regression suite
   passes, but only new calls can prove the live agent improved.
3. **Run the identical pipeline** on the new batch:
   `parse.py → run_eval.py --workers 8 → analyze.py → containment.py --workers 8`.
4. **Compare the new `summary.json` against this report's baseline.** The scoreboard:

| Fix | Metric to watch | Baseline (this report) | Target |
|---|---|---|---|
| 1 · Act on what the caller said | CONTEXT_IGNORED + WRONG_GUIDANCE calls | 21 (10.5%) | ≤ 3 (1.5%) |
| 2 · Stop repeating questions | STATE_ECHO calls | 68 (34%) | ≤ 20 (10%) |
| 3 · Name before action | identity criterion fails | 10 (5%) | 0 |
| 4 · Keep solved calls | flagged transfer nudges | 11 (5.5%) | ≤ 2 |

5. **Watch the guardrails** — improvement in one place must not break another:
   scope violations stay ≤ 1, `failed` share doesn't rise above 16%, fully-clean
   calls climb from 42%, and `resolved` share should climb as containment improves
   (every kept call moves from transferred to resolved).

**Two honest caveats.** First, rare events are noisy: with 200-call batches, a code
that fired 4–10 times can swing by a few counts by pure chance — treat single-digit
movement on rare codes as directional and confirm with a second batch before
declaring victory. Second, change one thing at a time (or, if the platform supports
it, run an A/B split — route half the calls to updated Mia, score both arms with the
same judge, and compare rates directly; that is the strongest causal evidence).

## 9. Pipeline health & reproducibility

- 200/200 calls scored · 0 lost · transient errors auto-recovered (retry / sweep /
  bracket-repair, all logged in `results/errors.log`)
- 87/87 containment candidates classified (Pass C), quote citations mechanically
  substring-verified against transcripts
- Judge spend ≈ $262 total (incl. calibration, re-runs, containment pass) · 8-worker
  parallel runtime ~50 min for the 182-call corpus leg
- Reproduce: `python3 scripts/run_eval.py --workers 8` (checkpointed; reruns skip
  scored calls) → `python3 scripts/analyze.py` → `python3 scripts/compare.py` (golden
  agreement) → `python3 scripts/containment.py --workers 8` · aggregates in
  `results/summary.json` and `results/containment.json`
