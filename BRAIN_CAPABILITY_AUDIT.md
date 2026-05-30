# BRAIN_CAPABILITY_AUDIT.md — can the brain synthesize everything old GT did?

**Date:** 2026-05-29 · **Question (verbatim):** does the brain *architecture* have the
**capability** to synthesize the same info as old GT (DOC_OF_HONOR + we_did), localization →
reindexing, start to end — independent of whether plumbing will *deliver* it?

**Method:** every function in DOC_OF_HONOR.md Layers 0–7 + the gt_intel evidence families,
mapped against the brain (TrajectoryView + estimator + policy + delivery gate) and the
REUSE-VERBATIM content engine it calls.

---

## The frame: the brain is a CONTROLLER, not a content engine

The brain never re-implements a content generator. It **calls** the same code old GT used.
So capability splits into three classes, and the answer differs per class:

- **Class A — WHAT (content synthesis).** curation_map, the hook evidence bodies, v1r brief,
  orientation composite, gt_intel families, the Go indexer/resolver/reindex. **REUSE-VERBATIM.**
  Capability = **full parity by construction** (it is the same code; the brain invokes it).
- **Class B — WHEN (trigger/timing state).** Old GT scattered this across ~40 `config._*`
  fields + per-hook gates. The brain **synthesizes it as a clean metric-state** — and adds
  numbers old GT never computed. Capability = **superset for what it models; a few event
  triggers not yet modeled.**
- **Class C — ACT (turn state into delivery).** Phase 1 only **withholds**. The rules that
  would turn the new metrics into proactive content are **unbuilt (Stage 5).**

Net: the architecture can **access/produce** everything (Class A), **synthesizes a richer
state** than old GT for the metrics it models (Class B), but **does not yet act** on most of
that state (Class C). "Can it synthesize the info" → yes; "does Phase 1 use it" → mostly not yet.

---

## Start → end inventory (DOC_OF_HONOR Layer 0–7 → brain)

Legend: **REUSE** = same code, brain calls it · **METRIC** = brain synthesizes as a metric-state
field · **DELEGATED** = still in the wrapper, brain doesn't touch · **NET-NEW** = brain computes
something old GT did not · **GAP** = capability missing/at-risk in the brain.

### Layer 0 — Source → gt-index → graph.db (the foundation)
| Fn | What | Brain relation |
|---|---|---|
| 0.1 Go binary / tree-sitter | parse → graph.db | REUSE (unchanged; brain reads graph.db) |
| 0.2 7-table schema | nodes/edges/properties/assertions/cochanges/closure/meta | REUSE — estimator reads nodes(sig,return), edges(resolution_method), cochanges |
| 0.3 8-pass indexing | build pipeline | REUSE |
| 0.4 23 property kinds | guards/returns/raises… | REUSE (content); **not** surfaced as a brain metric |
| 0.5 6-strategy resolver | name_match→deterministic provenance | REUSE — estimator's provenance gate **depends** on it (`_DETERMINISTIC_METHODS`) |
| 0.6 assertion resolution | test→target links | REUSE (content); not a brain metric |
| 0.7 serde-pair / 0.8 twin detection | structural twins | REUSE (content); not a brain metric |
| 0.9 import extraction | 14 handlers/18 langs | REUSE |
| 0.10 incremental reindex (L6) | gt-index -file after edit | **DELEGATED + GAP** — see Finding 1 |
| 0.11 pre-index orchestration | GHA | REUSE (infra) |

### Layer 1 — Path resolution
| 1.1 `resolve_to_stored_path()` | canonical path keying | REUSE — estimator uses `_normalize_rel_path` at the wrapper boundary; same keying |

