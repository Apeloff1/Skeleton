from __future__ import annotations

import hashlib
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from skeleton.contracts.canonical import canonical_json_bytes
from skeleton.native.jvm_registry import JvmAcceleratorRegistry
from skeleton.native.jvm_protocol import (
    JvmBenchmarkEvidence,
    JvmCallResult,
    JvmProtocolError,
    JvmQualificationPolicy,
    JvmRequest,
    JvmResultStatus,
    JvmRuntimeDescriptor,
    JvmWorkload,
    canonical_jvm_capabilities,
    capability_for,
    qualify_jvm_workload,
    validate_jvm_request,
    validate_jvm_result,
)


ROOT = Path(__file__).resolve().parents[2]


def runtime(**overrides) -> JvmRuntimeDescriptor:
    values = {
        "runtime_id": "java21-temurin",
        "java_major": 21,
        "vendor": "eclipse-temurin",
        "implementation": "hotspot",
        "runtime_digest": "a" * 64,
        "supported_protocol_versions": (1,),
        "max_heap_bytes": 2 * 1024**3,
        "max_parallelism": 16,
    }
    values.update(overrides)
    return JvmRuntimeDescriptor(**values)


def evidence(
    workload: JvmWorkload = JvmWorkload.VECTOR,
    *,
    capability=None,
    jvm_mean_ns: float = 500.0,
    reference_mean_ns: float = 1000.0,
    startup_amortized_ns: float = 50.0,
    p99_gc_pause_ms: float = 5.0,
    samples: int = 100,
    semantic_equivalent: bool = True,
    independent: bool = True,
    observed_at: float = 100.0,
    runtime_descriptor=None,
    protocol_version: int = 1,
) -> JvmBenchmarkEvidence:
    cap = capability or capability_for(workload)
    rt = runtime_descriptor or runtime()
    return JvmBenchmarkEvidence(
        workload=workload,
        capability_digest=cap.capability_digest,
        runtime_descriptor_digest=rt.descriptor_digest,
        protocol_version=protocol_version,
        reference_mean_ns=reference_mean_ns,
        jvm_mean_ns=jvm_mean_ns,
        startup_amortized_ns=startup_amortized_ns,
        p99_gc_pause_ms=p99_gc_pause_ms,
        samples=samples,
        semantic_equivalence_digest="b" * 64,
        semantic_equivalent=semantic_equivalent,
        independent=independent,
        observed_at=observed_at,
    )


def policy(**overrides) -> JvmQualificationPolicy:
    values = {
        "min_samples": 50,
        "min_speedup": 1.10,
        "max_p99_gc_pause_ms": 50.0,
        "max_evidence_age_s": 1000.0,
    }
    values.update(overrides)
    return JvmQualificationPolicy(**values)


@pytest.mark.parametrize(
    ("workload", "source", "class_name", "magic", "ops"),
    [
        (
            JvmWorkload.OBSERVABILITY,
            "java-accelerators/observability/AcceleratorMain.java",
            "AcceleratorMain",
            0x534B4F42,
            {
                "ping",
                "summary",
                "many_summaries",
                "anomaly_scan",
                "shutdown",
            },
        ),
        (
            JvmWorkload.VECTOR,
            "java-accelerators/vector/VectorSearchMain.java",
            "VectorSearchMain",
            0x534B5653,
            {
                "ping",
                "top_k",
                "batch_top_k",
                "range",
                "batch_range",
                "shutdown",
            },
        ),
        (
            JvmWorkload.PHYSICS,
            "java-accelerators/physics/BroadPhaseMain.java",
            "BroadPhaseMain",
            0x534B4250,
            {
                "ping",
                "pairs",
                "query_aabbs",
                "ray_aabbs",
                "sphere_cast_aabbs",
                "shutdown",
            },
        ),
    ],
)
def test_capability_registry_matches_actual_java_protocol_surface(
    workload: JvmWorkload,
    source: str,
    class_name: str,
    magic: int,
    ops: set[str],
) -> None:
    cap = capability_for(workload)

    assert cap.source_path == source
    assert cap.class_name == class_name
    assert cap.protocol_magic == magic
    assert cap.protocol_versions == (1,)
    assert set(cap.operations) == ops

    text = (ROOT / source).read_text(encoding="utf-8")
    assert f"public final class {class_name}" in text
    assert "static final short VERSION = 1;" in text
    assert f"0x{magic:08X}" in text


