# gt_slate_brain

A standalone project (independent of the GroundTruth repo) that combines:

1. **Foundation** — the GroundTruth codebase intelligence core (graph.db indexer,
   evidence hooks, brief pipeline), seeded from `groundtruth@gt-architecture-rebuild`.
2. **DeepSWE integration** — the mini-swe-agent + GroundTruth harness we built
   (`artifact_deepswe/`), with auto-injected post-view/post-edit evidence and a
   paired baseline-vs-GT eval pipeline:
   - `artifact_deepswe/gt_agent.py` — `GTMiniSweAgent` (brief + in-container patch + `GT_BASELINE` switch)
   - `artifact_deepswe/gt_mini_patch.py` — wraps `LocalEnvironment.execute` to inject `<gt-evidence>` (agent-class-agnostic)
   - `.github/workflows/deepswe_baseline.yml` — stock mini-swe-agent control arm (deepseek, thinking-off, temp 0)
   - `.github/workflows/deepswe_gt_arm.yml` — GT treatment arm (same config + GT)
   - `.github/workflows/deepswe_loadprobe.yml` — $0 load-mechanism probe (no LLM)
   - `scripts/deepswe_parse_result.py`, `scripts/deepswe_aggregate.py` — verdict tallying
   - `.github/configs/deepswe_baseline_mini.yaml` + config doc — pinned model/agent settings

This repo has no git/fork link to the GroundTruth repo; it is its own history.
