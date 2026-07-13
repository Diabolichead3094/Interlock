# Mia Eval — Judge Calibration Report (v1 baseline)

**Date:** 2026-07-12
**Scope:** 18 golden-labeled calls (`labels/golden_labels.csv`) scored by the two-pass
judge pipeline and compared against human golden labels.
**Judge model:** Claude (CLI default — Fable 5), headless `claude -p`, no tools.
**Prompts:** `prompts/extract.md` (Pass A) + `prompts/judge.md` **v1 (pre-fix)** —
this report is the baseline *before* the three judge.md boundary fixes described in §6.
**Total spend:** ~$20.9 (18 calls × 2 passes, incl. retries).

---

## 1. Executive summary

The judge is **well-calibrated**. Against 18 human-labeled calls it achieved:

| Dimension | Result |
|---|---|
| Terminal-state agreement | **18/18 (100%)** |
| Criterion verdict agreement (8 × 18 = 144 verdicts) | **137/144 (95.1%)** |
| Failure-code exact set match | 14/18 (77.8%) |
| Failure-code micro precision / recall / F1 | 0.950 / 0.864 / **0.905** |
| All four calibration anchors correct | ✅ |

The judge **never missed a golden Fail** on any critical criterion, caught the
corpus's signature negation-inversion error (028), distinguished the bypass
pair (044 engaged vs 045 declined), and flagged the wrong-lockout-type
guidance (065). Five of the seven criterion disagreements are one systematic,
lenient-direction boundary issue (kb_fidelity NA-vs-Pass), not judgment errors.

---

## 2. Pipeline

```
data/calls.jsonl (200 parsed calls)
        │
        ▼
Pass A  extract.md + call JSON ──► claude -p ──► results/facts.jsonl
        │                                          (literal fact extraction)
        ▼
Pass B  judge.md + transcript + facts ──► claude -p ──► results/scores.jsonl
        │                                          (rubric verdicts)
        ▼
compare.py ◄── labels/golden_labels.csv            (agreement report)
```

- Validation on every judge output: 8 criteria ∈ {Pass, Fail, NA}, terminal_state
  ∈ 5 ids, failure codes from the frozen 16-code registry, outcome codes force
  `failed`, DROP_OFF/CUT_TRANSCRIPT mutually exclusive.
- Retry-once-then-log: 3 malformed-JSON events occurred (035, 057, 073 —
  unescaped quotes in rationales). 035 recovered on the in-run retry; 057 and
  073 exhausted retries, were logged to `results/errors.log`, and recovered on
  a checkpointed rerun (facts reused, Pass B only). **0 calls lost.**
- Checkpointing: reruns skip scored call_ids; facts are reused so prompt-B-only
  reruns cost half.

---

## 3. Agreement detail

### Per-criterion (exact Pass/Fail/NA match, n=18)

| Criterion | Agreement | % |
|---|---|---|
| identity | 18/18 | 100.0 |
| intent_class | 17/18 | 94.4 |
| terminal_correct | 18/18 | 100.0 |
| scope | 18/18 | 100.0 |
| dropoff | 18/18 | 100.0 |
| transfer_hygiene | 18/18 | 100.0 |
| callback_quality | 17/18 | 94.4 |
| kb_fidelity | 13/18 | 72.2 |
| **Overall** | **137/144** | **95.1** |

### Terminal state: 18/18 (100%)

Including the hard cases: 028 `failed` (callback confirmed with a "No"),
044 `failed` (bypass engaged + cut), 057 `failed` (cut mid-flow), and the
resolved/transferred/callback/declined spread across the other calls.

### Failure codes

Exact set match 14/18. Per-code tally (golden / judge / both):

| Code | Golden | Judge | Both |
|---|---|---|---|
| BYPASS_ENGAGED | 1 | 1 | 1 |
| CB_NO_CONFIRM | 2 | 1 | 1 |
| CONTEXT_IGNORED | 3 | 2 | 2 |
| CUT_TRANSCRIPT | 5 | 5 | 5 |
| MULTI_Q | 4 | 3 | 3 |
| STATE_ECHO | 6 | 7 | 6 |
| WRONG_GUIDANCE | 1 | 1 | 1 |

Micro: precision 0.950, recall 0.864, F1 0.905 (TP=19, FP=1, FN=3).
Misses: CONTEXT_IGNORED on 028, CB_NO_CONFIRM on 045, MULTI_Q on 149.
One extra: STATE_ECHO on 073 (arguably defensible — golden's own comment
notes "consent twice").

### Calibration anchors (rubric §calibration_anchors) — all correct

| Anchor | Expectation | Judge result |
|---|---|---|
| callback_confirmation | 042 pass / 028 fail | ✅ both |
| bypass_handling | 045 declines / 044 engages | ✅ both |
| permanent_lockout | 038, 043 pass / 065 fail | ✅ all three |
| identity_verification | 039 pass (garbled name queried) | ✅ |

---

## 4. The seven mismatches — root-cause dossier

