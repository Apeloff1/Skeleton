from __future__ import annotations

import pytest

from skeleton.ai.runtime.observability.distributed_tracing import (
    Span,
    SpanContext,
)
from skeleton.ai.runtime.observability.trace_model import (
    SpanEvidence,
    TraceId,
    TraceLink,
    TraceModelError,
    causal_link_for,
    sanitize_trace_attributes,
    snapshot_span,
)


def _runtime_span(
    *,
    trace_id: str = "a" * 16,
    span_id: str = "b" * 16,
    parent_id: str | None = None,
    tags: dict[str, object] | None = None,
) -> Span:
    return Span(
        name="model.invoke",
        context=SpanContext(
            trace_id=trace_id,
            span_id=span_id,
            parent_id=parent_id,
            sampled=True,
        ),
        start_ns=100,
        end_ns=200,
        tags=tags or {"provider": "offline", "attempt": 1},
    )


def test_trace_id_binds_operation_and_correlation_identity() -> None:
    identity = TraceId(
        trace_id="a" * 16,
        operation_id="op-123",
        correlation_id="corr-123",
    )

    assert identity.trace_id == "a" * 16
    assert identity.operation_id == "op-123"
    assert identity.correlation_id == "corr-123"
    assert len(identity.digest) == 64


def test_snapshot_span_preserves_runtime_identity_but_not_mutability() -> None:
    runtime = _runtime_span(tags={"provider": "offline", "attempt": 1})

    evidence = snapshot_span(runtime)

    assert evidence.trace_id == runtime.context.trace_id
    assert evidence.span_id == runtime.context.span_id
    assert evidence.name == "model.invoke"
    assert evidence.attributes == (("attempt", 1), ("provider", "offline"))
    assert evidence.telemetry_authoritative is False

    runtime.tags["provider"] = "changed"
    assert evidence.attributes == (("attempt", 1), ("provider", "offline"))


def test_parent_span_produces_exact_causal_link() -> None:
    evidence = snapshot_span(
        _runtime_span(parent_id="c" * 16)
    )

    link = causal_link_for(evidence)

    assert link is not None
    assert link.trace_id == evidence.trace_id
    assert link.parent_span_id == "c" * 16
    assert link.child_span_id == evidence.span_id
    assert link.relation == "parent"
    assert len(link.digest) == 64


def test_root_span_has_no_synthetic_parent_link() -> None:
    evidence = snapshot_span(_runtime_span(parent_id=None))

    assert causal_link_for(evidence) is None


@pytest.mark.parametrize(
    "key",
    (
        "authorization",
        "api-key",
        "refresh_token",
        "user_prompt",
        "raw_content",
        "private_key",
    ),
)
def test_sensitive_trace_attributes_fail_closed(key: str) -> None:
    with pytest.raises(
        TraceModelError,
        match="sensitive trace attribute is forbidden",
    ):
        sanitize_trace_attributes({key: "example"})


def test_snapshot_rejects_sensitive_runtime_tags() -> None:
    with pytest.raises(
        TraceModelError,
        match="sensitive trace attribute is forbidden",
    ):
        snapshot_span(
            _runtime_span(tags={"token": "example-secret"})
        )


def test_trace_attributes_are_order_stable() -> None:
    left = sanitize_trace_attributes(
        {"provider": "offline", "attempt": 1}
    )
    right = sanitize_trace_attributes(
        {"attempt": 1, "provider": "offline"}
    )

    assert left == right


def test_trace_attributes_reject_nested_or_unbounded_values() -> None:
    with pytest.raises(
        TraceModelError,
        match="must be a JSON scalar",
    ):
        sanitize_trace_attributes({"payload": {"nested": True}})

    with pytest.raises(
        TraceModelError,
        match="exceeds maximum value length",
    ):
        sanitize_trace_attributes({"detail": "x" * 1025})


def test_unfinished_span_cannot_become_evidence() -> None:
    runtime = _runtime_span()
    runtime.end_ns = None

    with pytest.raises(
        TraceModelError,
        match="unfinished span cannot become trace evidence",
    ):
        snapshot_span(runtime)


def test_trace_evidence_cannot_claim_authoritative_runtime_state() -> None:
    with pytest.raises(
        TraceModelError,
        match="cannot be authoritative state",
    ):
        SpanEvidence(
            trace_id="a" * 16,
            span_id="b" * 16,
            parent_span_id=None,
            name="model.invoke",
            start_ns=100,
            end_ns=200,
            attributes=(),
            telemetry_authoritative=True,
        )


def test_trace_link_rejects_self_reference() -> None:
    with pytest.raises(
        TraceModelError,
        match="cannot self-reference",
    ):
        TraceLink(
            trace_id="a" * 16,
            parent_span_id="b" * 16,
            child_span_id="b" * 16,
        )


def test_trace_identity_rejects_noncanonical_hex() -> None:
    with pytest.raises(
        TraceModelError,
        match="lowercase hexadecimal",
    ):
        TraceId(
            trace_id="NOTHEX",
            operation_id="op-1",
            correlation_id="corr-1",
        )


def test_span_evidence_rejects_impossible_time_order() -> None:
    with pytest.raises(
        TraceModelError,
        match="span end cannot predate span start",
    ):
        SpanEvidence(
            trace_id="a" * 16,
            span_id="b" * 16,
            parent_span_id=None,
            name="model.invoke",
            start_ns=200,
            end_ns=100,
            attributes=(),
        )


def test_trace_attributes_reject_nonfinite_float() -> None:
    with pytest.raises(
        TraceModelError,
        match="must be finite",
    ):
        sanitize_trace_attributes({"latency_ms": float("nan")})


def test_span_evidence_rejects_duplicate_attribute_keys() -> None:
    with pytest.raises(
        TraceModelError,
        match="attribute keys must be unique",
    ):
        SpanEvidence(
            trace_id="a" * 16,
            span_id="b" * 16,
            parent_span_id=None,
            name="model.invoke",
            start_ns=100,
            end_ns=200,
            attributes=(
                ("provider", "offline"),
                ("provider", "changed"),
            ),
        )