def test_capability_registry_is_complete_and_deterministic() -> None:
    caps = canonical_jvm_capabilities()

    assert tuple(item.workload for item in caps) == (
        JvmWorkload.OBSERVABILITY,
        JvmWorkload.VECTOR,
        JvmWorkload.PHYSICS,
    )
    assert len({item.capability_digest for item in caps}) == 3
    assert canonical_jvm_capabilities() == caps


def test_fast_semantically_equivalent_vector_workload_qualifies() -> None:
    cap = capability_for(JvmWorkload.VECTOR)
    rt = runtime()
    ev = evidence(capability=cap, runtime_descriptor=rt)

    decision = qualify_jvm_workload(
        capability=cap,
        runtime=rt,
        evidence=ev,
        policy=policy(),
        observed_at=110.0,
    )

    assert decision.accepted is True
    assert decision.reasons == ()
    assert decision.negotiated_protocol_version == 1
    assert decision.speedup == pytest.approx(1000.0 / 550.0)
    assert decision.authority_scope == "jvm-admission-only"
    assert decision.production_authority is False


def test_no_speedup_means_reference_path_remains_authoritative() -> None:
    cap = capability_for(JvmWorkload.VECTOR)
    rt = runtime()
    ev = evidence(
        capability=cap,
        runtime_descriptor=rt,
        jvm_mean_ns=950.0,
        startup_amortized_ns=100.0,
    )

    decision = qualify_jvm_workload(
        capability=cap,
        runtime=rt,
        evidence=ev,
        policy=policy(),
        observed_at=110.0,
    )

    assert decision.accepted is False
    assert "jvm-speedup-insufficient" in decision.reasons


def test_startup_cost_is_included_in_workload_benefit() -> None:
    cap = capability_for(JvmWorkload.OBSERVABILITY)
    rt = runtime()
    ev = evidence(
        workload=JvmWorkload.OBSERVABILITY,
        capability=cap,
        runtime_descriptor=rt,
        reference_mean_ns=1000.0,
        jvm_mean_ns=400.0,
        startup_amortized_ns=600.0,
    )

    decision = qualify_jvm_workload(
        capability=cap,
        runtime=rt,
        evidence=ev,
        policy=policy(min_speedup=1.01),
        observed_at=110.0,
    )

    assert ev.speedup == pytest.approx(1.0)
    assert decision.accepted is False
    assert "jvm-speedup-insufficient" in decision.reasons


def test_semantic_equivalence_is_mandatory() -> None:
    cap = capability_for(JvmWorkload.PHYSICS)
    rt = runtime()
    ev = evidence(
        workload=JvmWorkload.PHYSICS,
        capability=cap,
        runtime_descriptor=rt,
        semantic_equivalent=False,
    )

    decision = qualify_jvm_workload(
        capability=cap,
        runtime=rt,
        evidence=ev,
        policy=policy(),
        observed_at=110.0,
    )

    assert decision.accepted is False
    assert "semantic-equivalence-failed" in decision.reasons


def test_benchmark_must_be_independent() -> None:
    cap = capability_for(JvmWorkload.VECTOR)
    rt = runtime()
    ev = evidence(
        capability=cap,
        runtime_descriptor=rt,
        independent=False,
    )

    decision = qualify_jvm_workload(
        capability=cap,
        runtime=rt,
        evidence=ev,
        policy=policy(),
        observed_at=110.0,
    )

    assert "benchmark-not-independent" in decision.reasons


def test_sample_count_gc_pause_and_freshness_are_policy_bound() -> None:
    cap = capability_for(JvmWorkload.VECTOR)
    rt = runtime()
    ev = evidence(
        capability=cap,
        runtime_descriptor=rt,
        samples=10,
        p99_gc_pause_ms=80.0,
        observed_at=10.0,
    )

    decision = qualify_jvm_workload(
        capability=cap,
        runtime=rt,
        evidence=ev,
        policy=policy(max_evidence_age_s=50.0),
        observed_at=100.0,
    )

    assert "benchmark-sample-count-insufficient" in decision.reasons
    assert "jvm-gc-pause-exceeded" in decision.reasons
    assert "benchmark-evidence-stale" in decision.reasons


