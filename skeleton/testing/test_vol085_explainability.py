from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import pytest

from skeleton.contracts.operation import OperationEnvelope, OperationState
from skeleton.observability.explainability import (
    DecisionFactor,
    DecisionFactorKind,
    ExplanationBuilder,
    ExplanationError,
    ExplanationLedger,
    ExplanationPolicy,
    ExplanationRecord,
    FactorRelation,
    FactorSensitivity,
    OperationProvenance,
    factor_from_reconstruction_receipt,
    source_digest,
)
from skeleton.observability.resilient_telemetry import ResilientTelemetry

ROOT = Path(__file__).resolve().parents[2]
NOW = "2026-10-05T00:00:00Z"


def operation(
    *,
    operation_id: str = str(UUID(int=85)),
    trace_id: str = "trace.vol085",
    state: OperationState = OperationState.RUNNING,
) -> OperationEnvelope:
    created = datetime(2026, 10, 5, tzinfo=timezone.utc)
    return OperationEnvelope(
        operation_id=operation_id,
        tenant_id="tenant.test",
        actor_id="actor.test",
        capability="explain",
        created_at=created,
        deadline=created + timedelta(hours=1),
        idempotency_key="vol085:test",
        trace_id=trace_id,
        state=state,
    )


def factor(
    factor_id: str,
    *,
    op: OperationEnvelope | None = None,
    kind: DecisionFactorKind = DecisionFactorKind.OBSERVED_INPUT,
    relation: FactorRelation = FactorRelation.DECISION_INPUT,
    summary: str = "The user selected option A.",
    source_ref: str | None = None,
    sensitivity: FactorSensitivity = FactorSensitivity.SAFE,
    depends_on: tuple[str, ...] = (),
    uncertainty: float | None = None,
    observed_at: str = NOW,
) -> DecisionFactor:
    target = op or operation()
    return DecisionFactor(
        factor_id=factor_id,
        operation_id=target.operation_id,
        kind=kind,
        relation=relation,
        summary=summary,
        source_ref=source_ref or f"source:{factor_id}",
        source_digest=source_digest(
            {"factor_id": factor_id, "summary": summary}
        ),
        observed_at=observed_at,
        sensitivity=sensitivity,
        depends_on=depends_on,
        uncertainty=uncertainty,
    )


def model_bundle(
    *,
    op: OperationEnvelope | None = None,
) -> tuple[DecisionFactor, ...]:
    target = op or operation()
    observed = factor("input.user", op=target)
    model = factor(
        "model.rank",
        op=target,
        kind=DecisionFactorKind.MODEL_OUTPUT,
        relation=FactorRelation.DECISION_INPUT,
        summary="The ranking model preferred option A.",
        source_ref="model:ranker:v3",
    )
    uncertainty = factor(
        "uncertainty.rank",
        op=target,
        kind=DecisionFactorKind.UNCERTAINTY,
        relation=FactorRelation.UNCERTAINTY_DISCLOSURE,
        summary="Ranking uncertainty is moderate.",
        source_ref="model:ranker:v3:uncertainty",
        depends_on=("model.rank",),
        uncertainty=0.31,
    )
    return observed, model, uncertainty


def policy(**overrides) -> ExplanationPolicy:
    values = {
        "policy_id": "policy.user.explanation",
        "max_factors": 64,
        "max_visible_factors": 32,
        "max_dependency_depth": 16,
        "require_decision_input": True,
        "require_uncertainty_for_model_output": True,
        "allow_post_hoc": True,
    }
    values.update(overrides)
    return ExplanationPolicy(**values)


def build(
    factors,
    *,
    op: OperationEnvelope | None = None,
    chosen_policy: ExplanationPolicy | None = None,
    outcome_summary: str = "Option A was selected.",
) -> ExplanationRecord:
    target = op or operation()
    return ExplanationBuilder().build(
        operation=target,
        decision_id="decision.primary",
        outcome_summary=outcome_summary,
        factors=factors,
        policy=chosen_policy or policy(),
        generated_at=NOW,
    )


def test_source_digest_is_canonical_across_mapping_order() -> None:
    assert source_digest({"a": 1, "b": 2}) == source_digest(
        {"b": 2, "a": 1}
    )


def test_operation_provenance_binds_exact_operation_snapshot() -> None:
    running = operation(state=OperationState.RUNNING)
    completed = operation(state=OperationState.COMPLETED)

    first = OperationProvenance.from_operation(running)
    second = OperationProvenance.from_operation(completed)

    assert first.operation_id == running.operation_id
    assert first.operation_identity_digest == running.identity_digest
    assert first.operation_snapshot_digest != second.operation_snapshot_digest
    assert first.digest != second.digest


