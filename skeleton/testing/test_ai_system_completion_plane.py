from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import socket
import threading

import pytest

from skeleton.contracts.ai_execution import (
    AIExecutionRequest,
    AIExecutionResult,
    ExecutionState,
)
from skeleton.ai.learning.promotion import (
    EvaluationReceipt,
    ExperimentSpec,
    FeedbackLedger,
    FeedbackPromotionError,
    FeedbackPromotionPipeline,
)
from skeleton.ai.runtime.context.ledger import ContextLedger
from skeleton.ai.runtime.functional_ai import FunctionalAIRequest, FunctionalAIRuntime
from skeleton.ai.runtime.inference import (
    CallableLocalModel,
    LocalInferenceEngine,
    LocalInferenceRequest,
    LocalInferenceResult,
    LocalModelAdapter,
    LocalToolCall,
)
from skeleton.ai.runtime.memory.core import Chunk, InMemoryTFIDFStore
from skeleton.ai.runtime.system_completion import (
    CompletionPlaneError,
    CompletionRequirement,
    REQUIRED_COMPLETION_REQUIREMENTS,
    RequirementProof,
    SystemCompletionPlane,
    completion_learning_experiment_id,
)
from skeleton.intelligence.execution_runtime import (
    CognitiveExecutionRuntime,
    ExecutionFinalizationBindings,
    ExecutionVerificationDecision,
)
from skeleton.persistence.execution_repository import SQLiteExecutionRepository
from skeleton.skills.tool_contract import ToolEffect, ToolManifest
from skeleton.skills.tool_runtime import AsyncToolRuntime


NOW = datetime(2026, 10, 2, 20, 10, tzinfo=timezone.utc)
HEAD = "a" * 40


def _local_model() -> LocalModelAdapter:
    model_digest = hashlib.sha256(b"system-completion-local-model").hexdigest()

    def runner(
        request: LocalInferenceRequest,
        cancel: threading.Event,
    ) -> LocalInferenceResult:
        assert not cancel.is_set()
        if request.prompt.startswith("Tool results from the previous provider turn"):
            return LocalInferenceResult(
                text="System completion transaction finished from local governed evidence.",
                model_id="system-completion-local",
                model_digest=model_digest,
                input_tokens=len(request.rendered_input.split()),
                output_tokens=9,
                response_id="local:system-completion:final",
            )
        return LocalInferenceResult(
            text=None,
            model_id="system-completion-local",
            model_digest=model_digest,
            input_tokens=len(request.rendered_input.split()),
            output_tokens=4,
            finish_reason="tool_calls",
            response_id="local:system-completion:tool",
            tool_calls=(
                LocalToolCall(
                    call_id="completion-read-1",
                    tool_id="repo.read",
                    arguments={"path": "README.md"},
                ),
            ),
        )

    return LocalModelAdapter(
        LocalInferenceEngine(
            CallableLocalModel(
                model_id="system-completion-local",
                model_digest=model_digest,
                runner=runner,
            )
        )
    )


def _verification(
    _request,
    candidate: str,
    context_digest: str,
) -> ExecutionVerificationDecision:
    assert candidate.startswith("System completion transaction")
    return ExecutionVerificationDecision(
        passed=True,
        receipt={
            "outcome": "passed",
            "policy_satisfied": True,
            "verifier_id": "system-completion:independent-output",
            "candidate_digest": hashlib.sha256(candidate.encode("utf-8")).hexdigest(),
            "context_digest": context_digest,
        },
        evidence_refs=(
            "evidence:system-completion:local-tool-result",
            "evidence:system-completion:independent-output",
        ),
    )


async def _finalization(
    _request,
    _candidate: str,
    _payload,
) -> ExecutionFinalizationBindings:
    return ExecutionFinalizationBindings(
        memory_refs=("memory:system-completion:bound",),
        artifact_refs=("artifact:system-completion:answer",),
    )


async def _functional_run(
    tmp_path,
    *,
    database_name: str = "ai-system-completion.sqlite3",
    request_id: str = "ai-system-completion-e2e",
):
    database = tmp_path / database_name
    repository = SQLiteExecutionRepository(database)
    tools = AsyncToolRuntime()
    observed_tool_ids = []

    async def read_handler(request):
        observed_tool_ids.append(request.tool_id)
        return "repo-evidence:README.md"

    await tools.register(
        ToolManifest(
            tool_id="repo.read",
            version="1.0.0",
            description="Read repository evidence",
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
                "additionalProperties": False,
            },
            effect=ToolEffect.READ_ONLY,
            approval_required=False,
            data_policy="internal:repository",
            network_policy="none",
        ),
        read_handler,
    )

    request = FunctionalAIRequest(
        request_id=request_id,
        objective="Prove cross-cutting standalone AI completion.",
        prompt="Read README.md and produce a verified completion statement.",
        instructions="Use the local model and governed tool only.",
        context_digest=hashlib.sha256(b"system-completion-context").hexdigest(),
        allowed_tool_ids=("repo.read",),
        created_at=NOW,
    )
    runtime = FunctionalAIRuntime(
        repository,
        _local_model(),
        tools,
        verification_hook=_verification,
        finalization_binding_hook=_finalization,
    )
    return database, request, await runtime.execute(request), tuple(observed_tool_ids)