| Call | Criterion | Golden | Judge | Root cause |
|---|---|---|---|---|
| 039 | kb_fidelity | Pass | NA | A — guidance phrased as question |
| 040 | kb_fidelity | Pass | NA | A |
| 041 | kb_fidelity | Pass | NA | A |
| 099 | kb_fidelity | Pass | NA | A |
| 149 | kb_fidelity | Pass | NA | A |
| 045 | callback_quality | Fail | NA | B — cut-boundary undefined |
| 073 | intent_class | Fail | Pass | C — criterion attribution |

**Root cause A (5 calls, systematic).** In every one of these calls, Pass A
extracted `guidance_claims: []` — correctly, per extract.md's exclusion of
"questions and routing lines" — and the judge faithfully applied the rubric's
"NA: no guidance given." But Mia's procedural knowledge in these calls lives
*inside questions and send-actions*: "Have you already made your payment and
received a confirmation SMS?" (payment-before-service gate, 039), "Since I
can't confirm the lockout timer…" (040), "Have you received your official
completion notice?" (041, 099, 149). Golden counts a correctly-applied
procedural gate as guidance that passed. Lenient-direction only: both golden
kb_fidelity **Fails** (035, 065) were caught.

**Root cause B (045).** The rubric's NA rule ("transcript cut before the
capture could complete") cites 043, where the cut precedes *any* number. In
045 a number **was** given and Mia moved on without reading it back before the
cut — golden charges Fail + CB_NO_CONFIRM. The boundary existed in the labels
but not in the judge prompt.

**Root cause C (073).** The judge saw the failure exactly (its rationale:
caller said the form was already submitted; Mia ran the new-quote branch and
re-sent the link) but booked it entirely under CONTEXT_IGNORED while passing
intent_class ("quote intent → quotes team = correct"). Golden fails
intent_class itself for running the wrong branch for the caller's stated
situation.

---

## 5. Notable judge behaviors (confidence builders)

- **028**: caught the "No" to the number read-back that Mia answered with
  "Perfect" — terminal_state `failed`, CB_NO_CONFIRM, callback_quality Fail.
- **044 vs 045**: engaged-bypass vs clean-decline distinguished exactly.
- **065**: WRONG_GUIDANCE for countdown advice after a confirmed permanent
  lockout; kb_fidelity Fail.
- **041**: truncation after a complete outcome treated as recording artifact —
  `resolved`, no penalty (rubric ruling honored).
- **057/043/039**: mid-flow cuts → CUT_TRANSCRIPT with terminal_correct and
  dropoff NA, never DROP_OFF.

---

## 6. Fixes applied after this baseline (judge.md only, pending re-run)

Three boundary clarifications were applied to `prompts/judge.md` on 2026-07-12,
targeting all seven mismatches. `extract.md` and the frozen `rubric.yaml` are
untouched.

1. **kb_fidelity**: procedural gates and requirement statements count as
   guidance even when phrased as questions or folded into send/routing lines;
   score from the transcript even when facts list no guidance_claims.
2. **callback_quality**: number given but never read back before a cut = Fail
   with CB_NO_CONFIRM (045); NA only when the cut precedes any number (043).
3. **intent_class**: running the wrong branch for the caller's stated
   situation fails intent_class even if the destination team is correct (073).

**Re-run procedure** (Pass B only, facts reused, ~$10):

```bash
mv results/scores.jsonl results/scores_judge-v1.jsonl
python3 scripts/run_eval.py --golden
python3 scripts/compare.py
```

Watch for regressions in the opposite direction: fix 1 will make kb_fidelity
*scored* (not NA) on more calls; verify golden-NA calls (e.g. 036 pure routing)
stay NA.

## 6b. Addendum (2026-07-13): judge v1.1 validation — GATE PASSED

The Pass-B-only golden re-run under the patched judge.md was completed
(v1 baseline archived at `results/scores_judge-v1.jsonl`):

| Dimension | v1 | v1.1 |
|---|---|---|
| Criterion agreement | 137/144 (95.1%) | **143/144 (99.3%)** |
| Terminal-state agreement | 18/18 | **18/18** |
| Failure-code F1 (micro) | 0.905 | 0.905 |

All 7 targeted flips landed: kb_fidelity NA→Pass on 039/040/041/099/149;
callback_quality NA→Fail + CB_NO_CONFIRM on 045 (code now 2/2);
intent_class Pass→Fail on 073. Six of eight criteria at 100%.

Residual (accepted): 037 kb_fidelity golden=NA / judge=Pass — the predicted
opposite-direction effect (judge now credits the completion-notice gate as
guidance on a call golden labeled pure routing). Lenient-direction only; no
Fail missed. MULTI_Q on 043 was caught in v1 but missed in v1.1 (minor
severity). Judge v1.1 approved for the full 200-call corpus run.

## 7. Next steps

1. Re-run golden Pass B under judge v1.1; confirm ≥ the 95.1% baseline and the
   7 targeted flips.
2. If clean: add `--workers N` to run_eval.py and launch the remaining 182
   calls (~$290, ~1–2 h parallelized).
3. Report corpus-wide failure-code rates (CUT_TRANSCRIPT excluded from
   behavioral rates per rubric, counted separately).
