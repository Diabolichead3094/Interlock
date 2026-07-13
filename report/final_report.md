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

### TASK 1 — Make satisfied dialog states idempotent (kill STATE_ECHO)

**Priority:** P1 (highest frequency — 1 in 3 calls) · **Severity family:** minor, but the
dominant UX drag and a multiplier on every other defect
**Suggested owner:** Voice-agent flow/state-machine engineering

**Evidence:** 68/200 calls (34%). Signature patterns: consent re-asked after a clean
"Yes" (040, 042, 099), the identity gate re-fired after the name was given (044), an
interrupted message restarted from the top instead of resuming (043). Co-occurs with
6 of the 9 other behavioral codes.

**Implementation approach:**
1. Audit the dialog state machine for transitions that re-enter a satisfied state;
   add a `slot_filled` guard so a state that has consumed a valid answer cannot re-fire.
2. Parse-and-commit affirmatives on first hearing: once consent/name/number is
   captured, downstream prompts must read the slot, not re-elicit it.
3. Fix barge-in handling: on interruption, resume the pending utterance from the
   sentence boundary, never from the top (043's restart pattern).
4. Regression-test against the eval: replay the 68 flagged calls' scenarios.

**Acceptance criteria:** STATE_ECHO ≤ 10% of calls on a corpus re-run of this eval;
zero double consent-asks in the 18-call golden set.

---

### TASK 2 — Ground actions in caller-confirmed facts (kill negation inversion)

**Priority:** P0 (highest severity-weighted — includes critical WRONG_GUIDANCE)
**Suggested owner:** Dialog/NLU engineering + prompt engineering (joint)

**Evidence:** 21/200 calls (10.5%): CONTEXT_IGNORED 15 (major), WRONG_GUIDANCE 6
(critical). The corpus's signature error is **negation inversion** — caller says "No"
to the number read-back and Mia replies "Perfect, I've noted your details" (028);
caller says "I have NOT received one" and Mia thanks him "for confirming you've
RECEIVED your completion notice" (035). WRONG_GUIDANCE exemplar: countdown-timer
advice after the caller confirmed a permanent lockout (065; also 020, 022, 056).

**Implementation approach:**
1. Add an explicit polarity check on every confirmation slot: classify the caller's
   answer {affirm / deny / unclear} before branching; "deny" and "unclear" must
   re-elicit, never proceed.
2. Persist confirmed situation facts (lockout type, completion-notice status, form
   already submitted) as structured slots; make guidance branches read the slot and
   hard-block advice that contradicts it (no countdown advice when
   `lockout_type=permanent`).
3. Build a negation regression suite directly from the eval's anchor calls
   (028, 035, 065, 073) plus the 21 flagged call_ids in `results/summary.json`.

**Acceptance criteria:** zero negation inversions on the golden set;
CONTEXT_IGNORED + WRONG_GUIDANCE combined ≤ 1.5% of calls on corpus re-run.

---

### TASK 3 — Enforce the identity gate before any action

**Priority:** P1 (critical severity, zero-tolerance criterion) ·
**Suggested owner:** Voice-agent flow engineering

**Evidence:** 10/200 calls (5%) fail the identity criterion: ID_SKIPPED 7 (name never
requested before an action/link/transfer — 084, 111 among worst), ID_INVALID 3 (an
obviously-not-a-name accepted and Mia proceeded — 066, 146). The rubric's positive
exemplar already exists in production behavior: 039 queried a garbled name-slot
answer and re-asked.

**Implementation approach:**
1. Make name-capture a hard precondition on the action states (send link, transfer,
   callback capture): the transition is unreachable while `name_captured=false`.
2. Add a name-plausibility validator on the slot (reject digits/command words/garble);
   on rejection, re-ask once as in 039 rather than accepting.
3. Keep v1 leniency intentional: first-name-only still passes (per rubric);
   log nursery ID_PARTIAL for tracking.

**Acceptance criteria:** identity criterion fail rate 0% on corpus re-run
(ID_SKIPPED = 0, ID_INVALID = 0).

---

### TASK 4 — Stop unsolicited transfer nudges; close resolved calls ⭐ NEW

**Priority:** P1 (direct operational cost — every containable transfer bills human-agent
time; also caps Mia's measurable containment rate)
**Suggested owner:** Voice-agent flow/prompt engineering

**Evidence (§6; all quotes verbatim, turn-cited):** 11 calls flagged (5.5%), of which
**7 transfers were containable** (092, 024, 051, 122, 149, 180, 197) and 3 resolved
calls carried a pointless closing nudge (015, 035, 041). The trailing
*"Would you like to speak with customer support as well?"* fires **after the need is
already resolved** in 7 of 11 flags; 092 escalated at turn 4 without attempting the
documented recall flow; in 154 and 197 the human's post-transfer answer was the
seven-day grace-window policy Mia already knows.

**Implementation approach:**
1. Gate the transfer offer on three conditions only: (a) caller asked for a human,
   (b) the need requires a CANNOT-zone action (price, booking, payment-taking, record
   edit, unlock code, legal), or (c) a designed flow mandates it (bypass redirect,
   permanent lockout, with-notice removal). Otherwise the offer state is unreachable.
2. Replace the resolved-state closer: after every accepted action is confirmed
   delivered, go to farewell — remove the appended "speak with customer support as
   well?" prompt (the 041 vs 149 pair shows the same call resolving or transferring
   on this single sentence).
3. For policy questions Mia can answer (grace windows, recall flows), require one
   containment attempt before any escalation offer (fixes 092/154/197-class exits).
4. Re-run `scripts/containment.py` after the change to re-measure.

**Acceptance criteria:** containable_but_transferred + resolved_then_nudged ≤ 2 calls
on corpus re-run; transferred share of terminal states drops with no rise in failed.

---

**Watch items (below top-4 threshold):** callback confirmation robustness
(CB_NO_CONFIRM — only 4 sightings but 15.4% of the flows where it can occur; fold into
Task 2's polarity work) · MULTI_Q compound questions (23 calls; style guide + prompt
fix) · CUT_TRANSCRIPT 14% is a **platform/telephony** recording-pipeline issue, not an
agent defect — route to the platform team to determine whether recordings clip or calls
genuinely drop.

## 8. Pipeline health & reproducibility

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
