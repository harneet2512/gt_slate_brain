# BRAIN_METRICS_SPEC.md

**Scope:** Step 1 of converting GroundTruth from event-bound layers into a metric-driven
brain — define ONLY the metric-state the brain reads from the agent's trajectory. No
policy, no controller, no evidence-content changes. Every claim cites `file:line` from
**code** (verified by direct read; docs treated as claims). Paths are under
`D:\gt_slate_brain`.

**Lens (a metric earns a place only if):** (a) it can trigger an intervention the model
could NOT make from its own local view, AND (b) it will not drag a correct model off
course. Outperform, never dampen. Signals failing either are dropped.

---

## 1. Trajectory Access Audit

**Single interception point exists; unified trajectory accessor does NOT.**

- Every agent step is intercepted at `patched_run_action` (`scripts/swebench/oh_gt_full_wrapper.py:3355`).
  It calls the original action first, then classifies via `classify_tool_event` (`:896`) →
  kind ∈ {post_view, post_edit, finish, skip}. The first message/brief is injected at
  `patched_get_instruction` (`:6050`).
- Running state is **fragmented across ~40 `config._*` fields** on the `GTRuntimeConfig`
  dataclass (`:354`), plus lazily-added attributes, plus 5 JSONL trace files. There is no
  single object/getter that returns "what has the agent done so far." Representative state:
  - `action_count` monotonic step counter (`:3437`)
  - `viewed_files` set (`:369`), `edited_files` set (`:368`), `_read_history` ordered list (`:403`)
  - `_source_edit_actions` — action_count values of source edits (`:401`)
  - `_stuck_compat_history` — 24-entry ring of `(action, obs_hash)` pairs (field `:439`; appended/trimmed `:3432-3434`)
  - `_pending_next_actions` legacy L5 tracker (`:421`); `evidence_sent` dedup dict (`:373`); `interaction_log` (`:379`)
- A canonical `AgentState` object is lazily built (`:1853-1875`) but is a **shadow**: the
  comment at `:1858-1859` states the legacy `config._pending_next_actions` "is preserved and
  mirrored from here on," i.e. legacy `config._*` remains source of truth and `_agent_state`
  failures are swallowed. `interaction_log` (`:379`) is the closest thing to a unified trace,
  but it is **GT-event-centric** (it logs GT's own deliveries: `layer`, `trigger`, `gt_sent`,
  `agent_action_before/after`), not a clean agent action/observation trajectory.

**Verdict:** no clean trajectory accessor exists today. The metric-state the brain needs is
*derivable* from these fragments, but only by reaching into ~40 fields. (See §6.)

---

## 2. Existing-Metric Inventory

Every place a current layer reads agent **trajectory state** (not evidence content). Family ∈
{TEMPO, STUCK/LOOP, SCOPE/COMPLETENESS, LOCALIZATION, SUBMISSION/REVIEW-TRANSITION}.

