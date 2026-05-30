"""Stage 6 — the typed unit a producer emits instead of pushing a string.

The full form of "the Brain is the layer between the producers and the agent":
under Stage 6 a producer (L1/L3/L3b/L5/L6) no longer renders its own agent-facing
text and calls ``append_observation`` — it emits an ``EvidenceEnvelope`` (content +
its PROVENANCE), and the Brain decides **truth** (is this a verified fact or an
unverified hint?), **form** (how to render it), and **delivery** (deliver / suppress
/ dedup, via ``decide_delivery``).

``deterministic`` is DERIVED from ``resolution_method`` using
``curation_map._DETERMINISTIC_METHODS`` — the SAME single fact-source the estimator
uses — and can never be set by a producer. ``name_match`` is never deterministic, so
a name-match relationship is rendered as an explicit ``(unverified)`` hint, never as
a fact (The Distracting Effect, 2025: plausible-but-wrong context misdirects; only
verified provenance is non-dampening). Deterministic, LLM-free.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Optional

from groundtruth.pretask.curation_map import _DETERMINISTIC_METHODS


def derive_deterministic(resolution_method: Optional[str]) -> bool:
    """True iff the resolution method is a VERIFIED one (never ``name_match``)."""
    rm = (resolution_method or "").strip().lower()
    return rm in _DETERMINISTIC_METHODS


@dataclass(frozen=True)
class EvidenceEnvelope:
    """What a producer hands the Brain. ``deterministic`` + ``dedupe_key`` are
    derived in ``__post_init__`` — a producer cannot assert determinism."""

    layer: str
    kind: str
    body: str                              # the evidence fragment (NO wrapper tag)
    resolution_method: str = "unknown"
    target_file: Optional[str] = None
    symbol: Optional[str] = None
    deterministic: bool = field(default=False)   # DERIVED — overwritten below
    dedupe_key: str = field(default="")          # DERIVED when empty

    def __post_init__(self) -> None:
        # provenance-derived determinism — overwrite any producer-supplied value
        object.__setattr__(
            self, "deterministic", derive_deterministic(self.resolution_method)
        )
        if not self.dedupe_key:
            norm = " ".join((self.body or "").split())
            digest = hashlib.md5(
                f"{self.layer}|{self.kind}|{self.target_file}|{self.symbol}|{norm}".encode("utf-8")
            ).hexdigest()[:16]
            object.__setattr__(self, "dedupe_key", digest)


def render_envelope(env: EvidenceEnvelope) -> str:
    """Render an envelope into a single agent-facing ``<gt-evidence>`` block.

    A non-deterministic (e.g. ``name_match``) envelope is rendered as an explicit
    ``(unverified)`` hint — never as a fact. Returns ``""`` for an empty body
    (correct-or-quiet). The result is shaped to pass ``delivery.verify_block``.
    """
    body = (env.body or "").strip()
    if not body:
        return ""
    kind = (env.kind or "evidence").strip() or "evidence"
    suffix = "" if env.deterministic else "\n(unverified — confirm before relying on this)"
    return f'<gt-evidence kind="{kind}">\n{body}{suffix}\n</gt-evidence>'


__all__ = ["EvidenceEnvelope", "derive_deterministic", "render_envelope"]
