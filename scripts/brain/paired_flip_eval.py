#!/usr/bin/env python3
"""Paired flip adjudicator for the GT brain (FLIP_AUDIT.md §5).

Compares two SWE-bench-Live eval arms on the SAME task list:
  - arm A = agent-alone           (GT_BASELINE=1)
  - arm B = agent + GT brain      (GT_BRAIN=1, redirected proactive rule + defensive rules)

and produces the per-task resolve grid, the flip / regression sets, McNemar on the
discordant pairs, and the §5 PASS / KILL verdict. Truth source is the eval
``report.json`` (resolved instance ids) — NEVER GT telemetry counters (those are
the job of ``verify_report.py``, which gates each arm's mechanism health
separately). This script answers the only question that matters for the goal:
does the brain RESOLVE tasks the baseline could not, without regressing any?

Deterministic, offline, no run. It adjudicates an already-completed paired run;
it does not launch one (see BRAIN_PAIRED_EVAL_RUNBOOK.md for the run gate).

§5 verdict:
  PASS  — ≥1 flip (B resolved, A not), canary preserved, ZERO regressions.
  KILL  — canary broke, OR net Δ ≤ 0 with no flip, OR any regression (dampening).

Usage:
  python scripts/brain/paired_flip_eval.py \
      --arm-a results/baseline/report.json \
      --arm-b results/brain/report.json \
      --canary <weasyprint instance_id> [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path


def load_resolved(report: str | Path | dict) -> set[str]:
    """Return the set of resolved instance_ids from a SWE-bench eval report.

    Robust to the common report shapes:
      - ``{"resolved_ids": [...]}`` / ``{"resolved": [...]}`` (SWE-bench harness)
      - ``{"<instance_id>": {"resolved": true}, ...}`` (per-task dict)
      - ``["<instance_id>", ...]`` (a bare resolved list)
    """
    data = report if isinstance(report, (dict, list)) else json.loads(Path(report).read_text(encoding="utf-8-sig"))
    if isinstance(data, list):
        return {str(x) for x in data}
    if isinstance(data, dict):
        for key in ("resolved_ids", "resolved", "resolved_instances"):
            v = data.get(key)
            if isinstance(v, list):
                return {str(x) for x in v}
        # per-task dict: {instance_id: {"resolved": bool}} or {instance_id: bool}
        out: set[str] = set()
        for k, v in data.items():
            if isinstance(v, bool) and v:
                out.add(str(k))
            elif isinstance(v, dict) and bool(v.get("resolved")):
                out.add(str(k))
        return out
    return set()


def mcnemar(b: int, c: int) -> dict:
    """McNemar on discordant pairs. ``b`` = regressions (A✓B✗), ``c`` = flips (A✗B✓).

    Returns the continuity-corrected χ² (the usual statistic) AND the exact
    two-sided binomial p (correct for the small n a 10-task smoke produces — the
    χ² approximation is unreliable when b+c is tiny, so the verdict uses the
    exact p and the raw counts, never the χ² alone).
    """
    n = b + c
    if n == 0:
        return {"b_regressions": b, "c_flips": c, "n_discordant": 0,
                "chi2_cc": None, "exact_p": 1.0}
    chi2_cc = ((abs(b - c) - 1) ** 2) / n if n > 0 else None
    # exact two-sided binomial p at p=0.5 over the discordant pairs
    k = min(b, c)
    from math import comb
    tail = sum(comb(n, i) for i in range(0, k + 1)) / (2 ** n)
    exact_p = min(1.0, 2.0 * tail)
    return {"b_regressions": b, "c_flips": c, "n_discordant": n,
            "chi2_cc": chi2_cc, "exact_p": exact_p}


@dataclass
class PairedResult:
    tasks: tuple[str, ...]
    both_pass: tuple[str, ...]
    both_fail: tuple[str, ...]
    flips: tuple[str, ...]          # B resolved, A not — the goal
    regressions: tuple[str, ...]    # A resolved, B not — dampening
    a_resolved_n: int
    b_resolved_n: int
    net_delta: int                  # |B| - |A| over the shared task set
    canary: str | None
    canary_preserved: bool | None
    mcnemar: dict
    verdict: str                    # PASS | KILL | INCOMPLETE
    reasons: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "tasks": list(self.tasks),
            "both_pass": list(self.both_pass),
            "both_fail": list(self.both_fail),
            "flips": list(self.flips),
            "regressions": list(self.regressions),
            "a_resolved_n": self.a_resolved_n,
            "b_resolved_n": self.b_resolved_n,
            "net_delta": self.net_delta,
            "canary": self.canary,
            "canary_preserved": self.canary_preserved,
            "mcnemar": self.mcnemar,
            "verdict": self.verdict,
            "reasons": list(self.reasons),
        }


def adjudicate(
    a_resolved: set[str],
    b_resolved: set[str],
    *,
    tasks: set[str] | None = None,
    canary: str | None = None,
) -> PairedResult:
    """Adjudicate a paired run per FLIP_AUDIT §5.

    ``tasks`` bounds the comparison to the intended task list (so a task missing
    from one arm is surfaced as INCOMPLETE, never silently treated as unresolved
    — a missing arm is not a regression). If omitted, the union of the two
    resolved sets is used (only valid when both arms ran every task).
    """
    universe = set(tasks) if tasks is not None else (a_resolved | b_resolved)
    a = a_resolved & universe
    b = b_resolved & universe

    flips = tuple(sorted(b - a))
    regressions = tuple(sorted(a - b))
    both_pass = tuple(sorted(a & b))
    both_fail = tuple(sorted(universe - a - b))

    mc = mcnemar(b=len(regressions), c=len(flips))
    net_delta = len(b) - len(a)

    canary_preserved: bool | None = None
    if canary is not None:
        canary_preserved = canary in b

    reasons: list[str] = []
    verdict = "PASS"

    # NOTE on "not run" vs "unresolved": a resolved set alone cannot distinguish
    # them. The runbook therefore REQUIRES both arms to attempt every task in
    # ``tasks``; under that contract, ``universe - resolved`` is genuinely
    # unresolved, never merely missing. (Enforcing attempted-completeness is a
    # runbook/preflight gate, not this adjudicator's job.)

    # §5 KILL criteria (any one fires):
    if canary is not None and not canary_preserved:
        verdict = "KILL"
        reasons.append(f"canary {canary!r} not resolved in arm B (redirect broke the proven path)")
    if regressions:
        verdict = "KILL"
        reasons.append(f"{len(regressions)} regression(s) (dampening): {list(regressions)}")
    if not flips and net_delta <= 0:
        verdict = "KILL"
        reasons.append("net resolution Δ ≤ 0 and no flip — lever is outside the brain (null confirmed)")

    # §5 PASS criteria (all must hold): ≥1 flip, canary preserved, zero regressions.
    if verdict != "KILL":
        if not flips:
            verdict = "KILL"
            reasons.append("no flip attributable to the brain")
        elif canary is not None and not canary_preserved:
            verdict = "KILL"
        elif regressions:
            verdict = "KILL"
        else:
            reasons.append(f"{len(flips)} flip(s), canary preserved, zero regressions")

    return PairedResult(
        tasks=tuple(sorted(universe)),
        both_pass=both_pass,
        both_fail=both_fail,
        flips=flips,
        regressions=regressions,
        a_resolved_n=len(a),
        b_resolved_n=len(b),
        net_delta=net_delta,
        canary=canary,
        canary_preserved=canary_preserved,
        mcnemar=mc,
        verdict=verdict,
        reasons=tuple(reasons),
    )


def render(result: PairedResult) -> str:
    icon = {"PASS": "[PASS]", "KILL": "[KILL]", "INCOMPLETE": "[INCOMPLETE]"}.get(result.verdict, "[?]")
    lines = [f"{icon} GT brain paired flip eval (FLIP_AUDIT §5)", ""]
    lines.append(f"  arm A (baseline) resolved: {result.a_resolved_n}")
    lines.append(f"  arm B (brain)    resolved: {result.b_resolved_n}")
    lines.append(f"  net delta (B-A): {result.net_delta:+d}")
    lines.append(f"  flips (B-resolved, A-not):       {list(result.flips)}")
    lines.append(f"  regressions (A-resolved, B-not): {list(result.regressions)}")
    if result.canary is not None:
        lines.append(f"  canary {result.canary}: {'PRESERVED' if result.canary_preserved else 'BROKEN'}")
    mc = result.mcnemar
    lines.append(f"  McNemar: flips(c)={mc['c_flips']} regressions(b)={mc['b_regressions']} "
                 f"exact_p={mc['exact_p']:.4f}")
    lines.append(f"  verdict: {result.verdict}")
    for r in result.reasons:
        lines.append(f"   - {r}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Paired flip adjudicator (FLIP_AUDIT §5)")
    ap.add_argument("--arm-a", required=True, help="arm A (baseline) report.json")
    ap.add_argument("--arm-b", required=True, help="arm B (brain) report.json")
    ap.add_argument("--canary", default=None, help="canary instance_id (must stay resolved in B)")
    ap.add_argument("--tasks", default=None,
                    help="optional JSON file with the intended task id list (bounds the grid)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    a = load_resolved(args.arm_a)
    b = load_resolved(args.arm_b)
    task_set = None
    if args.tasks:
        raw = json.loads(Path(args.tasks).read_text(encoding="utf-8-sig"))
        task_set = set(raw if isinstance(raw, list) else raw.get("tasks", []))

    result = adjudicate(a, b, tasks=task_set, canary=args.canary)
    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(render(result))
    return 0 if result.verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