| signal | computed at (file:line) | source | what it gates today | family |
|---|---|---|---|---|
| step counter `action_count` | wrapper:3437 | trajectory | iteration index for all timing logic | TEMPO |
| `iteration_ratio` band | post_view.py:472 | CLI arg (= action_count/max) | maps progress → edge-decay band | TEMPO |
| `iteration_ratio ≥ 0.85` | post_view.py:478 | trajectory | edge limit → 1; late-phase near-silence | TEMPO |
| `iteration_ratio ≥ 0.60` | post_view.py:481 | trajectory | halve edge limit; suppress importers | TEMPO |
| visited progress fraction | post_view.py:451,555 | `/tmp/gt_viewed.txt` / AgentState | "[Progress visited N/total]" + suppress seen | TEMPO + SCOPE |
| edit-count decay `base_max = 3 if edit_count<=3 else 2` | post_edit.py:2088 | `/tmp/gt_edited_files.txt` | caps callers shown as edits accumulate | TEMPO |
| `iteration_ratio` decay | post_edit.py:2050,2094 | trajectory | shrinks evidence chars late in run | TEMPO |
| repeated-obs check `_is_repeated_obs` | wrapper:3431 | `_stuck_compat_history[-8:]` | exact `(action,obs)` repeat → stuck-compat path | STUCK/LOOP |
| `_search_count_since_edit` | wrapper:3477 (reset 4254) | trajectory | counts grep/find since last edit | STUCK/LOOP |
| `_grep_intercept_count` | wrapper:3604 | trajectory | counts grep symbol interceptions | STUCK/LOOP |
| unseen-caller flag `is_unseen` | post_edit.py:891 (telemetry 948) | `edited_files`/seen set | ranks callers the agent has NOT visited first | STUCK/LOOP |
| `viewed_files` suppression | post_view.py:451 | visited set | drops already-seen callers/importers from recs | SCOPE/COMPLETENESS |
| `edited_files` peer sort | post_edit.py:2069 | edited set | orders peer implementations | SCOPE/COMPLETENESS |
| co-change reminder `_co_change_reminder` | post_edit.py:589 (reads `cochanges` 614-618) | graph.db + edited set | "[CO-CHANGE]" files unedited (≥ `COCHANGE_MEDIUM_THRESHOLD`, 657) | SCOPE/COMPLETENESS |
| scope completeness `_scope_completeness` | post_edit.py:696 | graph.db + edited set | "[SCOPE]" reminder vs edited set | SCOPE/COMPLETENESS |
| diff timeline `_diff_*` | wrapper:208-225 | git diff per step | tracks first/last/collapsed nonzero diff | SCOPE/COMPLETENESS |
| `brief_candidates` annotation | post_view.py:451,634 | `/tmp/gt_brief_candidates.txt` | "[CANDIDATE]" tag on recs | LOCALIZATION |
| `issue_terms` re-rank | post_view.py:114,147 / v1r_brief.py:147 | issue text | boosts symbols matching issue keywords | LOCALIZATION |
| `issue_anchors` boost | post_edit.py (anchors json) | `/tmp/gt_issue_anchors.json` | +2 priority to anchor-matching callers | LOCALIZATION |
| presubmit transition `_maybe_fire_presubmit_verify` | wrapper:769 (called 3472) | `_presubmit_*` (425-427) | fires test suggestions at edit→review transition | SUBMISSION/REVIEW-TRANSITION |
| `mode = post_failure/late_repair` | post_edit.py:2107 | CLI arg | changes evidence header/collapse | SUBMISSION/REVIEW-TRANSITION |
| `_source_edit_actions` timing | wrapper:401 | trajectory | iter-to-first-edit metric | SUBMISSION/REVIEW-TRANSITION |

**Excluded (content, not trajectory-state):** `_contract_pillar` ALWAYS-FIRE
(post_view.py:42, comment :45) is structural certainty from the `nodes` table, not a signal
about what the agent did. `curation_map._DETERMINISTIC_METHODS` (:40) / `_NAME_MATCH_FLOOR`
(:55) are the provenance gate — REUSE-VERBATIM, out of scope.

---

## 3. Gap List (lens-filtered)

Candidate brain metrics not cleanly exposed today. Each kept only if it passes the lens.

