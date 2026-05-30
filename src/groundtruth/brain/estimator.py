"""Stage 2 — the deterministic metric estimator.

``estimate(view, graph_db) -> MetricState`` computes the seven brain metrics
(BRAIN_METRICS_SPEC.md §4, with the Stage 2 corrections) as a pure, deterministic
function of a ``TrajectoryView`` and a per-task ``graph.db``. No policy, no
content, no LLM. The estimator returns *raw* values for the tuned metrics
(``no_progress_window`` count, ``scope_coverage`` fraction, ``co_change_gap``
partners+counts); the per-task cutoffs that turn those into decisions live in the
Stage 3 policy, never here (Dynamic pillar — no hardcoded absolutes).

Provenance discipline (the laundering guard): every scope/caller/contract read is
restricted to deterministic ``resolution_method`` edges via
``curation_map._DETERMINISTIC_METHODS`` — **never** ``name_match``, **never** a bare
confidence float, **never** the confidence-gated closure table. A ``name_match``
edge must not enter ``required`` scope or the caller set; if it did, a correct
internally-complete model would be told its fix is incomplete (a dampen bug). The
guard is unit-tested red-before-green.

Defined / undefined:
- ``no_progress_window``: ``None`` until the agent has added at least one new
  file (no "since last new" to measure otherwise).
- scope family (``scope_coverage``, ``uncovered_callers``, ``contract_break_risk``,
  ``co_change_gap``): ``None`` before the first edit, and ``None`` when ``graph.db``
  is absent/unopenable — **undefined, never zero** (zero would read as "fully
  covered / no callers", a silent dampen).
- ``contract_break_risk``: ``None`` unless pre-edit ``signature_snapshots`` are
  supplied (cannot tell a signature "changed" without the pre-edit value;
  Stage 3 captures these before the L6 reindex).
- ``co_change_gap``: ``None`` if the ``cochanges`` table is absent.
- ``about_to_submit``: requires the current ``step``; ``False`` if none given.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any, Optional, Union

# Reuse the single source of truth for "what is a fact" + the read-only opener.
# curation_map is REUSE-VERBATIM core; we import its provenance gate, never edit it.
from groundtruth.pretask.curation_map import _DETERMINISTIC_METHODS, _open_ro

_FUNC_LABELS = ("Function", "Method")
# verbatim_repeat mirrors the wrapper's _is_repeated_obs window (last 8); this is a
# structural mirror of existing behavior, not a new tuned knob.
_REPEAT_WINDOW = 8


@dataclass(frozen=True)
class MetricState:
    """The metric-state the brain reads each step. Raw values; thresholds are policy."""

    # trajectory-only
    no_progress_window: Optional[int]      # None = undefined (no new file yet)
    verbatim_repeat: bool                  # structural, binary
    about_to_submit: bool                  # structural, binary

    # scope family (graph + trajectory); None = undefined (no edit yet / no graph)
    scope_coverage: Optional[float]        # |required ∩ edited| / |required|
    uncovered_callers: Optional[tuple[str, ...]]   # verified caller files not yet viewed/edited
    contract_break_risk: Optional[bool]    # sig/return changed AND ≥1 uncovered verified caller
    co_change_gap: Optional[tuple[tuple[str, int], ...]]  # (partner_file, count) unedited

    # provenance / audit
    graph_available: bool
    required_scope: Optional[tuple[str, ...]] = None  # the deterministic required set (audit)

    # §4 bundle: VERIFIED test->target assertions covering an edited symbol — the
    # deterministic proxy for "what correct behavior is". None before the first
    # edit or when the assertions table is absent. Each entry: (test_file,
    # test_name, expression). Gated on a VERIFIED link (assertions.target_node_id>0).
    visible_tests: Optional[tuple[tuple[str, str, str], ...]] = None


GraphArg = Union[str, sqlite3.Connection, None]


def _is_fact_methods_lower() -> tuple[str, ...]:
    # _DETERMINISTIC_METHODS values are already lowercase; materialize for SQL IN.
    return tuple(sorted(_DETERMINISTIC_METHODS))


def _connect(graph_db: GraphArg) -> tuple[Optional[sqlite3.Connection], bool]:
    """Return (conn, owned). ``owned`` True means the caller must close it."""
    if graph_db is None:
        return None, False
    if isinstance(graph_db, sqlite3.Connection):
        return graph_db, False
    return _open_ro(graph_db), True


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    try:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone()
        return row is not None
    except sqlite3.Error:
        return False


def _seed_files(conn: sqlite3.Connection, edited: frozenset[str]) -> set[str]:
    """Edited files that actually have a Function/Method node in the graph."""
    if not edited:
        return set()
    ph = ",".join("?" for _ in edited)
    lab = ",".join("?" for _ in _FUNC_LABELS)
    try:
        rows = conn.execute(
            f"SELECT DISTINCT file_path FROM nodes "
            f"WHERE file_path IN ({ph}) AND label IN ({lab})",
            (*edited, *_FUNC_LABELS),
        ).fetchall()
    except sqlite3.Error:
        return set()
    return {r[0] for r in rows if r and r[0]}


def _deterministic_caller_files(conn: sqlite3.Connection, edited: frozenset[str]) -> set[str]:
    """Files with a DETERMINISTIC incoming CALLS edge into a node in an edited file.

    Restricted to ``resolution_method ∈ _DETERMINISTIC_METHODS`` — the laundering
    guard. name_match callers are never returned, so they can never inflate the
    required scope or the uncovered-caller set.
    """
    if not edited:
        return set()
    ph = ",".join("?" for _ in edited)
    methods = _is_fact_methods_lower()
    mph = ",".join("?" for _ in methods)
    try:
        rows = conn.execute(
            f"SELECT DISTINCT nsrc.file_path "
            f"FROM edges e "
            f"JOIN nodes nt   ON e.target_id = nt.id "
            f"JOIN nodes nsrc ON e.source_id = nsrc.id "
            f"WHERE e.type = 'CALLS' "
            f"  AND nt.file_path IN ({ph}) "
            f"  AND LOWER(TRIM(COALESCE(e.resolution_method, ''))) IN ({mph}) "
            f"  AND nsrc.file_path NOT IN ({ph})",
            (*edited, *methods, *edited),
        ).fetchall()
    except sqlite3.Error:
        return set()
    return {r[0] for r in rows if r and r[0]}


def _signatures(conn: sqlite3.Connection, files: frozenset[str]) -> dict[tuple[str, str], tuple[str, str]]:
    """{(file, name): (signature, return_type)} for Function/Method nodes in ``files``."""
    if not files:
        return {}
    ph = ",".join("?" for _ in files)
    lab = ",".join("?" for _ in _FUNC_LABELS)
    try:
        rows = conn.execute(
            f"SELECT file_path, name, COALESCE(signature,''), COALESCE(return_type,'') "
            f"FROM nodes WHERE file_path IN ({ph}) AND label IN ({lab})",
            (*files, *_FUNC_LABELS),
        ).fetchall()
    except sqlite3.Error:
        return {}
    return {(r[0], r[1]): (r[2], r[3]) for r in rows if r and r[0] and r[1]}


def _co_change_partners(conn: sqlite3.Connection, edited: frozenset[str]) -> dict[str, int]:
    """Co-change partners of edited files -> max co-change count. Excludes edited files."""
    if not edited or not _table_exists(conn, "cochanges"):
        return {}
    out: dict[str, int] = {}
    for f in edited:
        try:
            rows = conn.execute(
                "SELECT file_b, count FROM cochanges WHERE file_a = ? "
                "UNION ALL SELECT file_a, count FROM cochanges WHERE file_b = ?",
                (f, f),
            ).fetchall()
        except sqlite3.Error:
            continue
        for partner, cnt in rows:
            if not partner or partner in edited:
                continue
            out[partner] = max(out.get(partner, 0), int(cnt or 0))
    return out


def _visible_tests(conn: sqlite3.Connection, edited: frozenset[str]) -> list[tuple[str, str, str]]:
    """VERIFIED test->target assertions covering a symbol in an edited file.

    Restricted to ``assertions.target_node_id > 0`` — a RESOLVED (verified) link
    from a test to the edited symbol, never a 0/unresolved guess. Returns
    ``(test_file, test_name, expression)`` tuples — the visible test that defines
    correct behavior for the symbol the agent just edited. Empty when the
    assertions table is absent or no verified link targets an edited file.

    Raw SQL by module convention (matches ``_seed_files`` / ``_signatures`` /
    ``_deterministic_caller_files``, all of which read via ``curation_map._open_ro``
    rather than ``GraphStore``). SCHEMA-SYNC: the canonical symbol-level accessor
    is ``GraphStore.get_assertions_for_target``; if the ``assertions`` table schema
    changes (``test_node_id`` / ``target_node_id`` / ``expression``), update BOTH.
    """
    if not edited or not _table_exists(conn, "assertions"):
        return []
    ph = ",".join("?" for _ in edited)
    try:
        rows = conn.execute(
            f"SELECT DISTINCT tnode.file_path, tnode.name, a.expression "
            f"FROM assertions a "
            f"JOIN nodes tgt   ON a.target_node_id = tgt.id "
            f"JOIN nodes tnode ON a.test_node_id   = tnode.id "
            f"WHERE a.target_node_id > 0 AND tgt.file_path IN ({ph}) "
            f"ORDER BY tnode.file_path, tnode.name",
            (*edited,),
        ).fetchall()
    except sqlite3.Error:
        return []
    out: list[tuple[str, str, str]] = []
    for r in rows:
        tf, tn, expr = (r[0] or ""), (r[1] or ""), (r[2] or "")
        if tf and tn:
            out.append((tf, tn, expr))
    return out


def _signature_changed(
    snapshots: dict[tuple[str, str], tuple[str, str]],
    current: dict[tuple[str, str], tuple[str, str]],
) -> bool:
    """True if any snapshotted symbol's signature or return_type differs from current.

    Only symbols present in BOTH the pre-edit snapshot and the current graph are
    compared (a renamed/removed symbol is not a contract "change" we can verify).
    """
    for key, (old_sig, old_ret) in snapshots.items():
        if key in current:
            new_sig, new_ret = current[key]
            if old_sig != new_sig or old_ret != new_ret:
                return True
    return False


def estimate(
    view: Any,
    graph_db: GraphArg = None,
    *,
    step: Any = None,
    signature_snapshots: Optional[dict[tuple[str, str], tuple[str, str]]] = None,
) -> MetricState:
    """Compute the metric-state from a TrajectoryView and a per-task graph.db.

    ``view``: a TrajectoryView (duck-typed; needs the cumulative + verbatim_repeat
    surface). ``graph_db``: a path, an open sqlite3 connection, or None.
    ``step``: the current Step (for ``about_to_submit``). ``signature_snapshots``:
    pre-edit ``{(file, name): (signature, return_type)}`` (for ``contract_break_risk``).
    """
    # ---- trajectory-only metrics (no graph needed) ----
    lv = view.last_new_view_iter
    le = view.last_new_edit_iter
    if lv is None and le is None:
        no_progress_window: Optional[int] = None
    else:
        last_new = max(x for x in (lv, le) if x is not None)
        no_progress_window = int(view.action_count) - int(last_new)

    verbatim_repeat = bool(view.verbatim_repeat(_REPEAT_WINDOW))
    about_to_submit = bool(step is not None and getattr(step, "kind", "") == "finish")

    edited = view.edited_files
    viewed = view.viewed_files

    conn, owned = _connect(graph_db)
    graph_available = conn is not None

    # ---- scope family: undefined before first edit or without a graph ----
    scope_coverage: Optional[float] = None
    uncovered_callers: Optional[tuple[str, ...]] = None
    contract_break_risk: Optional[bool] = None
    co_change_gap: Optional[tuple[tuple[str, int], ...]] = None
    required_scope: Optional[tuple[str, ...]] = None
    visible_tests: Optional[tuple[tuple[str, str, str], ...]] = None

    try:
        if conn is not None and edited:
            seed = _seed_files(conn, edited)
            caller_files = _deterministic_caller_files(conn, edited)

            # uncovered = verified callers the agent has neither viewed nor edited
            uncovered = caller_files - viewed - edited
            uncovered_callers = tuple(sorted(uncovered))

            # required scope = edited files that exist in the graph + their verified
            # 1-hop caller files. Undefined (None) if the edited files have no nodes
            # AND there are no verified callers (nothing to anchor coverage on).
            required = seed | caller_files
            if required:
                required_scope = tuple(sorted(required))
                covered = required & edited
                scope_coverage = len(covered) / len(required)

            # contract break: needs pre-edit snapshots to tell "changed"
            if signature_snapshots:
                current = _signatures(conn, edited)
                changed = _signature_changed(signature_snapshots, current)
                contract_break_risk = bool(changed and len(uncovered) >= 1)

            partners = _co_change_partners(conn, edited)
            if _table_exists(conn, "cochanges"):
                co_change_gap = tuple(
                    sorted(partners.items(), key=lambda kv: (-kv[1], kv[0]))
                )

            # §4 bundle: verified visible-test assertions covering the edited symbol.
            if _table_exists(conn, "assertions"):
                visible_tests = tuple(_visible_tests(conn, edited))
    finally:
        if owned and conn is not None:
            try:
                conn.close()
            except sqlite3.Error:
                pass

    return MetricState(
        no_progress_window=no_progress_window,
        verbatim_repeat=verbatim_repeat,
        about_to_submit=about_to_submit,
        scope_coverage=scope_coverage,
        uncovered_callers=uncovered_callers,
        contract_break_risk=contract_break_risk,
        co_change_gap=co_change_gap,
        graph_available=graph_available,
        required_scope=required_scope,
        visible_tests=visible_tests,
    )
