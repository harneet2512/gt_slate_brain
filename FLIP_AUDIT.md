# FLIP_AUDIT.md — research-backed audit of the GT brain against its goal (flips)

**Date:** 2026-05-29 · **Type:** audit + recommendation ONLY (no code, no build). A negative
finding is a valid output; this pass does not rationalize toward Stages 3/5.

**Goal under audit (CLAUDE.md:5-10):** produce **flips** — resolve tasks the baseline agent
couldn't — via correct context → correct code. Flips are the output, not a feature to engineer
toward. "Built + suite-clean + zero-regression is NECESSARY, not done; smoke is the only done."

---

## 1. Classify every rule: harm-removal (defensive) vs flip-generating

| Rule | State (file) | Class | Evidence for the call |
|---|---|---|---|
| **Loop back-off** (`verbatim_repeat` + `no_progress_window`) | `brain/policy.py decide`; wired `oh_gt_full_wrapper.py:3534` region; `_brain_handle_suppress` ~`:1025` | **DEFENSIVE (harm-removal)** | It only *withholds* injection — it adds no correct context. Best case it recovers wasted turns + lets OH's stuck detector fire. On the TTD artifact (sh-744) it suppresses the dead tail, but sh-744 failed on **wrong logic**, not the loop — suppression cannot turn a wrong fix right. Pure harm-removal. |
| **Delivery gate** (`verify_block`) | `brain/delivery.py`; wired in `append/prepend_observation` | **DEFENSIVE (harm-removal)** | Drops malformed/leaked blocks. Prevents noise; generates no flip. |
| **Contract-break** (Stage 5) | `brain/policy.py decide_proactive` + `brain/content.py`; trigger `contract_break_risk` (`brain/estimator.py:60,179,254`) | **NARROW flip-generating — but mis-gated (see §3)** | Surfaces verified callers (the weasyprint-flip content) — BUT only when a **signature changed** (`_signature_changed`, estimator.py:179). The dominant observed failure (6/8 wrong-logic, no interface break) does not trip it, and the one real flip (weasyprint) had **no sig change** → this rule would be silent on it. Flip-generating in principle, ~0 expected yield on the evidence. |

**Verdict:** Nothing built so far is a demonstrated flip lever. Two rules are defensive; the
"proactive" one is gated such that it would not have fired on the only flip GT has ever produced.

---

## 2. The flip mechanism, research-backed

**What turns a wrong fix into a correct one the first time?** The agent must *understand the
behavior it must produce* before it writes the edit. GT's own evidence and the corpus converge:

