"""Stage 3 wiring — prove the GT_BRAIN gate is actually wired into the wrapper's
delivery choke (append_observation), ON and OFF. The loop-gate DECISION logic is
proven by test_policy_loop_ttd (replay through the same estimate/decide the gate
calls); this file proves the delivery gate's wire and the default-off invariant.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "swebench"))
import oh_gt_full_wrapper as w  # noqa: E402


class _Obs:
    def __init__(self, content=""):
        self.content = content


def test_brain_imports_available():
    assert w._BRAIN_AVAILABLE, "brain package must import inside the wrapper"


def test_delivery_gate_on_drops_malformed_keeps_wellformed(monkeypatch):
    monkeypatch.setattr(w, "_GT_BRAIN", True)
    o = _Obs("BASE")
    w.append_observation(o, '<gt-evidence dedup="true" />')      # empty self-closing
    assert o.content == "BASE", "malformed self-closing tag must be dropped"
    w.append_observation(o, "x\n[GT_STATUS] success:test_targets:8\ny")  # diagnostic leak
    assert o.content == "BASE", "diagnostic [GT_*] leak must be dropped"
    w.append_observation(o, "<gt-evidence>\n[CONTRACT] returns int\n</gt-evidence>")  # ok
    assert "[CONTRACT]" in o.content, "well-formed evidence must pass"


def test_delivery_gate_off_is_passthrough(monkeypatch):
    # default OFF: the gate must NOT alter behavior (no silent dropping)
    monkeypatch.setattr(w, "_GT_BRAIN", False)
    o = _Obs("BASE")
    w.append_observation(o, '<gt-evidence dedup="true" />')
    assert "dedup" in o.content, "with GT_BRAIN off, append must behave exactly as before"


# --- Finding 1 (BRAIN_CAPABILITY_AUDIT): suppress must NOT skip L6 reindex ---
# The loop gate early-returns before the post_edit dispatch where reindex lives. A
# suppressed EDIT changed the file, so graph.db must still be refreshed or the next
# step's scope/contract metrics read a stale signature. Only the INJECTION is dropped.

def test_suppressed_edit_still_reindexes(monkeypatch):
    calls = []
    monkeypatch.setattr(w, "_run_internal", lambda orig, cmd, timeout: calls.append(cmd))
    cfg = w.GTRuntimeConfig()
    cfg.gt_index_bin = "/tmp/gt-index"
    cfg.graph_db = "/tmp/g.db"
    cfg.workspace_root = "/workspace"
    ev = w.HookEvent("post_edit", path="/workspace/x.py")
    w._brain_handle_suppress(cfg, ev, "x.py", _Obs("c"), orig_run_action=lambda a: a)
    assert calls, "a suppressed EDIT must trigger L6 reindex (Finding 1)"
    assert "gt-index" in calls[0] and "g.db" in calls[0]
    assert "x.py" in cfg.edited_files  # tracking preserved


def test_suppressed_view_does_not_reindex(monkeypatch):
    calls = []
    monkeypatch.setattr(w, "_run_internal", lambda orig, cmd, timeout: calls.append(cmd))
    cfg = w.GTRuntimeConfig()
    cfg.gt_index_bin = "/tmp/gt-index"
    cfg.graph_db = "/tmp/g.db"
    cfg.workspace_root = "/workspace"
    ev = w.HookEvent("post_view", path="/workspace/x.py")
    w._brain_handle_suppress(cfg, ev, "x.py", _Obs(""), orig_run_action=lambda a: a)
    assert not calls, "a suppressed VIEW changes nothing — must not reindex"
    assert "x.py" in cfg.viewed_files
