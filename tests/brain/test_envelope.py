"""TTD for the Stage-6 EvidenceEnvelope — the typed unit producers emit.

Proves: determinism is DERIVED from provenance (never producer-set); name_match is
never deterministic; a non-deterministic envelope renders as an explicit
(unverified) hint, never a fact; the rendered block passes the delivery gate.
"""
from __future__ import annotations

from groundtruth.brain.delivery import verify_block
from groundtruth.brain.envelope import (
    EvidenceEnvelope,
    derive_deterministic,
    render_envelope,
)


def test_deterministic_derived_from_resolution_method():
    assert derive_deterministic("import") is True
    assert derive_deterministic("same_file") is True
    assert derive_deterministic("name_match") is False
    assert derive_deterministic("unknown") is False
    assert derive_deterministic(None) is False


def test_producer_cannot_assert_determinism():
    # producer passes deterministic=True on a name_match edge — must be overwritten
    env = EvidenceEnvelope(
        layer="L3", kind="caller", body="foo calls bar",
        resolution_method="name_match", deterministic=True,
    )
    assert env.deterministic is False


def test_verified_provenance_is_deterministic():
    env = EvidenceEnvelope(layer="L3", kind="caller", body="foo calls bar",
                           resolution_method="import")
    assert env.deterministic is True


def test_dedupe_key_derived_and_stable():
    a = EvidenceEnvelope(layer="L3", kind="caller", body="foo calls bar",
                         resolution_method="import", target_file="x.py", symbol="foo")
    b = EvidenceEnvelope(layer="L3", kind="caller", body="foo   calls bar",
                         resolution_method="import", target_file="x.py", symbol="foo")
    assert a.dedupe_key and len(a.dedupe_key) == 16
    assert a.dedupe_key == b.dedupe_key  # whitespace-normalized


def test_render_verified_has_no_unverified_marker():
    env = EvidenceEnvelope(layer="L3", kind="caller", body="[CALLER] foo calls bar",
                           resolution_method="import")
    out = render_envelope(env)
    assert "(unverified" not in out
    assert verify_block(out) == out  # passes the delivery gate


def test_render_name_match_is_an_unverified_hint():
    env = EvidenceEnvelope(layer="L3", kind="caller", body="[CALLER] foo calls bar",
                           resolution_method="name_match")
    out = render_envelope(env)
    assert "(unverified" in out          # never rendered as a fact
    assert verify_block(out) == out


def test_render_empty_body_is_silent():
    env = EvidenceEnvelope(layer="L3", kind="caller", body="   ",
                           resolution_method="import")
    assert render_envelope(env) == ""
