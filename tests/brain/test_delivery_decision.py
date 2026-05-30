"""TTD for decide_delivery — the single Brain decision EVERY layer's agent-bound
content routes through (the intermediary that makes producers into sensors)."""
from __future__ import annotations

from groundtruth.brain.delivery import decide_delivery


def test_safe_block_delivers():
    d = decide_delivery("L3", '<gt-evidence kind="x">real body</gt-evidence>')
    assert d.deliver and d.layer == "L3"
    assert d.text == '<gt-evidence kind="x">real body</gt-evidence>'


def test_unsafe_block_suppressed():
    assert decide_delivery("L3", "").deliver is False               # empty
    assert decide_delivery("L3", "[GT_META] leak").deliver is False  # diag leak
    assert decide_delivery("L3", "<gt-evidence/>").deliver is False  # self-closing
    assert decide_delivery("L3", "<gt-evidence></gt-evidence>").deliver is False  # empty body


def test_dedup_suppresses_repeat_same_layer():
    seen: set[str] = set()
    first = decide_delivery("L3", "[CALLER] foo calls bar", seen=seen)
    second = decide_delivery("L3", "[CALLER] foo   calls bar", seen=seen)  # ws-normalized dup
    assert first.deliver is True
    assert second.deliver is False and second.reason == "duplicate"


def test_dedup_is_per_layer():
    seen: set[str] = set()
    a = decide_delivery("L3", "[CALLER] foo", seen=seen)
    b = decide_delivery("L3b", "[CALLER] foo", seen=seen)  # same content, different layer
    assert a.deliver is True and b.deliver is True  # not a cross-layer dup


def test_no_seen_set_means_no_dedup():
    # without a seen-set the same block delivers every time (safety still applies)
    t = "[SCOPE] one\n[SCOPE] two"
    assert decide_delivery("L5", t).deliver is True
    assert decide_delivery("L5", t).deliver is True
