"""Stage 3 — the single delivery-verification gate (invariant 6).

Every GT injection must pass through one choke that verifies what is actually about
to reach the agent's observation. ``verify_block`` returns the block to inject, or
``None`` to DROP it. This closes the leak/empty/brief-shredding bug class: a dropped
block is never appended, so telemetry text and zero-content tags cannot reach the
model dressed as evidence.

Drop conditions (each an observed failure signature, not a hypothetical):
- empty / whitespace-only payload;
- a ``[GT_*]`` diagnostic leak (``[GT_META]`` / ``[GT_STATUS]`` / ``[GT_DELIVERY]`` …
  — these belong on stderr; the frozen sh-744 artifact shows ``[GT_STATUS]
  success:test_targets:8`` glued into an agent observation);
- an empty or self-closing ``<gt-evidence/>`` tag (the empty-dedup-tag noise class);
- more than one ``<gt-evidence>`` tag (not single-tagged);
- a ``<gt-evidence>…</gt-evidence>`` whose inner body is whitespace-only.

Content markers like ``[SIGNATURE]`` / ``[PATTERN]`` / ``[CALLERS]`` / ``[CONTRACT]``
are NOT diagnostics and pass — the regex matches only the literal ``GT_`` prefix.
Pure check; no side effects.
"""
from __future__ import annotations

import re
from typing import Optional

_DIAG_LEAK = re.compile(r"\[GT_[A-Z]+\]")
_TAG_OPEN = re.compile(r"<gt-evidence\b")
_SELF_CLOSING = re.compile(r"<gt-evidence\b[^>]*/>")
_TAG_WITH_BODY = re.compile(r"<gt-evidence\b[^>]*>(.*?)</gt-evidence>", re.S)


def verify_block(text: Optional[str]) -> Optional[str]:
    """Return ``text`` if it is safe to deliver, else ``None`` (drop it)."""
    if not text or not text.strip():
        return None
    if _DIAG_LEAK.search(text):
        return None
    n_tags = len(_TAG_OPEN.findall(text))
    if n_tags:
        if _SELF_CLOSING.search(text):
            return None
        if n_tags > 1:
            return None
        m = _TAG_WITH_BODY.search(text)
        if m is None or not m.group(1).strip():
            return None
    return text