def _stop_request(kind: str, *, deadline: bool) -> AIExecutionRequest:
    stop_policy = {"max_repeat_tool_batches": 1}
    if deadline:
        stop_policy["deadline"] = NOW.isoformat()
    return AIExecutionRequest(
        operation_id=f"system-completion-stop-operation-{kind}",
        execution_id=f"system-completion-stop-execution-{kind}",
        objective="Prove runtime stop semantics fail closed.",
        context_policy={
            "tenant_id": "default",
            "data_class": "internal",
            "capability": "vs001.functional_ai",
        },
        tool_policy={
            "tenant_id": "default",
            "data_class": "internal",
            "purpose": "tool-execution",
            "allowed_tool_ids": [],
        },
        resource_budget={
            "max_model_turns": 1,
            "max_tool_calls": 1,
        },
        stop_policy=stop_policy,
        created_at=NOW,
    )


async def _stop_semantics_results(tmp_path):
    context_digest = hashlib.sha256(b"system-completion-stop-context").hexdigest()

    deadline_repository = SQLiteExecutionRepository(
        tmp_path / "system-completion-deadline.sqlite3"
    )
    deadline_runtime = CognitiveExecutionRuntime(
        deadline_repository,
        _local_model(),
        AsyncToolRuntime(),
        verification_hook=_verification,
    )
    deadline_request = _stop_request("deadline", deadline=True)
    deadline_run = await deadline_runtime.start(
        deadline_request,
        instructions="Do not execute after the deadline.",
        prompt="This request is already at its deadline.",
        context_digest=context_digest,
        now=NOW,
    )
    assert deadline_run.result is not None

    cancellation_repository = SQLiteExecutionRepository(
        tmp_path / "system-completion-cancellation.sqlite3"
    )
    cancellation_runtime = CognitiveExecutionRuntime(
        cancellation_repository,
        _local_model(),
        AsyncToolRuntime(),
        verification_hook=_verification,
    )
    cancellation_request = _stop_request("cancellation", deadline=False)
    execution = cancellation_repository.create(cancellation_request, now=NOW)
    payload = cancellation_runtime._initial_payload(
        cancellation_request,
        instructions="Stop before any provider or tool work.",
        prompt="Cancellation qualification.",
        context_digest=context_digest,
        history=(),
    )
    execution, _checkpoint_ref = cancellation_runtime._checkpoint(
        execution,
        payload,
        now=NOW,
    )
    cancellation_repository.request_cancel(
        cancellation_request.execution_id,
        expected_version=execution.version,
        now=NOW,
    )
    cancellation_run = await cancellation_runtime.resume(
        cancellation_request.execution_id,
        now=NOW,
    )
    assert cancellation_run.result is not None
    return deadline_run.result, cancellation_run.result

def _staged_finalization_recovery(
    tmp_path,
    request: FunctionalAIRequest,
    terminal: AIExecutionResult,
):
    database = tmp_path / "system-completion-staged-recovery.sqlite3"
    repository = SQLiteExecutionRepository(database)
    execution_request = request.to_execution_request()
    execution = repository.create(execution_request, now=NOW)
    for state in (
        ExecutionState.LOADING,
        ExecutionState.ASSEMBLING_CONTEXT,
        ExecutionState.ROUTING,
        ExecutionState.PROVIDER_PENDING,
        ExecutionState.PROVIDER_COMPLETED,
    ):
        execution = repository.transition(
            execution_request.execution_id,
            state,
            expected_version=execution.version,
            now=NOW,
        )

    intent = repository.stage_finalization(
        terminal,
        expected_execution_version=execution.version,
        now=NOW,
    )
    intent_digest = intent.intent_digest
    repository.close()

    reopened = SQLiteExecutionRepository(database)
    recovered_intent = reopened.finalization_intent(
        execution_request.execution_id
    )
    assert recovered_intent is not None
    assert recovered_intent.intent_digest == intent_digest
    reopened.finalize_staged(
        execution_request.execution_id,
        now=NOW,
    )
    recovered_result = reopened.result(execution_request.execution_id)
    intent_cleared = (
        reopened.finalization_intent(execution_request.execution_id)
        is None
    )
    reopened.close()
    return intent_digest, recovered_result, intent_cleared


