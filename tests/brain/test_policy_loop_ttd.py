"""Stage 3 loop back-off TTD — artifact-first, red-before-green.

Starts from a FROZEN real failed run: the amoffat__sh-744 GT trajectory
(tests/brain/fixtures/sh744_loop_steps.json), the run the 2026-05-25 finding cites
("GT disables OH stuck detector -> agent loops, 0 useful progress"). We replay the
real ordered (kind, file, obs_hash, action_repr) steps through the REAL Stage 1
GTRuntimeConfig + TrajectoryView and the Stage 2 estimator + Stage 3 policy.

The failure mode, proven from the artifact (RED):
- the max run of CONSECUTIVE byte-identical (action, obs) pairs is < 4, so OH's
  stuck detector AND the wrapper's exact-hash STUCK_COMPAT path BOTH stay blind;
- so verbatim-repeat suppression alone never fires on this loop.

The fix (GREEN): the no-progress arm suppresses in the dead tail (no_progress_window
past the task's own max productive gap = 11), and NEVER during the productive phase
(action_count <= 21) — non-dampening.

Run with gt_slate_brain on PYTHONPATH and scripts/swebench importable:
    PYTHONPATH=...\\src;...\\scripts\\swebench  python -m pytest tests/brain/test_policy_loop_ttd.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "swebench"))
import oh_gt_full_wrapper as w  # noqa: E402

from groundtruth.brain import decide, estimate, no_progress_cutoff  # noqa: E402
from groundtruth.state import Step, TrajectoryView  # noqa: E402

_FX = json.loads((Path(__file__).parent / "fixtures" / "sh744_loop_steps.json").read_text(encoding="utf-8"))
_STEPS = _FX["steps"]
_LAST_NEW_FILE_AC = 21  # from the trace: last new file (edit sh.py) at action_count 21
_PRODUCTIVE_MAX_GAP = 11  # max gap between new-file discoveries (steps 10 -> 21)


def _replay():
    """Replay the frozen steps; return per-step records of the decision + state."""
    cfg = w.GTRuntimeConfig()
    view = TrajectoryView(cfg)
    out = []
    prev_pair = None
    consec = 0
    max_consec = 1
    for st in _STEPS:
        cfg.action_count += 1
        kind = st.get("kind", "skip")
        rel = st.get("file")
        obs_hash = str(st.get("obs_hash", ""))
        action_repr = str(st.get("action_repr", ""))
        # mirror the wrapper's stuck-compat ring (for verbatim_repeat projection)
        cfg._stuck_compat_history.append((action_repr, obs_hash))
        if len(cfg._stuck_compat_history) > 24:
            cfg._stuck_compat_history = cfg._stuck_compat_history[-24:]
        # consecutive-identical run length (OH stuck detector's signal)
        pair = (action_repr, obs_hash)
        if prev_pair is not None and pair == prev_pair:
            consec += 1
            max_consec = max(max_consec, consec + 1)
        else:
            consec = 0
        prev_pair = pair
        # current_is_new is decided on PRE-record state
        is_new = (
            (kind == "post_view" and rel and rel not in cfg.viewed_files)
            or (kind == "post_edit" and rel and rel not in cfg.edited_files)
        )
        if kind == "post_view" and rel:
            cfg.record_view(rel)
        elif kind == "post_edit" and rel:
            cfg.record_edit(rel)
        step = Step(kind=kind, file=rel, obs_hash=obs_hash)
        # loop arm is graph-free -> graph_db=None (cheap; works without graph.db too)
        state = estimate(view, None, step=step)
        dec = decide(view, state, current_is_new=bool(is_new))
        out.append({
            "ac": cfg.action_count, "kind": kind, "is_new": bool(is_new),
            "npw": state.no_progress_window, "verbatim": state.verbatim_repeat,
            "suppress": dec.suppress, "reason": dec.reason,
            "cutoff": no_progress_cutoff(view.new_file_iters),
        })
    return out, max_consec


def test_red_existing_detectors_are_blind_to_this_loop():
    """RED: the existing repeat-based detectors cannot see this interleaved loop."""
    _, max_consec = _replay()
    assert max_consec < 4, f"OH stuck detector needs >=4 consecutive identical; got {max_consec}"


def test_red_repeat_detection_misses_the_stuck_tail():
    """RED: repeat-based detection (OH's consecutive-4 and the verbatim arm) does NOT
    catch the no-progress tail. There exist stuck-tail steps (npw past the task's own
    max gap) where verbatim_repeat is False — i.e. without the no-progress arm the
    agent would keep looping uncaught. This is why the no-progress arm is necessary."""
    recs, _ = _replay()
    stuck_tail_not_verbatim = [
        r for r in recs
        if r["cutoff"] is not None and r["npw"] is not None
        and r["npw"] > r["cutoff"] and not r["verbatim"]
    ]
    assert stuck_tail_not_verbatim, "expected stuck no-progress steps that repeat-detection misses"


def test_green_no_progress_arm_fires_only_after_productive_phase():
    """GREEN + non-dampening (the no-progress arm is the risky/tuned one): it fires in
    the dead tail and NEVER at or before the last productive step (action_count 21).
    The verbatim arm (structurally safe — identical-obs re-injection avoidance) is
    allowed to fire anytime and is excluded from this non-dampening check."""
    recs, _ = _replay()
    np_supp = [r for r in recs if r["suppress"] and r["reason"].startswith("no_progress_window")]
    assert np_supp, "expected the no-progress arm to fire in the dead tail"
    assert all(r["ac"] > _LAST_NEW_FILE_AC for r in np_supp), \
        f"no-progress arm dampened productive steps: {[r['ac'] for r in np_supp if r['ac'] <= _LAST_NEW_FILE_AC]}"
    # any verbatim suppressions must be genuine exact-repeats (the safe arm)
    vb_supp = [r for r in recs if r["suppress"] and r["reason"] == "verbatim_repeat"]
    assert all(r["verbatim"] for r in vb_supp)


def test_green_cutoff_is_the_tasks_own_max_gap():
    """The per-task cutoff is derived from the trace, not hardcoded: it equals the
    largest gap between new-file discoveries (11), reached only after >=2 gaps. The
    first no-progress suppression lands exactly when npw first exceeds it (ac=33)."""
    recs, _ = _replay()
    assert recs[-1]["cutoff"] == _PRODUCTIVE_MAX_GAP
    first_np = next(r for r in recs if r["suppress"] and r["reason"].startswith("no_progress_window"))
    assert first_np["npw"] > _PRODUCTIVE_MAX_GAP
    assert first_np["ac"] == _LAST_NEW_FILE_AC + _PRODUCTIVE_MAX_GAP + 1  # 21 + 11 + 1 = 33
