"""TrajectoryView — the brain's single read-only accessor over agent state.

Brain Stage 1 (see ``GT_BRAIN_BUILD.md`` §3 and ``BRAIN_METRICS_SPEC.md`` §6).

``BRAIN_METRICS_SPEC.md`` §1/§6 found the readiness blocker: the agent's running
state is smeared across ~40 ``GTRuntimeConfig._*`` fields, lazy attributes, JSONL
trace files, and a shadow ``AgentState`` that is *not* source of truth. The metric
estimator (Stage 2) cannot be written against that.

``TrajectoryView`` is the fix: ONE read-only object that *projects* the metric-state
the brain reads from the EXISTING ``GTRuntimeConfig`` signals. It is **pure
projection** — it stores nothing of its own, so it cannot drift from ``config._*``.
It computes no metrics, makes no decisions, and mutates nothing. The estimator and
policy are later stages and depend on nothing here beyond the exposed surface.

Field provenance (every exposed field maps to an existing wrapper signal):

==========================  ==================================================
TrajectoryView surface      Backing GTRuntimeConfig state
==========================  ==================================================
action_count                ``action_count``
viewed_files                ``viewed_files`` (set; returned as a frozenset copy)
edited_files                ``edited_files`` (set; returned as a frozenset copy)
source_edit_iters           ``_source_edit_actions`` (list; tuple copy)
search_count_since_edit     ``_search_count_since_edit``
last_new_view_iter          ``last_new_view_iter`` (-1 -> None)
last_new_edit_iter          ``last_new_edit_iter`` (-1 -> None)
last_obs_hash               ``_stuck_compat_history[-1][1]``
verbatim_repeat(window)     ``_stuck_compat_history`` ring (mirrors _is_repeated_obs)
step(event, obs_hash)       classify_tool_event output + the raw-obs md5
==========================  ==================================================

The config is duck-typed (``Any``) on purpose: this module lives in the importable
``groundtruth`` package and must not depend on the ``scripts/swebench`` wrapper that
defines ``GTRuntimeConfig``/``HookEvent``. Anything exposing the attributes above
works (the real config, or a lightweight test stand-in).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class Step:
    """A single trajectory step, projected from the wrapper's per-step values.

    ``kind`` is the ``classify_tool_event`` classification
    (post_view / post_edit / finish / skip); ``file`` is the source path it
    classified (``None`` when there is none); ``obs_hash`` is the md5 of the raw
    observation the wrapper already fingerprints for the stuck detector.
    """

    kind: str
    file: Optional[str]
    obs_hash: str


class TrajectoryView:
    """Read-only projection of the agent's running state from a GTRuntimeConfig.

    Construct fresh from the live config whenever the state is needed; it holds a
    reference, never a copy, so reads always reflect current config values.
    """

    __slots__ = ("_c",)

    def __init__(self, config: Any) -> None:
        self._c = config

    # ----------------------------------------------------------------- cumulative
    @property
    def action_count(self) -> int:
        """Monotonic step counter (config.action_count)."""
        return int(self._c.action_count)

    @property
    def viewed_files(self) -> frozenset[str]:
        """Source files the agent has viewed — immutable copy (cannot mutate config)."""
        return frozenset(self._c.viewed_files)

    @property
    def edited_files(self) -> frozenset[str]:
        """Source files the agent has edited — immutable copy."""
        return frozenset(self._c.edited_files)

    @property
    def source_edit_iters(self) -> tuple[int, ...]:
        """action_count values at which the agent edited a non-test/non-scaffold
        source file (config._source_edit_actions). Empty before the first edit."""
        return tuple(self._c._source_edit_actions)

    @property
    def new_file_iters(self) -> tuple[int, ...]:
        """action_count values at which no_progress_window reset (a new file entered
        viewed_files or edited_files). Consecutive gaps = the task's productive
        cadence, from which the policy derives a per-task no-progress cutoff."""
        return tuple(getattr(self._c, "new_file_iters", ()))

    @property
    def search_count_since_edit(self) -> int:
        """grep/find/rg actions since the last source edit (config._search_count_since_edit)."""
        return int(self._c._search_count_since_edit)

    @property
    def last_new_view_iter(self) -> Optional[int]:
        """action_count at which a file FIRST entered viewed_files; None if none yet."""
        v = getattr(self._c, "last_new_view_iter", -1)
        return None if v is None or v < 0 else int(v)

    @property
    def last_new_edit_iter(self) -> Optional[int]:
        """action_count at which a file FIRST entered edited_files; None if none yet."""
        v = getattr(self._c, "last_new_edit_iter", -1)
        return None if v is None or v < 0 else int(v)

    # ------------------------------------------------------------- per-step / loop
    @property
    def last_obs_hash(self) -> Optional[str]:
        """md5 of the most recent raw observation; None before the first step."""
        hist = self._c._stuck_compat_history
        return hist[-1][1] if hist else None

    def verbatim_repeat(self, window: int = 8) -> bool:
        """Whether the latest (action, obs_hash) pair already appears in the
        preceding ``window`` history entries.

        Mirrors ``_is_repeated_obs`` (oh_gt_full_wrapper.py:3431), which checks the
        current pair against ``_stuck_compat_history[-8:]`` *before* appending it.
        Because the history here already contains the latest pair as ``hist[-1]``,
        the preceding window is ``hist[-(window+1):-1]``. Returns False with fewer
        than two observations (no repeat is detectable).
        """
        hist = self._c._stuck_compat_history
        if len(hist) < 2:
            return False
        latest = hist[-1]
        return latest in hist[-(window + 1):-1]

    def step(self, event: Any, obs_hash: str) -> Step:
        """Package the current step's per-step trio.

        Pure formatting of values the wrapper already holds each step
        (``classify_tool_event`` output + the raw-obs md5); stores nothing.
        ``event`` is duck-typed — anything with ``.kind`` and ``.path``.
        """
        kind = getattr(event, "kind", "") or ""
        path = getattr(event, "path", "") or None
        return Step(kind=kind, file=path, obs_hash=obs_hash)
