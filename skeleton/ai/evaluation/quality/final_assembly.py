"""Digest-bound final-assembly evidence and promotion fencing."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, Mapping

_SHA = re.compile(r"^[0-9a-f]{40,64}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class FinalAssemblyError(RuntimeError):
    pass


def _text(value: str, field: str, maximum: int = 2048) -> str:
    text = str(value).strip()
    if not text or len(text) > maximum:
        raise ValueError(f"{field} must be non-empty bounded text")
    return text


def _utc(value: str, field: str) -> str:
    text = _text(value, field, 64)
    if not text.endswith("Z"):
        raise ValueError(f"{field} must be RFC3339 UTC ending in Z")
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError(f"{field} must be RFC3339 UTC") from exc
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError(f"{field} must be UTC")
    return text


@dataclass(frozen=True, slots=True)
class GateReceipt:
    gate_id: str
    passed: bool
    stdout_sha256: str
    stderr_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "gate_id", _text(self.gate_id, "gate_id", 192))
        if not isinstance(self.passed, bool):
            raise TypeError("passed must be boolean")
        for field in ("stdout_sha256", "stderr_sha256"):
            value = _text(getattr(self, field), field, 64)
            if _SHA256.fullmatch(value) is None:
                raise ValueError(f"{field} must be lowercase SHA-256")


@dataclass(frozen=True, slots=True)
class RiskDisposition:
    risk_id: str
    status: str
    evidence_refs: tuple[str, ...]
    authority_ref: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "risk_id", _text(self.risk_id, "risk_id", 256))
        if self.status not in {"closed", "accepted", "blocking"}:
            raise ValueError("risk status must be closed, accepted, or blocking")
        refs = tuple(_text(x, "risk_evidence_ref") for x in self.evidence_refs)
        if not refs or len(refs) != len(set(refs)):
            raise ValueError("risk disposition requires unique evidence refs")
        object.__setattr__(self, "evidence_refs", refs)
        if self.status == "accepted":
            if self.authority_ref is None:
                raise ValueError("accepted risk requires authority_ref")
            object.__setattr__(
                self,
                "authority_ref",
                _text(self.authority_ref, "authority_ref"),
            )
        elif self.authority_ref is not None:
            object.__setattr__(
                self,
                "authority_ref",
                _text(self.authority_ref, "authority_ref"),
            )


@dataclass(frozen=True, slots=True)
class FinalAssemblyEvidence:
    source_sha: str
    environment: Mapping[str, str]
    gate_receipts: tuple[GateReceipt, ...]
    risk_dispositions: tuple[RiskDisposition, ...]
    dependency_snapshot_sha256: str
    builder_id: str
    verifier_id: str | None
    verified_at_utc: str | None

    def __post_init__(self) -> None:
        source = _text(self.source_sha, "source_sha", 64)
        if _SHA.fullmatch(source) is None:
            raise ValueError("source_sha must be a full lowercase Git object ID")
        object.__setattr__(self, "source_sha", source)
        env = {str(k): _text(v, f"environment.{k}", 256) for k, v in self.environment.items()}
        if set(env) != {"os", "python", "architecture"}:
            raise ValueError("environment must contain os/python/architecture exactly")
        object.__setattr__(self, "environment", dict(sorted(env.items())))
        if not self.gate_receipts:
            raise ValueError("final assembly requires gate receipts")
        gate_ids = [x.gate_id for x in self.gate_receipts]
        if len(gate_ids) != len(set(gate_ids)):
            raise ValueError("gate receipt IDs must be unique")
        risk_ids = [x.risk_id for x in self.risk_dispositions]
        if len(risk_ids) != len(set(risk_ids)):
            raise ValueError("risk disposition IDs must be unique")
        snapshot = _text(
            self.dependency_snapshot_sha256,
            "dependency_snapshot_sha256",
            64,
        )
        if _SHA256.fullmatch(snapshot) is None:
            raise ValueError("dependency_snapshot_sha256 must be lowercase SHA-256")
        object.__setattr__(self, "dependency_snapshot_sha256", snapshot)
        builder = _text(self.builder_id, "builder_id", 192)
        object.__setattr__(self, "builder_id", builder)
        if self.verifier_id is None:
            if self.verified_at_utc is not None:
                raise ValueError("verified_at_utc requires verifier_id")
        else:
            verifier = _text(self.verifier_id, "verifier_id", 192)
            if verifier == builder:
                raise FinalAssemblyError("builder and verifier must be independent")
            object.__setattr__(self, "verifier_id", verifier)
            if self.verified_at_utc is None:
                raise ValueError("verifier_id requires verified_at_utc")
            object.__setattr__(
                self,
                "verified_at_utc",
                _utc(self.verified_at_utc, "verified_at_utc"),
            )

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": "skeleton.p2.final_assembly_evidence.v1",
            "source_sha": self.source_sha,
            "environment": dict(self.environment),
            "gate_receipts": [
                {
                    "gate_id": x.gate_id,
                    "passed": x.passed,
                    "stdout_sha256": x.stdout_sha256,
                    "stderr_sha256": x.stderr_sha256,
                }
                for x in sorted(self.gate_receipts, key=lambda x: x.gate_id)
            ],
            "risk_dispositions": [
                {
                    "risk_id": x.risk_id,
                    "status": x.status,
                    "evidence_refs": list(x.evidence_refs),
                    "authority_ref": x.authority_ref,
                }
                for x in sorted(self.risk_dispositions, key=lambda x: x.risk_id)
            ],
            "dependency_snapshot_sha256": self.dependency_snapshot_sha256,
            "builder_id": self.builder_id,
            "verifier_id": self.verifier_id,
            "verified_at_utc": self.verified_at_utc,
        }

    @property
    def evidence_digest(self) -> str:
        raw = json.dumps(
            self.payload(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True, slots=True)
class PromotionDecision:
    ready: bool
    blockers: tuple[str, ...]
    evidence_digest: str


def evaluate_promotion(
    evidence: FinalAssemblyEvidence,
    *,
    presented_digest: str,
    expected_source_sha: str,
    expected_environment: Mapping[str, str],
    required_gate_ids: tuple[str, ...],
) -> PromotionDecision:
    if _SHA256.fullmatch(str(presented_digest)) is None:
        raise ValueError("presented_digest must be lowercase SHA-256")

    expected_source = _text(expected_source_sha, "expected_source_sha", 64)
    if _SHA.fullmatch(expected_source) is None:
        raise ValueError("expected_source_sha must be a full lowercase Git object ID")

    expected_env = {
        str(key): _text(value, f"expected_environment.{key}", 256)
        for key, value in expected_environment.items()
    }
    if set(expected_env) != {"os", "python", "architecture"}:
        raise ValueError(
            "expected_environment must contain os/python/architecture exactly"
        )

    required = tuple(_text(item, "required_gate_id", 192) for item in required_gate_ids)
    if not required:
        raise ValueError("required_gate_ids must not be empty")
    if len(required) != len(set(required)):
        raise ValueError("required_gate_ids must be unique")

    blockers: list[str] = []
    if presented_digest != evidence.evidence_digest:
        blockers.append("final assembly evidence digest mismatch")
    if evidence.source_sha != expected_source:
        blockers.append("final assembly source SHA mismatch")
    if dict(evidence.environment) != dict(sorted(expected_env.items())):
        blockers.append("final assembly environment mismatch")

    actual_gate_ids = tuple(sorted(gate.gate_id for gate in evidence.gate_receipts))
    expected_gate_ids = tuple(sorted(required))
    if actual_gate_ids != expected_gate_ids:
        blockers.append("final assembly gate receipt coverage mismatch")
    if any(not gate.passed for gate in evidence.gate_receipts):
        blockers.append("one or more final assembly gates failed")
    if any(risk.status == "blocking" for risk in evidence.risk_dispositions):
        blockers.append("unresolved blocking risk")
    if evidence.verifier_id is None:
        blockers.append("independent verification missing")
    return PromotionDecision(
        ready=not blockers,
        blockers=tuple(blockers),
        evidence_digest=evidence.evidence_digest,
    )


__all__ = [
    "FinalAssemblyError",
    "FinalAssemblyEvidence",
    "GateReceipt",
    "PromotionDecision",
    "RiskDisposition",
    "evaluate_promotion",
]
