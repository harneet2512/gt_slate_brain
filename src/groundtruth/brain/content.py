"""Stage 5 proactive content builders — diagnostic, verifiable-only.

The brain decides WHEN; these render WHAT. Strictly diagnostic framing ("verify",
never "edit X") per SWE-PRM (NeurIPS 2025): mid/late prescriptive feedback lowers
resolution, diagnostic feedback helps. Each builder returns a single well-formed
``<gt-evidence>`` block (passes the delivery gate) or "" (nothing to say).
"""
from __future__ import annotations

from typing import Sequence


def render_contract_break_note(callers: Sequence[str], *, max_files: int = 5) -> str:
    """Note for a verified contract break: the edited symbol's signature/return changed
    and these files call it via a deterministic edge but are not in the diff. Asks the
    agent to VERIFY, not to edit. Returns "" when there are no uncovered callers."""
    files = [c for c in callers if c][:max_files]
    if not files:
        return ""
    body = "\n".join(f"  - {f}" for f in files)
    return (
        '<gt-evidence kind="contract-break">\n'
        "[CONTRACT] You changed a function's signature or return type. These files call "
        "it via a verified edge and are not in your diff — confirm they don't need "
        "updating before you finish:\n"
        f"{body}\n"
        "</gt-evidence>"
    )
