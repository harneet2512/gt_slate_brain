#!/usr/bin/env python3
"""Offline replay -> per-step metric-state trace (Stage 2 audit substrate).

Walks a NORMALIZED step stream through the REAL Stage 1 ``GTRuntimeConfig`` +
``TrajectoryView`` and the Stage 2 ``estimate``, writing one metric-state row per
step. Read-only: it never mutates an agent observation; it only logs.

Normalized step JSONL (one object per line):
    {"kind": "post_view"|"post_edit"|"finish"|"skip",
     "file": "rel/path.py" | null,
     "obs_hash": "deadbeef",
     "action_repr": "CmdRunAction:cat rel/path.py"}

Harness-specific adapters (OpenHands output.jsonl, mini-swe-agent trajectory) that
emit this normalized stream are intentionally out of scope here — they classify via
``classify_tool_event`` and dump the four fields above. Decoupling the replay from
any one harness keeps the trace logic verifiable without a live run.

Usage:
    python scripts/brain/replay_metric_trace.py --steps steps.jsonl \
        --graph-db /path/graph.db --out trace.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Stage 1 config/view live in the wrapper + groundtruth.state; ensure both import.
_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "src"))
sys.path.insert(0, str(_REPO / "scripts" / "swebench"))

import oh_gt_full_wrapper as w  # noqa: E402
from groundtruth.brain import estimate  # noqa: E402
from groundtruth.brain.trace import append_metric_trace  # noqa: E402
from groundtruth.state import Step, TrajectoryView  # noqa: E402


def replay(steps: list[dict], graph_db: str | None, out_path: str) -> int:
    """Replay ``steps`` into a metric trace at ``out_path``. Returns rows written."""
    cfg = w.GTRuntimeConfig()
    view = TrajectoryView(cfg)
    Path(out_path).write_text("", encoding="utf-8")  # truncate
    written = 0
    for st in steps:
        cfg.action_count += 1
        kind = st.get("kind", "skip")
        rel = st.get("file")
        obs_hash = str(st.get("obs_hash", ""))
        action_repr = str(st.get("action_repr", f"{kind}:{rel}"))
        # mirror the wrapper's stuck-compat ring so verbatim_repeat projects
        cfg._stuck_compat_history.append((action_repr, obs_hash))
        if len(cfg._stuck_compat_history) > 24:
            cfg._stuck_compat_history = cfg._stuck_compat_history[-24:]
        if kind == "post_view" and rel:
            cfg.record_view(rel)
        elif kind == "post_edit" and rel:
            cfg.record_edit(rel)
        step = Step(kind=kind, file=rel, obs_hash=obs_hash)
        state = estimate(view, graph_db, step=step)
        append_metric_trace(out_path, cfg.action_count, state, kind=kind, file=rel)
        written += 1
    return written


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--steps", required=True, help="normalized step JSONL")
    ap.add_argument("--graph-db", default=None, help="per-task graph.db (optional)")
    ap.add_argument("--out", required=True, help="output metric-trace JSONL")
    args = ap.parse_args(argv)

    steps = [json.loads(line) for line in Path(args.steps).read_text(encoding="utf-8").splitlines() if line.strip()]
    n = replay(steps, args.graph_db, args.out)
    print(f"[brain] wrote {n} metric-state rows -> {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