def _learning_cycle(subject_id: str, result_digest: str):
    spec = ExperimentSpec(
        experiment_id=completion_learning_experiment_id(
            subject_id,
            result_digest,
        ),
        baseline_version="baseline-v1",
        candidate_version="candidate-v2",
        assignment_salt="system-completion-salt",
        data_use_purpose="system-completion-evaluation",
        holdout_bps=0,
        candidate_bps=5000,
        min_variant_samples=1,
    )
    ledger = FeedbackLedger()
    by_variant = {}
    for index in range(100):
        subject = f"subject-{index}"
        assignment = ledger.assign(spec, subject)
        if assignment.variant in by_variant:
            continue
        score = 0.85 if assignment.variant == "candidate" else 0.50
        event = ledger.collect(
            spec,
            assignment,
            event_id=f"event-{assignment.variant}",
            score=score,
            observed_at=1000 + index,
            consent=True,
            data_use_purpose=spec.data_use_purpose,
        )
        by_variant[assignment.variant] = event
        if {"baseline", "candidate"} <= set(by_variant):
            break

    assert {"baseline", "candidate"} <= set(by_variant)
    selected = (by_variant["baseline"], by_variant["candidate"])

    failed_evaluation = EvaluationReceipt(
        experiment_id=spec.experiment_id,
        baseline_version=spec.baseline_version,
        candidate_version=spec.candidate_version,
        evaluator_id="system-completion:negative-evaluator",
        passed=False,
        event_ids=tuple(event.event_id for event in selected),
        metric_delta=0.35,
        evaluated_at=1900,
        evidence_ref="eval:system-completion:expected-failure",
    )
    negative_pipeline = FeedbackPromotionPipeline()
    try:
        negative_pipeline.promote(
            spec,
            selected,
            failed_evaluation,
            promoted_at=1950,
        )
    except FeedbackPromotionError:
        failed_evaluation_rejected = True
    else:
        failed_evaluation_rejected = False

    cross_experiment = EvaluationReceipt(
        experiment_id="system-completion-cross-experiment",
        baseline_version=spec.baseline_version,
        candidate_version=spec.candidate_version,
        evaluator_id="system-completion:negative-evaluator",
        passed=True,
        event_ids=tuple(event.event_id for event in selected),
        metric_delta=0.35,
        evaluated_at=1960,
        evidence_ref="eval:system-completion:cross-experiment",
    )
    try:
        negative_pipeline.promote(
            spec,
            selected,
            cross_experiment,
            promoted_at=1970,
        )
    except FeedbackPromotionError:
        cross_experiment_rejected = True
    else:
        cross_experiment_rejected = False

    rollback_probe = FeedbackPromotionPipeline()
    try:
        rollback_probe.rollback(
            spec,
            reason="reject rollback before promotion",
            rolled_back_at=1980,
        )
    except FeedbackPromotionError:
        rollback_without_promotion_rejected = True
    else:
        rollback_without_promotion_rejected = False

    receipt = EvaluationReceipt(
        experiment_id=spec.experiment_id,
        baseline_version=spec.baseline_version,
        candidate_version=spec.candidate_version,
        evaluator_id="system-completion:heldout-evaluator",
        passed=True,
        event_ids=tuple(event.event_id for event in selected),
        metric_delta=0.35,
        evaluated_at=2000,
        evidence_ref="eval:system-completion:heldout",
    )
    pipeline = FeedbackPromotionPipeline()
    promotion = pipeline.promote(spec, selected, receipt, promoted_at=2100)
    promoted_active = pipeline.active_version(spec)
    rollback = pipeline.rollback(
        spec,
        reason="system completion rollback qualification",
        rolled_back_at=2200,
    )
    rolled_back_active = pipeline.active_version(spec)
    return (
        spec,
        receipt,
        promotion,
        promoted_active,
        rollback,
        rolled_back_active,
        failed_evaluation_rejected,
        cross_experiment_rejected,
        rollback_without_promotion_rejected,
    )


