"""Brain Stage 2 — deterministic metric estimator.

Synthetic in-memory graphs + a lightweight fake TrajectoryView (the view↔config
contract is already covered by tests/state/test_trajectory_view.py; here we test
the metric logic in isolation). Includes the laundering guard red-before-green:
a name_match-only graph must NOT inflate required scope / the uncovered-caller set.

Run with gt_slate_brain on PYTHONPATH so ``groundtruth`` resolves to THIS repo:
    PYTHONPATH=D:\\gt_slate_brain\\src python -m pytest tests/brain/test_estimator.py
"""
import sqlite3

from groundtruth.brain import MetricState, estimate
from groundtruth.brain.trace import metric_state_to_dict
from groundtruth.state import Step

# Minimal subset of the gt-index schema (sqlite.go) the estimator queries.
_SCHEMA = """
CREATE TABLE nodes (
    id INTEGER PRIMARY KEY,
    label TEXT NOT NULL,
    name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    signature TEXT,
    return_type TEXT
);
CREATE TABLE edges (
    id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL,
    target_id INTEGER NOT NULL,
    type TEXT NOT NULL,
    resolution_method TEXT,
    confidence REAL DEFAULT 0.0
);
"""

_COCHANGES = """
CREATE TABLE cochanges (
    file_a TEXT NOT NULL,
    file_b TEXT NOT NULL,
    count INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY(file_a, file_b)
);
"""


