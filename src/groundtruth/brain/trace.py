"""Per-step metric-state trace — the audit substrate for Stage 3/4.

Read-only side effect: appends one JSON object per step to a trace file so a real
(or replayed) run can be inspected after the fact. This never touches the agent's
observations; it is pure logging.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from groundtruth.brain.estimator import MetricState


def metric_state_to_dict(action_count: int, state: MetricState, **extra: Any) -> dict[str, Any]:
    """Flatten a MetricState (+ the step index) into a JSON-serializable row."""
    row: dict[str, Any] = {"action_count": int(action_count)}
    row.update(asdict(state))
    # tuples -> lists for stable JSON
    for k, v in list(row.items()):
        if isinstance(v, tuple):
            row[k] = [list(x) if isinstance(x, tuple) else x for x in v]
    row.update(extra)
    return row


def append_metric_trace(path: str, action_count: int, state: MetricState, **extra: Any) -> None:
    """Append one metric-state row to ``path`` as JSONL. Best-effort (never raises)."""
    try:
        row = metric_state_to_dict(action_count, state, **extra)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
    except Exception:  # noqa: BLE001 — tracing must never break the caller
        pass