def test_java_version_and_protocol_are_negotiated_fail_closed() -> None:
    cap = capability_for(JvmWorkload.VECTOR)
    old = runtime(java_major=17)
    wrong_protocol = runtime(supported_protocol_versions=(2,))

    old_decision = qualify_jvm_workload(
        capability=cap,
        runtime=old,
        evidence=evidence(capability=cap, runtime_descriptor=old),
        policy=policy(),
        observed_at=110.0,
    )
    protocol_decision = qualify_jvm_workload(
        capability=cap,
        runtime=wrong_protocol,
        evidence=evidence(
            capability=cap,
            runtime_descriptor=wrong_protocol,
            protocol_version=2,
        ),
        policy=policy(),
        observed_at=110.0,
    )

    assert "java-major-too-old" in old_decision.reasons
    assert "protocol-version-incompatible" in protocol_decision.reasons
    assert protocol_decision.negotiated_protocol_version is None


def test_benchmark_identity_must_match_exact_capability_and_runtime() -> None:
    vector = capability_for(JvmWorkload.VECTOR)
    physics = capability_for(JvmWorkload.PHYSICS)
    rt = runtime()
    wrong_rt = runtime(runtime_id="java21-other", runtime_digest="c" * 64)
    ev = evidence(
        workload=JvmWorkload.VECTOR,
        capability=physics,
        runtime_descriptor=wrong_rt,
    )

    decision = qualify_jvm_workload(
        capability=vector,
        runtime=rt,
        evidence=ev,
        policy=policy(),
        observed_at=110.0,
    )

    assert "benchmark-capability-mismatch" in decision.reasons
    assert "benchmark-runtime-mismatch" in decision.reasons


def test_qualified_request_is_bound_to_negotiated_protocol_and_operation() -> None:
    cap = capability_for(JvmWorkload.VECTOR)
    rt = runtime()
    ev = evidence(capability=cap, runtime_descriptor=rt)
    decision = qualify_jvm_workload(
        capability=cap,
        runtime=rt,
        evidence=ev,
        policy=policy(),
        observed_at=110.0,
    )
    request = JvmRequest(
        request_id="vector-1",
        workload=JvmWorkload.VECTOR,
        capability_digest=cap.capability_digest,
        runtime_descriptor_digest=rt.descriptor_digest,
        protocol_version=1,
        operation="top_k",
        payload_digest="d" * 64,
        max_wall_time_s=1.0,
        max_response_bytes=1024,
    )

    assert validate_jvm_request(
        request=request,
        capability=cap,
        runtime=rt,
        qualification=decision,
    ) == ()


def test_unknown_operation_and_protocol_drift_are_rejected() -> None:
    cap = capability_for(JvmWorkload.VECTOR)
    rt = runtime()
    ev = evidence(capability=cap, runtime_descriptor=rt)
    decision = qualify_jvm_workload(
        capability=cap,
        runtime=rt,
        evidence=ev,
        policy=policy(),
        observed_at=110.0,
    )
    request = JvmRequest(
        request_id="vector-2",
        workload=JvmWorkload.VECTOR,
        capability_digest=cap.capability_digest,
        runtime_descriptor_digest=rt.descriptor_digest,
        protocol_version=2,
        operation="delete_everything",
        payload_digest="d" * 64,
        max_wall_time_s=1.0,
        max_response_bytes=1024,
    )

    reasons = validate_jvm_request(
        request=request,
        capability=cap,
        runtime=rt,
        qualification=decision,
    )

    assert "request-capability-protocol-mismatch" in reasons
    assert "request-runtime-protocol-mismatch" in reasons
    assert "request-negotiated-protocol-mismatch" in reasons
    assert "request-operation-unsupported" in reasons


def test_unqualified_workload_cannot_enter_jvm_request_path() -> None:
    cap = capability_for(JvmWorkload.VECTOR)
    rt = runtime()
    rejected = qualify_jvm_workload(
        capability=cap,
        runtime=rt,
        evidence=evidence(
            capability=cap,
            runtime_descriptor=rt,
            semantic_equivalent=False,
        ),
        policy=policy(),
        observed_at=110.0,
    )
    request = JvmRequest(
        request_id="vector-3",
        workload=JvmWorkload.VECTOR,
        capability_digest=cap.capability_digest,
        runtime_descriptor_digest=rt.descriptor_digest,
        protocol_version=1,
        operation="top_k",
        payload_digest="d" * 64,
        max_wall_time_s=1.0,
        max_response_bytes=1024,
    )

    assert "jvm-workload-not-qualified" in validate_jvm_request(
        request=request,
        capability=cap,
        runtime=rt,
        qualification=rejected,
    )