def test_safe_factor_redacts_inline_credentials() -> None:
    item = factor(
        "input.secret-text",
        summary="request token=abc123 and Bearer super-secret",
    )

    assert "abc123" not in item.summary
    assert "super-secret" not in item.summary
    assert "[REDACTED]" in item.summary


def test_private_factor_never_retains_raw_summary_or_source_ref() -> None:
    item = factor(
        "input.private",
        summary="customer email is person@example.com",
        source_ref="database:customer:1234",
        sensitivity=FactorSensitivity.PRIVATE,
    )

    assert item.summary == "[WITHHELD:PRIVATE]"
    assert "person@example.com" not in item.summary
    assert item.source_ref == "withheld:observed_input"
    assert "customer" not in item.source_ref


def test_hidden_reasoning_source_is_automatically_internal() -> None:
    item = factor(
        "model.hidden",
        kind=DecisionFactorKind.MODEL_OUTPUT,
        summary="hidden reasoning content that must not escape",
        source_ref="chain_of_thought:model:private",
    )

    assert item.sensitivity is FactorSensitivity.INTERNAL
    assert item.summary == "[WITHHELD:INTERNAL]"
    assert "reasoning content" not in item.summary
    assert item.source_ref == "withheld:model_output"


def test_post_hoc_relation_requires_derived_summary_kind() -> None:
    with pytest.raises(
        ExplanationError,
        match="post_hoc_summary relation requires derived_summary",
    ):
        factor(
            "bad.posthoc",
            relation=FactorRelation.POST_HOC_SUMMARY,
        )


def test_post_hoc_summary_requires_dependencies() -> None:
    with pytest.raises(
        ExplanationError,
        match="requires explicit factor dependencies",
    ):
        factor(
            "posthoc",
            kind=DecisionFactorKind.DERIVED_SUMMARY,
            relation=FactorRelation.POST_HOC_SUMMARY,
        )


def test_derived_summary_cannot_masquerade_as_decision_input() -> None:
    with pytest.raises(
        ExplanationError,
        match="cannot masquerade as decision input",
    ):
        factor(
            "derived.input",
            kind=DecisionFactorKind.DERIVED_SUMMARY,
            relation=FactorRelation.DECISION_INPUT,
            depends_on=("input.user",),
        )


def test_uncertainty_requires_relation_dependency_and_value() -> None:
    with pytest.raises(
        ExplanationError,
        match="requires uncertainty_disclosure relation",
    ):
        factor(
            "uncertainty.bad-relation",
            kind=DecisionFactorKind.UNCERTAINTY,
            relation=FactorRelation.SUPPORTING_EVIDENCE,
            depends_on=("model.rank",),
            uncertainty=0.2,
        )

    with pytest.raises(
        ExplanationError,
        match="requires factor dependencies",
    ):
        factor(
            "uncertainty.no-dependency",
            kind=DecisionFactorKind.UNCERTAINTY,
            relation=FactorRelation.UNCERTAINTY_DISCLOSURE,
            uncertainty=0.2,
        )

    with pytest.raises(
        ExplanationError,
        match="requires uncertainty value",
    ):
        factor(
            "uncertainty.no-value",
            kind=DecisionFactorKind.UNCERTAINTY,
            relation=FactorRelation.UNCERTAINTY_DISCLOSURE,
            depends_on=("model.rank",),
        )


def test_uncertainty_value_is_forbidden_on_other_factor_kinds() -> None:
    with pytest.raises(
        ExplanationError,
        match="reserved for uncertainty factors",
    ):
        factor("input.bad", uncertainty=0.1)


def test_builder_is_deterministic_across_factor_input_order() -> None:
    factors = model_bundle()

    first = build(factors)
    second = build(tuple(reversed(factors)))

    assert first == second
    assert first.digest == second.digest
    assert [item.factor_id for item in first.factors] == [
        "input.user",
        "model.rank",
        "uncertainty.rank",
    ]


def test_builder_rejects_factor_from_another_operation() -> None:
    first = operation()
    second = operation(operation_id=str(UUID(int=86)))

    with pytest.raises(
        ExplanationError,
        match="belongs to another operation",
    ):
        build(
            (factor("input.other", op=second),),
            op=first,
            chosen_policy=policy(
                require_uncertainty_for_model_output=False,
            ),
        )