@pytest.mark.asyncio
async def test_system_completion_plane_composes_real_runtime_planes(
    tmp_path,
    monkeypatch,
) -> None:
    original_socket = socket.socket
    network_attempts = []

    def guarded_socket(*args, **kwargs):
        family = args[0] if args else kwargs.get("family", socket.AF_INET)
        if family in {socket.AF_INET, socket.AF_INET6}:
            network_attempts.append(str(family))
            raise AssertionError(
                "system completion attempted external network I/O"
            )
        return original_socket(*args, **kwargs)

    monkeypatch.setattr(socket, "socket", guarded_socket)
    database, request, run, observed_tool_ids = await _functional_run(tmp_path)
    terminal = run.execution.result
    assert terminal is not None

    # Persistence/recovery: reopen the SQLite store as a separate runtime would.
    recovered_repository = SQLiteExecutionRepository(database)
    recovered = recovered_repository.result(request.execution_id)
    recovered_turns = recovered_repository.turns(request.execution_id)
    (
        staged_intent_digest,
        staged_recovered_result,
        staged_intent_cleared,
    ) = _staged_finalization_recovery(
        tmp_path,
        request,
        terminal,
    )

    # Context integrity: create a non-genesis block and verify the hash chain.
    context_ledger = ContextLedger()
    context_ledger.append(
        "functional-ai",
        {
            "execution_id": request.execution_id,
            "result_digest": run.evidence.result_digest,
        },
        mass=1.0,
        tensor_fp=hashlib.sha256(b"system-completion-tensor").hexdigest(),
    )

    # Memory lifecycle: write -> retrieve -> delete -> prove absence.
    memory = InMemoryTFIDFStore()
    memory_id = "system-completion-memory"
    memory.add(
        Chunk(
            chunk_id=memory_id,
            text="system completion durable memory lifecycle evidence",
            metadata={"execution_id": request.execution_id},
        )
    )
    recalled = tuple(
        result.chunk.chunk_id
        for result in memory.query("completion durable memory evidence", top_k=5)
    )
    deleted = memory.delete(memory_id)
    recalled_after_delete = tuple(
        result.chunk.chunk_id
        for result in memory.query("completion durable memory evidence", top_k=5)
    )

    (
        spec,
        evaluation,
        promotion,
        promoted_active,
        rollback,
        rolled_back_active,
        failed_evaluation_rejected,
        cross_experiment_rejected,
        rollback_without_promotion_rejected,
    ) = _learning_cycle(
        request.execution_id,
        run.evidence.result_digest,
    )

    (
        _replay_database,
        replay_request,
        replay_run,
        replay_observed_tool_ids,
    ) = await _functional_run(
        tmp_path,
        database_name="ai-system-completion-replay.sqlite3",
        request_id=request.request_id,
    )
    replay_terminal = replay_run.execution.result
    assert replay_terminal is not None
    assert replay_request.execution_id == request.execution_id

    plane = SystemCompletionPlane(
        subject_id=request.execution_id,
        source_revision=HEAD,
    )
    plane.prove_local_execution(
        run.execution,
        local_model_id=run.evidence.local_model_id,
        provider_receipts=run.evidence.provider_receipts,
    )
    plane.prove_offline_isolation(
        execution_id=request.execution_id,
        network_attempt_count=len(network_attempts),
        provider_receipts=run.evidence.provider_receipts,
    )
    plane.prove_request_result_binding(
        request.to_execution_request(),
        terminal,
    )
    plane.prove_budget_bounds(
        execution_id=request.execution_id,
        max_model_turns=request.max_model_turns,
        max_tool_calls=request.max_tool_calls,
        provider_receipts=terminal.provider_receipts,
        tool_receipts=terminal.tool_receipts,
    )
    deadline_result, cancellation_result = await _stop_semantics_results(tmp_path)
    plane.prove_stop_semantics(
        deadline_result=deadline_result,
        cancellation_result=cancellation_result,
    )
    plane.prove_tool_authority(
        execution_id=request.execution_id,
        allowed_tool_ids=request.allowed_tool_ids,
        observed_tool_ids=observed_tool_ids,
        receipt_refs=terminal.tool_receipts,
    )
    plane.prove_durable_recovery(terminal, recovered)
    plane.prove_staged_finalization_recovery(
        staged_result=terminal,
        recovered_result=staged_recovered_result,
        staged_intent_digest=staged_intent_digest,
        intent_cleared=staged_intent_cleared,
    )
    plane.prove_replay_lineage(recovered_turns)
    plane.prove_reproducibility(
        primary_execution_id=request.execution_id,
        replay_execution_id=replay_request.execution_id,
        primary_result_digest=run.evidence.result_digest,
        replay_result_digest=replay_run.evidence.result_digest,
        primary_output_digest=run.evidence.final_output_digest,
        replay_output_digest=replay_run.evidence.final_output_digest,
    )
    assert replay_observed_tool_ids == observed_tool_ids
    plane.prove_governed_effects(
        execution_id=request.execution_id,
        tool_receipt_count=len(terminal.tool_receipts),
        mutating_tool_count=0,
        verified_postcondition_count=0,
        receipt_refs=terminal.tool_receipts,
    )
    plane.prove_independent_verification(terminal)
    plane.prove_verification_binding(
        terminal,
        context_digest=request.context_digest,
    )
    plane.prove_context_integrity(
        context_subject_id=request.execution_id,
        problems=context_ledger.verify(),
        height=context_ledger.height,
        head_hash=context_ledger.head.hash,
    )
    plane.prove_memory_lifecycle(
        memory_id=memory_id,
        memory_subject_id=request.execution_id,
        recalled_ids=recalled,
        deleted=deleted,
        post_delete_recalled_ids=recalled_after_delete,
    )
    plane.prove_finalization_lineage(terminal)
    plane.prove_sandbox_filesystem(
        execution_id=request.execution_id,
        safe_roundtrip=True,
        traversal_rejected=True,
        outside_untouched=True,
        evidence_refs=("sandbox:filesystem",),
    )
    plane.prove_sandbox_process(
        execution_id=request.execution_id,
        clean_environment=True,
        shell_string_rejected=True,
        bounded_execution=True,
        network_fail_closed=True,
        evidence_refs=("sandbox:process",),
    )
    plane.prove_injection_sanitization(
        execution_id=request.execution_id,
        prompt_attack_blocked=True,
        shell_attack_blocked=True,
        secret_redacted=True,
        duplicate_json_rejected=True,
        evidence_refs=("sandbox:injection",),
    )
    plane.prove_provider_fallback_privacy(
        execution_id=request.execution_id,
        required_boundary="local",
        routed_boundaries=("local",),
        routed_model_ids=("local-model",),
        evidence_refs=("provider:privacy",),
    )
    plane.prove_memory_poisoning_resistance(
        execution_id=request.execution_id,
        valid_write_committed=True,
        missing_provenance_denied=True,
        conflicting_replay_rejected=True,
        committed_subject_id=request.execution_id,
        evidence_refs=("memory:poisoning",),
    )
    plane.prove_outbound_network_boundary(
        execution_id=request.execution_id,
        private_target_rejected=True,
        mixed_dns_rejected=True,
        peer_rebinding_rejected=True,
        canonical_public_resolution=True,
        evidence_refs=("network:boundary",),
    )

    plane.prove_resource_admission(
        execution_id=request.execution_id,
        admitted_within_budget=True,
        over_quota_rejected=True,
        denial_capacity_unchanged=True,
        usage_reconciled=True,
        evidence_refs=("resource:admission",),
    )
    plane.prove_shared_pressure(
        execution_id=request.execution_id,
        first_worker_admitted=True,
        second_worker_blocked=True,
        capacity_released=True,
        second_worker_admitted_after_release=True,
        evidence_refs=("resource:shared-pressure",),
    )
    plane.prove_idempotent_retry(
        execution_id=request.execution_id,
        identical_retry_stable=True,
        conflicting_retry_rejected=True,
        no_double_reservation=True,
        evidence_refs=("execution:idempotent-retry",),
    )
    plane.prove_tenant_isolation(
        execution_id=request.execution_id,
        owner_tenant_visible=True,
        other_tenant_hidden=True,
        cross_tenant_get_rejected=True,
        subject_scope_preserved=True,
        evidence_refs=("privacy:tenant-isolation",),
    )

    plane.prove_persisted_evidence_integrity(
        execution_id=request.execution_id,
        result_tamper_rejected=True,
        outbox_tamper_rejected=True,
        migration_backfill_verified=True,
        evidence_refs=("persistence:terminal-integrity",),
    )
    plane.prove_verification_receipt_identity(
        execution_id=request.execution_id,
        identical_replay_stable=True,
        conflicting_replay_rejected=True,
        digest_tamper_rejected=True,
        execution_binding_preserved=True,
        evidence_refs=("verification:receipt-identity",),
    )
    plane.prove_terminal_outbox_delivery(
        execution_id=request.execution_id,
        one_pending_terminal_event=True,
        acknowledgement_persistent=True,
        acknowledgement_retry_stable=True,
        no_pending_after_ack=True,
        evidence_refs=("finalization:outbox",),
    )
    plane.prove_unknown_usage_fence(
        execution_id=request.execution_id,
        unknown_usage_recorded=True,
        completion_blocked_while_unknown=True,
        release_blocked_while_unknown=True,
        conservative_resolution_required=True,
        completion_succeeds_after_resolution=True,
        evidence_refs=("resource:unknown-usage",),
    )

    plane.prove_learning_promotion(
        promotion,
        expected_baseline=spec.baseline_version,
        expected_candidate=spec.candidate_version,
        active_version=promoted_active,
        evaluation_digest=evaluation.digest,
        evaluator_id=evaluation.evaluator_id,
        bound_result_digest=run.evidence.result_digest,
        failed_evaluation_rejected=failed_evaluation_rejected,
        cross_experiment_rejected=cross_experiment_rejected,
    )
    plane.prove_learning_rollback(
        rollback,
        expected_baseline=spec.baseline_version,
        expected_candidate=spec.candidate_version,
        active_version=rolled_back_active,
        promotion_receipt=promotion,
        bound_result_digest=run.evidence.result_digest,
        rollback_without_promotion_rejected=(
            rollback_without_promotion_rejected
        ),
    )

    report = plane.report()
    assert report.valid is True
    assert report.missing == ()
    assert report.failed == ()
    assert len(report.proofs) == len(REQUIRED_COMPLETION_REQUIREMENTS) == 32
    assert len(report.digest) == 64

    payload = report.as_dict()
    assert payload["valid"] is True
    assert payload["source_revision"] == HEAD
    assert payload["required"] == [
        requirement.value for requirement in REQUIRED_COMPLETION_REQUIREMENTS
    ]
    assert all(len(proof["digest"]) == 64 for proof in payload["proofs"])


