"""Deterministic resource-bounded build scheduling and evidence aggregation.

Issue #807 batch B005 builds on the content-addressed incremental graph.  This
module remains a planning/evidence primitive: it never launches a process or
opens the network.  Callers execute each wave through their reviewed runtime,
then return content-addressed evidence for aggregation.

The planner guarantees:

* dependency-closed target selection;
* dependencies always land in an earlier wave;
* independent ready targets fan out up to explicit parallel/resource bounds;
* deterministic ordering and tie-breaking;
* impossible resource requests fail closed instead of oversubscribing;
* execution evidence must cover the exact plan once, with bound graph/plan
  fingerprints and SHA-256 output/log digests.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Iterable, Mapping, Sequence

from skeleton.build.incremental_graph import MAX_EDGES, IncrementalBuildGraph
from skeleton.kernel.errors import SkeletonError


SCHEDULER_SCHEMA = 1
SCHEDULER_ALGORITHM = "sha256"
MAX_TARGETS = 4096
MAX_CLOSURE_VISITS = MAX_TARGETS + MAX_EDGES
MAX_WAVES = 4096
MAX_PARALLEL = 256
MAX_CPU_UNITS = 1_000_000
MAX_MEMORY_MIB = 16_777_216
MAX_IO_UNITS = 1_000_000
MAX_WEIGHT = 1_000_000
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_STATUSES = frozenset({"success", "failure", "cancelled"})


class ParallelSchedulerError(SkeletonError):
    """The requested schedule or execution evidence is not trustworthy."""

    code = "BUILD.PARALLEL_SCHEDULER"
    http_status = 400


@dataclass(frozen=True, slots=True)
class ResourceRequest:
    """Per-target resource request in abstract deterministic units."""

    cpu_units: int = 1
    memory_mib: int = 1
    io_units: int = 0
    weight: int = 1

    def to_dict(self) -> dict[str, int]:
        return {
            "cpu_units": self.cpu_units,
            "memory_mib": self.memory_mib,
            "io_units": self.io_units,
            "weight": self.weight,
        }


@dataclass(frozen=True, slots=True)
class ResourceCapacity:
    """Per-wave capacity shared by local and remote schedulers."""

    cpu_units: int
    memory_mib: int
    io_units: int
    weight: int

    def to_dict(self) -> dict[str, int]:
        return {
            "cpu_units": self.cpu_units,
            "memory_mib": self.memory_mib,
            "io_units": self.io_units,
            "weight": self.weight,
        }


@dataclass(frozen=True, slots=True)
class ScheduledTarget:
    node_id: str
    fingerprint: str
    resources: ResourceRequest

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "fingerprint": self.fingerprint,
            "resources": self.resources.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class ScheduleWave:
    index: int
    targets: tuple[ScheduledTarget, ...]
    used: ResourceRequest

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "targets": [target.to_dict() for target in self.targets],
            "used": self.used.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class ParallelBuildPlan:
    schema: int
    algorithm: str
    graph_fingerprint: str
    plan_fingerprint: str
    requested_targets: tuple[str, ...]
    selected_targets: tuple[str, ...]
    max_parallel: int
    capacity: ResourceCapacity
    waves: tuple[ScheduleWave, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "algorithm": self.algorithm,
            "graph_fingerprint": self.graph_fingerprint,
            "plan_fingerprint": self.plan_fingerprint,
            "requested_targets": list(self.requested_targets),
            "selected_targets": list(self.selected_targets),
            "max_parallel": self.max_parallel,
            "capacity": self.capacity.to_dict(),
            "waves": [wave.to_dict() for wave in self.waves],
        }

    def serialize(self) -> str:
        return _canonical_json(self.to_dict())


@dataclass(frozen=True, slots=True)
class TargetEvidence:
    node_id: str
    node_fingerprint: str
    graph_fingerprint: str
    plan_fingerprint: str
    status: str
    output_digest: str
    log_digest: str

    def to_dict(self) -> dict[str, str]:
        return {
            "node_id": self.node_id,
            "node_fingerprint": self.node_fingerprint,
            "graph_fingerprint": self.graph_fingerprint,
            "plan_fingerprint": self.plan_fingerprint,
            "status": self.status,
            "output_digest": self.output_digest,
            "log_digest": self.log_digest,
        }


@dataclass(frozen=True, slots=True)
class BuildEvidence:
    schema: int
    algorithm: str
    graph_fingerprint: str
    plan_fingerprint: str
    evidence_fingerprint: str
    success: bool
    records: tuple[TargetEvidence, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "algorithm": self.algorithm,
            "graph_fingerprint": self.graph_fingerprint,
            "plan_fingerprint": self.plan_fingerprint,
            "evidence_fingerprint": self.evidence_fingerprint,
            "success": self.success,
            "records": [record.to_dict() for record in self.records],
        }

    def serialize(self) -> str:
        return _canonical_json(self.to_dict())


def plan_parallel_build(
    graph: IncrementalBuildGraph,
    *,
    resources: Mapping[str, ResourceRequest | Mapping[str, Any]] | None = None,
    targets: Sequence[str] | None = None,
    capacity: ResourceCapacity,
    max_parallel: int = 8,
) -> ParallelBuildPlan:
    """Compile a deterministic dependency-safe parallel schedule."""

    if not isinstance(graph, IncrementalBuildGraph):
        raise ParallelSchedulerError("graph must be an IncrementalBuildGraph")
    checked_capacity = _require_capacity(capacity)
    checked_parallel = _bounded_int(
        max_parallel,
        field="max_parallel",
        minimum=1,
        maximum=MAX_PARALLEL,
    )
    node_map = graph.node_map()
    if not node_map:
        raise ParallelSchedulerError("graph must contain at least one node")

    requested = _normalize_targets(targets, graph.topological_order, node_map)
    selected_set = _dependency_closure(graph, requested)
    if len(selected_set) > MAX_TARGETS:
        raise ParallelSchedulerError(
            "selected target count exceeds scheduler bound",
            context={"targets": len(selected_set), "max_targets": MAX_TARGETS},
        )
    selected = tuple(
        node_id for node_id in graph.topological_order if node_id in selected_set
    )
    request_map = _normalize_resource_map(
        {} if resources is None else resources,
        node_map,
    )

    for node_id in selected:
        request = request_map.get(node_id, ResourceRequest())
        _require_fits_capacity(node_id, request, checked_capacity)

    waves: list[ScheduleWave] = []
    remaining = set(selected)
    completed: set[str] = set()
    while remaining:
        if len(waves) >= MAX_WAVES:
            raise ParallelSchedulerError(
                "wave count exceeds scheduler bound",
                context={"max_waves": MAX_WAVES},
            )

        ready = [
            node_id
            for node_id in remaining
            if all(dep in completed for dep in node_map[node_id].dependencies)
        ]
        if not ready:
            raise ParallelSchedulerError(
                "scheduler cannot make dependency progress",
                context={"remaining": sorted(remaining)[:16]},
            )

        # Largest deterministic cost first improves bounded packing while the
        # node id remains the stable tie-breaker.
        ready.sort(
            key=lambda node_id: (
                -request_map.get(node_id, ResourceRequest()).weight,
                -request_map.get(node_id, ResourceRequest()).cpu_units,
                -request_map.get(node_id, ResourceRequest()).memory_mib,
                node_id,
            )
        )
        chosen: list[str] = []
        used = ResourceRequest(cpu_units=0, memory_mib=0, io_units=0, weight=0)
        for node_id in ready:
            if len(chosen) >= checked_parallel:
                break
            request = request_map.get(node_id, ResourceRequest())
            candidate = _sum_resources(used, request)
            if _fits(candidate, checked_capacity):
                chosen.append(node_id)
                used = candidate

        if not chosen:
            # Every individual request was prevalidated against capacity, so
            # inability to place a ready node is an internal invariant breach.
            raise ParallelSchedulerError(
                "ready targets cannot fit an empty wave",
                context={"ready": ready[:16]},
            )

        scheduled = tuple(
            ScheduledTarget(
                node_id=node_id,
                fingerprint=node_map[node_id].fingerprint,
                resources=request_map.get(node_id, ResourceRequest()),
            )
            for node_id in chosen
        )
        waves.append(
            ScheduleWave(
                index=len(waves),
                targets=scheduled,
                used=used,
            )
        )
        completed.update(chosen)
        remaining.difference_update(chosen)

    payload = {
        "schema": SCHEDULER_SCHEMA,
        "algorithm": SCHEDULER_ALGORITHM,
        "graph_fingerprint": graph.fingerprint,
        "requested_targets": list(requested),
        "selected_targets": list(selected),
        "max_parallel": checked_parallel,
        "capacity": checked_capacity.to_dict(),
        "waves": [wave.to_dict() for wave in waves],
    }
    plan_fingerprint = _sha256(payload)
    return ParallelBuildPlan(
        schema=SCHEDULER_SCHEMA,
        algorithm=SCHEDULER_ALGORITHM,
        graph_fingerprint=graph.fingerprint,
        plan_fingerprint=plan_fingerprint,
        requested_targets=requested,
        selected_targets=selected,
        max_parallel=checked_parallel,
        capacity=checked_capacity,
        waves=tuple(waves),
    )


def aggregate_build_evidence(
    plan: ParallelBuildPlan,
    records: Iterable[TargetEvidence | Mapping[str, Any]],
) -> BuildEvidence:
    """Bind exactly one execution record to every scheduled target."""

    if not isinstance(plan, ParallelBuildPlan):
        raise ParallelSchedulerError("plan must be a ParallelBuildPlan")
    _validate_evidence_plan(plan)
    expected: dict[str, str] = {}
    for wave in plan.waves:
        for target in wave.targets:
            if target.node_id in expected:
                raise ParallelSchedulerError(
                    "plan contains duplicate target",
                    context={"node_id": target.node_id},
                )
            expected[target.node_id] = target.fingerprint

    normalized: dict[str, TargetEvidence] = {}
    count = 0
    for raw in records:
        count += 1
        if count > MAX_TARGETS:
            raise ParallelSchedulerError("evidence record count exceeds scheduler bound")
        record = _coerce_evidence(raw)
        if record.node_id in normalized:
            raise ParallelSchedulerError(
                "duplicate target evidence",
                context={"node_id": record.node_id},
            )
        if record.node_id not in expected:
            raise ParallelSchedulerError(
                "evidence references unscheduled target",
                context={"node_id": record.node_id},
            )
        if record.node_fingerprint != expected[record.node_id]:
            raise ParallelSchedulerError(
                "evidence node fingerprint mismatch",
                context={"node_id": record.node_id},
            )
        if record.graph_fingerprint != plan.graph_fingerprint:
            raise ParallelSchedulerError(
                "evidence graph fingerprint mismatch",
                context={"node_id": record.node_id},
            )
        if record.plan_fingerprint != plan.plan_fingerprint:
            raise ParallelSchedulerError(
                "evidence plan fingerprint mismatch",
                context={"node_id": record.node_id},
            )
        normalized[record.node_id] = record

    missing = sorted(set(expected) - set(normalized))
    if missing:
        raise ParallelSchedulerError(
            "evidence is incomplete",
            context={"missing": missing[:16], "missing_count": len(missing)},
        )

    ordered = tuple(normalized[node_id] for node_id in plan.selected_targets)
    evidence_payload = {
        "schema": SCHEDULER_SCHEMA,
        "algorithm": SCHEDULER_ALGORITHM,
        "graph_fingerprint": plan.graph_fingerprint,
        "plan_fingerprint": plan.plan_fingerprint,
        "records": [record.to_dict() for record in ordered],
    }
    return BuildEvidence(
        schema=SCHEDULER_SCHEMA,
        algorithm=SCHEDULER_ALGORITHM,
        graph_fingerprint=plan.graph_fingerprint,
        plan_fingerprint=plan.plan_fingerprint,
        evidence_fingerprint=_sha256(evidence_payload),
        success=all(record.status == "success" for record in ordered),
        records=ordered,
    )


def _validate_evidence_plan(plan: ParallelBuildPlan) -> None:
    if plan.schema != SCHEDULER_SCHEMA or plan.algorithm != SCHEDULER_ALGORITHM:
        raise ParallelSchedulerError("plan schema or algorithm is unsupported")
    _require_digest(plan.graph_fingerprint, field="graph_fingerprint")
    _require_digest(plan.plan_fingerprint, field="plan_fingerprint")
    checked_parallel = _bounded_int(
        plan.max_parallel,
        field="max_parallel",
        minimum=1,
        maximum=MAX_PARALLEL,
    )
    checked_capacity = _require_capacity(plan.capacity)

    if not plan.selected_targets or len(plan.selected_targets) > MAX_TARGETS:
        raise ParallelSchedulerError("plan selected target count is invalid")
    selected_seen: set[str] = set()
    for node_id in plan.selected_targets:
        checked_id = _required_text(node_id, field="selected target", maximum=256)
        if checked_id in selected_seen:
            raise ParallelSchedulerError(
                "plan contains duplicate selected target",
                context={"node_id": checked_id},
            )
        selected_seen.add(checked_id)

    if not plan.requested_targets or len(plan.requested_targets) > MAX_TARGETS:
        raise ParallelSchedulerError("plan requested target count is invalid")
    requested_seen: set[str] = set()
    for node_id in plan.requested_targets:
        checked_id = _required_text(node_id, field="requested target", maximum=256)
        if checked_id in requested_seen:
            raise ParallelSchedulerError(
                "plan contains duplicate requested target",
                context={"node_id": checked_id},
            )
        requested_seen.add(checked_id)
    if not requested_seen.issubset(selected_seen):
        raise ParallelSchedulerError(
            "plan requested targets are not contained in selected targets"
        )

    if not plan.waves or len(plan.waves) > MAX_WAVES:
        raise ParallelSchedulerError("plan wave count is invalid")
    wave_seen: set[str] = set()
    for expected_index, wave in enumerate(plan.waves):
        if not isinstance(wave, ScheduleWave) or wave.index != expected_index:
            raise ParallelSchedulerError("plan wave indices are not canonical")
        if not wave.targets or len(wave.targets) > checked_parallel:
            raise ParallelSchedulerError("plan wave target count is invalid")
        recomputed = ResourceRequest(
            cpu_units=0,
            memory_mib=0,
            io_units=0,
            weight=0,
        )
        for target in wave.targets:
            if not isinstance(target, ScheduledTarget):
                raise ParallelSchedulerError("plan contains invalid scheduled target")
            node_id = _required_text(target.node_id, field="scheduled target", maximum=256)
            if node_id in wave_seen:
                raise ParallelSchedulerError(
                    "plan contains duplicate scheduled target",
                    context={"node_id": node_id},
                )
            wave_seen.add(node_id)
            _require_digest(target.fingerprint, field="node_fingerprint")
            request = _coerce_request(target.resources)
            _require_fits_capacity(node_id, request, checked_capacity)
            recomputed = _sum_resources(recomputed, request)
        if not isinstance(wave.used, ResourceRequest):
            raise ParallelSchedulerError("plan wave used resources are invalid")
        checked_used = ResourceRequest(
            cpu_units=_bounded_int(
                wave.used.cpu_units,
                field="wave.used.cpu_units",
                minimum=0,
                maximum=MAX_CPU_UNITS,
            ),
            memory_mib=_bounded_int(
                wave.used.memory_mib,
                field="wave.used.memory_mib",
                minimum=0,
                maximum=MAX_MEMORY_MIB,
            ),
            io_units=_bounded_int(
                wave.used.io_units,
                field="wave.used.io_units",
                minimum=0,
                maximum=MAX_IO_UNITS,
            ),
            weight=_bounded_int(
                wave.used.weight,
                field="wave.used.weight",
                minimum=0,
                maximum=MAX_WEIGHT,
            ),
        )
        if recomputed != checked_used:
            raise ParallelSchedulerError(
                "plan wave resource accounting mismatch",
                context={"wave": expected_index},
            )
        if not _fits(checked_used, checked_capacity):
            raise ParallelSchedulerError(
                "plan wave exceeds resource capacity",
                context={"wave": expected_index},
            )

    if wave_seen != selected_seen:
        raise ParallelSchedulerError(
            "plan selected targets do not match scheduled targets"
        )

    payload = {
        "schema": plan.schema,
        "algorithm": plan.algorithm,
        "graph_fingerprint": plan.graph_fingerprint,
        "requested_targets": list(plan.requested_targets),
        "selected_targets": list(plan.selected_targets),
        "max_parallel": plan.max_parallel,
        "capacity": plan.capacity.to_dict(),
        "waves": [wave.to_dict() for wave in plan.waves],
    }
    if _sha256(payload) != plan.plan_fingerprint:
        raise ParallelSchedulerError("plan fingerprint does not match plan content")


def _normalize_targets(
    targets: Sequence[str] | None,
    topological_order: Sequence[str],
    node_map: Mapping[str, Any],
) -> tuple[str, ...]:
    if targets is None:
        return tuple(topological_order)
    if isinstance(targets, (str, bytes, bytearray)):
        raise ParallelSchedulerError("targets must be a sequence of node ids")
    if not targets:
        raise ParallelSchedulerError("targets must not be empty")
    if len(targets) > MAX_TARGETS:
        raise ParallelSchedulerError("requested target count exceeds scheduler bound")

    seen: set[str] = set()
    normalized: list[str] = []
    for raw in targets:
        if not isinstance(raw, str) or not raw or raw != raw.strip():
            raise ParallelSchedulerError("target id must be a non-empty trimmed string")
        if raw not in node_map:
            raise ParallelSchedulerError(
                "unknown requested target",
                context={"node_id": raw},
            )
        if raw in seen:
            raise ParallelSchedulerError(
                "duplicate requested target",
                context={"node_id": raw},
            )
        seen.add(raw)
        normalized.append(raw)
    return tuple(sorted(normalized))


def _dependency_closure(
    graph: IncrementalBuildGraph,
    requested: Sequence[str],
) -> frozenset[str]:
    node_map = graph.node_map()
    selected: set[str] = set()
    stack = list(reversed(requested))
    visits = 0
    while stack:
        visits += 1
        if visits > MAX_CLOSURE_VISITS:
            raise ParallelSchedulerError(
                "dependency closure exceeds visit bound",
                context={"max_visits": MAX_CLOSURE_VISITS},
            )
        node_id = stack.pop()
        if node_id in selected:
            continue
        selected.add(node_id)
        stack.extend(reversed(node_map[node_id].dependencies))
    return frozenset(selected)


def _normalize_resource_map(
    resources: Mapping[str, ResourceRequest | Mapping[str, Any]],
    node_map: Mapping[str, Any],
) -> dict[str, ResourceRequest]:
    if not isinstance(resources, Mapping):
        raise ParallelSchedulerError("resources must be a mapping")
    if len(resources) > MAX_TARGETS:
        raise ParallelSchedulerError("resource map exceeds scheduler bound")
    normalized: dict[str, ResourceRequest] = {}
    for node_id, raw in resources.items():
        if node_id not in node_map:
            raise ParallelSchedulerError(
                "resource request references unknown target",
                context={"node_id": node_id},
            )
        normalized[node_id] = _coerce_request(raw)
    return normalized


def _coerce_request(raw: ResourceRequest | Mapping[str, Any]) -> ResourceRequest:
    if isinstance(raw, ResourceRequest):
        request = raw
    elif isinstance(raw, Mapping):
        allowed = {"cpu_units", "memory_mib", "io_units", "weight"}
        extra = sorted(str(key) for key in raw if key not in allowed)
        if extra:
            raise ParallelSchedulerError(
                "resource request contains unknown keys",
                context={"keys": extra},
            )
        request = ResourceRequest(
            cpu_units=raw.get("cpu_units", 1),
            memory_mib=raw.get("memory_mib", 1),
            io_units=raw.get("io_units", 0),
            weight=raw.get("weight", 1),
        )
    else:
        raise ParallelSchedulerError("resource request must be a mapping or ResourceRequest")

    return ResourceRequest(
        cpu_units=_bounded_int(
            request.cpu_units,
            field="cpu_units",
            minimum=1,
            maximum=MAX_CPU_UNITS,
        ),
        memory_mib=_bounded_int(
            request.memory_mib,
            field="memory_mib",
            minimum=1,
            maximum=MAX_MEMORY_MIB,
        ),
        io_units=_bounded_int(
            request.io_units,
            field="io_units",
            minimum=0,
            maximum=MAX_IO_UNITS,
        ),
        weight=_bounded_int(
            request.weight,
            field="weight",
            minimum=1,
            maximum=MAX_WEIGHT,
        ),
    )


def _require_capacity(value: Any) -> ResourceCapacity:
    if not isinstance(value, ResourceCapacity):
        raise ParallelSchedulerError("capacity must be a ResourceCapacity")
    return ResourceCapacity(
        cpu_units=_bounded_int(
            value.cpu_units,
            field="capacity.cpu_units",
            minimum=1,
            maximum=MAX_CPU_UNITS,
        ),
        memory_mib=_bounded_int(
            value.memory_mib,
            field="capacity.memory_mib",
            minimum=1,
            maximum=MAX_MEMORY_MIB,
        ),
        io_units=_bounded_int(
            value.io_units,
            field="capacity.io_units",
            minimum=0,
            maximum=MAX_IO_UNITS,
        ),
        weight=_bounded_int(
            value.weight,
            field="capacity.weight",
            minimum=1,
            maximum=MAX_WEIGHT,
        ),
    )


def _require_fits_capacity(
    node_id: str,
    request: ResourceRequest,
    capacity: ResourceCapacity,
) -> None:
    if not _fits(request, capacity):
        raise ParallelSchedulerError(
            "target resource request exceeds wave capacity",
            context={"node_id": node_id},
        )


def _fits(request: ResourceRequest, capacity: ResourceCapacity) -> bool:
    return (
        request.cpu_units <= capacity.cpu_units
        and request.memory_mib <= capacity.memory_mib
        and request.io_units <= capacity.io_units
        and request.weight <= capacity.weight
    )


def _sum_resources(left: ResourceRequest, right: ResourceRequest) -> ResourceRequest:
    return ResourceRequest(
        cpu_units=left.cpu_units + right.cpu_units,
        memory_mib=left.memory_mib + right.memory_mib,
        io_units=left.io_units + right.io_units,
        weight=left.weight + right.weight,
    )


def _coerce_evidence(raw: TargetEvidence | Mapping[str, Any]) -> TargetEvidence:
    if isinstance(raw, TargetEvidence):
        record = raw
    elif isinstance(raw, Mapping):
        expected = {
            "node_id",
            "node_fingerprint",
            "graph_fingerprint",
            "plan_fingerprint",
            "status",
            "output_digest",
            "log_digest",
        }
        extra = sorted(str(key) for key in raw if key not in expected)
        missing = sorted(key for key in expected if key not in raw)
        if extra or missing:
            raise ParallelSchedulerError(
                "evidence keys mismatch",
                context={"missing": missing, "extra": extra},
            )
        record = TargetEvidence(
            node_id=raw["node_id"],
            node_fingerprint=raw["node_fingerprint"],
            graph_fingerprint=raw["graph_fingerprint"],
            plan_fingerprint=raw["plan_fingerprint"],
            status=raw["status"],
            output_digest=raw["output_digest"],
            log_digest=raw["log_digest"],
        )
    else:
        raise ParallelSchedulerError("evidence must be a TargetEvidence or mapping")

    node_id = _required_text(record.node_id, field="node_id", maximum=256)
    node_fingerprint = _require_digest(record.node_fingerprint, field="node_fingerprint")
    graph_fingerprint = _require_digest(
        record.graph_fingerprint,
        field="graph_fingerprint",
    )
    plan_fingerprint = _require_digest(
        record.plan_fingerprint,
        field="plan_fingerprint",
    )
    if not isinstance(record.status, str) or record.status not in _ALLOWED_STATUSES:
        raise ParallelSchedulerError(
            "unsupported evidence status",
            context={"status": repr(record.status)[:128]},
        )
    output_digest = _require_digest(record.output_digest, field="output_digest")
    log_digest = _require_digest(record.log_digest, field="log_digest")
    return TargetEvidence(
        node_id=node_id,
        node_fingerprint=node_fingerprint,
        graph_fingerprint=graph_fingerprint,
        plan_fingerprint=plan_fingerprint,
        status=record.status,
        output_digest=output_digest,
        log_digest=log_digest,
    )


def _require_digest(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise ParallelSchedulerError(f"{field} must be a lowercase SHA-256 digest")
    return value


def _required_text(value: Any, *, field: str, maximum: int) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ParallelSchedulerError(f"{field} must be a non-empty trimmed string")
    if len(value) > maximum or "\x00" in value or "\n" in value or "\r" in value:
        raise ParallelSchedulerError(f"{field} contains invalid characters or length")
    return value


def _bounded_int(
    value: Any,
    *,
    field: str,
    minimum: int,
    maximum: int,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ParallelSchedulerError(f"{field} must be an integer")
    if value < minimum or value > maximum:
        raise ParallelSchedulerError(
            f"{field} is out of range",
            context={"minimum": minimum, "maximum": maximum, "value": value},
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
        raise ParallelSchedulerError("value is not canonically serializable") from exc


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()