def test_builder_rejects_duplicate_factor_identity() -> None:
    item = factor("duplicate")

    with pytest.raises(
        ExplanationError,
        match="duplicate factor identity",
    ):
        build(
            (item, item),
            chosen_policy=policy(
                require_uncertainty_for_model_output=False,
            ),
        )


def test_builder_rejects_unknown_dependency() -> None:
    derived = factor(
        "summary",
        kind=DecisionFactorKind.DERIVED_SUMMARY,
        relation=FactorRelation.SUPPORTING_EVIDENCE,
        depends_on=("missing",),
    )

    with pytest.raises(
        ExplanationError,
        match="unknown dependency",
    ):
        build(
            (factor("input.user"), derived),
            chosen_policy=policy(
                require_uncertainty_for_model_output=False,
            ),
        )


def test_builder_rejects_dependency_cycle() -> None:
    left = factor(
        "summary.left",
        kind=DecisionFactorKind.DERIVED_SUMMARY,
        relation=FactorRelation.SUPPORTING_EVIDENCE,
        depends_on=("summary.right",),
    )
    right = factor(
        "summary.right",
        kind=DecisionFactorKind.DERIVED_SUMMARY,
        relation=FactorRelation.SUPPORTING_EVIDENCE,
        depends_on=("summary.left",),
    )

    with pytest.raises(
        ExplanationError,
        match="dependency cycle",
    ):
        build(
            (factor("input.user"), left, right),
            chosen_policy=policy(
                require_uncertainty_for_model_output=False,
            ),
        )


def test_builder_rejects_dependency_depth_above_policy() -> None:
    input_factor = factor("input.user")
    one = factor(
        "summary.one",
        kind=DecisionFactorKind.DERIVED_SUMMARY,
        relation=FactorRelation.SUPPORTING_EVIDENCE,
        depends_on=("input.user",),
    )
    two = factor(
        "summary.two",
        kind=DecisionFactorKind.DERIVED_SUMMARY,
        relation=FactorRelation.SUPPORTING_EVIDENCE,
        depends_on=("summary.one",),
    )

    with pytest.raises(
        ExplanationError,
        match="dependency depth exceeds policy bound",
    ):
        build(
            (input_factor, one, two),
            chosen_policy=policy(
                max_dependency_depth=2,
                require_uncertainty_for_model_output=False,
            ),
        )


def test_policy_can_require_recorded_decision_input() -> None:
    supporting = factor(
        "support.only",
        relation=FactorRelation.SUPPORTING_EVIDENCE,
    )

    with pytest.raises(
        ExplanationError,
        match="requires at least one recorded decision input",
    ):
        build(
            (supporting,),
            chosen_policy=policy(
                require_uncertainty_for_model_output=False,
            ),
        )


def test_policy_can_forbid_post_hoc_summaries() -> None:
    observed = factor("input.user")
    summary = factor(
        "summary.posthoc",
        kind=DecisionFactorKind.DERIVED_SUMMARY,
        relation=FactorRelation.POST_HOC_SUMMARY,
        depends_on=("input.user",),
    )

    with pytest.raises(
        ExplanationError,
        match="forbids post-hoc",
    ):
        build(
            (observed, summary),
            chosen_policy=policy(
                allow_post_hoc=False,
                require_uncertainty_for_model_output=False,
            ),
        )


def test_model_output_requires_specific_uncertainty_disclosure() -> None:
    observed = factor("input.user")
    model = factor(
        "model.rank",
        kind=DecisionFactorKind.MODEL_OUTPUT,
        relation=FactorRelation.DECISION_INPUT,
    )

    with pytest.raises(
        ExplanationError,
        match="lacks uncertainty disclosure",
    ):
        build((observed, model))


def test_uncertainty_for_other_model_does_not_satisfy_requirement() -> None:
    observed = factor("input.user")
    first_model = factor(
        "model.first",
        kind=DecisionFactorKind.MODEL_OUTPUT,
        relation=FactorRelation.DECISION_INPUT,
    )
    second_model = factor(
        "model.second",
        kind=DecisionFactorKind.MODEL_OUTPUT,
        relation=FactorRelation.SUPPORTING_EVIDENCE,
    )
    disclosure = factor(
        "uncertainty.second",
        kind=DecisionFactorKind.UNCERTAINTY,
        relation=FactorRelation.UNCERTAINTY_DISCLOSURE,
        depends_on=("model.second",),
        uncertainty=0.4,
    )

    with pytest.raises(
        ExplanationError,
        match="model output model.first lacks uncertainty disclosure",
    ):
        build((observed, first_model, second_model, disclosure))


