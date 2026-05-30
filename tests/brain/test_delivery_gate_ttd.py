"""Stage 3 delivery-gate TTD — artifact-derived, not implementation-derived.

The fixture (tests/brain/fixtures/delivery_blocks.json) holds a REAL malformed-
delivery signature extracted from a frozen GT run: ``[GT_STATUS] success:test_targets:8``
glued into an agent observation (a telemetry line that reached the model as content),
plus a well-formed ``<gt-evidence>`` block from the same artifacts as the positive
control. The gate must DROP the former and PASS the latter.

Run with gt_slate_brain on PYTHONPATH.
"""
import json
from pathlib import Path

from groundtruth.brain import verify_block

_FX = json.loads((Path(__file__).parent / "fixtures" / "delivery_blocks.json").read_text(encoding="utf-8"))


def test_real_diagnostic_leak_is_dropped():
    leak = _FX["real_diagnostic_leak"]
    assert "[GT_" in leak  # fixture provenance: it really contains a GT_* diagnostic
    assert verify_block(leak) is None


def test_wellformed_block_passes():
    block = _FX["wellformed_block"]
    assert block and "<gt-evidence" in block
    assert verify_block(block) == block  # passes unchanged


def test_content_markers_are_not_diagnostics():
    # [SIGNATURE]/[PATTERN]/[CALLERS]/[CONTRACT] are content, must pass
    ok = "<gt-evidence>\n[CONTRACT] returns Optional[User]\n[CALLERS] 2 in foo.py\n</gt-evidence>"
    assert verify_block(ok) == ok


def test_empty_and_whitespace_dropped():
    assert verify_block(None) is None
    assert verify_block("") is None
    assert verify_block("   \n  ") is None


def test_empty_and_self_closing_tags_dropped():
    assert verify_block('<gt-evidence dedup="true" />') is None      # empty-dedup noise class
    assert verify_block("<gt-evidence kind='x'></gt-evidence>") is None  # whitespace body
    assert verify_block("<gt-evidence>   </gt-evidence>") is None


def test_multiple_tags_not_single_tagged_dropped():
    two = "<gt-evidence>a</gt-evidence>\n<gt-evidence>b</gt-evidence>"
    assert verify_block(two) is None


def test_meta_and_delivery_leaks_dropped():
    assert verify_block("foo\n[GT_META] prebuilt_graph_db: x\nbar") is None
    assert verify_block("[GT_DELIVERY] append_observation OK") is None
