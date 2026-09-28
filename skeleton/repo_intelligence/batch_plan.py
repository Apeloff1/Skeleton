"""Validated current-main contract for the #807 game-creation batch program.

The plan is deliberately data-first.  This module does not claim that any batch
is complete: it validates the dependency graph and exposes deterministic,
content-addressed scheduling helpers that higher-level automation can consume.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

from .git_index import GitIndex, GitIndexSnapshot

PLAN_PATH = Path(__file__).with_name("game_creation_batches.json")
SCHEMA_VERSION = 2
BATCH_COUNT = 100
BATCH_ID_RE = re.compile(r"^B(?P<number>[0-9]{3})$")
LANES = (
    "build",
    "creator",
    "gameplay",
    "ai",
    "world",
    "assets",
    "network",
    "quality",
    "security",
    "platform",
)
BATCHES_PER_LANE = 10
MAX_WAVE = 3


class BatchPlanError(ValueError):
    """The tracked game-creation plan is malformed or ambiguous."""


@dataclass(frozen=True, slots=True)
class BatchSpec:
    id: str
    lane: str
    wave: int
    title: str
    depends_on: tuple[str, ...]
    success: str

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "lane": self.lane,
            "wave": self.wave,
            "title": self.title,
            "depends_on": list(self.depends_on),
            "success": self.success,
        }


@dataclass(frozen=True, slots=True)
class BatchPlan:
    schema: int
    execution_model: str
    batches: tuple[BatchSpec, ...]
    digest: str

    @property
    def by_id(self) -> Mapping[str, BatchSpec]:
        return {batch.id: batch for batch in self.batches}

    def ready(
        self,
        completed: Iterable[str] = (),
        *,
        max_wave: int | None = None,
    ) -> tuple[BatchSpec, ...]:
        """Return dependency-satisfied unfinished batches in canonical order."""
        completed_set = _validated_batch_id_set(completed, label="completed")
        if max_wave is not None:
            if isinstance(max_wave, bool) or not isinstance(max_wave, int):
                raise BatchPlanError("max_wave must be an integer")
            if max_wave < 1 or max_wave > MAX_WAVE:
                raise BatchPlanError("max_wave is outside the declared wave range")

        ready: list[BatchSpec] = []
        for batch in self.batches:
            if batch.id in completed_set:
                continue
            if max_wave is not None and batch.wave > max_wave:
                continue
            if set(batch.depends_on).issubset(completed_set):
                ready.append(batch)
        return tuple(ready)

    def transitive_dependencies(self, batch_id: str) -> tuple[str, ...]:
        """Return the canonical ordered transitive dependency closure."""
        target = _validated_known_id(batch_id, self.by_id)
        seen: set[str] = set()

        def visit(current: str) -> None:
            for dependency in self.by_id[current].depends_on:
                if dependency in seen:
                    continue
                seen.add(dependency)
                visit(dependency)

        visit(target)
        return tuple(batch.id for batch in self.batches if batch.id in seen)


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def _plan_digest(
    *,
    schema: int,
    execution_model: str,
    batches: tuple[BatchSpec, ...],
) -> str:
    payload = {
        "schema": schema,
        "batch_count": len(batches),
        "execution_model": execution_model,
        "batches": [batch.as_dict() for batch in batches],
    }
    return hashlib.sha256(_canonical_json(payload)).hexdigest()


def _bounded_text(value: object, *, label: str, limit: int) -> str:
    if not isinstance(value, str):
        raise BatchPlanError(f"{label} must be text")
    if value != value.strip() or not value:
        raise BatchPlanError(f"{label} must be non-empty canonical text")
    if len(value.encode("utf-8")) > limit:
        raise BatchPlanError(f"{label} exceeds its byte bound")
    if any(ord(character) < 32 and character not in "\t" for character in value):
        raise BatchPlanError(f"{label} contains control characters")
    return value


def _batch_from_payload(value: object, *, index: int) -> BatchSpec:
    if not isinstance(value, dict):
        raise BatchPlanError(f"batch {index} must be an object")
    expected = {"id", "lane", "wave", "title", "depends_on", "success"}
    if set(value) != expected:
        raise BatchPlanError(f"batch {index} has an invalid field set")

    batch_id = value["id"]
    if not isinstance(batch_id, str) or BATCH_ID_RE.fullmatch(batch_id) is None:
        raise BatchPlanError(f"batch {index} has an invalid id")

    lane = value["lane"]
    if not isinstance(lane, str) or lane not in LANES:
        raise BatchPlanError(f"{batch_id} has an unsupported lane")

    wave = value["wave"]
    if isinstance(wave, bool) or not isinstance(wave, int) or not 1 <= wave <= MAX_WAVE:
        raise BatchPlanError(f"{batch_id} has an invalid wave")

    dependencies = value["depends_on"]
    if not isinstance(dependencies, list):
        raise BatchPlanError(f"{batch_id} dependencies must be a list")
    if len(dependencies) != len(set(dependencies)):
        raise BatchPlanError(f"{batch_id} contains duplicate dependencies")
    for dependency in dependencies:
        if not isinstance(dependency, str) or BATCH_ID_RE.fullmatch(dependency) is None:
            raise BatchPlanError(f"{batch_id} has an invalid dependency id")
        if dependency == batch_id:
            raise BatchPlanError(f"{batch_id} cannot depend on itself")

    return BatchSpec(
        id=batch_id,
        lane=lane,
        wave=wave,
        title=_bounded_text(value["title"], label=f"{batch_id} title", limit=160),
        depends_on=tuple(dependencies),
        success=_bounded_text(
            value["success"],
            label=f"{batch_id} success criterion",
            limit=512,
        ),
    )


def _validate_graph(batches: tuple[BatchSpec, ...]) -> None:
    expected_ids = tuple(f"B{number:03d}" for number in range(1, BATCH_COUNT + 1))
    actual_ids = tuple(batch.id for batch in batches)
    if actual_ids != expected_ids:
        raise BatchPlanError("batch ids must be the canonical ordered B001..B100 set")

    by_id = {batch.id: batch for batch in batches}
    lane_counts = {lane: 0 for lane in LANES}
    for batch in batches:
        lane_counts[batch.lane] += 1
        unknown = set(batch.depends_on) - by_id.keys()
        if unknown:
            raise BatchPlanError(
                f"{batch.id} references unknown dependencies: {sorted(unknown)}"
            )
    if any(count != BATCHES_PER_LANE for count in lane_counts.values()):
        raise BatchPlanError(
            "each canonical lane must own exactly ten batches"
        )

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(batch_id: str) -> None:
        if batch_id in visited:
            return
        if batch_id in visiting:
            raise BatchPlanError(f"dependency cycle detected at {batch_id}")
        visiting.add(batch_id)
        for dependency in by_id[batch_id].depends_on:
            visit(dependency)
        visiting.remove(batch_id)
        visited.add(batch_id)

    for batch in batches:
        visit(batch.id)
    if len(visited) != BATCH_COUNT:
        raise BatchPlanError("dependency graph did not cover every batch")


def _validated_batch_id_set(values: Iterable[str], *, label: str) -> set[str]:
    result: set[str] = set()
    for value in values:
        if not isinstance(value, str) or BATCH_ID_RE.fullmatch(value) is None:
            raise BatchPlanError(f"{label} contains an invalid batch id")
        if value not in {f"B{number:03d}" for number in range(1, BATCH_COUNT + 1)}:
            raise BatchPlanError(f"{label} contains an unknown batch id")
        if value in result:
            raise BatchPlanError(f"{label} contains a duplicate batch id")
        result.add(value)
    return result


def _validated_known_id(value: str, by_id: Mapping[str, BatchSpec]) -> str:
    if not isinstance(value, str) or value not in by_id:
        raise BatchPlanError("unknown batch id")
    return value


def load_plan(path: Path = PLAN_PATH) -> BatchPlan:
    """Load and fully validate one tracked plan, failing closed on ambiguity."""
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise BatchPlanError("batch plan is unavailable") from exc
    if not raw or len(raw) > 256 * 1024:
        raise BatchPlanError("batch plan size is invalid")
    try:
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_object,
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise BatchPlanError("batch plan is not canonical JSON data") from exc

    if not isinstance(payload, dict):
        raise BatchPlanError("batch plan root must be an object")
    if set(payload) != {"schema", "batch_count", "execution_model", "batches"}:
        raise BatchPlanError("batch plan root has an invalid field set")
    if payload["schema"] != SCHEMA_VERSION:
        raise BatchPlanError("unsupported batch plan schema")
    if payload["batch_count"] != BATCH_COUNT:
        raise BatchPlanError("batch_count must equal 100")

    execution_model = _bounded_text(
        payload["execution_model"],
        label="execution_model",
        limit=1024,
    )
    raw_batches = payload["batches"]
    if not isinstance(raw_batches, list) or len(raw_batches) != BATCH_COUNT:
        raise BatchPlanError("batch plan must contain exactly 100 batches")
    batches = tuple(
        _batch_from_payload(value, index=index)
        for index, value in enumerate(raw_batches, start=1)
    )
    _validate_graph(batches)
    return BatchPlan(
        schema=SCHEMA_VERSION,
        execution_model=execution_model,
        batches=batches,
        digest=_plan_digest(
            schema=SCHEMA_VERSION,
            execution_model=execution_model,
            batches=batches,
        ),
    )



def snapshot_b001(root: str | Path) -> GitIndexSnapshot:
    """Run B001 on the existing hardened content-addressed Git index."""
    plan = load_plan()
    batch = plan.by_id["B001"]
    if batch.lane != "build" or batch.title != "Repository intelligence spine":
        raise BatchPlanError("B001 repository-intelligence identity drifted")
    return GitIndex(root).snapshot()


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BatchPlanError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


__all__ = [
    "BATCH_COUNT",
    "BatchPlan",
    "BatchPlanError",
    "BatchSpec",
    "LANES",
    "PLAN_PATH",
    "load_plan",
    "snapshot_b001",
]