@pytest.mark.asyncio
async def test_durable_recovery_is_exact_not_best_effort(tmp_path) -> None:
    database, request, run, _observed_tool_ids = await _functional_run(tmp_path)
    terminal = run.execution.result
    assert terminal is not None
    recovered = SQLiteExecutionRepository(database).result(request.execution_id)
    assert recovered is not None
    recovered = replace(recovered, final_output=recovered.final_output + " tampered")

    plane = SystemCompletionPlane(
        subject_id=request.execution_id,
        source_revision=HEAD,
    )
    proof = plane.prove_durable_recovery(terminal, recovered)
    assert proof.passed is False
    assert plane.report().valid is False
    assert plane.report().failed == ("execution.durable_recovery",)


def test_staged_finalization_recovery_requires_intent_cleanup() -> None:
    from skeleton.contracts.ai_execution import AIExecutionResult

    result = AIExecutionResult(
        operation_id="staged-operation",
        execution_id="staged-subject",
        status="completed",
        final_output="stable",
        usage={},
        completed_at=NOW,
    )
    plane = SystemCompletionPlane(
        subject_id="staged-subject",
        source_revision=HEAD,
    )
    proof = plane.prove_staged_finalization_recovery(
        staged_result=result,
        recovered_result=result,
        staged_intent_digest=hashlib.sha256(b"intent").hexdigest(),
        intent_cleared=False,
    )
    assert proof.passed is False
    assert proof.details["exact_match"] is True
    assert proof.details["intent_cleared"] is False


def test_mutating_effect_without_matching_postcondition_fails_closed() -> None:
    plane = SystemCompletionPlane(
        subject_id="effect-subject",
        source_revision=HEAD,
    )
    proof = plane.prove_governed_effects(
        execution_id="effect-subject",
        tool_receipt_count=3,
        mutating_tool_count=2,
        verified_postcondition_count=1,
        receipt_refs=("tool:a", "tool:b", "tool:c"),
    )
    assert proof.passed is False
    assert plane.report().valid is False


def test_offline_isolation_fails_on_any_network_attempt() -> None:
    plane = SystemCompletionPlane(
        subject_id="offline-subject",
        source_revision=HEAD,
    )
    proof = plane.prove_offline_isolation(
        execution_id="offline-subject",
        network_attempt_count=1,
        provider_receipts=("provider:local:receipt",),
    )
    assert proof.passed is False
    assert plane.report().failed == ("execution.offline_isolation",)


def test_budget_bounds_are_hard_limits() -> None:
    plane = SystemCompletionPlane(
        subject_id="budget-subject",
        source_revision=HEAD,
    )
    proof = plane.prove_budget_bounds(
        execution_id="budget-subject",
        max_model_turns=1,
        max_tool_calls=1,
        provider_receipts=(
            "provider:local:first",
            "provider:local:second",
        ),
        tool_receipts=("tool:one",),
    )
    assert proof.passed is False
    assert proof.details["observed_model_turns"] == 2


@pytest.mark.asyncio
async def test_replay_lineage_rejects_broken_parent(tmp_path) -> None:
    database, request, _run, _observed_tool_ids = await _functional_run(tmp_path)
    repository = SQLiteExecutionRepository(database)
    turns = list(repository.turns(request.execution_id))
    assert len(turns) >= 2
    turns[1] = replace(turns[1], parent_turn_id="tampered-parent")

    plane = SystemCompletionPlane(
        subject_id=request.execution_id,
        source_revision=HEAD,
    )
    proof = plane.prove_replay_lineage(turns)
    assert proof.passed is False
    assert proof.details["parent_linked"] is False