def test_sensitive_factor_taints_derived_descendants() -> None:
    public_input = factor("input.public")
    private_input = factor(
        "input.private",
        sensitivity=FactorSensitivity.PRIVATE,
        summary="private account value",
    )
    derived = factor(
        "summary.private-derived",
        kind=DecisionFactorKind.DERIVED_SUMMARY,
        relation=FactorRelation.SUPPORTING_EVIDENCE,
        summary="This summary could reveal private account value.",
        depends_on=("input.private",),
    )

    record = build(
        (public_input, private_input, derived),
        chosen_policy=policy(
            require_uncertainty_for_model_output=False,
        ),
    )

    assert [item.factor_id for item in record.factors] == [
        "input.public",
    ]
    assert record.withheld_factor_count == 2
    rendered = json_text(record.to_public_dict())
    assert "private account value" not in rendered
    assert "summary.private-derived" not in rendered


def json_text(value: object) -> str:
    import json
    return json.dumps(value, sort_keys=True)


def test_public_surface_omits_source_refs_and_withheld_digests() -> None:
    public_input = factor("input.public")
    private_input = factor(
        "input.private",
        sensitivity=FactorSensitivity.PRIVATE,
        summary="private data",
    )
    record = build(
        (public_input, private_input),
        chosen_policy=policy(
            require_uncertainty_for_model_output=False,
        ),
    )

    payload = record.to_public_dict()
    rendered = json_text(payload)

    assert "source_ref" not in rendered
    assert "withheld_factor_digests" not in payload
    assert payload["withheld_factor_count"] == 1
    assert "private data" not in rendered


def test_audit_surface_exposes_safe_source_ref_not_unsafe_content() -> None:
    safe = factor("input.safe", source_ref="api:user-selection")
    hidden = factor(
        "input.hidden",
        source_ref="system_prompt:private",
        summary="do not expose this hidden text",
    )
    record = build(
        (safe, hidden),
        chosen_policy=policy(
            require_uncertainty_for_model_output=False,
        ),
    )

    payload = record.to_audit_dict()
    rendered = json_text(payload)

    assert "api:user-selection" in rendered
    assert "system_prompt:private" not in rendered
    assert "do not expose this hidden text" not in rendered
    assert len(payload["withheld_factor_digests"]) == 1


def test_visible_factor_limit_fails_instead_of_silent_truncation() -> None:
    factors = tuple(factor(f"input.{index}") for index in range(3))

    with pytest.raises(
        ExplanationError,
        match="refusing silent truncation",
    ):
        build(
            factors,
            chosen_policy=policy(
                max_visible_factors=2,
                require_uncertainty_for_model_output=False,
            ),
        )


def test_total_factor_limit_fails_closed() -> None:
    factors = tuple(factor(f"input.{index}") for index in range(3))

    with pytest.raises(
        ExplanationError,
        match="factor count exceeds policy",
    ):
        build(
            factors,
            chosen_policy=policy(
                max_factors=2,
                max_visible_factors=2,
                require_uncertainty_for_model_output=False,
            ),
        )


def test_outcome_summary_is_redacted() -> None:
    record = build(
        (factor("input.user"),),
        chosen_policy=policy(
            require_uncertainty_for_model_output=False,
        ),
        outcome_summary="Selected A with password=hunter2",
    )

    assert "hunter2" not in record.outcome_summary
    assert "[REDACTED]" in record.outcome_summary


def test_verify_rejects_different_operation_state_snapshot() -> None:
    running = operation(state=OperationState.RUNNING)
    record = build(
        (factor("input.user", op=running),),
        op=running,
        chosen_policy=policy(
            require_uncertainty_for_model_output=False,
        ),
    )
    completed = operation(state=OperationState.COMPLETED)

    with pytest.raises(
        ExplanationError,
        match="exact operation provenance",
    ):
        ExplanationBuilder().verify(
            record=record,
            operation=completed,
            policy=policy(
                require_uncertainty_for_model_output=False,
            ),
        )


def test_verify_rejects_policy_substitution() -> None:
    chosen = policy(
        require_uncertainty_for_model_output=False,
    )
    record = build(
        (factor("input.user"),),
        chosen_policy=chosen,
    )
    changed = replace(chosen, max_factors=63)

    with pytest.raises(
        ExplanationError,
        match="policy digest mismatch",
    ):
        ExplanationBuilder().verify(
            record=record,
            operation=operation(),
            policy=changed,
        )


