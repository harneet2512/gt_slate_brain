"""Stage 5 proactive contract-break TTD (hybrid: contract-break trigger + uncovered-
caller payload).

Two halves:
- Synthetic-graph unit tests for the firing LOGIC (no graph.db artifact exists, so the
  graph-scope part can only be unit-tested on a controlled graph — the honest constraint).
- The headline NON-DAMPENING claim on the REAL sh-744 trajectory: at its edit→review
  transition the timing gate opens, but with no verified contract break the rule stays
  SILENT — exactly where a `scope_coverage < 1` completeness rule WOULD have false-positived
  (sh-744 failed on logic, not a missed caller). This is why the hybrid beats completeness.

Run with gt_slate_brain on PYTHONPATH (+ scripts/swebench for the sh-744 replay).
"""
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "swebench"))
import oh_gt_full_wrapper as w  # noqa: E402

from groundtruth.brain import (  # noqa: E402
    decide_proactive,
    estimate,
    is_review_phase,
    render_contract_break_note,
    verify_block,
)
from groundtruth.state import Step  # noqa: E402

_SCHEMA = """
CREATE TABLE nodes (id INTEGER PRIMARY KEY, label TEXT, name TEXT, file_path TEXT, signature TEXT, return_type TEXT);
CREATE TABLE edges (id INTEGER PRIMARY KEY, source_id INT, target_id INT, type TEXT, resolution_method TEXT, confidence REAL);
"""


def _graph(foo_sig="foo(a, b)"):
    """foo (id1, sig=foo_sig) in x.py; verified callers a.py, b.py."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(_SCHEMA)
    conn.execute("INSERT INTO nodes VALUES(1,'Function','foo','x.py',?, 'int')", (foo_sig,))
    conn.execute("INSERT INTO nodes VALUES(2,'Function','ca','a.py','ca()','')")
    conn.execute("INSERT INTO nodes VALUES(3,'Function','cb','b.py','cb()','')")
    conn.execute("INSERT INTO edges VALUES(1,2,1,'CALLS','import',1.0)")  # a.py -> foo
    conn.execute("INSERT INTO edges VALUES(2,3,1,'CALLS','import',1.0)")  # b.py -> foo
    conn.commit()
    return conn


class FakeView:
    def __init__(self, *, action_count=0, viewed=(), edited=(), source_edit_iters=(),
                 new_file_iters=(), last_new_view_iter=None, last_new_edit_iter=None, repeat=False):
        self.action_count = action_count
        self.viewed_files = frozenset(viewed)
        self.edited_files = frozenset(edited)
        self.source_edit_iters = tuple(source_edit_iters)
        self.new_file_iters = tuple(new_file_iters)
        self.last_new_view_iter = last_new_view_iter
        self.last_new_edit_iter = last_new_edit_iter
        self._repeat = repeat

    def verbatim_repeat(self, window=8):
        return self._repeat


def _review_view(**kw):
    # review phase: edited a source file at iter 5, now at 10 (>=3 actions later)
    kw.setdefault("action_count", 10)
    kw.setdefault("source_edit_iters", (5,))
    kw.setdefault("edited", ("x.py",))
    kw.setdefault("last_new_edit_iter", 5)
    return FakeView(**kw)


# ---------------------------------------------------------------- firing logic
def test_fires_on_real_contract_break():
    g = _graph(foo_sig="foo(a, b)")        # current sig
    snap = {("x.py", "foo"): ("foo(a)", "int")}  # pre-edit sig differs -> changed
    v = _review_view()
    state = estimate(v, g, signature_snapshots=snap)
    assert state.contract_break_risk is True
    dec = decide_proactive(v, state)
    assert dec.fire is True
    assert set(dec.callers) == {"a.py", "b.py"}


def test_silent_when_signature_unchanged():
    """NON-DAMPENING: a correct internal-only fix (no signature change) stays silent
    even though verified uncovered callers exist."""
    g = _graph(foo_sig="foo(a, b)")
    snap = {("x.py", "foo"): ("foo(a, b)", "int")}  # identical -> NOT changed
    v = _review_view()
    state = estimate(v, g, signature_snapshots=snap)
    assert state.contract_break_risk is False
    assert decide_proactive(v, state).fire is False


def test_silent_when_callers_covered():
    g = _graph(foo_sig="foo(a, b)")
    snap = {("x.py", "foo"): ("foo(a)", "int")}      # changed...
    v = _review_view(edited=("x.py", "a.py", "b.py"))  # ...but all callers edited
    state = estimate(v, g, signature_snapshots=snap)
    assert state.contract_break_risk is False  # no uncovered caller
    assert decide_proactive(v, state).fire is False


def test_silent_before_review_phase():
    g = _graph(foo_sig="foo(a, b)")
    snap = {("x.py", "foo"): ("foo(a)", "int")}
    v = FakeView(action_count=6, source_edit_iters=(5,), edited=("x.py",), last_new_edit_iter=5)
    assert is_review_phase(v) is False          # only 1 action since edit (<3)
    state = estimate(v, g, signature_snapshots=snap)
    assert state.contract_break_risk is True    # break exists...
    assert decide_proactive(v, state).fire is False  # ...but not review time yet


def test_fire_once():
    g = _graph(foo_sig="foo(a, b)")
    snap = {("x.py", "foo"): ("foo(a)", "int")}
    v = _review_view()
    state = estimate(v, g, signature_snapshots=snap)
    assert decide_proactive(v, state, already_fired=True).fire is False


# --------------------------------------------------------------- content + gate
def test_note_is_wellformed_and_passes_gate():
    note = render_contract_break_note(("a.py", "b.py"))
    assert "[CONTRACT]" in note and "a.py" in note
    assert verify_block(note) == note          # survives the delivery gate
    assert "verify" in note.lower() or "confirm" in note.lower()  # diagnostic, not prescriptive
    assert render_contract_break_note(()) == ""  # nothing to say -> empty


# ----------------------------------------------- REAL artifact: non-dampening
def test_sh744_review_phase_but_no_false_positive():
    """Headline: on the real sh-744 trajectory the timing gate opens in the dead tail
    (is_review_phase True), but with no VERIFIED contract break the proactive rule stays
    SILENT — exactly the false-positive a scope_coverage<1 completeness rule would have
    produced on this logic-bug failure."""
    fx = json.loads((Path(__file__).parent / "fixtures" / "sh744_loop_steps.json").read_text(encoding="utf-8"))
    from groundtruth.state import TrajectoryView
    cfg = w.GTRuntimeConfig()
    view = TrajectoryView(cfg)
    saw_review = False
    fired = False
    for st in fx["steps"]:
        cfg.action_count += 1
        kind, rel = st.get("kind", "skip"), st.get("file")
        if kind == "post_view" and rel:
            cfg.record_view(rel)
        elif kind == "post_edit" and rel:
            cfg.record_edit(rel)
            # mirror the wrapper: source edits populate _source_edit_actions
            cfg._source_edit_actions.append(cfg.action_count)
        if is_review_phase(view):
            saw_review = True
        # graph-free estimate (no graph.db artifact) -> contract_break_risk is None
        state = estimate(view, None, step=Step(kind, rel, str(st.get("obs_hash", ""))))
        if decide_proactive(view, state, already_fired=fired).fire:
            fired = True
    assert saw_review, "timing gate must open at sh-744's edit->review tail"
    assert not fired, "no verified contract break -> proactive rule must stay SILENT (non-dampening)"