def test_result_binds_request_protocol_and_resource_budgets() -> None:
    cap = capability_for(JvmWorkload.OBSERVABILITY)
    rt = runtime()
    request = JvmRequest(
        request_id="obs-1",
        workload=JvmWorkload.OBSERVABILITY,
        capability_digest=cap.capability_digest,
        runtime_descriptor_digest=rt.descriptor_digest,
        protocol_version=1,
        operation="summary",
        payload_digest="d" * 64,
        max_wall_time_s=0.5,
        max_response_bytes=128,
    )
    good = JvmCallResult(
        request_digest=request.request_digest,
        protocol_version=1,
        status=JvmResultStatus.SUCCEEDED,
        response_digest="e" * 64,
        response_bytes=64,
        wall_time_s=0.2,
    )
    bad = JvmCallResult(
        request_digest="0" * 64,
        protocol_version=2,
        status=JvmResultStatus.FAILED,
        response_digest="e" * 64,
        response_bytes=256,
        wall_time_s=1.0,
        error_code="protocol_error",
    )

    assert validate_jvm_result(request=request, result=good) == ()
    reasons = validate_jvm_result(request=request, result=bad)
    assert set(reasons) == {
        "result-not-successful",
        "result-protocol-version-mismatch",
        "result-request-mismatch",
        "result-response-budget-exceeded",
        "result-wall-time-budget-exceeded",
    }


def test_contract_identities_use_shared_canonical_bytes() -> None:
    cap = capability_for(JvmWorkload.VECTOR)
    rt = runtime()
    ev = evidence(capability=cap, runtime_descriptor=rt)
    p = policy()
    decision = qualify_jvm_workload(
        capability=cap,
        runtime=rt,
        evidence=ev,
        policy=p,
        observed_at=110.0,
    )

    assert cap.capability_digest == hashlib.sha256(
        canonical_json_bytes(cap.payload())
    ).hexdigest()
    assert rt.descriptor_digest == hashlib.sha256(
        canonical_json_bytes(rt.payload())
    ).hexdigest()
    assert ev.evidence_digest == hashlib.sha256(
        canonical_json_bytes(ev.payload())
    ).hexdigest()
    assert decision.decision_digest == hashlib.sha256(
        canonical_json_bytes(decision.payload())
    ).hexdigest()


def test_jvm_protocol_source_and_ai_mirror_are_byte_identical() -> None:
    source = ROOT / "skeleton/native/jvm_protocol.py"
    mirror = ROOT / "skeleton/ai/runtime/native/jvm_protocol.py"
    assert source.read_bytes() == mirror.read_bytes()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"java_major": 0},
        {"max_heap_bytes": 0},
        {"max_parallelism": 0},
        {"supported_protocol_versions": ()},
    ],
)
def test_invalid_runtime_descriptor_fails_closed(kwargs: dict[str, object]) -> None:
    with pytest.raises(JvmProtocolError):
        runtime(**kwargs)



def test_registry_preflight_exposes_protocol_identity_without_starting_java() -> None:
    source = ROOT / "java-accelerators/vector/VectorSearchMain.java"
    registry = JvmAcceleratorRegistry(
        config_providers={
            "vector": lambda: SimpleNamespace(
                java_binary="definitely-not-a-java-binary",
                source=source,
            ),
        }
    )

    preflight = registry.preflight("vector")["vector"]
    capability = capability_for(JvmWorkload.VECTOR)

    assert registry.initialized("vector") is False
    assert preflight.capability_digest == capability.capability_digest
    assert preflight.protocol_versions == capability.protocol_versions
    assert preflight.minimum_java_major == capability.minimum_java_major
    assert preflight.source_available is True
    assert registry.initialized("vector") is False


def test_jvm_registry_source_and_ai_mirror_remain_byte_identical() -> None:
    source = ROOT / "skeleton/native/jvm_registry.py"
    mirror = ROOT / "skeleton/ai/runtime/native/jvm_registry.py"
    assert source.read_bytes() == mirror.read_bytes()
