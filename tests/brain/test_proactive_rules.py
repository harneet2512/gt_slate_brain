"""TTD for the authorized proactive rules (FLIP_AUDIT §4 bundle + the deferred
completeness + wandering rules) and their content renderers.

Invariants checked: fire only on VERIFIED content, diagnostic framing, single
well-formed <gt-evidence> that passes the delivery gate, no [GT_*] leak, silent
when nothing verified exists.
"""
from __future__ import annotations

import sqlite3

from groundtruth.brain.content import (
    render_completeness_note,
    render_evidence_bundle,
    render_wandering_note,
)
from groundtruth.brain.delivery import verify_block
from groundtruth.brain.estimator import estimate
from groundtruth.brain.policy import (
    decide_bundle,
    decide_completeness,
    decide_wandering,
)


class FakeView:
    def __init__(self, *, edited=(), viewed=(), action_count=10,
                 last_new_view_iter=None, last_new_edit_iter=1,
                 new_file_iters=(), source_edit_iters=(1,)):
        self.edited_files = frozenset(edited)
        self.viewed_files = frozenset(viewed)
        self.action_count = action_count
        self.last_new_view_iter = last_new_view_iter
        self.last_new_edit_iter = last_new_edit_iter
        self.new_file_iters = tuple(new_file_iters)
        self.source_edit_iters = tuple(source_edit_iters)

    def verbatim_repeat(self, window=8):
        return False


class FakeState:
    def __init__(self, **kw):
        self.uncovered_callers = kw.get("uncovered_callers")
        self.visible_tests = kw.get("visible_tests")
        self.required_scope = kw.get("required_scope")
        self.co_change_gap = kw.get("co_change_gap")
        self.no_progress_window = kw.get("no_progress_window")
        self.about_to_submit = kw.get("about_to_submit", False)


# --------------------------- estimator.visible_tests ---------------------------

def _graph_with_assertion(edited_file: str, *, target_resolved: bool) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE nodes (id INTEGER PRIMARY KEY, file_path TEXT, name TEXT, "
        "label TEXT, signature TEXT, return_type TEXT, is_test INTEGER DEFAULT 0)"
    )
    conn.execute(
        "CREATE TABLE assertions (id INTEGER PRIMARY KEY, test_node_id INTEGER, "
        "target_node_id INTEGER DEFAULT 0, resolution_score REAL, kind TEXT, "
        "expression TEXT, expected TEXT, line INTEGER)"
    )
    conn.execute("INSERT INTO nodes VALUES (1, ?, 'parse', 'Function', 'parse(x)', 'int', 0)", (edited_file,))
    conn.execute("INSERT INTO nodes VALUES (2, 'tests/test_p.py', 'test_parse', 'Function', '', '', 1)")
    tgt = 1 if target_resolved else 0
    conn.execute(
        "INSERT INTO assertions VALUES (1, 2, ?, 1.0, 'equals', 'parse(\"x\") == 1', '1', 5)",
        (tgt,),
    )
    conn.commit()
    return conn


def test_estimator_surfaces_verified_visible_test():
    conn = _graph_with_assertion("src/p.py", target_resolved=True)
    view = FakeView(edited=["src/p.py"], last_new_edit_iter=1, action_count=3)
    st = estimate(view, conn)
    assert st.visible_tests is not None
    assert ("tests/test_p.py", "test_parse", 'parse("x") == 1') in st.visible_tests


def test_estimator_ignores_unverified_assertion_link():
    # target_node_id == 0 is an UNRESOLVED link — must never surface as a fact.
    conn = _graph_with_assertion("src/p.py", target_resolved=False)
    view = FakeView(edited=["src/p.py"], last_new_edit_iter=1, action_count=3)
    st = estimate(view, conn)
    assert st.visible_tests == ()


# ------------------------------ §4 bundle rule ------------------------------

def test_bundle_fires_at_first_edit_on_verified_content():
    view = FakeView(edited=["src/p.py"])
    st = FakeState(uncovered_callers=("a.py", "b.py"),
                   visible_tests=(("tests/t.py", "test_x", "x==1"),))
    d = decide_bundle(view, st)
    assert d.fire and d.callers == ("a.py", "b.py") and len(d.tests) == 1


