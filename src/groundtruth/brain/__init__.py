"""GroundTruth brain — deterministic metric-state over the agent trajectory.

The brain reads the agent's trajectory as a metric-state each step and (in later
stages) decides, on its own, when surfacing context changes what the model does
next. This package is built in stages (see ``GT_BRAIN_BUILD.md``):

- Stage 1: ``groundtruth.state.TrajectoryView`` — the read-only accessor.
- Stage 2 (here): ``estimator`` — the deterministic metric-state over
  (TrajectoryView, graph.db). Metrics only; no policy, no content.
- Stage 3+: the policy ``π`` and the single delivery gate (not in this package yet).

Everything here is LLM-free and read-only. Provenance for scope/caller/contract
metrics is gated on deterministic ``resolution_method`` (never ``name_match``) by
reusing ``groundtruth.pretask.curation_map`` — the single source of truth for
"what is a fact".
"""
from __future__ import annotations

from groundtruth.brain.content import (
    render_completeness_note,
    render_contract_break_note,
    render_evidence_bundle,
    render_wandering_note,
)
from groundtruth.brain.delivery import verify_block
from groundtruth.brain.estimator import MetricState, estimate
from groundtruth.brain.policy import (
    BundleDecision,
    CompletenessDecision,
    Decision,
    ProactiveDecision,
    WanderingDecision,
    decide,
    decide_bundle,
    decide_completeness,
    decide_proactive,
    decide_wandering,
    is_review_phase,
    no_progress_cutoff,
)

__all__ = [
    "MetricState",
    "estimate",
    "Decision",
    "ProactiveDecision",
    "BundleDecision",
    "CompletenessDecision",
    "WanderingDecision",
    "decide",
    "decide_proactive",
    "decide_bundle",
    "decide_completeness",
    "decide_wandering",
    "is_review_phase",
    "no_progress_cutoff",
    "render_contract_break_note",
    "render_evidence_bundle",
    "render_completeness_note",
    "render_wandering_note",
]