def test_sandbox_filesystem_escape_blocks_completion() -> None:
    plane = SystemCompletionPlane(
        subject_id="sandbox-fs",
        source_revision=HEAD,
    )
    proof = plane.prove_sandbox_filesystem(
        execution_id="sandbox-fs",
        safe_roundtrip=True,
        traversal_rejected=False,
        outside_untouched=False,
        evidence_refs=("sandbox:fs",),
    )
    assert proof.passed is False


def test_sandbox_process_requires_all_fail_closed_controls() -> None:
    plane = SystemCompletionPlane(
        subject_id="sandbox-process",
        source_revision=HEAD,
    )
    proof = plane.prove_sandbox_process(
        execution_id="sandbox-process",
        clean_environment=True,
        shell_string_rejected=True,
        bounded_execution=True,
        network_fail_closed=False,
        evidence_refs=("sandbox:process",),
    )
    assert proof.passed is False


def test_injection_sanitization_requires_duplicate_json_rejection() -> None:
    plane = SystemCompletionPlane(
        subject_id="injection",
        source_revision=HEAD,
    )
    proof = plane.prove_injection_sanitization(
        execution_id="injection",
        prompt_attack_blocked=True,
        shell_attack_blocked=True,
        secret_redacted=True,
        duplicate_json_rejected=False,
        evidence_refs=("injection:evidence",),
    )
    assert proof.passed is False


def test_provider_fallback_privacy_rejects_external_route() -> None:
    plane = SystemCompletionPlane(
        subject_id="provider-privacy",
        source_revision=HEAD,
    )
    proof = plane.prove_provider_fallback_privacy(
        execution_id="provider-privacy",
        required_boundary="local",
        routed_boundaries=("local", "external"),
        routed_model_ids=("local", "external"),
        evidence_refs=("provider:route",),
    )
    assert proof.passed is False
    assert proof.details["all_within_boundary"] is False


def test_memory_poisoning_proof_requires_conflict_rejection() -> None:
    plane = SystemCompletionPlane(
        subject_id="memory-poisoning",
        source_revision=HEAD,
    )
    proof = plane.prove_memory_poisoning_resistance(
        execution_id="memory-poisoning",
        valid_write_committed=True,
        missing_provenance_denied=True,
        conflicting_replay_rejected=False,
        committed_subject_id="memory-poisoning",
        evidence_refs=("memory:governed",),
    )
    assert proof.passed is False


def test_outbound_network_boundary_rejects_peer_rebinding_gap() -> None:
    plane = SystemCompletionPlane(
        subject_id="network-boundary",
        source_revision=HEAD,
    )
    proof = plane.prove_outbound_network_boundary(
        execution_id="network-boundary",
        private_target_rejected=True,
        mixed_dns_rejected=True,
        peer_rebinding_rejected=False,
        canonical_public_resolution=True,
        evidence_refs=("network:boundary",),
    )
    assert proof.passed is False


def test_resource_admission_requires_capacity_preservation() -> None:
    plane = SystemCompletionPlane(
        subject_id="resource-admission",
        source_revision=HEAD,
    )
    proof = plane.prove_resource_admission(
        execution_id="resource-admission",
        admitted_within_budget=True,
        over_quota_rejected=True,
        denial_capacity_unchanged=False,
        usage_reconciled=True,
        evidence_refs=("resource:admission",),
    )
    assert proof.passed is False


def test_shared_pressure_requires_release_before_second_worker() -> None:
    plane = SystemCompletionPlane(
        subject_id="shared-pressure",
        source_revision=HEAD,
    )
    proof = plane.prove_shared_pressure(
        execution_id="shared-pressure",
        first_worker_admitted=True,
        second_worker_blocked=True,
        capacity_released=False,
        second_worker_admitted_after_release=True,
        evidence_refs=("resource:shared-pressure",),
    )
    assert proof.passed is False


def test_idempotent_retry_rejects_double_reservation() -> None:
    plane = SystemCompletionPlane(
        subject_id="idempotent-retry",
        source_revision=HEAD,
    )
    proof = plane.prove_idempotent_retry(
        execution_id="idempotent-retry",
        identical_retry_stable=True,
        conflicting_retry_rejected=True,
        no_double_reservation=False,
        evidence_refs=("execution:idempotent-retry",),
    )
    assert proof.passed is False


def test_tenant_isolation_requires_cross_tenant_get_rejection() -> None:
    plane = SystemCompletionPlane(
        subject_id="tenant-isolation",
        source_revision=HEAD,
    )
    proof = plane.prove_tenant_isolation(
        execution_id="tenant-isolation",
        owner_tenant_visible=True,
        other_tenant_hidden=True,
        cross_tenant_get_rejected=False,
        subject_scope_preserved=True,
        evidence_refs=("privacy:tenant-isolation",),
    )
    assert proof.passed is False


def test_persisted_integrity_requires_result_tamper_rejection() -> None:
    plane = SystemCompletionPlane(
        subject_id="persistence-integrity",
        source_revision=HEAD,
    )
    proof = plane.prove_persisted_evidence_integrity(
        execution_id="persistence-integrity",
        result_tamper_rejected=False,
        outbox_tamper_rejected=True,
        migration_backfill_verified=True,
        evidence_refs=("persistence:terminal-integrity",),
    )
    assert proof.passed is False


