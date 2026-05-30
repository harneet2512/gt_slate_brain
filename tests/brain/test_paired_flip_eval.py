"""TTD for the paired flip adjudicator (FLIP_AUDIT §5).

Proves the verdict logic: a flip with canary preserved and zero regressions
PASSes; a canary break, any regression, or no-flip-with-flat-delta KILLs.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "brain"))

from paired_flip_eval import adjudicate, load_resolved, mcnemar  # noqa: E402

CANARY = "Kozea__WeasyPrint-2300"
TASKS = {CANARY, "t1", "t2", "t3", "t4"}


# ---- load_resolved: robust to report shapes ----

def test_load_resolved_resolved_ids_list():
    assert load_resolved({"resolved_ids": ["a", "b"]}) == {"a", "b"}


def test_load_resolved_bare_list():
    assert load_resolved(["a", "b"]) == {"a", "b"}


def test_load_resolved_per_task_dict():
    assert load_resolved({"a": {"resolved": True}, "b": {"resolved": False}, "c": True}) == {"a", "c"}


def test_load_resolved_raises_on_count_style_report():
    # a count-style / ambiguous report must FAIL LOUD, not be misparsed by
    # iterating metadata keys as instance_ids (#4)
    import pytest
    with pytest.raises(ValueError):
        load_resolved({"resolved": 3, "unresolved": 2})
    with pytest.raises(ValueError):
        load_resolved({"resolved_ids": None, "instances": {"x": True}})


# ---- mcnemar counts + exact p ----

def test_mcnemar_no_discordant():
    mc = mcnemar(b=0, c=0)
    assert mc["n_discordant"] == 0 and mc["exact_p"] == 1.0


def test_mcnemar_flips_only():
    mc = mcnemar(b=0, c=3)  # 3 flips, 0 regressions
    assert mc["c_flips"] == 3 and mc["b_regressions"] == 0
    assert 0.0 < mc["exact_p"] <= 0.25 + 1e-9  # 2*(0.5^3) = 0.25


# ---- adjudicate: PASS path ----

def test_pass_one_flip_canary_preserved_no_regression():
    a = {"t1"}                      # baseline resolves t1
    b = {"t1", CANARY, "t2"}        # brain adds canary (control) + t2 (the new flip)
    r = adjudicate(a, b, tasks=TASKS, canary=CANARY)
    assert r.verdict == "PASS"
    # canary is the must-preserve control, NOT counted as a flip
    assert set(r.flips) == {"t2"}
    assert CANARY not in r.flips
    assert r.regressions == ()
    assert r.canary_preserved is True
    assert r.net_delta == 2


def test_canary_only_flip_is_not_a_pass():
    # brain resolves ONLY the canary (the control), nothing new -> not a PASS (#7)
    a = {"t1"}
    b = {"t1", CANARY}
    r = adjudicate(a, b, tasks=TASKS, canary=CANARY)
    assert r.verdict == "KILL"
    assert r.flips == ()
    assert r.canary_preserved is True
    assert any("no new" in x for x in r.reasons)


def test_canary_omitted_from_task_list_not_false_killed():
    # canary resolved in B but NOT listed in --tasks -> must NOT be a false KILL (#2)
    a = {"t1"}
    b = {"t1", "t2", CANARY}
    r = adjudicate(a, b, tasks={"t1", "t2"}, canary=CANARY)  # CANARY omitted from tasks
    assert r.canary_preserved is True   # checked against raw arm-B set
    assert set(r.flips) == {"t2"}
    assert r.verdict == "PASS"


# ---- adjudicate: KILL paths ----

def test_kill_canary_broken():
    a = {"t1"}
    b = {"t1", "t2"}                # flip on t2 but canary NOT resolved
    r = adjudicate(a, b, tasks=TASKS, canary=CANARY)
    assert r.verdict == "KILL"
    assert r.canary_preserved is False
    assert any("canary" in x for x in r.reasons)


def test_kill_regression_is_dampening():
    a = {CANARY, "t1"}
    b = {CANARY, "t2"}             # gained t2 (flip) but LOST t1 (regression)
    r = adjudicate(a, b, tasks=TASKS, canary=CANARY)
    assert r.verdict == "KILL"
    assert r.regressions == ("t1",)
    assert any("regression" in x for x in r.reasons)


def test_kill_no_flip_flat_delta():
    a = {CANARY, "t1"}
    b = {CANARY, "t1"}            # identical — no flip, Δ=0
    r = adjudicate(a, b, tasks=TASKS, canary=CANARY)
    assert r.verdict == "KILL"
    assert r.flips == ()
    assert any("no new" in x for x in r.reasons)


def test_bounded_task_set_excludes_extraneous_ids():
    # an id resolved in B but NOT in the intended task list must not count as a flip
    a = {"t1"}
    b = {"t1", CANARY, "stray_task_not_in_list"}
    r = adjudicate(a, b, tasks=TASKS, canary=CANARY)
    assert "stray_task_not_in_list" not in r.flips
    # CANARY is the control (excluded from flips); stray is excluded by the universe
    assert CANARY not in r.flips
    assert r.flips == ()
