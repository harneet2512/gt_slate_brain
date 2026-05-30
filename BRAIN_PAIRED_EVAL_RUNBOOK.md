# BRAIN_PAIRED_EVAL_RUNBOOK.md — the GT-brain paired flip smoke (FLIP_AUDIT §5)

**Purpose.** Decide, on real tasks, whether the GT brain (`GT_BRAIN=1`) **resolves
tasks the baseline agent could not** (flips) without regressing any — the only
thing that can settle the steelmanned null in `FLIP_AUDIT.md §3`. Offline work
(unit/replay) cannot settle it; per the constitution nothing is "done" until a
metric moves.

> **RUN GATE — not yet authorized.** This is a *paid* eval (LLM + Docker, via
> GHA/GCP). Do NOT trigger it without explicit approval. The harness below is
> **set up and unit-verified**; launching arms A/B is a separate, approved step.

---

## Arms (paired, same task list, same model/seed/config)

| Arm | Env | What it is |
|---|---|---|
| **A — baseline** | `GT_BASELINE=1` (and `GT_BRAIN` unset) | agent-alone; no GT layers |
| **B — brain**    | `GT_BRAIN=1` (`GT_BASELINE` unset) | agent + GT brain (defensive rules + proactive rule) |

Both arms: identical model (`deepseek/deepseek-v4-flash`, temp/top_p per
`LATEST_TASK.md`), identical task list, identical iteration cap. The brain is
gated entirely by `GT_BRAIN`; the Safe-Renderer/contract pillar still run in B.

## Task list (10, multi-language, **weasyprint-2300 is the canary**)

Fill `scripts/brain/paired_smoke_tasks.json` with the **exact SWE-bench-Live
`instance_id`s** (do not guess — confirm against the dataset / the existing
`canary_3arm.yml` / `swebench_30task.yml` task set). The canary **weasyprint-2300**
MUST be present and MUST resolve in arm B (it is GT's only proven flip — if the
brain breaks it, the redirect broke the proven path → KILL).

```json
{ "canary": "<weasyprint-2300 instance_id>",
  "tasks": ["<weasyprint-2300 instance_id>", "<task2>", "...", "<task10>"] }
```

## Run each arm (GHA preferred — see `.github/workflows/`)

Per-arm, the SWE-bench-Live eval produces a `report.json` (resolved ids) and the
GT mechanism artifacts (`gt_arm_summary.json`, `output.jsonl`). Example single-arm
manual form (mirrors `LATEST_TASK.md`):

```bash
export DEEPSEEK_API_KEY=...        # RUN GATE: requires the key + Docker + dataset
# arm A:
GT_BASELINE=1 python scripts/swebench/oh_gt_full_wrapper.py \
    --instance-ids-file scripts/brain/paired_smoke_tasks.json \
    -l eval -i 100 --eval-num-workers 1 \
    --eval-output-dir results/paired/armA \
    --dataset SWE-bench-Live/SWE-bench-Live --split lite
# arm B: identical, but  GT_BRAIN=1  and  --eval-output-dir results/paired/armB
```

## Per-arm health gate (mechanism, not flips) — mandatory

```bash
python scripts/swebench/verify_report.py append --run-dir results/paired/armB
```
`verify_report` gates each arm's GT mechanism health (delivery/engagement/layer
fire). It does NOT decide flips — that is the adjudicator below.

## Adjudicate the pair (flips / regressions / canary / McNemar) — offline, no run

```bash
python scripts/brain/paired_flip_eval.py \
    --arm-a results/paired/armA/report.json \
    --arm-b results/paired/armB/report.json \
    --canary "<weasyprint-2300 instance_id>" \
    --tasks scripts/brain/paired_smoke_tasks.json --json
```

**Truth source = `report.json` (resolved) + `output.jsonl` agent observations** for
each flip (confirm the verified bundle actually reached the agent at the first
edit). NEVER telemetry counters.

## Verdict (FLIP_AUDIT §5)

- **PASS** — ≥1 flip (B✓ A✗), **canary preserved**, **zero regressions**.
- **KILL** — canary broke; OR any regression (dampening) → revert; OR net Δ ≤ 0
  with no flip → the lever is outside the brain (null confirmed) → stop adding
  proactive rules.

The adjudicator returns this verdict + the per-task grid; pair it with the
`output.jsonl` excerpt for each flip as the artifact.

---

## Status

- Adjudicator `scripts/brain/paired_flip_eval.py` — **built, 10 unit tests green.**
- Task list `scripts/brain/paired_smoke_tasks.json` — **operator must fill exact ids** (template in repo).
- Arms A/B run — **BLOCKED on approval** (paid, GHA/GCP/DeepSeek key). Not triggered.