def test_bundle_silent_without_verified_content():
    view = FakeView(edited=["src/p.py"])
    assert decide_bundle(view, FakeState()).fire is False
    # and never before an edit
    assert decide_bundle(FakeView(edited=[]), FakeState(uncovered_callers=("a.py",))).fire is False


def test_bundle_fires_once():
    view = FakeView(edited=["src/p.py"])
    st = FakeState(uncovered_callers=("a.py",))
    assert decide_bundle(view, st, already_fired=True).fire is False


def test_bundle_not_gated_on_signature_change():
    # the whole point of the redirect: no contract_break_risk needed (weasyprint).
    view = FakeView(edited=["src/p.py"])
    st = FakeState(visible_tests=(("tests/t.py", "test_x", "x==1"),))  # callers empty, no sig change
    assert decide_bundle(view, st).fire is True


# ------------------------------ completeness rule ------------------------------

def test_completeness_fires_at_submit_on_uncovered_scope():
    view = FakeView(edited=["src/p.py"], source_edit_iters=(2,), action_count=2)
    st = FakeState(about_to_submit=True, required_scope=("src/p.py", "src/q.py"),
                   co_change_gap=(("src/r.py", 4),))
    d = decide_completeness(view, st)
    assert d.fire and "src/q.py" in d.uncovered_scope and ("src/r.py", 4) in d.co_change


def test_completeness_silent_when_fully_covered():
    view = FakeView(edited=["src/p.py"], action_count=10, source_edit_iters=(1,))
    st = FakeState(about_to_submit=True, required_scope=("src/p.py",), co_change_gap=())
    assert decide_completeness(view, st).fire is False


def test_completeness_silent_before_review_or_submit():
    view = FakeView(edited=["src/p.py"], action_count=2, source_edit_iters=(2,))  # just edited
    st = FakeState(about_to_submit=False, required_scope=("src/p.py", "src/q.py"))
    assert decide_completeness(view, st).fire is False


# ------------------------------ wandering rule ------------------------------

def test_wandering_fires_with_verified_scope():
    # cadence: new files at iters 0 and 2 -> max gap 2; npw=5 > cutoff 2
    view = FakeView(edited=["src/p.py"], viewed=["src/p.py"], new_file_iters=(0, 2, 4))
    # 3 discoveries -> 2 gaps (cutoff defined); npw below well exceeds the max gap (2)
    st = FakeState(no_progress_window=9, required_scope=("src/p.py", "src/q.py"))
    d = decide_wandering(view, st)
    assert d.fire and "src/q.py" in d.scope and "src/p.py" not in d.scope  # seen excluded


def test_wandering_silent_without_verified_scope():
    view = FakeView(edited=["src/p.py"], viewed=["src/p.py"])
    view.new_file_iters = (0, 2, 4)
    st = FakeState(no_progress_window=9, required_scope=("src/p.py",))  # all seen
    assert decide_wandering(view, st).fire is False


def test_wandering_silent_when_not_wandering():
    view = FakeView(edited=["src/p.py"])
    view.new_file_iters = (0, 1, 2)
    st = FakeState(no_progress_window=0, required_scope=("src/q.py",))
    assert decide_wandering(view, st).fire is False


# ------------------------------ content renderers ------------------------------

def test_bundle_render_passes_delivery_gate_and_has_no_diag_leak():
    out = render_evidence_bundle(("a.py", "b.py"), (("tests/t.py", "test_x", "x == 1"),))
    assert verify_block(out) == out
    assert "[GT_" not in out
    assert "[CALLERS]" in out and "[TESTS]" in out


def test_completeness_render_passes_gate():
    out = render_completeness_note(("src/q.py",), (("src/r.py", 3),))
    assert verify_block(out) == out and "[GT_" not in out


def test_wandering_render_passes_gate():
    out = render_wandering_note(("src/q.py",))
    assert verify_block(out) == out and "[GT_" not in out


def test_renderers_empty_on_no_content():
    assert render_evidence_bundle((), ()) == ""
    assert render_completeness_note((), ()) == ""
    assert render_wandering_note(()) == ""
