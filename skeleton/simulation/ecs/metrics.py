"""Deterministic structural metrics for ECS state and schedules."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from typing import Any

from .canonical import digest
from .errors import ValidationError
from .schedule import ExecutionPlan, SystemGraph
from .store import EntityStore


@dataclass(frozen=True)
class StoreMetrics:
    revision: int
    entities: int
    components: int
    resources: int
    tombstones: int
    schema_versions: int
    component_types_in_use: int
    min_components_per_entity: int
    max_components_per_entity: int
    mean_components_per_entity: float
    density_by_schema: tuple[tuple[str, int], ...]
    metrics_digest: str

    def to_record(self) -> dict[str, Any]:
        return {
            "revision": self.revision,
            "entities": self.entities,
            "components": self.components,
            "resources": self.resources,
            "tombstones": self.tombstones,
            "schema_versions": self.schema_versions,
            "component_types_in_use": self.component_types_in_use,
            "min_components_per_entity": self.min_components_per_entity,
            "max_components_per_entity": self.max_components_per_entity,
            "mean_components_per_entity": self.mean_components_per_entity,
            "density_by_schema": [list(item) for item in self.density_by_schema],
            "metrics_digest": self.metrics_digest,
        }


@dataclass(frozen=True)
class PlanMetrics:
    systems: int
    dependency_edges: int
    batches: int
    largest_batch: int
    mean_batch_size: float
    read_keys: int
    write_keys: int
    plan_fingerprint: str
    metrics_digest: str

    def to_record(self) -> dict[str, Any]:
        return {
            "systems": self.systems,
            "dependency_edges": self.dependency_edges,
            "batches": self.batches,
            "largest_batch": self.largest_batch,
            "mean_batch_size": self.mean_batch_size,
            "read_keys": self.read_keys,
            "write_keys": self.write_keys,
            "plan_fingerprint": self.plan_fingerprint,
            "metrics_digest": self.metrics_digest,
        }


def store_metrics(store: EntityStore) -> StoreMetrics:
    if not isinstance(store, EntityStore):
        raise ValidationError("store_metrics requires EntityStore")
    counts: list[int] = []
    by_schema: dict[str, int] = {}
    for entity_id in store.entity_ids():
        component_ids = store.component_ids(entity_id)
        counts.append(len(component_ids))
        for schema_id in component_ids:
            by_schema[schema_id] = by_schema.get(schema_id, 0) + 1
    catalog = store.registry.catalog()
    material = {
        "domain": "skeleton.simulation.ecs.store_metrics.v1",
        "store_digest": store.state_digest,
        "revision": store.revision,
        "entities": store.entity_count,
        "components": store.component_count,
        "resources": store.resource_count,
        "tombstones": store.tombstone_count,
        "schema_versions": len(catalog),
        "component_types_in_use": len(by_schema),
        "min_components_per_entity": min(counts, default=0),
        "max_components_per_entity": max(counts, default=0),
        "mean_components_per_entity": mean(counts) if counts else 0.0,
        "density_by_schema": sorted(by_schema.items()),
    }
    return StoreMetrics(
        revision=store.revision,
        entities=store.entity_count,
        components=store.component_count,
        resources=store.resource_count,
        tombstones=store.tombstone_count,
        schema_versions=len(catalog),
        component_types_in_use=len(by_schema),
        min_components_per_entity=min(counts, default=0),
        max_components_per_entity=max(counts, default=0),
        mean_components_per_entity=float(mean(counts)) if counts else 0.0,
        density_by_schema=tuple(sorted(by_schema.items())),
        metrics_digest=digest(material),
    )


def plan_metrics(graph: SystemGraph) -> PlanMetrics:
    if not isinstance(graph, SystemGraph):
        raise ValidationError("plan_metrics requires SystemGraph")
    plan: ExecutionPlan = graph.plan()
    dependency_edges = sum(len(values) for values in plan.dependencies.values())
    batch_sizes = [len(batch.system_ids) for batch in plan.batches]
    read_keys = set()
    write_keys = set()
    for system_id in graph.system_ids():
        spec = graph.get(system_id)
        read_keys.update(spec.reads)
        write_keys.update(spec.writes)
    material = {
        "domain": "skeleton.simulation.ecs.plan_metrics.v1",
        "plan_fingerprint": plan.fingerprint,
        "systems": len(plan.ordered_system_ids),
        "dependency_edges": dependency_edges,
        "batches": len(plan.batches),
        "largest_batch": max(batch_sizes, default=0),
        "mean_batch_size": mean(batch_sizes) if batch_sizes else 0.0,
        "read_keys": sorted(read_keys),
        "write_keys": sorted(write_keys),
    }
    return PlanMetrics(
        systems=len(plan.ordered_system_ids),
        dependency_edges=dependency_edges,
        batches=len(plan.batches),
        largest_batch=max(batch_sizes, default=0),
        mean_batch_size=float(mean(batch_sizes)) if batch_sizes else 0.0,
        read_keys=len(read_keys),
        write_keys=len(write_keys),
        plan_fingerprint=plan.fingerprint,
        metrics_digest=digest(material),
    )
