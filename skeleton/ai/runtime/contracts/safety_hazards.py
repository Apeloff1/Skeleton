"""Formal system-level safety hazard analysis contracts for VOL-025.

The manifest is policy evidence, not execution authority.  It gives runtime
safety gates a deterministic, versioned taxonomy that can be bound into
qualification receipts without allowing the model or caller to redefine the
hazards being evaluated.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import re
from typing import Iterable

from .canonical import CanonicalContractError, canonical_json_bytes


SAFETY_HAZARD_SCHEMA_VERSION = 1
DEFAULT_SAFETY_POLICY_ID = "skeleton.safety.p1"
DEFAULT_SAFETY_POLICY_VERSION = 1
MAX_SAFETY_HAZARDS = 64
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+_-]{0,255}$")


class SafetyHazardError(ValueError):
    """A safety-hazard artifact is malformed or non-canonical."""


class SafetyHazardClass(str, Enum):
    AUTHORITY_ESCALATION = "authority_escalation"
    IRREVERSIBLE_SIDE_EFFECT = "irreversible_side_effect"
    CROSS_TENANT_IMPACT = "cross_tenant_impact"
    SENSITIVE_DATA_EXPOSURE = "sensitive_data_exposure"
    POLICY_CONFLICT = "policy_conflict"
    SPECIFICATION_GAMING = "specification_gaming"
    DECEPTIVE_BEHAVIOR = "deceptive_behavior"
    GOAL_DRIFT = "goal_drift"
    RECOVERY_FAILURE = "recovery_failure"
    UNRESOLVED_COUNTEREXAMPLE = "unresolved_counterexample"


class SafetyHazardSeverity(str, Enum):
    HIGH = "high"
    CRITICAL = "critical"


def _text(value: object, field: str, *, maximum: int = 4096) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SafetyHazardError(f"{field} must be non-empty")
    normalized = value.strip()
    if normalized != value or len(normalized) > maximum:
        raise SafetyHazardError(f"{field} must be normalized")
    return normalized


def _token(value: object, field: str, *, maximum: int = 256) -> str:
    text = _text(value, field, maximum=maximum)
    if not _TOKEN_RE.fullmatch(text):
        raise SafetyHazardError(f"{field} must be a canonical token")
    return text


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise SafetyHazardError(f"{field} must be a positive integer")
    return value


def _canonical_tokens(
    values: tuple[str, ...],
    field: str,
    *,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise SafetyHazardError(f"{field} must be a tuple")
    normalized = tuple(_token(value, field) for value in values)
    canonical = tuple(sorted(set(normalized)))
    if normalized != canonical:
        raise SafetyHazardError(f"{field} must be sorted unique canonical tokens")
    if not canonical and not allow_empty:
        raise SafetyHazardError(f"{field} must be non-empty")
    return canonical


def _digest(value: object) -> str:
    try:
        raw = canonical_json_bytes(value)
    except CanonicalContractError as exc:
        raise SafetyHazardError("safety hazard payload must be canonical JSON") from exc
    return hashlib.sha256(raw).hexdigest()


def make_safety_hazard_id(
    hazard_class: SafetyHazardClass | str,
    statement: str,
) -> str:
    try:
        kind = SafetyHazardClass(hazard_class)
    except ValueError as exc:
        raise SafetyHazardError("invalid safety hazard class") from exc
    normalized_statement = _text(statement, "statement")
    suffix = _digest(
        {
            "hazard_class": kind.value,
            "statement": normalized_statement,
        }
    )[:16]
    return f"HZ-{kind.value.replace('_', '-')}-{suffix}"


@dataclass(frozen=True, slots=True)
class SafetyHazard:
    hazard_class: SafetyHazardClass
    statement: str
    severity: SafetyHazardSeverity
    trigger_signals: tuple[str, ...]
    required_mitigations: tuple[str, ...]
    evidence_modes: tuple[str, ...]
    blocking: bool = True

    def __post_init__(self) -> None:
        try:
            object.__setattr__(
                self,
                "hazard_class",
                SafetyHazardClass(self.hazard_class),
            )
            object.__setattr__(
                self,
                "severity",
                SafetyHazardSeverity(self.severity),
            )
        except ValueError as exc:
            raise SafetyHazardError("invalid safety hazard enum") from exc
        object.__setattr__(self, "statement", _text(self.statement, "statement"))
        object.__setattr__(
            self,
            "trigger_signals",
            _canonical_tokens(self.trigger_signals, "trigger_signals"),
        )
        object.__setattr__(
            self,
            "required_mitigations",
            _canonical_tokens(
                self.required_mitigations,
                "required_mitigations",
            ),
        )
        object.__setattr__(
            self,
            "evidence_modes",
            _canonical_tokens(self.evidence_modes, "evidence_modes"),
        )
        if not isinstance(self.blocking, bool):
            raise SafetyHazardError("blocking must be boolean")

    @property
    def hazard_id(self) -> str:
        return make_safety_hazard_id(self.hazard_class, self.statement)

    def payload(self) -> dict[str, object]:
        return {
            "hazard_id": self.hazard_id,
            "hazard_class": self.hazard_class.value,
            "statement": self.statement,
            "severity": self.severity.value,
            "trigger_signals": list(self.trigger_signals),
            "required_mitigations": list(self.required_mitigations),
            "evidence_modes": list(self.evidence_modes),
            "blocking": self.blocking,
        }

    @property
    def hazard_digest(self) -> str:
        return _digest(self.payload())


@dataclass(frozen=True, slots=True)
class SafetyHazardManifest:
    policy_id: str
    policy_version: int
    hazards: tuple[SafetyHazard, ...]
    authority_scope: str = "safety-policy-only"
    schema_version: int = SAFETY_HAZARD_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "policy_id",
            _token(self.policy_id, "policy_id"),
        )
        object.__setattr__(
            self,
            "policy_version",
            _positive_int(self.policy_version, "policy_version"),
        )
        if (
            not isinstance(self.hazards, tuple)
            or not self.hazards
            or len(self.hazards) > MAX_SAFETY_HAZARDS
        ):
            raise SafetyHazardError("hazards must be a bounded non-empty tuple")
        if any(not isinstance(item, SafetyHazard) for item in self.hazards):
            raise SafetyHazardError("hazards must contain SafetyHazard values")
        ids = tuple(item.hazard_id for item in self.hazards)
        if ids != tuple(sorted(set(ids))):
            raise SafetyHazardError("hazards must be sorted by unique hazard_id")
        object.__setattr__(
            self,
            "authority_scope",
            _token(self.authority_scope, "authority_scope"),
        )
        if self.authority_scope != "safety-policy-only":
            raise SafetyHazardError("hazard manifest cannot grant execution authority")
        if self.schema_version != SAFETY_HAZARD_SCHEMA_VERSION:
            raise SafetyHazardError("unsupported safety hazard schema version")

    @property
    def hazard_ids(self) -> tuple[str, ...]:
        return tuple(item.hazard_id for item in self.hazards)

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "hazards": [item.payload() for item in self.hazards],
            "authority_scope": self.authority_scope,
            "production_authority": False,
        }

    @property
    def manifest_digest(self) -> str:
        return _digest(self.payload())

    def hazards_for_signals(
        self,
        signals: tuple[str, ...],
    ) -> tuple[str, ...]:
        normalized = _canonical_tokens(
            signals,
            "signals",
            allow_empty=True,
        )
        observed = set(normalized)
        return tuple(
            item.hazard_id
            for item in self.hazards
            if observed.intersection(item.trigger_signals)
        )


def _hazard(
    hazard_class: SafetyHazardClass,
    statement: str,
    severity: SafetyHazardSeverity,
    trigger_signals: Iterable[str],
    required_mitigations: Iterable[str],
    evidence_modes: Iterable[str],
) -> SafetyHazard:
    return SafetyHazard(
        hazard_class=hazard_class,
        statement=statement,
        severity=severity,
        trigger_signals=tuple(sorted(set(trigger_signals))),
        required_mitigations=tuple(sorted(set(required_mitigations))),
        evidence_modes=tuple(sorted(set(evidence_modes))),
    )


_DEFAULT_HAZARDS = (
    _hazard(
        SafetyHazardClass.AUTHORITY_ESCALATION,
        "An action may exceed delegated or explicitly approved authority.",
        SafetyHazardSeverity.CRITICAL,
        (
            "action.privileged",
            "approval.invalid",
            "approval.missing",
            "authority.mismatch",
            "risk_binding.missing",
            "risk_binding.unresolved",
        ),
        (
            "exact-authority-binding",
            "human-approval",
            "independent-risk-binding",
        ),
        (
            "human_control_authorization",
            "risk_evidence",
        ),
    ),
    _hazard(
        SafetyHazardClass.IRREVERSIBLE_SIDE_EFFECT,
        "An action may create destructive, irreversible, or externally persistent effects.",
        SafetyHazardSeverity.CRITICAL,
        (
            "action.destructive",
            "action.irreversible",
            "effect.external_persistent",
        ),
        (
            "human-approval",
            "recovery-plan",
            "rollback-test",
        ),
        (
            "human_control_authorization",
            "rollback",
        ),
    ),
    _hazard(
        SafetyHazardClass.CROSS_TENANT_IMPACT,
        "An action may affect more than one tenant or escape its intended scope.",
        SafetyHazardSeverity.CRITICAL,
        ("scope.cross_tenant",),
        (
            "human-approval",
            "tenant-isolation",
        ),
        (
            "blast_radius",
            "human_control_authorization",
        ),
    ),
    _hazard(
        SafetyHazardClass.SENSITIVE_DATA_EXPOSURE,
        "An action may expose or mutate sensitive data outside its intended boundary.",
        SafetyHazardSeverity.CRITICAL,
        ("data.sensitive",),
        (
            "data-governance",
            "human-approval",
        ),
        (
            "data_governance",
            "human_control_authorization",
        ),
    ),
    _hazard(
        SafetyHazardClass.POLICY_CONFLICT,
        "Independent review detected a conflict with governing policy.",
        SafetyHazardSeverity.CRITICAL,
        ("alignment.policy_conflict",),
        ("policy-reconciliation",),
        ("adversarial",),
    ),
    _hazard(
        SafetyHazardClass.SPECIFICATION_GAMING,
        "Observed behavior may satisfy a proxy while violating the intended objective.",
        SafetyHazardSeverity.HIGH,
        ("alignment.specification_gaming",),
        ("independent-adversarial-review",),
        ("adversarial",),
    ),
    _hazard(
        SafetyHazardClass.DECEPTIVE_BEHAVIOR,
        "Observed behavior may conceal state, intent, or material risk from oversight.",
        SafetyHazardSeverity.CRITICAL,
        ("alignment.deceptive_behavior",),
        (
            "human-escalation",
            "independent-adversarial-review",
        ),
        ("adversarial",),
    ),
    _hazard(
        SafetyHazardClass.GOAL_DRIFT,
        "Observed behavior may have drifted from the authorized objective.",
        SafetyHazardSeverity.HIGH,
        ("alignment.goal_drift",),
        (
            "goal-reauthorization",
            "independent-adversarial-review",
        ),
        ("adversarial",),
    ),
    _hazard(
        SafetyHazardClass.RECOVERY_FAILURE,
        "A recoverable action lacks complete, tested recovery evidence.",
        SafetyHazardSeverity.HIGH,
        ("recovery.evidence_missing",),
        (
            "recovery-plan",
            "rollback-test",
        ),
        ("rollback",),
    ),
    _hazard(
        SafetyHazardClass.UNRESOLVED_COUNTEREXAMPLE,
        "Independent review found unresolved counterexamples to safe execution.",
        SafetyHazardSeverity.HIGH,
        ("alignment.counterexample",),
        ("counterexample-resolution",),
        ("adversarial",),
    ),
)

DEFAULT_SAFETY_HAZARD_MANIFEST = SafetyHazardManifest(
    policy_id=DEFAULT_SAFETY_POLICY_ID,
    policy_version=DEFAULT_SAFETY_POLICY_VERSION,
    hazards=tuple(sorted(_DEFAULT_HAZARDS, key=lambda item: item.hazard_id)),
)
DEFAULT_SAFETY_HAZARD_MANIFEST_DIGEST = (
    DEFAULT_SAFETY_HAZARD_MANIFEST.manifest_digest
)


__all__ = [
    "DEFAULT_SAFETY_HAZARD_MANIFEST",
    "DEFAULT_SAFETY_HAZARD_MANIFEST_DIGEST",
    "DEFAULT_SAFETY_POLICY_ID",
    "DEFAULT_SAFETY_POLICY_VERSION",
    "MAX_SAFETY_HAZARDS",
    "SAFETY_HAZARD_SCHEMA_VERSION",
    "SafetyHazard",
    "SafetyHazardClass",
    "SafetyHazardError",
    "SafetyHazardManifest",
    "SafetyHazardSeverity",
    "make_safety_hazard_id",
]
