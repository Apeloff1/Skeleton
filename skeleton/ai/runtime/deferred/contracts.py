"""Executable contracts for the deferred 165-volume AI frontier.

The package deliberately separates implementation-candidate evidence from
masterplan completion authority.  A capability may be implemented, tested and
even enabled in a bounded runtime without mutating canonical masterplan
checkboxes or signatures.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, Iterable, Mapping

_VOLUME_RE = re.compile(r"^VOL-(?:0[0-9]{2}|[1-3][0-9]{2}|4[0-2][0-9])$")
_HEX40_RE = re.compile(r"^[0-9a-f]{40}$")
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_STATES = ("planned", "implementation_candidate", "verified", "enabled", "retired")
_ALLOWED = {
    "planned": {"implementation_candidate"},
    "implementation_candidate": {"verified", "planned"},
    "verified": {"enabled", "implementation_candidate"},
    "enabled": {"retired", "verified"},
    "retired": set(),
}


def canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def sha256_json(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _require_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty text")
    return value.strip()


def _require_unique_texts(values: Iterable[object], field_name: str) -> tuple[str, ...]:
    output: list[str] = []
    for item in values:
        output.append(_require_text(item, field_name))
    if len(output) != len(set(output)):
        raise ValueError(f"{field_name} must be unique")
    return tuple(output)


@dataclass(frozen=True, slots=True)
class CapabilitySpec:
    volume_id: str
    title: str
    plane: str
    handler: str
    dependencies: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    acceptance: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        volume_id = _require_text(self.volume_id, "volume_id")
        if not _VOLUME_RE.fullmatch(volume_id):
            raise ValueError("volume_id must be VOL-NNN")
        title = _require_text(self.title, "title")
        plane = _require_text(self.plane, "plane")
        handler = _require_text(self.handler, "handler")
        dependencies = _require_unique_texts(self.dependencies, "dependencies")
        for dep in dependencies:
            if not _VOLUME_RE.fullmatch(dep):
                raise ValueError("dependencies must contain VOL-NNN ids")
            if dep == volume_id:
                raise ValueError("capability cannot depend on itself")
        object.__setattr__(self, "volume_id", volume_id)
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "plane", plane)
        object.__setattr__(self, "handler", handler)
        object.__setattr__(self, "dependencies", dependencies)
        object.__setattr__(self, "risks", _require_unique_texts(self.risks, "risks"))
        object.__setattr__(
            self,
            "acceptance",
            _require_unique_texts(self.acceptance, "acceptance"),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "volume_id": self.volume_id,
            "title": self.title,
            "plane": self.plane,
            "handler": self.handler,
            "dependencies": list(self.dependencies),
            "risks": list(self.risks),
            "acceptance": list(self.acceptance),
        }

    @property
    def digest(self) -> str:
        return sha256_json(self.as_dict())


@dataclass(frozen=True, slots=True)
class EvidenceReceipt:
    volume_id: str
    head_sha: str
    artifact_digests: tuple[str, ...]
    tests: tuple[str, ...]
    status: str = "implementation_candidate"
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def __post_init__(self) -> None:
        if not _VOLUME_RE.fullmatch(_require_text(self.volume_id, "volume_id")):
            raise ValueError("volume_id must be VOL-NNN")
        if not isinstance(self.head_sha, str) or not _HEX40_RE.fullmatch(self.head_sha):
            raise ValueError("head_sha must be a lowercase 40-char git sha")
        artifacts = _require_unique_texts(self.artifact_digests, "artifact_digests")
        if any(not _HEX64_RE.fullmatch(item) for item in artifacts):
            raise ValueError("artifact_digests must be lowercase sha256")
        tests = _require_unique_texts(self.tests, "tests")
        if self.status not in {"implementation_candidate", "verified"}:
            raise ValueError("unsupported evidence receipt status")
        _require_text(self.created_at, "created_at")
        object.__setattr__(self, "artifact_digests", artifacts)
        object.__setattr__(self, "tests", tests)

    def as_dict(self) -> dict[str, object]:
        return {
            "volume_id": self.volume_id,
            "head_sha": self.head_sha,
            "artifact_digests": list(self.artifact_digests),
            "tests": list(self.tests),
            "status": self.status,
            "created_at": self.created_at,
        }

    @property
    def digest(self) -> str:
        return sha256_json(self.as_dict())


@dataclass(slots=True)
class CapabilityRecord:
    spec: CapabilitySpec
    state: str = "planned"
    evidence: dict[str, EvidenceReceipt] = field(default_factory=dict)

    def transition(self, target: str) -> None:
        if target not in _STATES:
            raise ValueError("unknown capability state")
        if target not in _ALLOWED[self.state]:
            raise ValueError(f"illegal capability transition {self.state}->{target}")
        self.state = target

    def attach(self, receipt: EvidenceReceipt) -> str:
        if receipt.volume_id != self.spec.volume_id:
            raise ValueError("receipt volume does not match capability")
        encoded = canonical_json(receipt.as_dict())
        digest = receipt.digest
        prior = self.evidence.get(digest)
        if prior is not None and canonical_json(prior.as_dict()) != encoded:
            raise ValueError("evidence digest collision")
        self.evidence[digest] = receipt
        return digest

    def candidate(self, receipt: EvidenceReceipt) -> str:
        if receipt.status != "implementation_candidate":
            raise ValueError("candidate transition needs implementation_candidate receipt")
        digest = self.attach(receipt)
        if self.state == "planned":
            self.transition("implementation_candidate")
        elif self.state != "implementation_candidate":
            raise ValueError("candidate evidence not valid in current state")
        return digest

    def verify(self, receipt: EvidenceReceipt) -> str:
        if receipt.status != "verified":
            raise ValueError("verification needs verified receipt")
        digest = self.attach(receipt)
        if self.state != "implementation_candidate":
            raise ValueError("verification requires implementation candidate")
        if not any(
            item.status == "implementation_candidate" for item in self.evidence.values()
        ):
            raise ValueError("verification requires candidate evidence")
        self.transition("verified")
        return digest

    def enable(self, dependency_states: Mapping[str, str]) -> None:
        if self.state != "verified":
            raise ValueError("enable requires verified capability")
        unresolved = [
            dep
            for dep in self.spec.dependencies
            if dependency_states.get(dep) not in {"verified", "enabled", "retired"}
        ]
        if unresolved:
            raise ValueError(
                "unresolved capability dependencies: " + ",".join(sorted(unresolved))
            )
        self.transition("enabled")


class CapabilityRegistry:
    def __init__(self, specs: Iterable[CapabilitySpec] = ()) -> None:
        self._records: dict[str, CapabilityRecord] = {}
        for spec in specs:
            self.register(spec)

    def register(self, spec: CapabilitySpec) -> None:
        if not isinstance(spec, CapabilitySpec):
            raise TypeError("spec must be CapabilitySpec")
        if spec.volume_id in self._records:
            raise ValueError(f"duplicate capability {spec.volume_id}")
        self._records[spec.volume_id] = CapabilityRecord(spec=spec)

    def get(self, volume_id: str) -> CapabilityRecord:
        try:
            return self._records[volume_id]
        except KeyError as exc:
            raise KeyError(f"unknown deferred capability {volume_id}") from exc

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._records))

    def assert_exact_ids(self, expected: Iterable[str]) -> None:
        expected_set = set(expected)
        actual_set = set(self._records)
        if actual_set != expected_set:
            missing = sorted(expected_set - actual_set)
            extra = sorted(actual_set - expected_set)
            raise ValueError(f"deferred frontier mismatch missing={missing} extra={extra}")

    def dependency_states(self) -> dict[str, str]:
        return {key: record.state for key, record in self._records.items()}

    def enable(self, volume_id: str) -> None:
        self.get(volume_id).enable(self.dependency_states())

    def snapshot(self) -> dict[str, object]:
        rows = []
        for volume_id in sorted(self._records):
            record = self._records[volume_id]
            rows.append(
                {
                    "spec": record.spec.as_dict(),
                    "spec_digest": record.spec.digest,
                    "state": record.state,
                    "evidence_digests": sorted(record.evidence),
                }
            )
        payload = {"schema_version": 1, "capabilities": rows}
        return {**payload, "snapshot_digest": sha256_json(payload)}


@dataclass(frozen=True, slots=True)
class Budget:
    max_attempts: int = 1
    max_cost_units: int = 1
    max_latency_ms: int = 1

    def __post_init__(self) -> None:
        for name in ("max_attempts", "max_cost_units", "max_latency_ms"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")


@dataclass(slots=True)
class BudgetLedger:
    budget: Budget
    attempts: int = 0
    cost_units: int = 0
    latency_ms: int = 0

    def admit(self, *, cost_units: int = 0, latency_ms: int = 0) -> None:
        for name, value in (("cost_units", cost_units), ("latency_ms", latency_ms)):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.attempts + 1 > self.budget.max_attempts:
            raise RuntimeError("attempt budget exhausted")
        if self.cost_units + cost_units > self.budget.max_cost_units:
            raise RuntimeError("cost budget exhausted")
        if self.latency_ms + latency_ms > self.budget.max_latency_ms:
            raise RuntimeError("latency budget exhausted")
        self.attempts += 1
        self.cost_units += cost_units
        self.latency_ms += latency_ms