### Layer 2 — Passive delivery layers (the hooks)
| Fn | Old "when" / "what" | Brain relation |
|---|---|---|
| 2.1 L1 brief | task-start curation | DELEGATED (brief runs at `patched_get_instruction`, outside the per-step loop; brain doesn't synthesize it) |
| 2.1+ L1 edit-plan + key contracts | orientation composite (5-signal) | DELEGATED (brief-time localization; not in the estimator) |
| 2.2 L3 post-edit | contract/signature/callers/propagation/co-change/scope/mismatch | **WHAT=REUSE** (content). **WHEN→METRIC**: scope_coverage, uncovered_callers, contract_break_risk, co_change_gap now exist as numbers |
| 2.3 L3b post-view | contract pillar always-fire + callers/callees/importers/ego | WHAT=REUSE; contract-always-fire preserved by delegation |
| 2.4 L4a auto-query | (RETIRED, subsumed by L3b) | n/a |
| 2.5 L5 scaffold governor | non-source edit without progress | **PARTIAL METRIC** — no_progress_window covers "without progress"; scaffold-file-specificity not a distinct metric (GAP 2) |
| 2.6 L5b late reminder | unexamined structural signal | DELEGATED (diagnostic content) |
| 2.7 L6 reindex | keep graph fresh after edit | DELEGATED + **GAP** (Finding 1) |
| 2.8 L6 pre-submit verify | tests covering the diff at edit→review | WHEN→METRIC: `about_to_submit` + `source_edit_iters`; WHAT (which tests) = REUSE/DELEGATED |
| 2.9 grep intercept | agent searches symbol → inject ego-graph | **GAP 2** — no "current grep symbol" metric; brain delegates it |

### Layer 3 — Consensus / localization
| 3.1 scope-aware consensus | multi-file scope | DELEGATED; partially echoed by scope_coverage/co_change_gap |

### Layer 4 — Active tools (MCP) + stuck detector
| 4.1 registered tools / 4.2 tool-as-hooks | 16/7 MCP tools | REUSE (unchanged) |
| 4.3 stuck-detector compatibility | exact (action,obs) repeat skip | **METRIC + NET-NEW** — `verbatim_repeat` mirrors it; the **no_progress arm is net-new** (catches the interleaved loop the exact-repeat path misses — proven on sh-744) |

### Layer 5 — Supporting infra
| 5.1 dedup | per-file evidence dedup | DELEGATED (still wrapper) |
| 5.2 evidence budget / 5.5 condenser | iteration_ratio decay, token caps | **GAP 2** — brain has `action_count` but does not yet expose iteration_ratio or own the decay |
| 5.4 delivery ledger `_deliver_or_trace` | delivery invariant | REUSE + **NET-NEW** delivery gate (`verify_block` drops [GT_*] leak / empty / malformed) |
| 5.6 preflight | doc/health checks | REUSE (infra) |

### gt_intel evidence families (the 7-family synthesis)
| Family | Old (content) | Brain as a METRIC |
|---|---|---|
| CALLER | cross-file callers | **YES** — `uncovered_callers` |
| IMPACT | blast radius (caller count) | **YES** — derivable from uncovered/caller set |
| TYPE | return-type contract | **YES** — `contract_break_risk` (signature/return) |
| IMPORT | correct import paths | REUSE only (not a metric) |
| SIBLING | structural twins / norms | REUSE only (not a metric) |
| TEST | test assertions | REUSE only (`about_to_submit` flags the moment, not the content) |
| PRECEDENT | last git commit | REUSE only (not a metric) |

---

## Findings (the honest gaps)

> **UPDATE 2026-05-29:** Finding 1 **RESOLVED** (`_brain_handle_suppress` reindexes a
> suppressed edit; tests added). Finding 2 **partially addressed** — the first proactive rule
> (contract-break, hybrid: trigger=`contract_break_risk`, payload=uncovered verified callers)
> is now built + TTD-proven + wired behind GT_BRAIN. Completeness-without-break and wandering
> rules remain deliberately unbuilt (real-artifact evidence argued against bare completeness).

**Finding 1 — Suppress-early-return skips L6 reindex (regression risk, fixable).**
The Phase-1 loop gate (oh_gt_full_wrapper.py ~3503) mirrors STUCK_COMPAT: on suppress it
records the file and `return obs` — *before* the post_edit dispatch, where L6 reindex fires
(line 4428). For STUCK_COMPAT this is safe (it only fires on a byte-identical repeat → re-index
is redundant). But the brain's **no_progress arm can suppress a non-identical re-edit** of an
already-seen file (not `current_is_new`, npw>cutoff) → that edit's reindex is skipped →
graph.db goes stale → downstream `contract_break_risk` reads an old signature. **Capability
impact:** the brain can compute the metrics, but this wiring can *starve its own graph input*.
Fix options: suppress injection only (not reindex); never suppress `post_edit` kind; or move
the gate below the reindex. Flagged, not yet fixed. (Default-off, so inert today.)

**Finding 2 — Class C is the real "missing function": proactive delivery is unbuilt.**
The estimator synthesizes `uncovered_callers`, `contract_break_risk`, `scope_coverage`,
`co_change_gap` — but **no wired rule turns any of them into a content injection.** Phase 1
only *withholds*. So the architecture can SYNTHESIZE the state old GT emitted as content, but
cannot yet ACT on it proactively. The corresponding content generators exist (curation_map,
`_contract_pillar`, `_scope_completeness`, `_co_change_reminder`) and are callable — they are
simply not invoked by π yet. This is exactly Stage 5 of the build, and is the honest answer to
"can it do what old GT did": the WHAT exists, the brain-driven WHEN exists, the brain-driven
ACT does not.

**Finding 3 — A handful of old triggers are not modeled as metrics.**
- grep-symbol intercept (2.9) — no "current search symbol" field; delegated.
- iteration_ratio decay / evidence budget (5.2/5.5) — `action_count` is exposed but the
  ratio and decay aren't; delegated to the hooks.
- scaffold-file-specific signal (2.5) — only the generic no-progress is modeled.
These are all *event-local* triggers; the brain currently relies on the existing dispatch for
them. None are lost (delegated), but they are not part of the metric-state.

**Finding 4 — Three evidence families are content-only, not metrics.**
SIBLING, IMPORT, PRECEDENT are synthesized by old GT as content and remain REUSE-only; the
estimator does not expose them as brain-readable signals. CALLER / IMPACT / TYPE are now
metrics. If a future policy needs to gate on "twin exists" or "co-author precedent," that would
be a new estimator field (cheap; the graph already has the data — properties, assertions,
git precedent).

**Finding 5 — Brief / localization is outside the per-step loop (by design).**
v1r_brief + orientation composite run once at task start (`patched_get_instruction`). The brain
is a per-step controller and does not synthesize the brief. This is correct separation (the
brief is the upfront localization lever; the brain is mid-trajectory), but it means "localization"
in the start-to-end question is **delegated, not brain-synthesized**.

---

## Verdict

| Capability class | Old GT | Brain architecture | Parity |
|---|---|---|---|
| **WHAT** — content synthesis (indexer, resolver, families, hooks' bodies, brief) | full | **calls the same code** | **FULL (by construction)** |
| **WHEN** — trigger/timing state | scattered across ~40 fields + per-hook gates | clean metric-state + **net-new** contract_break_risk / scope_coverage / no_progress | **SUPERSET** for modeled metrics; 3 triggers (grep, iteration-decay, scaffold) not yet modeled |
| **ACT** — turn state into delivery | each hook delivers its own content | **only withholds (Phase 1)**; proactive rules unbuilt | **NOT YET** (Stage 5) |
| **Lifecycle** — reindex freshness | L6 fires every edit | delegated; **suppress can skip reindex** (Finding 1) | **AT RISK** until Finding 1 fixed |

**Bottom line.** The architecture **can synthesize everything old GT synthesized** — because the
content engine is REUSE-VERBATIM and the brain has an invocation path to all of it — and it
synthesizes a **richer per-step state** (contract-break, scope-coverage, no-progress as numbers
old GT never computed). What it does **not yet do** is (a) *act* on that richer state (proactive
delivery = Stage 5), (b) model 3 event-local triggers as metrics (grep/decay/scaffold), and
(c) guarantee reindex freshness under suppression (Finding 1). None of these are capability
*ceilings* — they are unbuilt wiring and one fixable ordering bug. No content capability is lost.