def test_record_constructor_detects_factor_set_tampering() -> None:
    chosen = policy(
        require_uncertainty_for_model_output=False,
    )
    record = build(
        (factor("input.user"),),
        chosen_policy=chosen,
    )
    replacement = factor(
        "input.other",
        summary="Different evidence.",
    )

    with pytest.raises(
        ExplanationError,
        match="factor_set_digest",
    ):
        replace(
            record,
            factors=(replacement,),
        )


def test_explanation_id_changes_with_factor_or_policy_identity() -> None:
    base = build(
        (factor("input.user"),),
        chosen_policy=policy(
            require_uncertainty_for_model_output=False,
        ),
    )
    changed_factor = build(
        (
            factor(
                "input.user",
                summary="A different observed input.",
            ),
        ),
        chosen_policy=policy(
            require_uncertainty_for_model_output=False,
        ),
    )
    changed_policy = build(
        (factor("input.user"),),
        chosen_policy=policy(
            max_factors=63,
            require_uncertainty_for_model_output=False,
        ),
    )

    assert base.explanation_id != changed_factor.explanation_id
    assert base.explanation_id != changed_policy.explanation_id


def test_ledger_is_idempotent_for_identical_record() -> None:
    record = build(
        (factor("input.user"),),
        chosen_policy=policy(
            require_uncertainty_for_model_output=False,
        ),
    )
    ledger = ExplanationLedger()

    assert ledger.append(record) is record
    assert ledger.append(record) is record
    assert ledger.get(record.explanation_id) is record
    assert ledger.for_operation(operation().operation_id) == (record,)
    assert ledger.digest


def test_record_identity_rejects_content_substitution() -> None:
    record = build(
        (factor("input.user"),),
        chosen_policy=policy(
            require_uncertainty_for_model_output=False,
        ),
    )

    with pytest.raises(
        ExplanationError,
        match="explanation_id does not bind record content",
    ):
        replace(
            record,
            outcome_summary="A different sanitized outcome.",
        )


def test_full_ledger_still_allows_idempotent_replay() -> None:
    first = build(
        (factor("input.user"),),
        chosen_policy=policy(
            require_uncertainty_for_model_output=False,
        ),
    )
    second = build(
        (
            factor(
                "input.other",
                summary="Another input.",
            ),
        ),
        chosen_policy=policy(
            require_uncertainty_for_model_output=False,
        ),
    )
    ledger = ExplanationLedger(max_records=1)
    ledger.append(first)

    assert ledger.append(first) is first
    with pytest.raises(
        ExplanationError,
        match="capacity reached",
    ):
        ledger.append(second)


def test_reconstruction_receipt_can_be_bound_as_evidence_factor() -> None:
    telemetry = ResilientTelemetry(clock=lambda: 1.0)
    emitted = telemetry.emit(
        "tool.completed",
        payload={"tool": "calculator", "result": "ok"},
        correlation_id="correlation.vol085",
    )
    op = operation()

    item = factor_from_reconstruction_receipt(
        operation=op,
        factor_id="receipt.tool",
        receipt=emitted.receipt,
        summary="The recorded tool operation completed.",
        observed_at=NOW,
    )

    assert item.kind is DecisionFactorKind.EVIDENCE_RECEIPT
    assert item.source_digest == emitted.receipt.event_digest
    assert item.source_ref.startswith("telemetry:tool.completed:")


def test_reconstruction_receipt_factor_participates_in_explanation() -> None:
    telemetry = ResilientTelemetry(clock=lambda: 1.0)
    receipt = telemetry.emit(
        "tool.completed",
        payload={"tool": "safe"},
        correlation_id="corr",
    ).receipt
    op = operation()
    decision_input = factor("input.user", op=op)
    evidence_factor = factor_from_reconstruction_receipt(
        operation=op,
        factor_id="receipt.tool",
        receipt=receipt,
        summary="A tool receipt supports the decision.",
        observed_at=NOW,
    )

    record = build(
        (decision_input, evidence_factor),
        op=op,
        chosen_policy=policy(
            require_uncertainty_for_model_output=False,
        ),
    )

    assert {
        item.kind for item in record.factors
    } == {
        DecisionFactorKind.OBSERVED_INPUT,
        DecisionFactorKind.EVIDENCE_RECEIPT,
    }


