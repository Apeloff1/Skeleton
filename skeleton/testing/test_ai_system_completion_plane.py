from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import socket
import threading

import pytest

from skeleton.ai.learning.promotion import (
    EvaluationReceipt,
    ExperimentSpec,
    FeedbackLedger,
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
)
from skeleton.intelligence.execution_runtime import (
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


async def _functional_run(tmp_path):
    database = tmp_path / "ai-system-completion.sqlite3"
    repository = SQLiteExecutionRepository(database)
    tools = AsyncToolRuntime()

    async def read_handler(_request):
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
        request_id="ai-system-completion-e2e",
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
    return database, request, await runtime.execute(request)


def _learning_cycle():
    spec = ExperimentSpec(
        experiment_id="system-completion-learning",
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
    return spec, promotion, promoted_active, rollback, rolled_back_active


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
    database, request, run = await _functional_run(tmp_path)
    terminal = run.execution.result
    assert terminal is not None

    # Persistence/recovery: reopen the SQLite store as a separate runtime would.
    recovered_repository = SQLiteExecutionRepository(database)
    recovered = recovered_repository.result(request.execution_id)
    recovered_turns = recovered_repository.turns(request.execution_id)

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

    spec, promotion, promoted_active, rollback, rolled_back_active = _learning_cycle()

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
        network_attempt_count=len(network_attempts),
        provider_receipts=run.evidence.provider_receipts,
    )
    plane.prove_budget_bounds(
        max_model_turns=request.max_model_turns,
        max_tool_calls=request.max_tool_calls,
        provider_receipts=terminal.provider_receipts,
        tool_receipts=terminal.tool_receipts,
    )
    plane.prove_durable_recovery(terminal, recovered)
    plane.prove_replay_lineage(recovered_turns)
    plane.prove_governed_effects(
        tool_receipt_count=len(terminal.tool_receipts),
        mutating_tool_count=0,
        verified_postcondition_count=0,
        receipt_refs=terminal.tool_receipts,
    )
    plane.prove_independent_verification(terminal)
    plane.prove_context_integrity(
        problems=context_ledger.verify(),
        height=context_ledger.height,
        head_hash=context_ledger.head.hash,
    )
    plane.prove_memory_lifecycle(
        memory_id=memory_id,
        recalled_ids=recalled,
        deleted=deleted,
        post_delete_recalled_ids=recalled_after_delete,
    )
    plane.prove_finalization_lineage(terminal)
    plane.prove_learning_promotion(
        promotion,
        expected_baseline=spec.baseline_version,
        expected_candidate=spec.candidate_version,
        active_version=promoted_active,
    )
    plane.prove_learning_rollback(
        rollback,
        expected_baseline=spec.baseline_version,
        expected_candidate=spec.candidate_version,
        active_version=rolled_back_active,
    )

    report = plane.report()
    assert report.valid is True
    assert report.missing == ()
    assert report.failed == ()
    assert len(report.proofs) == len(REQUIRED_COMPLETION_REQUIREMENTS) == 12
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
    database, request, run = await _functional_run(tmp_path)
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


def test_mutating_effect_without_matching_postcondition_fails_closed() -> None:
    plane = SystemCompletionPlane(
        subject_id="effect-subject",
        source_revision=HEAD,
    )
    proof = plane.prove_governed_effects(
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
    database, request, _run = await _functional_run(tmp_path)
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


def test_memory_requires_recall_and_observed_forgetting() -> None:
    plane = SystemCompletionPlane(
        subject_id="memory-subject",
        source_revision=HEAD,
    )
    proof = plane.prove_memory_lifecycle(
        memory_id="m1",
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
        tool_receipt_count=0,
        mutating_tool_count=0,
        verified_postcondition_count=0,
        receipt_refs=("tool:none:policy-proof",),
    )
    with pytest.raises(CompletionPlaneError, match="already proved"):
        plane.prove_governed_effects(
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
            passed=True,
            producer_id="same-authority",
            verifier_id="same-authority",
            evidence_refs=("context:proof",),
        )


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
        passed=True,
        producer_id="context-ledger",
        verifier_id="ai-system-completion:independent",
        evidence_refs=("context:a",),
        details={"height": 1},
    )
    second = RequirementProof(
        requirement=CompletionRequirement.MEMORY_LIFECYCLE,
        subject_id="digest-subject",
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
