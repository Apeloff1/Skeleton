"""PR runner hygiene / auto-merge control-plane extension (Pack E).

Additive fail-closed helpers for deps/queue pressure, boundary registry,
admission evidence, and merge-gate hygiene. Complements runner-v2 (#1639)
without colliding. Does not authorize merges.
"""

from __future__ import annotations

from .admission import AdmissionDecision, evaluate_admission, evaluate_binding_only
from .boundary_registry import (
    BoundaryRegistry,
    audit_live_service_boundaries,
    load_live_service_manifest,
)
from .observe_mode import ObservePolicy, force_observe_for_schedule
from .queue_starvation import (
    QueuePressure,
    filter_before_cap,
    assess_queue_starvation,
)
from .types import HygieneMode, HygieneVerdict, canonical_json, fingerprint

__all__ = [
    "AdmissionDecision",
    "BoundaryRegistry",
    "HygieneMode",
    "HygieneVerdict",
    "ObservePolicy",
    "QueuePressure",
    "assess_queue_starvation",
    "audit_live_service_boundaries",
    "canonical_json",
    "evaluate_admission",
    "evaluate_binding_only",
    "filter_before_cap",
    "fingerprint",
    "force_observe_for_schedule",
    "load_live_service_manifest",
]