- **`obs_similarity` / `no_progress_window`** — PARTIAL. `_stuck_compat_history` (wrapper:3431)
  is **exact-hash** over the last 8 and exists only to feed the stuck-compat path, not as a
  metric. A real "no new file/edit in N turns" or fuzzy-similarity signal is absent. **Passes:**
  a model can't see its own loop from its local view; backing off a *looping* model cannot
  dampen a *correct* one (a correct model isn't looping).
- **`scope_coverage` (single number)** — ABSENT as a metric. The data exists (post_edit:696
  `_scope_completeness`, the `closure` table sqlite.go:244) but is emitted as content, never as
  one brain-readable fraction. **Passes:** the global reachable set is exactly what the model's
  local search lacks.
- **`uncovered_callers` (as a metric)** — PARTIAL. post_edit:891 flags `is_unseen` to *rank*
  callers, but emits no count/set the brain can gate on. **Passes:** requires the full incoming
  CALLS set the model hasn't enumerated.
- **`contract_break_risk`** — ABSENT. No layer compares an edited symbol's changed
  `signature`/`return_type` against untouched dependents. **Passes:** the dependent set is global
  (model can't see all callers); verifiable from the graph; high value pre-submit.
- **`about_to_submit` (clean boolean)** — PARTIAL. `_maybe_fire_presubmit_verify` (wrapper:769)
  detects an edit→review transition but exposes no clean predicate the brain can read. **Passes:**
  enables a pre-submit completeness check; a fully-covered correct model gets nothing → no dampening.

All five survive. None dropped.

---

## 4. Metric Spec (surviving metrics)

For each: name · definition · source · deterministic formula · defined-vs-undefined · Mandatory
Property touched (Dynamic / Hybrid / Confidence-gated).

1. **`no_progress_window`** — turns since the agent last added a *new* file to `viewed_files` or
   `edited_files`. Source: trajectory. Formula: `action_count − max(last_new_view_iter,
   last_new_edit_iter)`. Undefined: before the first action. Property: **Dynamic** (the "stuck"
   cutoff is a per-task distribution, not an absolute).
2. **`verbatim_repeat`** — the current `(action, obs)` pair already appears in recent history.
   Source: trajectory (`_stuck_compat_history`, wrapper:3431). Formula: `pair ∈ history[-W:]`,
   exact hash. Undefined: <2 observations. Property: **Confidence-gated** (binary, structural; no
   tuning — see §5).
3. **`scope_coverage`** — fraction of an edited symbol's required scope that has been edited.
   Source: graph.db + trajectory. Formula: `|required ∩ edited_files| / |required|`, where
   `required` = files of nodes reachable from edited symbols via `closure(source_id, target_id,
   depth, min_confidence)` (sqlite.go:244-248, gates `depth≤3`, `min_confidence≥0.5`). Undefined:
   before the first edit, or when `required` is empty. Property: **Confidence-gated** (closure is
   verified-edge-only) + **Hybrid** (reach + edit-set).
4. **`uncovered_callers`** — count/set of verified callers of an edited symbol not yet viewed or
   edited. Source: graph.db + trajectory. Formula: `{src : edges(target_id=sym, type='CALLS',
   resolution_method ∈ deterministic-set) } \ (viewed ∪ edited)` (edges cols sqlite.go:159-170;
   `resolution_method` :164). Undefined: before the first edit. Property: **Confidence-gated**
   (provenance-filtered, never `name_match`).
5. **`contract_break_risk`** — an edited symbol's `signature` or `return_type` changed AND ≥1
   uncovered verified caller exists. Source: graph.db (`nodes.signature` sqlite.go:149,
   `nodes.return_type` :150) + edges + trajectory. Formula: `(sig_changed ∨ ret_changed) ∧
   uncovered_callers ≥ 1`. Undefined: before the first edit. Property: **Confidence-gated** +
   **Hybrid**.
6. **`co_change_gap`** — historically co-changing files (≥ threshold) not yet edited. Source:
   graph.db `cochanges(file_a, file_b, count)` (sqlite.go:228-231) + trajectory. Formula:
   `{partner : cochanges(edited_file) ∧ count ≥ τ} \ edited_files`. Undefined: before the first
   edit, or no `cochanges` table. Property: **Dynamic** (τ must be per-repo, not a constant).
7. **`about_to_submit`** — the current action is finish/submit-shaped. Source: trajectory
   (`classify_tool_event` kind = finish, wrapper:896). Formula: `kind == "finish"`. Undefined:
   until such an action. Property: **Confidence-gated** (binary).

---

## 5. Structural-vs-Tuned Split

Apply the resolution_method-over-confidence discipline to thresholds.

**Structural / binary — defensible, NO tuning:**
- `verbatim_repeat` — exact `(action, obs)` match (wrapper:3431). Binary fact.
- `contract_break_risk` — signature/return changed **with ≥1 uncovered verified caller**. Binary,
  graph-structural (gated on deterministic `resolution_method`, not a float).
- `about_to_submit ∧ scope_coverage < 1` — binary transition + a strict `<1` (not a tuned cutoff).
- `uncovered_callers ≥ 1` existence — binary (the *count's* "how many is too many" would be tuned,
  but mere existence is structural).

**Tuned — requires a genuine numeric threshold (MUST be derived per-task-distribution, never a
hardcoded absolute):**
- `no_progress_window` length (how many stale turns = "stuck").
- `scope_coverage` "low" cutoff (what fraction is "incomplete enough to flag").
- `obs_similarity` cutoff, if a fuzzy variant is ever added (the exact-match version is structural).
- `co_change_gap` threshold τ.

**Existing hardcoded-absolute debt to flag (anti-pattern per the Dynamic pillar):**
- `iteration_ratio` bands `0.60` / `0.85` (post_view.py:478,481; post_edit decay :2050/2094) — fixed
  absolutes applied uniformly regardless of task length/shape.
- edit-count decay `edit_count <= 3` (post_edit.py:2088) — fixed absolute.
- co-change `COCHANGE_MEDIUM_THRESHOLD` (post_edit.py:657) — a *named* constant, but still a fixed
  absolute, not per-repo-derived.
These should be migrated to per-task/per-repo distributions when the brain subsumes them.

**Schema-vs-doc finding (no DOC LIES here):** the post-merge categorical columns the scope metrics
can lean on — `trust_tier` (sqlite.go:167), `candidate_count` (:168), `evidence_type` (:169),
`verification_status` (:170) — **do exist in the schema**, with an index `idx_edges_target_tier`
(:199). This contradicts any doc worry that they are doc-only; they are real and usable.

---

## 6. Readiness Verdict

**Blocker (§1) is RESOLVED as of Stage 1.** The metric-state is fully *derivable* from existing
signals — every metric in §4 maps to a real `config._*` field, a `classify_tool_event` output, or a
verified graph.db column — but those signals were scattered across ~40 `GTRuntimeConfig` fields,
lazy attributes, and JSONL files. Stage 1 added a **single, read-only `TrajectoryView`** that
projects the metric-state from those existing signals (pure projection — NOT a new mutable store,
NOT a change to evidence content).

### Stage 1 delivered

- **`src/groundtruth/state/trajectory_view.py`** — `TrajectoryView(config)` (read-only projection
  over `GTRuntimeConfig`; stores nothing of its own) + `Step(kind, file, obs_hash)` dataclass.
  Exported from `groundtruth.state`.
- **Two minimal first-seen stamps** added at the *existing* update sites (no parallel store):
  `GTRuntimeConfig.last_new_view_iter` / `last_new_edit_iter` (default `-1` = undefined), stamped by
  new helpers `record_view` / `record_edit` that replaced the 4 inline `viewed_files.add` /
  `edited_files.add` call-sites (`oh_gt_full_wrapper.py` 3444/3767 view, 3449/4251 edit). The
  scaffold/test-gated `_source_edit_actions` / `_presubmit_*` tracking stays at the call-site
  unchanged. Behavior on the sets / `_read_history` is byte-identical; only the two stamps are new.
- **Tests:** `tests/state/test_trajectory_view.py` — 11 passing (undefined-before-first-action,
  undefined-before-first-edit, new-vs-repeat first-seen stamping, copy-not-alias, `last_obs_hash`,
  `verbatim_repeat` mirroring `_is_repeated_obs`, `step()`). Run with gt_slate_brain on `PYTHONPATH`
  (the env's editable `groundtruth` points at a sibling repo; do NOT change the global install).
- Wrapper regression: `tests/openhands/test_oh_gt_full_wrapper.py`, `test_classify_bash_edit.py`,
  `test_presubmit_verify.py` — 44 passing after the swap.

### API surface

| Accessor | Type | Backing signal |
|---|---|---|
| `action_count` | `int` | `config.action_count` |
| `viewed_files` | `frozenset[str]` (copy) | `config.viewed_files` |
| `edited_files` | `frozenset[str]` (copy) | `config.edited_files` |
| `source_edit_iters` | `tuple[int,...]` (copy) | `config._source_edit_actions` |
| `search_count_since_edit` | `int` | `config._search_count_since_edit` |
| `last_new_view_iter` | `int \| None` (−1→None) | `config.last_new_view_iter` (Stage 1) |
| `last_new_edit_iter` | `int \| None` (−1→None) | `config.last_new_edit_iter` (Stage 1) |
| `last_obs_hash` | `str \| None` | `config._stuck_compat_history[-1][1]` |
| `verbatim_repeat(window=8)` | `bool` | `_stuck_compat_history` (mirrors `_is_repeated_obs`) |
| `step(event, obs_hash)` | `Step` | `classify_tool_event` output + raw-obs md5 |

### All seven §4 metrics map onto the exposed surface

1. `no_progress_window` = `action_count − max(last_new_view_iter, last_new_edit_iter)` ✓ (Stage 1
   added the two `last_new_*_iter` fields this needs).
2. `verbatim_repeat` ← `TrajectoryView.verbatim_repeat()` / `last_obs_hash` ✓.
3. `scope_coverage` ← `edited_files` ∩ graph closure (graph read is Stage 2) ✓.
4. `uncovered_callers` ← `viewed_files ∪ edited_files` vs graph callers ✓.
5. `contract_break_risk` ← `edited_files` + graph signature/return (Stage 2) ✓.
6. `co_change_gap` ← `edited_files` + `cochanges` (Stage 2) ✓.
7. `about_to_submit` ← `step(event,…).kind == "finish"` ✓.

The scope family (3–6) assumes a per-task `graph.db` is present (already a precondition of the
brief); when absent, scope metrics are `undefined`, not zero — the estimator (Stage 2) enforces
this. No policy or content work is unblocked or implied here — Stage 1 is the accessor only.

---

## 7. Stage 2 status — estimator built (2026-05-29)

`src/groundtruth/brain/estimator.py` implements `estimate(view, graph_db, *, step,
signature_snapshots) -> MetricState` over the Stage 1 `TrajectoryView`. Corrections from the
GT_BRAIN_BUILD.md Stage 2 mission are baked in:

- **#3 scope_coverage** uses **deterministic 1-hop CALLS edges** (`_DETERMINISTIC_METHODS`), NOT
  the confidence≥0.5 closure table. `required = edited-files-with-nodes ∪ deterministic 1-hop
  caller files`; `coverage = |required ∩ edited| / |required|`.
- **#4 provenance** — callers / required-scope reuse `curation_map._DETERMINISTIC_METHODS` +
  `_open_ro` (single source of truth; never `name_match`, never a bare confidence float).
- **#5 contract_break_risk** compares injected pre-edit `signature_snapshots` against the
  (post-L6-reindex) graph signature — no tree-sitter. `None` without snapshots. Snapshot capture
  before reindex is Stage 3 wiring.
- **#6 co_change_gap** is lowest-priority; raw partners+counts, `None` if no `cochanges` table.

**Structural-vs-tuned (the §5 discipline, enforced):** the estimator returns **raw** values for
the tuned metrics (`no_progress_window` int, `scope_coverage` fraction, `co_change_gap`
partners+counts). The per-task cutoffs that turn those into decisions are NOT baked into the
estimator — they belong to the Stage 3 policy (Dynamic pillar; no hardcoded absolutes here). Only
the structural/binary metrics (`verbatim_repeat`, `about_to_submit`, `contract_break_risk`) are
decided in the estimator.

**Defined/undefined enforced:** scope family is `None` (not zero) before the first edit and when
`graph.db` is absent. **Laundering guard** unit-tested red-before-green: a name_match-only graph
must NOT inflate `required` (a complete internal fix still scores `coverage = 1`); the identical
edge set with a deterministic `resolution_method` DOES count — proving the filter, not the absence
of edges, suppresses the name_match case.

Tests: `tests/brain/test_estimator.py` (17). Audit substrate: `src/groundtruth/brain/trace.py`
(JSONL logger) + `scripts/brain/replay_metric_trace.py` (offline replay). Real-run trace pending a
captured artifact.