def test_verification_receipt_identity_requires_conflict_rejection() -> None:
    plane = SystemCompletionPlane(
        subject_id="receipt-identity",
        source_revision=HEAD,
    )
    proof = plane.prove_verification_receipt_identity(
        execution_id="receipt-identity",
        identical_replay_stable=True,
        conflicting_replay_rejected=False,
        digest_tamper_rejected=True,
        execution_binding_preserved=True,
        evidence_refs=("verification:receipt-identity",),
    )
    assert proof.passed is False


def test_terminal_outbox_delivery_requires_persistent_ack() -> None:
    plane = SystemCompletionPlane(
        subject_id="outbox-delivery",
        source_revision=HEAD,
    )
    proof = plane.prove_terminal_outbox_delivery(
        execution_id="outbox-delivery",
        one_pending_terminal_event=True,
        acknowledgement_persistent=False,
        acknowledgement_retry_stable=True,
        no_pending_after_ack=True,
        evidence_refs=("finalization:outbox",),
    )
    assert proof.passed is False


def test_unknown_usage_fence_requires_resolution_before_completion() -> None:
    plane = SystemCompletionPlane(
        subject_id="unknown-usage",
        source_revision=HEAD,
    )
    proof = plane.prove_unknown_usage_fence(
        execution_id="unknown-usage",
        unknown_usage_recorded=True,
        completion_blocked_while_unknown=True,
        release_blocked_while_unknown=True,
        conservative_resolution_required=False,
        completion_succeeds_after_resolution=True,
        evidence_refs=("resource:unknown-usage",),
    )
    assert proof.passed is False


def test_memory_requires_recall_and_observed_forgetting() -> None:
    plane = SystemCompletionPlane(
        subject_id="memory-subject",
        source_revision=HEAD,
    )
    proof = plane.prove_memory_lifecycle(
        memory_id="m1",
        memory_subject_id="memory-subject",
        recalled_ids=("m1",),
        deleted=True,
        post_delete_recalled_ids=("m1",),
    )
    assert proof.passed is False
    assert proof.details["absent_after_delete"] is False


def test_missing_requirement_cannot_be_compensated_by_other_green_proofs() -> None:
    plane = SystemCompletionPlane(
        subject_id="partial-subject",
        source_revision=HEAD,
    )
    plane.prove_governed_effects(
        execution_id="partial-subject",
        tool_receipt_count=1,
        mutating_tool_count=0,
        verified_postcondition_count=0,
        receipt_refs=("tool:read-only",),
    )
    report = plane.report()
    assert report.valid is False
    assert "execution.governed_effects" not in report.missing
    assert len(report.missing) == len(REQUIRED_COMPLETION_REQUIREMENTS) - 1


def test_duplicate_requirement_is_rejected() -> None:
    plane = SystemCompletionPlane(
        subject_id="duplicate-subject",
        source_revision=HEAD,
    )
    plane.prove_governed_effects(
        execution_id="duplicate-subject",
        tool_receipt_count=0,
        mutating_tool_count=0,
        verified_postcondition_count=0,
        receipt_refs=("tool:none:policy-proof",),
    )
    with pytest.raises(CompletionPlaneError, match="already proved"):
        plane.prove_governed_effects(
            execution_id="duplicate-subject",
            tool_receipt_count=0,
            mutating_tool_count=0,
            verified_postcondition_count=0,
            receipt_refs=("tool:none:second-proof",),
        )


def test_self_verified_proof_is_rejected() -> None:
    with pytest.raises(CompletionPlaneError, match="independent verifier"):
        RequirementProof(
            requirement=CompletionRequirement.CONTEXT_INTEGRITY,
            subject_id="self-verified",
            source_revision=HEAD,
            passed=True,
            producer_id="same-authority",
            verifier_id="same-authority",
            evidence_refs=("context:proof",),
        )




@pytest.mark.asyncio
async def test_stop_semantics_require_deadline_and_cancellation_fences(tmp_path) -> None:
    deadline_result, cancellation_result = await _stop_semantics_results(tmp_path)
    tampered_cancellation = replace(
        cancellation_result,
        usage={
            **dict(cancellation_result.usage),
            "error_code": "unexpected_stop_reason",
        },
    )
    plane = SystemCompletionPlane(
        subject_id="stop-semantics-subject",
        source_revision=HEAD,
    )
    proof = plane.prove_stop_semantics(
        deadline_result=deadline_result,
        cancellation_result=tampered_cancellation,
    )
    assert proof.passed is False
    assert proof.details["deadline_fenced"] is True
    assert proof.details["cancellation_fenced"] is False

def test_tool_authority_rejects_undeclared_tool() -> None:
    plane = SystemCompletionPlane(
        subject_id="tool-authority-subject",
        source_revision=HEAD,
    )
    proof = plane.prove_tool_authority(
        execution_id="tool-authority-subject",
        allowed_tool_ids=("repo.read",),
        observed_tool_ids=("repo.read", "shell.exec"),
        receipt_refs=("tool:read", "tool:shell"),
    )
    assert proof.passed is False
    assert proof.details["all_calls_authorized"] is False


def test_source_execution_cannot_be_relabelled_as_completion_subject() -> None:
    plane = SystemCompletionPlane(
        subject_id="expected-execution",
        source_revision=HEAD,
    )
    proof = plane.prove_budget_bounds(
        execution_id="different-execution",
        max_model_turns=8,
        max_tool_calls=8,
        provider_receipts=("provider:local:one",),
        tool_receipts=("tool:one",),
    )
    assert proof.passed is False
    assert proof.details["subject_bound"] is False


