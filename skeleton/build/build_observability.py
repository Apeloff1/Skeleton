"""Deterministic build telemetry and regression budgets for #807 B009.

This module consumes a validated incremental graph and B005 parallel plan. It
records per-node duration, peak memory, and cache disposition, then derives the
observed dependency critical path and conservative wave-level resource metrics.
No wall-clock timestamps or host-global counters enter the evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Iterable, Mapping

from skeleton.build.incremental_graph import IncrementalBuildGraph
from skeleton.build.parallel_scheduler import ParallelBuildPlan
from skeleton.kernel.errors import SkeletonError


OBSERVABILITY_SCHEMA = 1
CACHE_STATES = frozenset({"hit", "miss", "disabled"})
MAX_DURATION_MS = 7 * 24 * 60 * 60 * 1000
MAX_MEMORY_BYTES = 1 << 50
MAX_RATIO_PPM = 1_000_000
MAX_NODE_BUDGETS = 4096


class BuildObservabilityError(SkeletonError):
    code = "BUILD.OBSERVABILITY"
    http_status = 400


@dataclass(frozen=True, slots=True)
class NodeObservation:
    node_id: str
    duration_ms: int
    peak_memory_bytes: int
    cache_status: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "duration_ms": self.duration_ms,
            "peak_memory_bytes": self.peak_memory_bytes,
            "cache_status": self.cache_status,
        }


@dataclass(frozen=True, slots=True)
class NodeRegressionBudget:
    node_id: str
    max_duration_ms: int
    max_peak_memory_bytes: int

    def to_payload(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "max_duration_ms": self.max_duration_ms,
            "max_peak_memory_bytes": self.max_peak_memory_bytes,
        }


@dataclass(frozen=True, slots=True)
class BuildRegressionBudget:
    max_critical_path_ms: int
    max_wave_elapsed_ms: int
    max_peak_parallel_memory_bytes: int
    min_cache_hit_ratio_ppm: int = 0
    node_budgets: tuple[NodeRegressionBudget, ...] = ()

    @property
    def budget_digest(self) -> str:
        return _digest(self.to_payload())

    def to_payload(self) -> dict[str, Any]:
        return {
            "max_critical_path_ms": self.max_critical_path_ms,
            "max_wave_elapsed_ms": self.max_wave_elapsed_ms,
            "max_peak_parallel_memory_bytes": self.max_peak_parallel_memory_bytes,
            "min_cache_hit_ratio_ppm": self.min_cache_hit_ratio_ppm,
            "node_budgets": [
                row.to_payload()
                for row in sorted(self.node_budgets, key=lambda row: row.node_id)
            ],
        }


@dataclass(frozen=True, slots=True)
class BuildTelemetry:
    graph_fingerprint: str
    plan_fingerprint: str
    records: tuple[NodeObservation, ...]
    critical_path: tuple[str, ...]
    critical_path_ms: int
    wave_elapsed_ms: int
    peak_parallel_memory_bytes: int
    cache_hits: int
    cache_misses: int
    cache_disabled: int
    cache_hit_ratio_ppm: int
    schema: int = OBSERVABILITY_SCHEMA

    @property
    def telemetry_digest(self) -> str:
        return _digest(self.to_payload(include_digest=False))

    def to_payload(self, *, include_digest: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema": self.schema,
            "graph_fingerprint": self.graph_fingerprint,
            "plan_fingerprint": self.plan_fingerprint,
            "records": [row.to_payload() for row in self.records],
            "critical_path": list(self.critical_path),
            "critical_path_ms": self.critical_path_ms,
            "wave_elapsed_ms": self.wave_elapsed_ms,
            "peak_parallel_memory_bytes": self.peak_parallel_memory_bytes,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "cache_disabled": self.cache_disabled,
            "cache_hit_ratio_ppm": self.cache_hit_ratio_ppm,
        }
        if include_digest:
            payload["telemetry_digest"] = self.telemetry_digest
        return payload

    def serialize(self) -> str:
        return _canonical_json(self.to_payload())


@dataclass(frozen=True, slots=True)
class BuildBudgetDecision:
    accepted: bool
    reasons: tuple[str, ...]
    telemetry_digest: str
    budget_digest: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "reasons": list(self.reasons),
            "telemetry_digest": self.telemetry_digest,
            "budget_digest": self.budget_digest,
        }


def observe_build(
    graph: IncrementalBuildGraph,
    plan: ParallelBuildPlan,
    observations: Iterable[NodeObservation | Mapping[str, Any]],
) -> BuildTelemetry:
    if not isinstance(graph, IncrementalBuildGraph):
        raise BuildObservabilityError("graph must be an IncrementalBuildGraph")
    if not isinstance(plan, ParallelBuildPlan):
        raise BuildObservabilityError("plan must be a ParallelBuildPlan")
    if plan.graph_fingerprint != graph.fingerprint:
        raise BuildObservabilityError("plan graph fingerprint does not match graph")

    expected = tuple(plan.selected_targets)
    expected_set = set(expected)
    records_by_id: dict[str, NodeObservation] = {}
    for raw in observations:
        record = _coerce_observation(raw)
        if record.node_id in records_by_id:
            raise BuildObservabilityError(
                "duplicate node observation",
                context={"node_id": record.node_id},
            )
        if record.node_id not in expected_set:
            raise BuildObservabilityError(
                "observation references unscheduled node",
                context={"node_id": record.node_id},
            )
        records_by_id[record.node_id] = record

    missing = sorted(expected_set - set(records_by_id))
    if missing:
        raise BuildObservabilityError(
            "observations do not cover the exact build plan",
            context={"missing": missing[:16], "missing_count": len(missing)},
        )

    records = tuple(records_by_id[node_id] for node_id in expected)
    critical_path, critical_ms = _critical_path(graph, expected_set, records_by_id)

    wave_elapsed = 0
    peak_parallel_memory = 0
    for wave in plan.waves:
        ids = tuple(target.node_id for target in wave.targets)
        if not ids:
            raise BuildObservabilityError("plan contains an empty wave")
        wave_elapsed += max(records_by_id[node_id].duration_ms for node_id in ids)
        wave_memory = sum(
            records_by_id[node_id].peak_memory_bytes for node_id in ids
        )
        peak_parallel_memory = max(peak_parallel_memory, wave_memory)

    hits = sum(row.cache_status == "hit" for row in records)
    misses = sum(row.cache_status == "miss" for row in records)
    disabled = sum(row.cache_status == "disabled" for row in records)
    cache_attempts = hits + misses
    hit_ratio = 0 if cache_attempts == 0 else hits * MAX_RATIO_PPM // cache_attempts

    return BuildTelemetry(
        graph_fingerprint=graph.fingerprint,
        plan_fingerprint=plan.plan_fingerprint,
        records=records,
        critical_path=critical_path,
        critical_path_ms=critical_ms,
        wave_elapsed_ms=wave_elapsed,
        peak_parallel_memory_bytes=peak_parallel_memory,
        cache_hits=hits,
        cache_misses=misses,
        cache_disabled=disabled,
        cache_hit_ratio_ppm=hit_ratio,
    )


def evaluate_build_budget(
    telemetry: BuildTelemetry,
    budget: BuildRegressionBudget,
    *,
    graph: IncrementalBuildGraph,
    plan: ParallelBuildPlan,
) -> BuildBudgetDecision:
    checked = _coerce_budget(budget)
    if not isinstance(telemetry, BuildTelemetry):
        raise BuildObservabilityError("telemetry must be BuildTelemetry")
    verified = observe_build(graph, plan, telemetry.records)
    if telemetry != verified:
        raise BuildObservabilityError(
            "telemetry derived metrics drifted from graph/plan observations"
        )

    reasons: list[str] = []
    if telemetry.critical_path_ms > checked.max_critical_path_ms:
        reasons.append(
            "critical-path-budget:"
            f"{telemetry.critical_path_ms}>{checked.max_critical_path_ms}"
        )
    if telemetry.wave_elapsed_ms > checked.max_wave_elapsed_ms:
        reasons.append(
            "wave-elapsed-budget:"
            f"{telemetry.wave_elapsed_ms}>{checked.max_wave_elapsed_ms}"
        )
    if (
        telemetry.peak_parallel_memory_bytes
        > checked.max_peak_parallel_memory_bytes
    ):
        reasons.append(
            "parallel-memory-budget:"
            f"{telemetry.peak_parallel_memory_bytes}>"
            f"{checked.max_peak_parallel_memory_bytes}"
        )
    if telemetry.cache_hit_ratio_ppm < checked.min_cache_hit_ratio_ppm:
        reasons.append(
            "cache-hit-budget:"
            f"{telemetry.cache_hit_ratio_ppm}<"
            f"{checked.min_cache_hit_ratio_ppm}"
        )

    record_by_id = {row.node_id: row for row in telemetry.records}
    for node_budget in checked.node_budgets:
        observed = record_by_id.get(node_budget.node_id)
        if observed is None:
            reasons.append(f"node-budget-missing:{node_budget.node_id}")
            continue
        if observed.duration_ms > node_budget.max_duration_ms:
            reasons.append(
                f"node-duration-budget:{node_budget.node_id}:"
                f"{observed.duration_ms}>{node_budget.max_duration_ms}"
            )
        if observed.peak_memory_bytes > node_budget.max_peak_memory_bytes:
            reasons.append(
                f"node-memory-budget:{node_budget.node_id}:"
                f"{observed.peak_memory_bytes}>"
                f"{node_budget.max_peak_memory_bytes}"
            )

    normalized = tuple(sorted(reasons))
    return BuildBudgetDecision(
        accepted=not normalized,
        reasons=normalized,
        telemetry_digest=telemetry.telemetry_digest,
        budget_digest=checked.budget_digest,
    )


def _critical_path(
    graph: IncrementalBuildGraph,
    selected: set[str],
    observations: Mapping[str, NodeObservation],
) -> tuple[tuple[str, ...], int]:
    node_map = graph.node_map()
    best_ms: dict[str, int] = {}
    best_path: dict[str, tuple[str, ...]] = {}

    for node_id in graph.topological_order:
        if node_id not in selected:
            continue
        dependencies = tuple(
            dep for dep in node_map[node_id].dependencies if dep in selected
        )
        if dependencies:
            max_parent_ms = max(best_ms[dep] for dep in dependencies)
            parent_paths = [
                best_path[dep]
                for dep in dependencies
                if best_ms[dep] == max_parent_ms
            ]
            parent_path = min(parent_paths)
            parent_ms = max_parent_ms
        else:
            parent_path = ()
            parent_ms = 0
        best_ms[node_id] = parent_ms + observations[node_id].duration_ms
        best_path[node_id] = (*parent_path, node_id)

    if not best_ms:
        return (), 0
    max_ms = max(best_ms.values())
    candidates = [
        best_path[node_id] for node_id, value in best_ms.items() if value == max_ms
    ]
    return min(candidates), max_ms


def _coerce_observation(raw: NodeObservation | Mapping[str, Any]) -> NodeObservation:
    if isinstance(raw, NodeObservation):
        node_id = _token(raw.node_id, field="node_id")
        duration = _bounded_int(
            raw.duration_ms,
            field="duration_ms",
            maximum=MAX_DURATION_MS,
        )
        memory = _bounded_int(
            raw.peak_memory_bytes,
            field="peak_memory_bytes",
            maximum=MAX_MEMORY_BYTES,
        )
        cache = _cache_status(raw.cache_status)
    elif isinstance(raw, Mapping):
        expected = {
            "node_id",
            "duration_ms",
            "peak_memory_bytes",
            "cache_status",
        }
        extra = sorted(str(key) for key in raw if key not in expected)
        missing = sorted(key for key in expected if key not in raw)
        if extra or missing:
            raise BuildObservabilityError(
                "observation keys mismatch",
                context={"missing": missing, "extra": extra},
            )
        node_id = _token(raw["node_id"], field="node_id")
        duration = _bounded_int(
            raw["duration_ms"],
            field="duration_ms",
            maximum=MAX_DURATION_MS,
        )
        memory = _bounded_int(
            raw["peak_memory_bytes"],
            field="peak_memory_bytes",
            maximum=MAX_MEMORY_BYTES,
        )
        cache = _cache_status(raw["cache_status"])
    else:
        raise BuildObservabilityError(
            "observation must be NodeObservation or mapping"
        )
    return NodeObservation(
        node_id=node_id,
        duration_ms=duration,
        peak_memory_bytes=memory,
        cache_status=cache,
    )


def _coerce_budget(raw: BuildRegressionBudget) -> BuildRegressionBudget:
    if not isinstance(raw, BuildRegressionBudget):
        raise BuildObservabilityError("budget must be BuildRegressionBudget")
    if len(raw.node_budgets) > MAX_NODE_BUDGETS:
        raise BuildObservabilityError("node budget count exceeds bound")

    node_budgets: list[NodeRegressionBudget] = []
    seen: set[str] = set()
    for row in raw.node_budgets:
        if not isinstance(row, NodeRegressionBudget):
            raise BuildObservabilityError(
                "node_budgets must contain NodeRegressionBudget values"
            )
        node_id = _token(row.node_id, field="node_id")
        if node_id in seen:
            raise BuildObservabilityError(
                "duplicate node regression budget",
                context={"node_id": node_id},
            )
        seen.add(node_id)
        node_budgets.append(
            NodeRegressionBudget(
                node_id=node_id,
                max_duration_ms=_bounded_int(
                    row.max_duration_ms,
                    field="max_duration_ms",
                    maximum=MAX_DURATION_MS,
                ),
                max_peak_memory_bytes=_bounded_int(
                    row.max_peak_memory_bytes,
                    field="max_peak_memory_bytes",
                    maximum=MAX_MEMORY_BYTES,
                ),
            )
        )

    return BuildRegressionBudget(
        max_critical_path_ms=_bounded_int(
            raw.max_critical_path_ms,
            field="max_critical_path_ms",
            maximum=MAX_DURATION_MS,
        ),
        max_wave_elapsed_ms=_bounded_int(
            raw.max_wave_elapsed_ms,
            field="max_wave_elapsed_ms",
            maximum=MAX_DURATION_MS,
        ),
        max_peak_parallel_memory_bytes=_bounded_int(
            raw.max_peak_parallel_memory_bytes,
            field="max_peak_parallel_memory_bytes",
            maximum=MAX_MEMORY_BYTES,
        ),
        min_cache_hit_ratio_ppm=_bounded_int(
            raw.min_cache_hit_ratio_ppm,
            field="min_cache_hit_ratio_ppm",
            maximum=MAX_RATIO_PPM,
        ),
        node_budgets=tuple(sorted(node_budgets, key=lambda row: row.node_id)),
    )


def _token(value: Any, *, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 256
        or any(ch in value for ch in ("\x00", "\n", "\r"))
    ):
        raise BuildObservabilityError(f"{field} must be a bounded string")
    return value


def _cache_status(value: Any) -> str:
    if not isinstance(value, str) or value not in CACHE_STATES:
        raise BuildObservabilityError(
            "cache_status must be hit, miss, or disabled"
        )
    return value


def _bounded_int(value: Any, *, field: str, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise BuildObservabilityError(f"{field} must be an integer")
    if value < 0 or value > maximum:
        raise BuildObservabilityError(
            f"{field} is out of range",
            context={"value": value, "maximum": maximum},
        )
    return value


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise BuildObservabilityError(
            "value is not canonically serializable"
        ) from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


__all__ = [
    "OBSERVABILITY_SCHEMA",
    "BuildBudgetDecision",
    "BuildObservabilityError",
    "BuildRegressionBudget",
    "BuildTelemetry",
    "NodeObservation",
    "NodeRegressionBudget",
    "evaluate_build_budget",
    "observe_build",
]