- **GT's only real flip — weasyprint-2300 — came from `L3b` post-VIEW callers delivered at
  navigation time** (DOC_OF_HONOR.md:1497 "caller lookup at navigation time"; :1663 "L3b callers
  at entry 185 = flip mechanism"). Verified caller context, **ungated**, at the moment the agent
  was reading the code it would edit.
- **The bottleneck is understanding, not localization.** 7-task v2_live: GT reached gold 6/6;
  5/5 failures were the agent writing **wrong logic post-localization** (project memory
  `no_flips_rootcause_2026_05_29`). Dual-agent analysis: "L3 *contract specificity* is the lever,
  not delivery" — GT delivered on 13/16 BOTH_FAIL but the content wasn't specific/actionable
  enough (`dual_agent_analysis_2026_05_20`).
- **RepoGraph (ICLR 2025):** the 1-hop ego-graph (callers/callees) is the useful structural unit;
  deeper traversal is net-negative. → the flip-relevant content is verified 1-hop callers/contract.
- **LocAgent (ACL 2025):** dependency (invoke/import) edges are the edges that matter — not bare
  containment. → caller/contract edges, provenance-gated.
- **CGM (Code Graph Model, NeurIPS 2025) [moderate confidence]:** conditioning repair on the
  repository graph improves *fix generation*, not only localization → structure helps the WRITE.
- **KGCompass (2025) [moderate confidence]:** linking the issue to repo entities (and their tests)
  tightens the repair target → issue-anchored contract/test surfacing.
- **The Distracting Effect (arXiv:2505.06914, 2025):** plausible-but-wrong context drops accuracy
  6-11pp and models don't filter it → the non-dampening guarantee must come from **verified
  provenance**, never from `name_match`.
- **SWE-PRM (NeurIPS 2025, 2509.02360):** mid-trajectory feedback helps **only when diagnostic**;
  prescriptive feedback *lowers* resolution → surface facts ("this test asserts X"), never "edit Y".
- **Geifman & El-Yaniv (NeurIPS 2017):** selective prediction — abstention is first-class →
  correct-or-quiet.

**Is the lever NEW content or curation/timing of EXISTING content?** **Curation/timing of existing
verified content.** The flip content already exists in GT's engine — the contract pillar
(`post_view.py:42`, always-fire), verified 1-hop callers (the weasyprint mechanism), and
visible-test assertions (the `assertions` table with verified test→target links, `sqlite.go:211-226`).
Nothing new must be generated (REUSE VERBATIM). The lever is **getting the right verified content
(callers + behavioral contract + the visible test that defines correct behavior) in front of the
agent at the first edit of the issue-relevant symbol, issue-ranked for specificity.**

---

## 3. STEELMAN THE NULL (no softening)

**Claim: the current brain does not move flips, and the lever is where the brain does not reach.**

1. **The only flip predates the brain and bypasses it.** weasyprint flipped via L3b post-view
   callers — existing reactive content. Neither loop back-off nor contract-break produced it, and
   the **contract-break rule, gated on a signature change (`estimator.py:179,254`), would be SILENT
   on weasyprint** (no sig change). The one thing we built to be "proactive and flip-generating"
   would not have fired on the only flip we have. In hardening for non-dampening I gated out the
   proven mechanism.
2. **The built rules don't touch the dominant failure mode.** 6/8 failures are wrong-logic
   post-localization. Loop back-off (withholding) and contract-break (interface) address neither
   logic nor localization — they address loops and signature breaks, failure classes that are
   absent or rare on the observed set.
3. **A deterministic, no-leakage, LLM-free brain may be structurally incapable of fixing
   wrong-logic.** Correct logic requires either the gold patch (forbidden: benchmaxxing) or a model
   that reasons about correctness (forbidden: no LLM in the loop). The brain can surface *what
   correct behavior IS* only via the visible test — and only if such a test exists and is verified-
   linked. The project's own estimate for that lever is **~1-2 flips, not a transformation**
   (`no_flips_rootcause_2026_05_29`). So the ceiling of any deterministic context layer on this
   failure distribution is low.
4. **Offline-green is not evidence.** Every "proven" claim in this build is a synthetic/replay
   test or a frozen-artifact replay. Zero flips have moved. Per the constitution that means
   **nothing built is done**, and the brain's flip contribution is **currently zero, measured**.

**The null, stated plainly:** GT already had its flip lever (verified callers/contract at
navigation, in the existing hooks). The brain's two rules are defensive or mis-gated. The
remaining failure mode (implementation correctness) is largely outside what a deterministic,
no-leakage, no-LLM brain can change. The honest expected value of *any* further brain rule on
this evidence is 1-3 flips, and it is not yet established that it beats the existing reactive
delivery at all.

---

## 4. DECISION — the single highest-probability flip lever to build next

**Lever: proactive, issue-anchored delivery of the VERIFIED flip-content bundle (1-hop callers +
behavioral contract + the visible-test assertions that define correct behavior) at the FIRST EDIT
of the issue-relevant symbol — provenance-gated, NOT gated on a signature change.**

This is the weasyprint mechanism (verified callers at the edit) generalized and made specific:
it adds the behavioral contract (`post_view.py:42` content) and the visible-test assertions
(`assertions` table, verified `target_node_id>0`, `sqlite.go:211-226`) — the deterministic proxy
for "what correct behavior is" — at the moment correct context becomes correct code.

**Why this and not more of Stage 5:** the audit shows the Stage 5 sig-change gate is the wrong
gate — it excludes the proven flip mechanism. The correct non-dampening guarantee is **provenance
+ relevance**, per The Distracting Effect (verified content cannot misdirect), not a sig-change
predicate. So the concrete next move is to **redirect the proactive rule**: drop the sig-change
trigger; fire the verified caller/contract/test bundle for the issue-anchored symbol at first edit.

**Scoped to the invariants:**
- **Deterministic provenance only** — callers via `_DETERMINISTIC_METHODS` (never `name_match`);
  test links via verified `assertions.target_node_id>0`. (The Distracting Effect, 2025.)
- **Don't dampen** — verified facts cannot misdirect; surfacing the contract/test a *correct* fix
  already satisfies is confirmatory, not corrective → cannot fire harmfully on a correct
  trajectory. Diagnostic framing only (SWE-PRM, 2025). Silent when no verified test/caller exists
  (Geifman & El-Yaniv, 2017).
- **No LLM in the loop** — pure SQL over `graph.db` + the assertions table.
- **Contract pillar stays always-fire** (`post_view.py:42`) — this rule *reinforces* it at the
  edit moment, never gates it.
- **One delivery gate** — routes through `verify_block` (`brain/delivery.py`).

**Honest expectation:** 1-3 flips on this distribution, not transformational. The null in §3
remains live: if a smoke shows no delta over the existing reactive delivery, the lever is outside
the brain and GT should stop adding proactive rules.

---

## 5. VALIDATION GATE — offline-decidable vs run-only

**Settled offline (this audit + unit/replay tests):**
- The Stage 5 sig-change gate excludes the weasyprint mechanism — **decided** (estimator.py:179
  + DOC_OF_HONOR:1497).
- Loop back-off and the delivery gate are defensive — **decided** (they add no content).
- A redirected rule fires on verified callers/contract/test and stays silent without verified
  provenance — **offline-checkable** (synthetic graph + the sh-744 non-dampening replay).

**Only a real run can settle:**
- Whether delivering the verified bundle at first edit **moves resolution** (flips) over
  agent-alone, and whether the brain's timing/specificity beats the existing reactive hooks.
- Whether it dampens any currently-passing task.

**Minimal smoke that VALIDATES or KILLS the lever:**
- **10 tasks**, multi-language, including **weasyprint-2300 as the canary** (must still flip).
- **Paired**: arm A = agent-alone (`GT_BASELINE=1`); arm B = GT-brain+agent (`GT_BRAIN=1` with the
  redirected rule + the defensive rules). Same model, same seed/config, same task list.
- **Truth source = `output.jsonl` agent observations**, never telemetry counts. Verify per task:
  did the verified bundle reach the agent at the first edit; did any task regress; canary preserved.
- **Artifact = per-task resolve grid** (A vs B) + the agent-observation excerpt for each B flip.
- **KILL criteria:** (a) canary no longer flips → the redirect broke the proven path; (b) net
  resolution Δ ≤ 0 with no new flip attributable to the bundle in `output.jsonl` → the lever is
  outside the brain (null confirmed) → stop building proactive rules; (c) any currently-passing
  task regresses → dampening, revert.
- **PASS:** ≥1 new flip attributable (from `output.jsonl`) to the bundle-at-edit, canary preserved,
  zero regressions.

---

## Recommendation (one paragraph)

Stop adding proactive rules and **fix the gate, not the rule**: the audit shows the Stage 5
contract-break trigger is gated on a signature change that would have silenced GT on its only real
flip (weasyprint, which flipped via *ungated* verified callers at navigation — DOC_OF_HONOR:1497).
The single highest-probability flip lever is to **redirect the proactive rule to deliver the
verified bundle (1-hop callers + behavioral contract + visible-test assertions for the
issue-anchored symbol) at the first edit, gated by provenance and relevance, not by a sig change**
— curation/timing of EXISTING verified content, within all invariants. But its honest ceiling on
this failure distribution is 1-3 flips, and the steelmanned null (the wrong-logic bottleneck is
outside a deterministic no-leakage brain) is live. Therefore **no build proceeds until (a) this
recommendation is accepted and (b) the 10-task paired smoke above has run** — that smoke is the
only thing that can tell us whether the brain moves flips or whether the lever is elsewhere. Offline
work cannot settle it; the constitution forbids calling any of this done until a metric moves.