def test_public_record_labels_post_hoc_and_uncertainty_distinctly() -> None:
    observed, model, uncertainty = model_bundle()
    posthoc = factor(
        "summary.posthoc",
        kind=DecisionFactorKind.DERIVED_SUMMARY,
        relation=FactorRelation.POST_HOC_SUMMARY,
        summary="After the decision, the evidence can be summarized this way.",
        depends_on=("input.user", "model.rank"),
    )

    record = build((observed, model, uncertainty, posthoc))
    by_id = {
        item["factor_id"]: item
        for item in record.to_public_dict()["factors"]
    }

    assert by_id["model.rank"]["relation"] == "decision_input"
    assert by_id["uncertainty.rank"]["relation"] == (
        "uncertainty_disclosure"
    )
    assert by_id["summary.posthoc"]["relation"] == "post_hoc_summary"


def test_withheld_model_output_and_uncertainty_do_not_leak() -> None:
    observed = factor("input.user")
    hidden_model = factor(
        "model.private",
        kind=DecisionFactorKind.MODEL_OUTPUT,
        relation=FactorRelation.DECISION_INPUT,
        sensitivity=FactorSensitivity.INTERNAL,
        summary="private internal model trace",
        source_ref="private_reasoning:model",
    )
    uncertainty = factor(
        "uncertainty.private",
        kind=DecisionFactorKind.UNCERTAINTY,
        relation=FactorRelation.UNCERTAINTY_DISCLOSURE,
        summary="uncertainty based on private model trace",
        source_ref="model:private:uncertainty",
        depends_on=("model.private",),
        uncertainty=0.6,
    )

    record = build((observed, hidden_model, uncertainty))
    rendered = json_text(record.to_public_dict())

    assert [item.factor_id for item in record.factors] == ["input.user"]
    assert record.withheld_factor_count == 2
    assert "private internal model trace" not in rendered
    assert "uncertainty based on private model trace" not in rendered


def test_factor_digest_changes_with_relation_not_just_text() -> None:
    first = factor(
        "factor.same",
        relation=FactorRelation.DECISION_INPUT,
    )
    second = factor(
        "factor.same",
        relation=FactorRelation.SUPPORTING_EVIDENCE,
    )

    assert first.digest != second.digest


def test_public_serialization_is_deterministic() -> None:
    record = build(model_bundle())

    assert record.to_public_dict() == record.to_public_dict()
    assert record.digest == record.digest


def test_canonical_and_ai_explainability_runtime_are_byte_identical() -> None:
    canonical = ROOT / "skeleton/observability/explainability.py"
    mirror = ROOT / "skeleton/ai/runtime/observability/explainability.py"

    assert canonical.read_bytes() == mirror.read_bytes()


def test_public_surface_omits_trace_id_but_audit_retains_it() -> None:
    record = build(
        (factor("input.user"),),
        chosen_policy=policy(
            require_uncertainty_for_model_output=False,
        ),
    )

    public = record.to_public_dict()
    audit = record.to_audit_dict()

    assert "trace_id" not in public
    assert audit["trace_id"] == operation().trace_id


def test_private_uncertainty_taints_otherwise_safe_model_output() -> None:
    observed = factor("input.user")
    model = factor(
        "model.rank",
        kind=DecisionFactorKind.MODEL_OUTPUT,
        relation=FactorRelation.DECISION_INPUT,
        summary="Safe model-output summary.",
    )
    uncertainty = factor(
        "uncertainty.rank",
        kind=DecisionFactorKind.UNCERTAINTY,
        relation=FactorRelation.UNCERTAINTY_DISCLOSURE,
        summary="private calibration details",
        sensitivity=FactorSensitivity.PRIVATE,
        depends_on=("model.rank",),
        uncertainty=0.2,
    )

    record = build((observed, model, uncertainty))

    assert [item.factor_id for item in record.factors] == ["input.user"]
    assert record.withheld_factor_count == 2
    rendered = json_text(record.to_public_dict())
    assert "Safe model-output summary." not in rendered
    assert "private calibration details" not in rendered

def test_future_observation_cannot_masquerade_as_decision_provenance() -> None:
    future = factor(
        "input.future",
        observed_at="2026-10-05T00:00:01Z",
    )

    with pytest.raises(
        ExplanationError,
        match="cannot occur after explanation generation",
    ):
        build((future,), chosen_policy=policy(
            require_uncertainty_for_model_output=False,
        ))
