"""Stage 5 proactive content builders — diagnostic, verifiable-only.

The brain decides WHEN; these render WHAT. Strictly diagnostic framing ("verify",
never "edit X") per SWE-PRM (NeurIPS 2025): mid/late prescriptive feedback lowers
resolution, diagnostic feedback helps. Each builder returns a single well-formed
``<gt-evidence>`` block (passes the delivery gate) or "" (nothing to say).
"""
from __future__ import annotations

from typing import Sequence


def render_evidence_bundle(
    callers: Sequence[str],
    tests: Sequence[tuple[str, str, str]],
    *,
    max_files: int = 5,
    max_tests: int = 3,
) -> str:
    """§4 verified flip-content bundle for the symbol the agent just edited:
    uncovered 1-hop callers + the visible-test assertions that define correct
    behavior. Diagnostic framing ("confirm"/"run"), never "edit X" (SWE-PRM 2025).
    Markers are ``[CALLERS]``/``[TESTS]`` — NOT ``[GT_*]`` (the delivery gate drops
    that prefix). Returns "" when no verified content exists (correct-or-quiet)."""
    cs = [c for c in callers if c][:max_files]
    ts = [t for t in tests if t and t[0] and t[1]][:max_tests]
    if not cs and not ts:
        return ""
    parts = ['<gt-evidence kind="bundle">']
    if cs:
        parts.append(
            "[CALLERS] Verified callers of the symbol you just edited (not in your "
            "diff) — confirm your change still satisfies them:"
        )
        parts.extend(f"  - {c}" for c in cs)
    if ts:
        parts.append(
            "[TESTS] Verified tests that exercise this symbol — run them to confirm "
            "the behavior they assert:"
        )
        for tf, tn, expr in ts:
            line = f"  - {tf}::{tn}"
            if expr and expr.strip():
                line += f"  (asserts: {expr.strip()[:120]})"
            parts.append(line)
    parts.append("</gt-evidence>")
    return "\n".join(parts)


def render_completeness_note(
    uncovered_scope: Sequence[str],
    co_change: Sequence[tuple[str, int]],
    *,
    max_files: int = 5,
) -> str:
    """Completeness reminder at review/submit: verified scope files / historical
    co-change partners that are unedited. Diagnostic — surfaces files to CONFIRM,
    never "edit them". Returns "" when nothing verified is uncovered."""
    scope = [f for f in uncovered_scope if f][:max_files]
    partners = [(f, n) for (f, n) in co_change if f][:max_files]
    if not scope and not partners:
        return ""
    parts = ['<gt-evidence kind="completeness">']
    if scope:
        parts.append(
            "[SCOPE] These files are in the verified call-scope of your edits but are "
            "not in your diff — confirm the fix doesn't need to extend to them:"
        )
        parts.extend(f"  - {f}" for f in scope)
    if partners:
        parts.append(
            "[CO-CHANGE] These files historically changed together with what you "
            "edited — confirm whether they need a parallel change:"
        )
        parts.extend(f"  - {f} (co-changed {n}x)" for f, n in partners)
    parts.append("</gt-evidence>")
    return "\n".join(parts)


def render_wandering_note(scope: Sequence[str], *, max_files: int = 5) -> str:
    """Wandering re-anchor: the agent has gone N steps without progress; surface the
    VERIFIED call-scope of its edits as facts to re-anchor on. Facts, not a directive
    ("related to your edits", never "go look at"). Returns "" with no verified scope."""
    files = [f for f in scope if f][:max_files]
    if not files:
        return ""
    body = "\n".join(f"  - {f}" for f in files)
    return (
        '<gt-evidence kind="wandering">\n'
        "[SCOPE] You've taken several steps without touching a new file. These files "
        "are in the verified call-scope of what you've already edited — they may be "
        "where the rest of the change belongs:\n"
        f"{body}\n"
        "</gt-evidence>"
    )


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