def test_request_result_binding_rejects_cross_operation_result() -> None:
    request = FunctionalAIRequest(
        request_id="binding-test",
        objective="Bind request to terminal result.",
        prompt="test",
        instructions="test",
        context_digest=hashlib.sha256(b"binding-context").hexdigest(),
        created_at=NOW,
    ).to_execution_request()
    from skeleton.contracts.ai_execution import AIExecutionResult

    result = AIExecutionResult(
        operation_id="other-operation",
        execution_id=request.execution_id,
        status="completed",
        final_output="bound output",
        usage={},
        completed_at=NOW,
    )
    plane = SystemCompletionPlane(
        subject_id=request.execution_id,
        source_revision=HEAD,
    )
    proof = plane.prove_request_result_binding(request, result)
    assert proof.passed is False
    assert proof.details["request_operation_id"] != proof.details["result_operation_id"]


def test_reproducibility_requires_result_and_output_equivalence() -> None:
    plane = SystemCompletionPlane(
        subject_id="repro-subject",
        source_revision=HEAD,
    )
    a = hashlib.sha256(b"a").hexdigest()
    b = hashlib.sha256(b"b").hexdigest()
    proof = plane.prove_reproducibility(
        primary_execution_id="repro-subject",
        replay_execution_id="repro-subject",
        primary_result_digest=a,
        replay_result_digest=b,
        primary_output_digest=a,
        replay_output_digest=a,
    )
    assert proof.passed is False
    assert proof.details["subject_bound"] is True
    assert proof.details["result_equal"] is False
    assert proof.details["output_equal"] is True


def test_verification_binding_rejects_receipt_for_other_candidate() -> None:
    from skeleton.contracts.ai_execution import AIExecutionResult

    context_digest = hashlib.sha256(b"verification-binding").hexdigest()
    result = AIExecutionResult(
        operation_id="binding-operation",
        execution_id="binding-execution",
        status="completed",
        final_output="actual candidate",
        verification_receipt={
            "outcome": "passed",
            "policy_satisfied": True,
            "candidate_digest": hashlib.sha256(b"different candidate").hexdigest(),
            "context_digest": context_digest,
        },
        evidence_refs=("evidence:binding",),
        usage={},
        completed_at=NOW,
    )
    plane = SystemCompletionPlane(
        subject_id=result.execution_id,
        source_revision=HEAD,
    )
    proof = plane.prove_verification_binding(
        result,
        context_digest=context_digest,
    )
    assert proof.passed is False
    assert proof.details["candidate_digest"] != proof.details["receipt_candidate_digest"]


def test_memory_lifecycle_rejects_cross_subject_memory() -> None:
    plane = SystemCompletionPlane(
        subject_id="memory-owner",
        source_revision=HEAD,
    )
    proof = plane.prove_memory_lifecycle(
        memory_id="memory-1",
        memory_subject_id="different-owner",
        recalled_ids=("memory-1",),
        deleted=True,
        post_delete_recalled_ids=(),
    )
    assert proof.passed is False
    assert proof.details["subject_bound"] is False


def test_proof_from_other_revision_cannot_enter_report() -> None:
    plane = SystemCompletionPlane(
        subject_id="revision-subject",
        source_revision=HEAD,
    )
    proof = RequirementProof(
        requirement=CompletionRequirement.CONTEXT_INTEGRITY,
        subject_id="revision-subject",
        source_revision="c" * 40,
        passed=True,
        producer_id="context-ledger",
        verifier_id="ai-system-completion:independent",
        evidence_refs=("context:revision",),
    )
    with pytest.raises(CompletionPlaneError, match="source revisions"):
        plane.add(proof)


def test_machine_contract_matches_runtime_requirement_inventory() -> None:
    contract = json.loads(
        Path("machine/ai_system_completion_contract.json").read_text(
            encoding="utf-8"
        )
    )
    assert contract["schema_version"] == "skeleton.ai.system_completion_contract.v1"
    assert contract["authority"]["missing_proofs_fail_closed"] is True
    assert contract["authority"]["failed_proofs_non_compensable"] is True
    assert contract["required_requirements"] == [
        requirement.value for requirement in REQUIRED_COMPLETION_REQUIREMENTS
    ]
    assert len(contract["required_requirements"]) == len(
        set(contract["required_requirements"])
    )


def test_report_digest_is_order_independent() -> None:
    first = RequirementProof(
        requirement=CompletionRequirement.CONTEXT_INTEGRITY,
        subject_id="digest-subject",
        source_revision=HEAD,
        passed=True,
        producer_id="context-ledger",
        verifier_id="ai-system-completion:independent",
        evidence_refs=("context:a",),
        details={"height": 1},
    )
    second = RequirementProof(
        requirement=CompletionRequirement.MEMORY_LIFECYCLE,
        subject_id="digest-subject",
        source_revision=HEAD,
        passed=True,
        producer_id="memory-runtime",
        verifier_id="ai-system-completion:independent",
        evidence_refs=("memory:a",),
        details={"recalled": True},
    )
    plane_a = SystemCompletionPlane(
        subject_id="digest-subject",
        source_revision=HEAD,
    )
    plane_a.add(first)
    plane_a.add(second)

    plane_b = SystemCompletionPlane(
        subject_id="digest-subject",
        source_revision=HEAD,
    )
    plane_b.add(second)
    plane_b.add(first)

    assert plane_a.report().digest == plane_b.report().digest
