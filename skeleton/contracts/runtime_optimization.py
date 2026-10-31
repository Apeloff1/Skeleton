"""Shared bounded operator policy contract, without runtime or model authority.

These fields describe patches and forms. Existing capability owners validate the
merged policy and dynamic operator ceilings before committing desired state.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

POLICY_CONTROLS_SCHEMA = "skeleton.ai.runtime_policy_controls.v1"
MAX_POLICY_PATCH_BYTES = 16 * 1024


@dataclass(frozen=True, slots=True)
class RuntimePolicyField:
    type: str
    min: int | float | None = None
    max: int | float | None = None
    unit: str = "count"
    description: str = ""

    def metadata(self) -> dict[str, Any]:
        value = {"type": self.type, "unit": self.unit, "description": self.description}
        if self.min is not None:
            value.update(min=self.min, max=self.max)
        return value


def _boolean(description: str) -> RuntimePolicyField:
    return RuntimePolicyField("boolean", unit="toggle", description=description)


def _integer(low: int, high: int, unit: str, description: str) -> RuntimePolicyField:
    return RuntimePolicyField("integer", low, high, unit, description)


def _number(low: float, high: float, unit: str, description: str) -> RuntimePolicyField:
    return RuntimePolicyField("number", low, high, unit, description)


SERVING_POLICY_FIELDS = MappingProxyType(
    {
        "enabled": _boolean(
            "Adjust derived admission from observed pressure within static operator capacity."
        ),
        "min_effective_concurrency": _integer(
            1,
            32,
            "workers",
            "Minimum adaptive concurrency; cannot exceed the selected operator ceiling or maximum.",
        ),
        "max_effective_concurrency": _integer(
            1, 32, "workers", "Adaptive concurrency ceiling; never raises activated operator capacity."
        ),
        "target_latency_ms": _number(
            100, 600000, "ms", "Latency target used by adaptive feedback; not a response deadline guarantee."
        ),
        "cooldown_seconds": _number(0.5, 300, "seconds", "Minimum interval between feedback adjustments."),
        "recovery_samples": _integer(
            2, 128, "samples", "Healthy observations required before increasing derived capacity."
        ),
        "max_queue_wait_seconds": _number(
            0.05, 3600, "seconds", "Upper admission queue wait; request deadlines can expire earlier."
        ),
        "background_max_concurrency": _integer(
            0, 32, "workers", "Background admission ceiling within the selected operator capacity."
        ),
        "cache_max_bytes": _integer(
            0,
            1073741824,
            "bytes",
            "Maximum derived response cache bytes; reducing it can evict cached results.",
        ),
        "cache_ttl_seconds": _number(0, 86400, "seconds", "Maximum derived response cache age."),
        "memory_high_watermark": _number(
            0.5, 0.99, "fraction", "Memory pressure at which adaptive capacity is reduced."
        ),
        "memory_low_watermark": _number(
            0.1, 0.95, "fraction", "Recovery memory watermark; must remain below the high watermark."
        ),
        "max_active_per_tenant": _integer(
            1, 32, "workers", "Per-tenant active ceiling within effective and static capacity."
        ),
        "max_queued_per_tenant": _integer(
            0, 65536, "requests", "Per-tenant pending ceiling within the configured operator queue."
        ),
        "background_starvation_seconds": _number(
            0.1, 3600, "seconds", "Age at which background work can receive a protected fair admission."
        ),
        "memory_shed_watermark": _number(
            0.5, 1, "fraction", "Memory pressure at which new work is shed; running workers retain custody."
        ),
    }
)

LEARNING_POLICY_FIELDS = MappingProxyType(
    {
        "enabled": _boolean(
            "Learn from canonical numeric terminal outcomes; disabled learning still retains admitted diagnostics."
        ),
        "min_samples": _integer(
            4,
            10000,
            "outcomes",
            "Minimum fresh canonical observations before learned guidance can become eligible.",
        ),
        "replay_capacity": _integer(
            8,
            256,
            "samples",
            "Bounded numeric replay capacity; reducing it trims examples on subsequent owner updates.",
        ),
        "replay_steps": _integer(
            0, 3, "updates", "Maximum extra replay updates granted per new canonical outcome."
        ),
        "learning_rate": _number(
            0.00001,
            0.05,
            "rate",
            "Operational predictor Adam step size; does not update transformer weights.",
        ),
        "gradient_clip": _number(0.01, 5, "norm", "Operational predictor gradient norm cap."),
        "max_effort_rounds": _integer(
            1, 3, "rounds", "Advice ceiling; cannot enlarge an execution's original stage or resource grants."
        ),
        "target_latency_seconds": _number(
            0.1, 86400, "seconds", "Operational latency objective for numeric guidance."
        ),
        "pressure_threshold": _number(
            0.1, 1, "fraction", "Serving pressure above which background effort is deferred."
        ),
        "uncertainty_ceiling": _number(
            0.05,
            0.75,
            "fraction",
            "Maximum admitted prediction uncertainty; other confidence constraints still apply.",
        ),
        "partition_limit": _integer(
            1, 128, "partitions", "Retained learner partition bound; no automatic active-state deletion."
        ),
        "retained_outcomes": _integer(
            128,
            100000,
            "rows",
            "Derived diagnostic row target; lowering it permits bounded cleanup, preserving canonical results and feedback markers.",
        ),
        "outcome_max_age_days": _integer(
            1,
            3650,
            "days",
            "Derived outcome age horizon; learned guidance is ineligible when canonical evidence exceeds this horizon.",
        ),
        "maintenance_receipt_retention": _integer(
            16,
            100000,
            "receipts",
            "Full acknowledged predictor receipt target; replay tombstones and unacknowledged receipts remain.",
        ),
    }
)

MAINTENANCE_POLICY_FIELDS = MappingProxyType(
    {
        "enabled": _boolean(
            "Admit bounded local housekeeping only after host quiescence and resource checks."
        ),
        "augmentation_enabled": _boolean(
            "Allow bounded extra numeric replay from deferred credits; no provider work or transformer training."
        ),
        "maximum_tasks_per_tick": _integer(1, 8, "tasks", "Maximum admitted chunks per maintenance tick."),
        "maximum_queue": _integer(
            1, 8192, "tasks", "Host queue admission ceiling; lowering it does not discard running work."
        ),
        "maximum_scope_queue": _integer(
            1, 8192, "tasks", "Per-scope queue ceiling, additionally limited by the host queue."
        ),
        "maximum_retained_tasks": _integer(
            1, 8192, "tasks", "Terminal task projection retention; immutable effect receipts remain separate."
        ),
        "maximum_chunk_wall_ms": _integer(1, 5000, "ms", "Per-chunk elapsed-time admission budget."),
        "maximum_chunk_cpu_ms": _integer(1, 5000, "ms", "Per-chunk CPU-time budget."),
        "maximum_chunk_polls": _integer(4, 65536, "polls", "Bounded cooperative checkpoint polls per chunk."),
        "maximum_memory_drop_ppm": _integer(
            0, 1000000, "ppm", "Maximum observed memory headroom drop during a chunk."
        ),
        "maximum_consecutive_failures": _integer(
            1, 32, "failures", "Failed chunk limit before explicit operator recovery is required."
        ),
        "initial_backoff_ms": _integer(
            1, 300000, "ms", "Initial retry backoff; cannot exceed maximum backoff."
        ),
        "maximum_backoff_ms": _integer(1, 86400000, "ms", "Maximum retry or acknowledgement backoff."),
        "preemption_backoff_ms": _integer(
            1, 300000, "ms", "Delay before reconsidering work interrupted by foreground pressure."
        ),
        "circuit_failure_threshold": _integer(
            1, 32, "failures", "Scoped-kind failure count that opens a circuit."
        ),
        "circuit_cooldown_ms": _integer(
            1,
            86400000,
            "ms",
            "Open circuit cooldown; manual reset still requires exact observed custody and failure binding.",
        ),
        "interrupted_lease_grace_ms": _integer(
            1000, 300000, "ms", "Recovery observation grace; timeout alone never proves physical drain."
        ),
        "priority_aging_ms": _integer(
            1000, 86400000, "ms", "Queue age interval used for fair priority aging."
        ),
        "maximum_admission_wait_ms": _integer(
            1000,
            3600000,
            "ms",
            "Queue age at which bounded fairness gives waiting work priority for the next admission attempt.",
        ),
        "clock_jump_tolerance_ms": _integer(
            100, 60000, "ms", "Wall/monotonic divergence threshold for clock-jump diagnostics."
        ),
        "maximum_owner_heartbeat_ms": _integer(
            10000, 300000, "ms", "Maximum fresh owner heartbeat age for host coordination."
        ),
        "maximum_chunk_results": _integer(
            1,
            16384,
            "results",
            "Completed/reserved chunk projection capacity; unresolved proofs exert backpressure.",
        ),
        "maximum_ack_retries_per_tick": _integer(
            1,
            16,
            "attempts",
            "Bounded retries of verified completion acknowledgement, without re-running work.",
        ),
    }
)

POLICY_FIELDS = MappingProxyType(
    {
        "serving": SERVING_POLICY_FIELDS,
        "learning": LEARNING_POLICY_FIELDS,
        "maintenance": MAINTENANCE_POLICY_FIELDS,
    }
)


def validate_runtime_policy_patch(section: str, values: Mapping[str, Any]) -> dict[str, Any]:
    fields = POLICY_FIELDS.get(section)
    if fields is None or not isinstance(values, Mapping) or not values or set(values) - set(fields):
        raise ValueError("runtime policy requires known non-empty fields")
    result = {}
    for name, value in values.items():
        field = fields[name]
        if field.type == "boolean":
            if type(value) is not bool:
                raise ValueError(f"{section}.{name} must be boolean")
        else:
            if field.type == "integer" and type(value) is not int:
                raise ValueError(f"{section}.{name} must be an integer")
            if type(value) not in (int, float):
                raise ValueError(f"{section}.{name} must be numeric")
            try:
                valid = math.isfinite(value) and field.min <= value <= field.max
            except (ValueError, OverflowError):
                valid = False
            if not valid:
                raise ValueError(f"{section}.{name} is outside its finite bounds")
        result[name] = value
    return result


def runtime_policy_controls() -> dict[str, Any]:
    """Describe editable fields; this value grants no caller authority."""
    constraints = {
        "serving": [
            "min_effective_concurrency <= max_effective_concurrency",
            "memory_low_watermark < memory_high_watermark",
            "concurrency and queue limits <= selected operator ceilings",
        ],
        "learning": [
            "original execution grants and verification floors remain authoritative",
            "retention changes apply through bounded owner updates",
        ],
        "maintenance": [
            "initial_backoff_ms <= maximum_backoff_ms",
            "physical custody and fresh host admission remain authoritative",
        ],
    }
    return {
        "schema_version": POLICY_CONTROLS_SCHEMA,
        "max_patch_bytes": MAX_POLICY_PATCH_BYTES,
        **{
            section: {
                "scope": "tenant" if section == "learning" else "host",
                "fields": {name: field.metadata() for name, field in fields.items()},
                "constraints": constraints[section],
            }
            for section, fields in POLICY_FIELDS.items()
        },
    }
