"""Stage 3 Phase 1 — the policy π (loop back-off).

π reads the metric-state and decides ONE thing this phase: suppress GT injection
this step, or delegate to the existing dispatch. Withholding only — Phase 1
introduces no new content type. Deterministic, no LLM. Silence is never the *only*
output here (the existing dispatch still runs when π does not suppress); π adds the
cross-event loop decision the event-bound layers structurally could not make.

Two arms:
  1. ``verbatim_repeat`` — exact (action, obs) repeat. Structural, binary, zero
     dampening risk (a correct model is not emitting byte-identical pairs).
  2. ``no_progress_window`` beyond the task's own productive cadence. The cutoff is
     **per-task dynamic**: the largest gap between new-file discoveries seen so far
     (``view.new_file_iters``). Undefined until ≥2 such gaps exist, so a thin trace
     never fires — π errs toward NOT suppressing (never dampen). π never suppresses
     on a step that itself introduces a new file (that step IS progress).

Artifact basis (TTD): the frozen amoffat__sh-744 GT run — 2 files viewed / 1 edited
over 38 actions, a 17-step no-progress tail, and a max consecutive-identical
(action,obs) run of 2 (< OH's stuck threshold of 4). Neither OH's detector nor the
exact-hash STUCK_COMPAT path fires on that interleaved loop; the no-progress arm
does, and only in the dead tail (cutoff = the trace's own max productive gap = 11).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

# Minimum number of productive gaps before a cadence ceiling is meaningful. Two is
# the smallest sample that has a max-over-variation; below it the cutoff is
# undefined and π does not fire (structural minimum, not a tuned threshold).
_MIN_GAPS_FOR_CADENCE = 2


# Edit→review transition: actions since the last source edit before the agent is
# "reviewing" (stopped editing, can still act). Inherited from the existing
# _maybe_fire_presubmit_verify timing — a small structural minimum, not a fresh tune.
_REVIEW_WINDOW = 3


@dataclass(frozen=True)
class Decision:
    suppress: bool
    reason: str = ""


@dataclass(frozen=True)
class ProactiveDecision:
    fire: bool
    callers: tuple[str, ...] = ()
    reason: str = ""


@dataclass(frozen=True)
class BundleDecision:
    """§4 redirected proactive rule output: the verified flip-content bundle."""

    fire: bool
    callers: tuple[str, ...] = ()
    tests: tuple[tuple[str, str, str], ...] = ()
    reason: str = ""


def is_review_phase(view: Any, *, review_window: int = _REVIEW_WINDOW) -> bool:
    """True once the agent has edited ≥1 source file and then taken ≥review_window
    actions without another source edit (the actionable edit→review moment). Cheap,
    trajectory-only — used to gate the expensive graph estimate to one moment."""
    sei = tuple(view.source_edit_iters)
    if not sei:
        return False
    return (int(view.action_count) - max(sei)) >= review_window


def decide_proactive(view: Any, state: Any, *, already_fired: bool = False,
                     review_window: int = _REVIEW_WINDOW) -> ProactiveDecision:
    """Stage 5 proactive rule (hybrid: contract-break trigger + completeness payload).

    Fire ONCE, at the edit→review transition, ONLY when a real contract break exists —
    ``contract_break_risk`` is True (signature/return changed AND ≥1 uncovered verified
    caller). Payload = those uncovered callers. Does NOT fire on correct internal fixes,
    on logic bugs without a signature change, before review, or twice. This is strictly
    more precise than ``scope_coverage < 1`` (which would false-positive on all of those).
    """
    if already_fired:
        return ProactiveDecision(False, reason="already_fired")
    if not is_review_phase(view, review_window=review_window):
        return ProactiveDecision(False, reason="not_review_phase")
    if state.contract_break_risk:
        return ProactiveDecision(True, tuple(state.uncovered_callers or ()), "contract_break")
    return ProactiveDecision(False, reason="no_break")


def decide_bundle(view: Any, state: Any, *, already_fired: bool = False) -> BundleDecision:
    """§4 REDIRECTED proactive rule (FLIP_AUDIT §4) — the highest-probability flip lever.

    Fire ONCE, at the FIRST EDIT, surfacing the VERIFIED flip-content bundle for the
    symbol the agent just edited: 1-hop uncovered callers + the visible-test
    assertions that define correct behavior. Gated by **provenance + relevance**, NOT
    by a signature change — the sig-change gate (decide_proactive) would have stayed
    silent on weasyprint, GT's only real flip (DOC_OF_HONOR:1497). Relevance = the
    agent's own edit (it chose the symbol). Non-dampening: every item is verified
    (callers via deterministic edges, tests via assertions.target_node_id>0), so it
    confirms a correct fix and cannot misdirect (The Distracting Effect, 2025). Silent
    when no verified content exists (Geifman & El-Yaniv, 2017).
    """
    if already_fired:
        return BundleDecision(False, reason="already_fired")
    if not view.edited_files:
        return BundleDecision(False, reason="no_edit")
    callers = tuple(state.uncovered_callers or ())
    tests = tuple(state.visible_tests or ())
    if not callers and not tests:
        return BundleDecision(False, reason="no_verified_content")
    return BundleDecision(True, callers, tests, "bundle_at_first_edit")


@dataclass(frozen=True)
class CompletenessDecision:
    fire: bool
    uncovered_scope: tuple[str, ...] = ()
    co_change: tuple[tuple[str, int], ...] = ()
    reason: str = ""


@dataclass(frozen=True)
class WanderingDecision:
    fire: bool
    scope: tuple[str, ...] = ()
    reason: str = ""


def decide_completeness(view: Any, state: Any, *, already_fired: bool = False,
                        review_window: int = _REVIEW_WINDOW) -> CompletenessDecision:
    """Completeness-without-break (deferred in FLIP_AUDIT §3, now authorized): at the
    review/submit moment, surface the VERIFIED scope the diff has not covered —
    required-scope files not edited + historical co-change partners. Diagnostic only
    ("confirm"), once. Fires only on verified scope (required_scope is deterministic-
    edge-derived; co_change is the cochanges table), so it cannot misdirect a correct,
    internally-complete fix beyond a confirmatory prompt."""
    if already_fired:
        return CompletenessDecision(False, reason="already_fired")
    submitting = bool(getattr(state, "about_to_submit", False))
    if not (submitting or is_review_phase(view, review_window=review_window)):
        return CompletenessDecision(False, reason="not_review_or_submit")
    edited = set(view.edited_files)
    uncovered = tuple(f for f in (state.required_scope or ()) if f not in edited)
    co = tuple(state.co_change_gap or ())
    if not uncovered and not co:
        return CompletenessDecision(False, reason="complete")
    return CompletenessDecision(True, uncovered, co, "incomplete_scope")


def decide_wandering(view: Any, state: Any, *, already_fired: bool = False) -> WanderingDecision:
    """Wandering (deferred in FLIP_AUDIT, now authorized): when the agent is wandering
    (no_progress beyond the task's OWN cadence, same dynamic cutoff as the loop
    back-off), surface the VERIFIED call-scope of its edits as FACTS to re-anchor on —
    never a 'go look here' directive. Fire once. Silent when no verified scope exists
    (then the loop back-off's withholding is the only action — no steering on weak
    signal). This is the content complement to the defensive suppression."""
    if already_fired:
        return WanderingDecision(False, reason="already_fired")
    npw = getattr(state, "no_progress_window", None)
    cutoff = no_progress_cutoff(tuple(view.new_file_iters))
    if npw is None or cutoff is None or npw <= cutoff:
        return WanderingDecision(False, reason="not_wandering")
    seen = set(view.edited_files) | set(view.viewed_files)
    scope = tuple(f for f in (state.required_scope or ()) if f not in seen)
    if not scope:
        return WanderingDecision(False, reason="no_verified_scope")
    return WanderingDecision(True, scope, "wandering_with_scope")


def no_progress_cutoff(new_file_iters: tuple[int, ...]) -> Optional[int]:
    """Per-task no-progress cutoff = the LARGEST gap between consecutive new-file
    discoveries seen so far. ``None`` (undefined) until ≥2 gaps exist. Dynamic;
    derived entirely from this task's cadence — never a hardcoded absolute.
    """
    if len(new_file_iters) < _MIN_GAPS_FOR_CADENCE + 1:
        return None
    gaps = [b - a for a, b in zip(new_file_iters, new_file_iters[1:])]
    return max(gaps) if gaps else None


def decide(view: Any, state: Any, *, current_is_new: bool = False) -> Decision:
    """Return the Phase-1 suppression decision for this step.

    ``view``: TrajectoryView (needs ``new_file_iters``). ``state``: MetricState
    (needs ``verbatim_repeat``, ``no_progress_window``). ``current_is_new``: True if
    THIS step introduces a file not previously viewed/edited (then never suppress).
    """
    if getattr(state, "verbatim_repeat", False):
        return Decision(True, "verbatim_repeat")
    if not current_is_new:
        npw = state.no_progress_window
        cutoff = no_progress_cutoff(tuple(view.new_file_iters))
        if npw is not None and cutoff is not None and npw > cutoff:
            return Decision(True, f"no_progress_window={npw}>cutoff={cutoff}")
    return Decision(False, "")
