"""VOL-033 JVM workload qualification and protocol negotiation.

The existing JVM registry owns lazy process lifecycle. This module owns the
cross-runtime contract above it: known accelerator capabilities, protocol
version negotiation, benchmark-qualified workload admission, and result
identity. It does not start Java or execute work.

A JVM workload is admitted only when independent benchmark evidence proves:
* semantic equivalence to the reference implementation;
* enough samples;
* a configured minimum speedup after amortized process/startup cost;
* bounded GC pause; and
* fresh evidence for the exact capability/runtime/protocol identity.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import math
import re
from typing import Any, Iterable

from skeleton.contracts.canonical import canonical_json_bytes


JVM_PROTOCOL_SCHEMA_VERSION = 1
JVM_PROTOCOL_TASK_ID = "VOL-033"
JVM_PROTOCOL_ACCOUNTABILITY_ID = "ACC-VOL-033"
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+#-]{0,191}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class JvmProtocolError(ValueError):
    """JVM protocol or qualification evidence is malformed."""


class JvmWorkload(str, Enum):
    OBSERVABILITY = "observability"
    VECTOR = "vector"
    PHYSICS = "physics"


class JvmResultStatus(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


def _token(value: object, field: str) -> str:
    if not isinstance(value, str) or not _TOKEN.fullmatch(value):
        raise JvmProtocolError(f"{field} must be a canonical token")
    return value


def _sha(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise JvmProtocolError(f"{field} must be lowercase sha256")
    return value


def _finite(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise JvmProtocolError(f"{field} must be finite numeric")
    result = float(value)
    if not math.isfinite(result):
        raise JvmProtocolError(f"{field} must be finite numeric")
    return result


def _positive(value: object, field: str) -> float:
    result = _finite(value, field)
    if result <= 0:
        raise JvmProtocolError(f"{field} must be positive")
    return result


def _nonnegative(value: object, field: str) -> float:
    result = _finite(value, field)
    if result < 0:
        raise JvmProtocolError(f"{field} must be non-negative")
    return result


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise JvmProtocolError(f"{field} must be positive integer")
    return value


def _tokens(values: Iterable[str], field: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise JvmProtocolError(f"{field} must be an iterable")
    result = tuple(sorted({_token(value, field) for value in values}))
    if not result:
        raise JvmProtocolError(f"{field} must be non-empty")
    return result


@dataclass(frozen=True, slots=True)
class JvmCapability:
    workload: JvmWorkload | str
    capability_id: str
    source_path: str
    class_name: str
    protocol_magic: int
    protocol_versions: tuple[int, ...]
    operations: tuple[str, ...]
    minimum_java_major: int = 21
    schema_version: int = JVM_PROTOCOL_SCHEMA_VERSION

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "workload", JvmWorkload(self.workload))
        except ValueError as exc:
            raise JvmProtocolError("invalid JVM workload") from exc
        for field in ("capability_id", "source_path", "class_name"):
            object.__setattr__(self, field, _token(getattr(self, field), field))
        if (
            isinstance(self.protocol_magic, bool)
            or not isinstance(self.protocol_magic, int)
            or self.protocol_magic < 1
            or self.protocol_magic > 0xFFFFFFFF
        ):
            raise JvmProtocolError("protocol_magic must be uint32")
        if (
            not isinstance(self.protocol_versions, tuple)
            or not self.protocol_versions
            or any(
                isinstance(value, bool) or not isinstance(value, int) or value < 1
                for value in self.protocol_versions
            )
        ):
            raise JvmProtocolError(
                "protocol_versions must be non-empty positive integer tuple"
            )
        versions = tuple(sorted(set(self.protocol_versions)))
        if len(versions) != len(self.protocol_versions):
            raise JvmProtocolError("protocol_versions must be unique")
        object.__setattr__(self, "protocol_versions", versions)
        object.__setattr__(self, "operations", _tokens(self.operations, "operations"))
        object.__setattr__(
            self,
            "minimum_java_major",
            _positive_int(self.minimum_java_major, "minimum_java_major"),
        )
        if self.schema_version != JVM_PROTOCOL_SCHEMA_VERSION:
            raise JvmProtocolError("unsupported JVM capability schema")

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "workload": self.workload.value,
            "capability_id": self.capability_id,
            "source_path": self.source_path,
            "class_name": self.class_name,
            "protocol_magic": self.protocol_magic,
            "protocol_versions": list(self.protocol_versions),
            "operations": list(self.operations),
            "minimum_java_major": self.minimum_java_major,
            "production_authority": False,
        }

    @property
    def capability_digest(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.payload())).hexdigest()


@dataclass(frozen=True, slots=True)
class JvmRuntimeDescriptor:
    runtime_id: str
    java_major: int
    vendor: str
    implementation: str
    runtime_digest: str
    supported_protocol_versions: tuple[int, ...]
    max_heap_bytes: int
    max_parallelism: int

    def __post_init__(self) -> None:
        for field in ("runtime_id", "vendor", "implementation"):
            object.__setattr__(self, field, _token(getattr(self, field), field))
        object.__setattr__(
            self,
            "java_major",
            _positive_int(self.java_major, "java_major"),
        )
        object.__setattr__(
            self,
            "runtime_digest",
            _sha(self.runtime_digest, "runtime_digest"),
        )
        if (
            not isinstance(self.supported_protocol_versions, tuple)
            or not self.supported_protocol_versions
        ):
            raise JvmProtocolError(
                "supported_protocol_versions must be non-empty tuple"
            )
        versions = tuple(
            sorted(
                {
                    _positive_int(value, "supported_protocol_versions")
                    for value in self.supported_protocol_versions
                }
            )
        )
        object.__setattr__(self, "supported_protocol_versions", versions)
        object.__setattr__(
            self,
            "max_heap_bytes",
            _positive_int(self.max_heap_bytes, "max_heap_bytes"),
        )
        object.__setattr__(
            self,
            "max_parallelism",
            _positive_int(self.max_parallelism, "max_parallelism"),
        )

    def payload(self) -> dict[str, Any]:
        return {
            "runtime_id": self.runtime_id,
            "java_major": self.java_major,
            "vendor": self.vendor,
            "implementation": self.implementation,
            "runtime_digest": self.runtime_digest,
            "supported_protocol_versions": list(
                self.supported_protocol_versions
            ),
            "max_heap_bytes": self.max_heap_bytes,
            "max_parallelism": self.max_parallelism,
        }

    @property
    def descriptor_digest(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.payload())).hexdigest()


@dataclass(frozen=True, slots=True)
class JvmBenchmarkEvidence:
    workload: JvmWorkload | str
    capability_digest: str
    runtime_descriptor_digest: str
    protocol_version: int
    reference_mean_ns: float
    jvm_mean_ns: float
    startup_amortized_ns: float
    p99_gc_pause_ms: float
    samples: int
    semantic_equivalence_digest: str
    semantic_equivalent: bool
    independent: bool
    observed_at: float

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "workload", JvmWorkload(self.workload))
        except ValueError as exc:
            raise JvmProtocolError("invalid benchmark workload") from exc
        for field in ("capability_digest", "runtime_descriptor_digest", "semantic_equivalence_digest"):
            object.__setattr__(self, field, _sha(getattr(self, field), field))
        object.__setattr__(
            self,
            "protocol_version",
            _positive_int(self.protocol_version, "protocol_version"),
        )
        for field in (
            "reference_mean_ns",
            "jvm_mean_ns",
            "startup_amortized_ns",
        ):
            object.__setattr__(self, field, _positive(getattr(self, field), field))
        object.__setattr__(
            self,
            "p99_gc_pause_ms",
            _nonnegative(self.p99_gc_pause_ms, "p99_gc_pause_ms"),
        )
        object.__setattr__(self, "samples", _positive_int(self.samples, "samples"))
        for field in ("semantic_equivalent", "independent"):
            if not isinstance(getattr(self, field), bool):
                raise JvmProtocolError(f"{field} must be boolean")
        object.__setattr__(
            self,
            "observed_at",
            _nonnegative(self.observed_at, "observed_at"),
        )

    @property
    def effective_jvm_mean_ns(self) -> float:
        return self.jvm_mean_ns + self.startup_amortized_ns

    @property
    def speedup(self) -> float:
        return self.reference_mean_ns / self.effective_jvm_mean_ns

    def payload(self) -> dict[str, Any]:
        return {
            "workload": self.workload.value,
            "capability_digest": self.capability_digest,
            "runtime_descriptor_digest": self.runtime_descriptor_digest,
            "protocol_version": self.protocol_version,
            "reference_mean_ns": self.reference_mean_ns,
            "jvm_mean_ns": self.jvm_mean_ns,
            "startup_amortized_ns": self.startup_amortized_ns,
            "p99_gc_pause_ms": self.p99_gc_pause_ms,
            "samples": self.samples,
            "semantic_equivalence_digest": self.semantic_equivalence_digest,
            "semantic_equivalent": self.semantic_equivalent,
            "independent": self.independent,
            "observed_at": self.observed_at,
        }

    @property
    def evidence_digest(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.payload())).hexdigest()


@dataclass(frozen=True, slots=True)
class JvmQualificationPolicy:
    min_samples: int = 50
    min_speedup: float = 1.10
    max_p99_gc_pause_ms: float = 50.0
    max_evidence_age_s: float = 7 * 24 * 60 * 60

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "min_samples",
            _positive_int(self.min_samples, "min_samples"),
        )
        object.__setattr__(
            self,
            "min_speedup",
            _positive(self.min_speedup, "min_speedup"),
        )
        object.__setattr__(
            self,
            "max_p99_gc_pause_ms",
            _nonnegative(self.max_p99_gc_pause_ms, "max_p99_gc_pause_ms"),
        )
        object.__setattr__(
            self,
            "max_evidence_age_s",
            _positive(self.max_evidence_age_s, "max_evidence_age_s"),
        )

    def payload(self) -> dict[str, Any]:
        return {
            "min_samples": self.min_samples,
            "min_speedup": self.min_speedup,
            "max_p99_gc_pause_ms": self.max_p99_gc_pause_ms,
            "max_evidence_age_s": self.max_evidence_age_s,
        }

    @property
    def policy_digest(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.payload())).hexdigest()


@dataclass(frozen=True, slots=True)
class JvmQualificationDecision:
    accepted: bool
    reasons: tuple[str, ...]
    workload: JvmWorkload | str
    capability_digest: str
    runtime_descriptor_digest: str
    benchmark_evidence_digest: str
    policy_digest: str
    negotiated_protocol_version: int | None
    speedup: float
    authority_scope: str = "jvm-admission-only"
    production_authority: bool = False
    schema_version: int = JVM_PROTOCOL_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.accepted, bool):
            raise JvmProtocolError("accepted must be boolean")
        if not isinstance(self.reasons, tuple) or any(
            not isinstance(reason, str) or not reason for reason in self.reasons
        ):
            raise JvmProtocolError("reasons must contain non-empty strings")
        try:
            object.__setattr__(self, "workload", JvmWorkload(self.workload))
        except ValueError as exc:
            raise JvmProtocolError("invalid qualification workload") from exc
        for field in (
            "capability_digest",
            "runtime_descriptor_digest",
            "benchmark_evidence_digest",
            "policy_digest",
        ):
            object.__setattr__(self, field, _sha(getattr(self, field), field))
        if self.negotiated_protocol_version is not None:
            object.__setattr__(
                self,
                "negotiated_protocol_version",
                _positive_int(
                    self.negotiated_protocol_version,
                    "negotiated_protocol_version",
                ),
            )
        object.__setattr__(self, "speedup", _positive(self.speedup, "speedup"))
        if self.authority_scope != "jvm-admission-only":
            raise JvmProtocolError("JVM admission scope escalation")
        if self.production_authority is not False:
            raise JvmProtocolError("JVM admission cannot claim production authority")
        if self.schema_version != JVM_PROTOCOL_SCHEMA_VERSION:
            raise JvmProtocolError("unsupported JVM qualification schema")
        if self.accepted and (self.reasons or self.negotiated_protocol_version is None):
            raise JvmProtocolError("accepted qualification must be complete")

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": JVM_PROTOCOL_TASK_ID,
            "accountability_id": JVM_PROTOCOL_ACCOUNTABILITY_ID,
            "accepted": self.accepted,
            "reasons": list(self.reasons),
            "workload": self.workload.value,
            "capability_digest": self.capability_digest,
            "runtime_descriptor_digest": self.runtime_descriptor_digest,
            "benchmark_evidence_digest": self.benchmark_evidence_digest,
            "policy_digest": self.policy_digest,
            "negotiated_protocol_version": self.negotiated_protocol_version,
            "speedup": self.speedup,
            "authority_scope": self.authority_scope,
            "production_authority": self.production_authority,
        }

    @property
    def decision_digest(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.payload())).hexdigest()


@dataclass(frozen=True, slots=True)
class JvmRequest:
    request_id: str
    workload: JvmWorkload | str
    capability_digest: str
    runtime_descriptor_digest: str
    protocol_version: int
    operation: str
    payload_digest: str
    max_wall_time_s: float
    max_response_bytes: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "request_id", _token(self.request_id, "request_id"))
        try:
            object.__setattr__(self, "workload", JvmWorkload(self.workload))
        except ValueError as exc:
            raise JvmProtocolError("invalid request workload") from exc
        for field in ("capability_digest", "runtime_descriptor_digest", "payload_digest"):
            object.__setattr__(self, field, _sha(getattr(self, field), field))
        object.__setattr__(
            self,
            "protocol_version",
            _positive_int(self.protocol_version, "protocol_version"),
        )
        object.__setattr__(self, "operation", _token(self.operation, "operation"))
        object.__setattr__(
            self,
            "max_wall_time_s",
            _positive(self.max_wall_time_s, "max_wall_time_s"),
        )
        object.__setattr__(
            self,
            "max_response_bytes",
            _positive_int(self.max_response_bytes, "max_response_bytes"),
        )

    def payload(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "workload": self.workload.value,
            "capability_digest": self.capability_digest,
            "runtime_descriptor_digest": self.runtime_descriptor_digest,
            "protocol_version": self.protocol_version,
            "operation": self.operation,
            "payload_digest": self.payload_digest,
            "max_wall_time_s": self.max_wall_time_s,
            "max_response_bytes": self.max_response_bytes,
        }

    @property
    def request_digest(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.payload())).hexdigest()


@dataclass(frozen=True, slots=True)
class JvmCallResult:
    request_digest: str
    protocol_version: int
    status: JvmResultStatus | str
    response_digest: str
    response_bytes: int
    wall_time_s: float
    error_code: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "request_digest", _sha(self.request_digest, "request_digest"))
        object.__setattr__(
            self,
            "protocol_version",
            _positive_int(self.protocol_version, "protocol_version"),
        )
        try:
            object.__setattr__(self, "status", JvmResultStatus(self.status))
        except ValueError as exc:
            raise JvmProtocolError("invalid JVM result status") from exc
        object.__setattr__(self, "response_digest", _sha(self.response_digest, "response_digest"))
        object.__setattr__(
            self,
            "response_bytes",
            _positive_int(self.response_bytes, "response_bytes"),
        )
        object.__setattr__(
            self,
            "wall_time_s",
            _nonnegative(self.wall_time_s, "wall_time_s"),
        )
        if self.error_code is not None:
            object.__setattr__(self, "error_code", _token(self.error_code, "error_code"))
        if self.status is JvmResultStatus.SUCCEEDED and self.error_code is not None:
            raise JvmProtocolError("successful result cannot carry error_code")

    def payload(self) -> dict[str, Any]:
        return {
            "request_digest": self.request_digest,
            "protocol_version": self.protocol_version,
            "status": self.status.value,
            "response_digest": self.response_digest,
            "response_bytes": self.response_bytes,
            "wall_time_s": self.wall_time_s,
            "error_code": self.error_code,
        }

    @property
    def result_digest(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.payload())).hexdigest()


def canonical_jvm_capabilities() -> tuple[JvmCapability, ...]:
    return (
        JvmCapability(
            workload=JvmWorkload.OBSERVABILITY,
            capability_id="jvm.observability.v1",
            source_path="java-accelerators/observability/AcceleratorMain.java",
            class_name="AcceleratorMain",
            protocol_magic=0x534B4F42,
            protocol_versions=(1,),
            operations=(
                "ping",
                "summary",
                "many_summaries",
                "anomaly_scan",
                "shutdown",
            ),
        ),
        JvmCapability(
            workload=JvmWorkload.VECTOR,
            capability_id="jvm.vector.v1",
            source_path="java-accelerators/vector/VectorSearchMain.java",
            class_name="VectorSearchMain",
            protocol_magic=0x534B5653,
            protocol_versions=(1,),
            operations=(
                "ping",
                "top_k",
                "batch_top_k",
                "range",
                "batch_range",
                "shutdown",
            ),
        ),
        JvmCapability(
            workload=JvmWorkload.PHYSICS,
            capability_id="jvm.physics.v1",
            source_path="java-accelerators/physics/BroadPhaseMain.java",
            class_name="BroadPhaseMain",
            protocol_magic=0x534B4250,
            protocol_versions=(1,),
            operations=(
                "ping",
                "pairs",
                "query_aabbs",
                "ray_aabbs",
                "sphere_cast_aabbs",
                "shutdown",
            ),
        ),
    )


def capability_for(workload: JvmWorkload | str) -> JvmCapability:
    target = JvmWorkload(workload)
    for capability in canonical_jvm_capabilities():
        if capability.workload is target:
            return capability
    raise JvmProtocolError("unknown JVM workload")


def qualify_jvm_workload(
    *,
    capability: JvmCapability,
    runtime: JvmRuntimeDescriptor,
    evidence: JvmBenchmarkEvidence,
    policy: JvmQualificationPolicy,
    observed_at: float,
) -> JvmQualificationDecision:
    if not isinstance(capability, JvmCapability):
        raise TypeError("capability must be JvmCapability")
    if not isinstance(runtime, JvmRuntimeDescriptor):
        raise TypeError("runtime must be JvmRuntimeDescriptor")
    if not isinstance(evidence, JvmBenchmarkEvidence):
        raise TypeError("evidence must be JvmBenchmarkEvidence")
    if not isinstance(policy, JvmQualificationPolicy):
        raise TypeError("policy must be JvmQualificationPolicy")
    now = _nonnegative(observed_at, "observed_at")

    reasons: list[str] = []
    common_versions = tuple(
        sorted(
            set(capability.protocol_versions)
            & set(runtime.supported_protocol_versions)
        )
    )
    negotiated = common_versions[-1] if common_versions else None
    if negotiated is None:
        reasons.append("protocol-version-incompatible")
    if runtime.java_major < capability.minimum_java_major:
        reasons.append("java-major-too-old")
    if evidence.workload is not capability.workload:
        reasons.append("benchmark-workload-mismatch")
    if evidence.capability_digest != capability.capability_digest:
        reasons.append("benchmark-capability-mismatch")
    if evidence.runtime_descriptor_digest != runtime.descriptor_digest:
        reasons.append("benchmark-runtime-mismatch")
    if negotiated is not None and evidence.protocol_version != negotiated:
        reasons.append("benchmark-protocol-version-mismatch")
    if not evidence.independent:
        reasons.append("benchmark-not-independent")
    if not evidence.semantic_equivalent:
        reasons.append("semantic-equivalence-failed")
    if evidence.samples < policy.min_samples:
        reasons.append("benchmark-sample-count-insufficient")
    if evidence.speedup < policy.min_speedup:
        reasons.append("jvm-speedup-insufficient")
    if evidence.p99_gc_pause_ms > policy.max_p99_gc_pause_ms:
        reasons.append("jvm-gc-pause-exceeded")
    if now < evidence.observed_at:
        reasons.append("benchmark-not-yet-valid")
    elif now - evidence.observed_at > policy.max_evidence_age_s:
        reasons.append("benchmark-evidence-stale")

    normalized = tuple(sorted(set(reasons)))
    return JvmQualificationDecision(
        accepted=not normalized,
        reasons=normalized,
        workload=capability.workload,
        capability_digest=capability.capability_digest,
        runtime_descriptor_digest=runtime.descriptor_digest,
        benchmark_evidence_digest=evidence.evidence_digest,
        policy_digest=policy.policy_digest,
        negotiated_protocol_version=negotiated,
        speedup=evidence.speedup,
    )


def validate_jvm_request(
    *,
    request: JvmRequest,
    capability: JvmCapability,
    runtime: JvmRuntimeDescriptor,
    qualification: JvmQualificationDecision,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if not qualification.accepted:
        reasons.append("jvm-workload-not-qualified")
    if request.workload is not capability.workload:
        reasons.append("request-workload-mismatch")
    if request.capability_digest != capability.capability_digest:
        reasons.append("request-capability-mismatch")
    if request.runtime_descriptor_digest != runtime.descriptor_digest:
        reasons.append("request-runtime-mismatch")
    if request.protocol_version not in capability.protocol_versions:
        reasons.append("request-capability-protocol-mismatch")
    if request.protocol_version not in runtime.supported_protocol_versions:
        reasons.append("request-runtime-protocol-mismatch")
    if request.protocol_version != qualification.negotiated_protocol_version:
        reasons.append("request-negotiated-protocol-mismatch")
    if request.operation not in capability.operations:
        reasons.append("request-operation-unsupported")
    return tuple(sorted(set(reasons)))


def validate_jvm_result(
    *,
    request: JvmRequest,
    result: JvmCallResult,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if result.request_digest != request.request_digest:
        reasons.append("result-request-mismatch")
    if result.protocol_version != request.protocol_version:
        reasons.append("result-protocol-version-mismatch")
    if result.response_bytes > request.max_response_bytes:
        reasons.append("result-response-budget-exceeded")
    if result.wall_time_s > request.max_wall_time_s:
        reasons.append("result-wall-time-budget-exceeded")
    if result.status is not JvmResultStatus.SUCCEEDED:
        reasons.append("result-not-successful")
    return tuple(sorted(set(reasons)))


__all__ = [
    "JVM_PROTOCOL_ACCOUNTABILITY_ID",
    "JVM_PROTOCOL_SCHEMA_VERSION",
    "JVM_PROTOCOL_TASK_ID",
    "JvmBenchmarkEvidence",
    "JvmCallResult",
    "JvmCapability",
    "JvmProtocolError",
    "JvmQualificationDecision",
    "JvmQualificationPolicy",
    "JvmRequest",
    "JvmResultStatus",
    "JvmRuntimeDescriptor",
    "JvmWorkload",
    "canonical_jvm_capabilities",
    "capability_for",
    "qualify_jvm_workload",
    "validate_jvm_request",
    "validate_jvm_result",
]
