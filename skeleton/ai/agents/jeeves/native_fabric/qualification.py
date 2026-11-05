"""Aggregate independent native readiness evidence without inventing passes.

The inspected facts come from caller-supplied exact-head GitHub checks,
source-bound GGUF activation, real device telemetry and explicit operator
permission. No item is accepted solely because another layer succeeded.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
from typing import Mapping, Sequence

from .contracts import ContractHold, digest, fingerprint
from .assurance import GateReport
from .model_inventory import ModelQualification
from .health import HealthAssessment


@dataclass(frozen=True, slots=True)
class ReadinessEvidence:
    gates: GateReport
    model: ModelQualification
    health: HealthAssessment
    native_agent_completed: bool
    cold_planner_checkpoint_recovered: bool
    terminal_answer_replayed: bool
    memory_scope_rehydrated: bool
    security_reviewed: bool
    model_rights_independent_review: bool
    source_only_tests_passed: bool

    def __post_init__(self):
        if not isinstance(self.gates, GateReport):
            raise ContractHold("exact-head gate report required")
        if not isinstance(self.model, ModelQualification):
            raise ContractHold("typed native model proof required")
        if not isinstance(self.health, HealthAssessment):
            raise ContractHold("typed health assessment required")
        for field_name in (
            "native_agent_completed",
            "cold_planner_checkpoint_recovered",
            "terminal_answer_replayed",
            "memory_scope_rehydrated",
            "security_reviewed",
            "model_rights_independent_review",
            "source_only_tests_passed",
        ):
            if type(getattr(self, field_name)) is not bool:
                raise ContractHold("readiness evidence must use strict observed flags")

    def holds(self) -> tuple[str, ...]:
        failures = []
        if not self.gates.fully_qualified:
            failures.append("mandatory_exact_head_checks")
        failures.extend("model:" + x for x in self.model.outstanding())
        if not self.health.can_activate:
            failures.append("device_health")
        for name in (
            "native_agent_completed",
            "cold_planner_checkpoint_recovered",
            "terminal_answer_replayed",
            "memory_scope_rehydrated",
            "security_reviewed",
            "model_rights_independent_review",
            "source_only_tests_passed",
        ):
            if not getattr(self, name):
                failures.append(name)
        return tuple(failures)

    def to_record(self):
        return {
            "schema": "jeeves.fabric.readiness_evidence.v1",
            "head_sha": self.gates.head_sha,
            "model_source_binding": self.model.source_binding,
            "holds": list(self.holds()),
            "all_declared_local_evidence_present": not self.holds(),
            "independent_end_user_device_qualification": False,
            "release_certified": False,
        }


def evidence_fingerprint(evidence: ReadinessEvidence) -> str:
    if not isinstance(evidence, ReadinessEvidence):
        raise ContractHold("typed readiness evidence required")
    return fingerprint({
        "gate": evidence.gates.to_record(),
        "model": evidence.model.to_record(),
        "health": evidence.health.to_record(),
        "readiness": evidence.to_record(),
    })


__all__ = ["ReadinessEvidence", "evidence_fingerprint"]
