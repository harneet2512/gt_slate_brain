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
    b = {"t1", CANARY, "t2"}        # brain adds canary + t2 (two flips)
    r = adjudicate(a, b, tasks=TASKS, canary=CANARY)
    assert r.verdict == "PASS"
    assert set(r.flips) == {CANARY, "t2"}
    assert r.regressions == ()
    assert r.canary_preserved is True
    assert r.net_delta == 2


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
    assert any("net resolution" in x or "no flip" in x for x in r.reasons)


def test_bounded_task_set_excludes_extraneous_ids():
    # an id resolved in B but NOT in the intended task list must not count as a flip
    a = {"t1"}
    b = {"t1", CANARY, "stray_task_not_in_list"}
    r = adjudicate(a, b, tasks=TASKS, canary=CANARY)
    assert "stray_task_not_in_list" not in r.flips
    assert set(r.flips) == {CANARY}
