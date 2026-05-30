"""Brain Stage 1 — TrajectoryView read-only accessor.

Drives the REAL ``GTRuntimeConfig`` (from the OH wrapper) plus its new
``record_view`` / ``record_edit`` helpers through synthetic sequences and asserts
the ``TrajectoryView`` projection. No OpenHands runtime needed — the wrapper is
import-safe by design (its docstring: "the small functions below are deliberately
testable with fake runtimes").

Covers the Stage 1 GATE cases:
- undefined-before-first-action, undefined-before-first-edit
- first-seen stamping (new file advances last_new_*_iter; repeat does not)
- projection correctness + copy-not-alias of the exposed collections
- per-step / loop projection (last_obs_hash, verbatim_repeat, step()).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "swebench"))
import oh_gt_full_wrapper as w  # noqa: E402

from groundtruth.state import Step, TrajectoryView  # noqa: E402
from groundtruth.state.trajectory_view import Step as StepDirect  # noqa: E402


def _cfg():
    return w.GTRuntimeConfig()


# --------------------------------------------------------------- undefined state
def test_undefined_before_first_action():
    v = TrajectoryView(_cfg())
    assert v.action_count == 0
    assert v.viewed_files == frozenset()
    assert v.edited_files == frozenset()
    assert v.source_edit_iters == ()
    assert v.search_count_since_edit == 0
    assert v.last_new_view_iter is None
    assert v.last_new_edit_iter is None
    assert v.last_obs_hash is None
    assert v.verbatim_repeat() is False


def test_undefined_before_first_edit():
    c = _cfg()
    c.action_count = 2
    c.record_view("src/a.py")
    v = TrajectoryView(c)
    assert v.viewed_files == frozenset({"src/a.py"})
    assert v.last_new_view_iter == 2
    # no edit yet
    assert v.edited_files == frozenset()
    assert v.last_new_edit_iter is None
    assert v.source_edit_iters == ()


# ------------------------------------------------------------- first-seen stamps
def test_new_view_advances_last_new_view_iter():
    c = _cfg()
    c.action_count = 3
    c.record_view("src/a.py")
    assert TrajectoryView(c).last_new_view_iter == 3
    # NEW file at a later count advances it
    c.action_count = 7
    c.record_view("src/b.py")
    assert TrajectoryView(c).last_new_view_iter == 7
    # REPEAT of an already-seen file does NOT advance it
    c.action_count = 11
    c.record_view("src/a.py")
    assert TrajectoryView(c).last_new_view_iter == 7
    assert TrajectoryView(c).viewed_files == frozenset({"src/a.py", "src/b.py"})


def test_new_edit_advances_last_new_edit_iter():
    c = _cfg()
    c.action_count = 4
    c.record_edit("src/x.py")
    assert TrajectoryView(c).last_new_edit_iter == 4
    c.action_count = 9
    c.record_edit("src/y.py")
    assert TrajectoryView(c).last_new_edit_iter == 9
    c.action_count = 15
    c.record_edit("src/x.py")  # repeat
    assert TrajectoryView(c).last_new_edit_iter == 9
    assert TrajectoryView(c).edited_files == frozenset({"src/x.py", "src/y.py"})


def test_record_view_appends_read_history_like_old_inline():
    # behavior-preserving: record_view does set-add + _read_history append
    c = _cfg()
    c.record_view("src/a.py")
    c.record_view("src/a.py")  # repeat still appends to ordered history
    assert c._read_history == ["src/a.py", "src/a.py"]
    assert c.viewed_files == {"src/a.py"}


def test_record_edit_does_not_touch_source_edit_or_presubmit():
    # record_edit must ONLY add to edited_files + stamp; the scaffold/test-gated
    # _source_edit_actions / _presubmit_* tracking stays at the wrapper call-site.
    c = _cfg()
    c.action_count = 5
    c.record_edit("src/x.py")
    assert c.edited_files == {"src/x.py"}
    assert c._source_edit_actions == []
    assert c._presubmit_edited_files == set()


# ------------------------------------------------------------- projection / copy
def test_projection_mirrors_config_fields():
    c = _cfg()
    c.action_count = 12
    c._source_edit_actions = [4, 9]
    c._search_count_since_edit = 3
    v = TrajectoryView(c)
    assert v.action_count == 12
    assert v.source_edit_iters == (4, 9)
    assert v.search_count_since_edit == 3


def test_exposed_collections_are_copies_not_aliases():
    c = _cfg()
    c.record_view("src/a.py")
    c.record_edit("src/x.py")
    c._source_edit_actions = [1]
    v = TrajectoryView(c)
    # mutating the returned collections must not affect the config
    viewed = set(v.viewed_files)
    viewed.add("HACK")
    assert "HACK" not in c.viewed_files
    edited = set(v.edited_files)
    edited.add("HACK")
    assert "HACK" not in c.edited_files
    assert isinstance(v.viewed_files, frozenset)
    assert isinstance(v.source_edit_iters, tuple)


# --------------------------------------------------------------- per-step / loop
def test_last_obs_hash_projection():
    c = _cfg()
    c._stuck_compat_history = [("Act:cmd1", "h1"), ("Act:cmd2", "h2")]
    assert TrajectoryView(c).last_obs_hash == "h2"


def test_verbatim_repeat_mirrors_is_repeated_obs():
    c = _cfg()
    # latest pair (a,h1) appears in the preceding window -> repeat
    c._stuck_compat_history = [("a", "h1"), ("b", "h2"), ("a", "h1")]
    assert TrajectoryView(c).verbatim_repeat(window=8) is True
    # latest pair is novel -> not a repeat
    c._stuck_compat_history = [("a", "h1"), ("b", "h2")]
    assert TrajectoryView(c).verbatim_repeat(window=8) is False
    # the repeated pair is OUTSIDE the window -> not a repeat
    c._stuck_compat_history = [("a", "h1"), ("b", "h2"), ("c", "h3"), ("a", "h1")]
    assert TrajectoryView(c).verbatim_repeat(window=2) is False


def test_step_packages_event_and_hash():
    c = _cfg()
    v = TrajectoryView(c)
    ev = w.classify_tool_event  # use real HookEvent via classify? simpler: build one
    # build a HookEvent directly (kind/path/reason dataclass)
    he = w.HookEvent("post_edit", path="src/x.py")
    s = v.step(he, "deadbeef")
    assert isinstance(s, Step) and Step is StepDirect
    assert s.kind == "post_edit"
    assert s.file == "src/x.py"
    assert s.obs_hash == "deadbeef"
    # skip event with no path -> file is None
    he2 = w.HookEvent("skip", reason="non_source_ext")
    assert v.step(he2, "abc").file is None
    del ev  # silence unused