def make_graph(nodes, edges, cochanges=None):
    """nodes: (id,label,name,file,sig,ret); edges: (sid,tid,type,method,conf)."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(_SCHEMA)
    if cochanges is not None:
        conn.executescript(_COCHANGES)
    for nid, label, name, fp, sig, ret in nodes:
        conn.execute(
            "INSERT INTO nodes(id,label,name,file_path,signature,return_type) VALUES(?,?,?,?,?,?)",
            (nid, label, name, fp, sig, ret),
        )
    for sid, tid, typ, method, conf in edges:
        conn.execute(
            "INSERT INTO edges(source_id,target_id,type,resolution_method,confidence) VALUES(?,?,?,?,?)",
            (sid, tid, typ, method, conf),
        )
    for fa, fb, cnt in (cochanges or []):
        conn.execute("INSERT INTO cochanges(file_a,file_b,count) VALUES(?,?,?)", (fa, fb, cnt))
    conn.commit()
    return conn


class FakeView:
    def __init__(self, *, action_count=0, viewed=(), edited=(),
                 last_new_view_iter=None, last_new_edit_iter=None, repeat=False):
        self.action_count = action_count
        self.viewed_files = frozenset(viewed)
        self.edited_files = frozenset(edited)
        self.last_new_view_iter = last_new_view_iter
        self.last_new_edit_iter = last_new_edit_iter
        self._repeat = repeat

    def verbatim_repeat(self, window=8):
        return self._repeat


# --------------------------------------------------------- trajectory-only metrics
def test_no_progress_window_basic():
    v = FakeView(action_count=10, last_new_view_iter=3, last_new_edit_iter=7)
    assert estimate(v).no_progress_window == 3  # 10 - max(3,7)


def test_no_progress_window_undefined_when_no_new_file():
    v = FakeView(action_count=5)  # never added a file
    assert estimate(v).no_progress_window is None


def test_verbatim_repeat_and_about_to_submit_passthrough():
    v = FakeView(action_count=2, repeat=True)
    s = estimate(v, step=Step("finish", None, "h"))
    assert s.verbatim_repeat is True
    assert s.about_to_submit is True
    assert estimate(v, step=Step("post_edit", "x.py", "h")).about_to_submit is False
    assert estimate(v).about_to_submit is False


# ------------------------------------------------------ scope family undefined-ness
def test_scope_undefined_before_first_edit():
    g = make_graph([(1, "Function", "foo", "x.py", "foo()", "int")], [])
    s = estimate(FakeView(action_count=1, viewed=("x.py",)), g)
    assert s.scope_coverage is None
    assert s.uncovered_callers is None
    assert s.contract_break_risk is None
    assert s.graph_available is True


def test_scope_undefined_without_graph():
    s = estimate(FakeView(action_count=4, edited=("x.py",), last_new_edit_iter=4), None)
    assert s.graph_available is False
    assert s.scope_coverage is None
    assert s.uncovered_callers is None
    assert s.co_change_gap is None


# ----------------------------------------------- deterministic callers + coverage
def _graph_with_callers(caller_method):
    # foo (id1) in x.py; callers a.py(id2), b.py(id3) call it; c.py(id4) name_match.
    nodes = [
        (1, "Function", "foo", "x.py", "foo(a)", "int"),
        (2, "Function", "ca", "a.py", "ca()", ""),
        (3, "Function", "cb", "b.py", "cb()", ""),
        (4, "Function", "cc", "c.py", "cc()", ""),
    ]
    edges = [
        (2, 1, "CALLS", caller_method, 1.0),     # a.py -> foo
        (3, 1, "CALLS", caller_method, 1.0),     # b.py -> foo
        (4, 1, "CALLS", "name_match", 0.9),      # c.py -> foo (NEVER a fact)
    ]
    return make_graph(nodes, edges)


def test_uncovered_callers_deterministic_only():
    g = _graph_with_callers("import")
    v = FakeView(action_count=6, edited=("x.py",), last_new_edit_iter=6)
    s = estimate(v, g)
    # a.py, b.py are verified callers, not yet viewed/edited; c.py is name_match -> excluded
    assert s.uncovered_callers == ("a.py", "b.py")
    assert "c.py" not in (s.required_scope or ())


def test_uncovered_callers_subtract_viewed():
    g = _graph_with_callers("import")
    v = FakeView(action_count=6, edited=("x.py",), viewed=("a.py",), last_new_edit_iter=6)
    assert estimate(v, g).uncovered_callers == ("b.py",)  # a.py already viewed


def test_scope_coverage_partial_then_full():
    g = _graph_with_callers("import")
    # edited only the seed -> required {x,a,b}, covered {x} -> 1/3
    partial = estimate(FakeView(action_count=6, edited=("x.py",), last_new_edit_iter=6), g)
    assert partial.required_scope == ("a.py", "b.py", "x.py")
    assert abs(partial.scope_coverage - 1 / 3) < 1e-9
    # edited all required -> coverage 1.0, nothing uncovered
    full = estimate(
        FakeView(action_count=9, edited=("x.py", "a.py", "b.py"), last_new_edit_iter=9), g
    )
    assert full.scope_coverage == 1.0
    assert full.uncovered_callers == ()


# ----------------------------------------------- THE LAUNDERING GUARD (red-green)
def test_name_match_callers_do_not_inflate_required_scope():
    """A complete internal fix must score coverage = 1 even when name_match callers
    exist. If name_match leaked into `required`, coverage would drop below 1 and a
    correct model would be told its fix is incomplete (a dampen bug)."""
    g = _graph_with_callers("name_match")  # ALL caller edges are name_match
    v = FakeView(action_count=6, edited=("x.py",), last_new_edit_iter=6)
    s = estimate(v, g)
    # required is the edited seed only; name_match callers excluded
    assert s.required_scope == ("x.py",)
    assert s.scope_coverage == 1.0
    assert s.uncovered_callers == ()


def test_same_graph_deterministic_would_flag_incomplete():
    """Contrast partner to the guard: the IDENTICAL edge set, but with a
    deterministic resolution_method, DOES count — proving the filter (not the
    absence of edges) is what suppresses the name_match case."""
    g = _graph_with_callers("import")
    v = FakeView(action_count=6, edited=("x.py",), last_new_edit_iter=6)
    s = estimate(v, g)
    assert s.scope_coverage is not None and s.scope_coverage < 1.0
    assert s.uncovered_callers == ("a.py", "b.py")


# ------------------------------------------------------------- contract_break_risk
def test_contract_break_risk_true_on_sig_change_with_uncovered_caller():
    g = _graph_with_callers("import")  # x.py foo signature is "foo(a)"
    v = FakeView(action_count=6, edited=("x.py",), last_new_edit_iter=6)
    pre = {("x.py", "foo"): ("foo()", "int")}  # old sig differs from current "foo(a)"
    s = estimate(v, g, signature_snapshots=pre)
    assert s.contract_break_risk is True


def test_contract_break_risk_false_when_unchanged():
    g = _graph_with_callers("import")
    v = FakeView(action_count=6, edited=("x.py",), last_new_edit_iter=6)
    pre = {("x.py", "foo"): ("foo(a)", "int")}  # identical to current
    assert estimate(v, g, signature_snapshots=pre).contract_break_risk is False


def test_contract_break_risk_false_without_uncovered_caller():
    g = _graph_with_callers("name_match")  # no verified callers -> none uncovered
    v = FakeView(action_count=6, edited=("x.py",), last_new_edit_iter=6)
    pre = {("x.py", "foo"): ("foo()", "int")}  # changed sig...
    assert estimate(v, g, signature_snapshots=pre).contract_break_risk is False


def test_contract_break_risk_undefined_without_snapshots():
    g = _graph_with_callers("import")
    v = FakeView(action_count=6, edited=("x.py",), last_new_edit_iter=6)
    assert estimate(v, g).contract_break_risk is None


# ------------------------------------------------------------------- co_change_gap
def test_co_change_gap_partners_sorted():
    nodes = [(1, "Function", "foo", "x.py", "foo()", "int")]
    g = make_graph(nodes, [], cochanges=[("x.py", "y.py", 5), ("x.py", "z.py", 2)])
    v = FakeView(action_count=6, edited=("x.py",), last_new_edit_iter=6)
    assert estimate(v, g).co_change_gap == (("y.py", 5), ("z.py", 2))


def test_co_change_gap_excludes_edited_and_undefined_without_table():
    nodes = [(1, "Function", "foo", "x.py", "foo()", "int")]
    g_with = make_graph(nodes, [], cochanges=[("x.py", "y.py", 5)])
    v = FakeView(action_count=6, edited=("x.py", "y.py"), last_new_edit_iter=6)
    assert estimate(v, g_with).co_change_gap == ()  # y.py already edited
    g_without = make_graph(nodes, [])  # no cochanges table
    assert estimate(v, g_without).co_change_gap is None


# ------------------------------------------------------------------------- trace
def test_metric_state_to_dict_is_json_round_trippable():
    import json
    g = _graph_with_callers("import")
    v = FakeView(action_count=6, edited=("x.py",), last_new_edit_iter=6)
    s = estimate(v, g)
    row = metric_state_to_dict(6, s)
    assert json.loads(json.dumps(row))["uncovered_callers"] == ["a.py", "b.py"]
    assert isinstance(s, MetricState)
