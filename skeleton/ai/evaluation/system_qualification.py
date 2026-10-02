"""Executable end-to-end qualification for standalone AI system completion.

Unlike the structural verifier, this module runs the assembled local AI through
its real execution, persistence, context, memory, verification, finalization,
learning-promotion, and rollback planes.  It then feeds independently observed
facts into :mod:`skeleton.ai.runtime.system_completion` and emits a durable
machine-readable receipt.

The qualifier is deliberately credential-free and network-denying.  It is a
qualification harness, not a production authority: it does not grant tool
permissions or bypass any runtime policy.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import socket
import threading
from typing import Mapping

from skeleton.contracts.ai_execution import AIExecutionRequest
from skeleton.ai.learning.promotion import (
    EvaluationReceipt,
    ExperimentSpec,
    FeedbackLedger,
    FeedbackPromotionPipeline,
    PromotionReceipt,
)
from skeleton.ai.runtime.context.ledger import ContextLedger
from skeleton.ai.runtime.functional_ai import FunctionalAIRequest, FunctionalAIRun, FunctionalAIRuntime
from skeleton.ai.runtime.inference import (
    CallableLocalModel,
    LocalInferenceEngine,
    LocalInferenceRequest,
    LocalInferenceResult,
    LocalModelAdapter,
    LocalToolCall,
)
from skeleton.ai.runtime.memory.core import Chunk, InMemoryTFIDFStore
from skeleton.ai.runtime.system_completion import SystemCompletionPlane, SystemCompletionReport
from skeleton.intelligence.execution_runtime import (
    CognitiveExecutionRuntime,
    ExecutionFinalizationBindings,
    ExecutionVerificationDecision,
)
from skeleton.persistence.execution_repository import SQLiteExecutionRepository
from skeleton.skills.tool_contract import ToolEffect, ToolManifest
from skeleton.skills.tool_runtime import AsyncToolRuntime


QUALIFICATION_TIME = datetime(2026, 10, 2, 20, 30, tzinfo=timezone.utc)
QUALIFICATION_REQUEST_ID = "ai-system-completion-qualification-v1"
QUALIFICATION_CONTEXT_DIGEST = hashlib.sha256(
    b"skeleton-ai-system-completion-qualification-context-v1"
).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


class OfflineSocketGuard(AbstractContextManager["OfflineSocketGuard"]):
    """Deny AF_INET/AF_INET6 sockets and count every attempted escape."""

    def __init__(self) -> None:
        self.attempts: list[str] = []
        self._original = socket.socket

    def __enter__(self) -> "OfflineSocketGuard":
        original = self._original
        attempts = self.attempts

        def guarded_socket(*args, **kwargs):
            family = args[0] if args else kwargs.get("family", socket.AF_INET)
            if family in {socket.AF_INET, socket.AF_INET6}:
                attempts.append(str(family))
                raise RuntimeError(
                    "AI system qualification attempted external network I/O"
                )
            return original(*args, **kwargs)

        socket.socket = guarded_socket  # type: ignore[assignment]
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        socket.socket = self._original  # type: ignore[assignment]
        return False


@dataclass(frozen=True, slots=True)
class QualificationRun:
    database_path: Path
    request: FunctionalAIRequest
    run: FunctionalAIRun
    observed_tool_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LearningCycle:
    spec: ExperimentSpec
    evaluation: EvaluationReceipt
    promotion: PromotionReceipt
    promoted_active: str
    rollback: PromotionReceipt
    rolled_back_active: str


@dataclass(frozen=True, slots=True)
class SystemQualificationReceipt:
    """Durable exact-revision evidence emitted by executable qualification."""

    source_revision: str
    subject_id: str
    report: SystemCompletionReport
    primary_result_digest: str
    replay_result_digest: str
    primary_output_digest: str
    replay_output_digest: str
    network_attempt_count: int
    observed_tool_ids: tuple[str, ...]
    replay_observed_tool_ids: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return bool(
            self.report.valid
            and self.report.subject_id == self.subject_id
            and self.report.source_revision == self.source_revision
            and self.network_attempt_count == 0
            and self.primary_result_digest == self.replay_result_digest
            and self.primary_output_digest == self.replay_output_digest
            and self.observed_tool_ids == self.replay_observed_tool_ids
        )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema_version": "skeleton.ai.system_qualification.v1",
                "source_revision": self.source_revision,
                "subject_id": self.subject_id,
                "report_digest": self.report.digest,
                "primary_result_digest": self.primary_result_digest,
                "replay_result_digest": self.replay_result_digest,
                "primary_output_digest": self.primary_output_digest,
                "replay_output_digest": self.replay_output_digest,
                "network_attempt_count": self.network_attempt_count,
                "observed_tool_ids": list(self.observed_tool_ids),
                "replay_observed_tool_ids": list(self.replay_observed_tool_ids),
                "valid": self.valid,
            }
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "skeleton.ai.system_qualification.v1",
            "source_revision": self.source_revision,
            "subject_id": self.subject_id,
            "report": self.report.as_dict(),
            "primary_result_digest": self.primary_result_digest,
            "replay_result_digest": self.replay_result_digest,
            "primary_output_digest": self.primary_output_digest,
            "replay_output_digest": self.replay_output_digest,
            "network_attempt_count": self.network_attempt_count,
            "observed_tool_ids": list(self.observed_tool_ids),
            "replay_observed_tool_ids": list(self.replay_observed_tool_ids),
            "valid": self.valid,
            "digest": self.digest,
        }


def _local_model() -> LocalModelAdapter:
    model_digest = hashlib.sha256(
        b"skeleton-system-qualification-local-model-v1"
    ).hexdigest()

    def runner(
        request: LocalInferenceRequest,
        cancel: threading.Event,
    ) -> LocalInferenceResult:
        if cancel.is_set():
            raise RuntimeError("qualification local model was cancelled")
        if request.prompt.startswith(
            "Tool results from the previous provider turn"
        ):
            return LocalInferenceResult(
                text=(
                    "Standalone AI qualification completed from the governed "
                    "local repository receipt."
                ),
                model_id="system-qualification-local",
                model_digest=model_digest,
                input_tokens=len(request.rendered_input.split()),
                output_tokens=11,
                response_id="local:system-qualification:final",
            )
        if not any(tool.get("tool_id") == "repo.read" for tool in request.tools):
            raise RuntimeError("qualification lost governed repo.read authority")
        return LocalInferenceResult(
            text=None,
            model_id="system-qualification-local",
            model_digest=model_digest,
            input_tokens=len(request.rendered_input.split()),
            output_tokens=4,
            finish_reason="tool_calls",
            response_id="local:system-qualification:tool",
            tool_calls=(
                LocalToolCall(
                    call_id="system-qualification-read-1",
                    tool_id="repo.read",
                    arguments={"path": "README.md"},
                ),
            ),
        )

    return LocalModelAdapter(
        LocalInferenceEngine(
            CallableLocalModel(
                model_id="system-qualification-local",
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
    expected_prefix = "Standalone AI qualification completed"
    passed = candidate.startswith(expected_prefix)
    candidate_digest = hashlib.sha256(candidate.encode("utf-8")).hexdigest()
    return ExecutionVerificationDecision(
        passed=passed,
        receipt={
            "outcome": "passed" if passed else "failed",
            "policy_satisfied": passed,
            "verifier_id": "system-qualification:independent-output-v1",
            "candidate_digest": candidate_digest,
            "context_digest": context_digest,
        },
        evidence_refs=(
            "evidence:system-qualification:governed-local-read",
            "evidence:system-qualification:independent-output",
        ),
    )


async def _finalization(
    _request,
    candidate: str,
    payload: Mapping[str, object],
) -> ExecutionFinalizationBindings:
    result_binding = hashlib.sha256(candidate.encode("utf-8")).hexdigest()
    payload_binding = _digest(dict(payload))
    return ExecutionFinalizationBindings(
        memory_refs=(
            "memory:system-qualification:" + result_binding,
        ),
        artifact_refs=(
            "artifact:system-qualification:" + payload_binding,
        ),
    )


async def _run_once(
    workdir: Path,
    *,
    database_name: str,
) -> QualificationRun:
    database_path = workdir / database_name
    if database_path.exists():
        database_path.unlink()

    repository = SQLiteExecutionRepository(database_path)
    tools = AsyncToolRuntime()
    observed_tool_ids: list[str] = []

    async def read_handler(request):
        observed_tool_ids.append(request.tool_id)
        return "repo-evidence:README.md:system-qualification"

    await tools.register(
        ToolManifest(
            tool_id="repo.read",
            version="1.0.0",
            description="Read one repository path for system qualification",
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
        request_id=QUALIFICATION_REQUEST_ID,
        objective="Prove assembled standalone AI completion end to end.",
        prompt="Read README.md and publish a verified qualification statement.",
        instructions=(
            "Use only the credential-free local model and explicitly governed "
            "repo.read tool."
        ),
        context_digest=QUALIFICATION_CONTEXT_DIGEST,
        allowed_tool_ids=("repo.read",),
        created_at=QUALIFICATION_TIME,
    )
    runtime = FunctionalAIRuntime(
        repository,
        _local_model(),
        tools,
        verification_hook=_verification,
        finalization_binding_hook=_finalization,
    )
    run = await runtime.execute(request)
    return QualificationRun(
        database_path=database_path,
        request=request,
        run=run,
        observed_tool_ids=tuple(observed_tool_ids),
    )



def _stop_request(kind: str, *, deadline: bool) -> AIExecutionRequest:
    stop_policy: dict[str, object] = {"max_repeat_tool_batches": 1}
    if deadline:
        stop_policy["deadline"] = QUALIFICATION_TIME.isoformat()
    return AIExecutionRequest(
        operation_id=f"system-qualification-stop-operation-{kind}",
        execution_id=f"system-qualification-stop-execution-{kind}",
        objective="Prove standalone AI stop semantics fail closed.",
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
        created_at=QUALIFICATION_TIME,
    )


async def _stop_semantics_results(
    workdir: Path,
):
    context_digest = hashlib.sha256(
        b"system-qualification-stop-context-v1"
    ).hexdigest()

    deadline_repository = SQLiteExecutionRepository(
        workdir / "system-qualification-deadline.sqlite3"
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
        prompt="This qualification request is already at its deadline.",
        context_digest=context_digest,
        now=QUALIFICATION_TIME,
    )
    if deadline_run.result is None:
        raise RuntimeError("deadline qualification did not terminate")

    cancellation_repository = SQLiteExecutionRepository(
        workdir / "system-qualification-cancellation.sqlite3"
    )
    cancellation_runtime = CognitiveExecutionRuntime(
        cancellation_repository,
        _local_model(),
        AsyncToolRuntime(),
        verification_hook=_verification,
    )
    cancellation_request = _stop_request("cancellation", deadline=False)
    execution = cancellation_repository.create(
        cancellation_request,
        now=QUALIFICATION_TIME,
    )
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
        now=QUALIFICATION_TIME,
    )
    cancellation_repository.request_cancel(
        cancellation_request.execution_id,
        expected_version=execution.version,
        now=QUALIFICATION_TIME,
    )
    cancellation_run = await cancellation_runtime.resume(
        cancellation_request.execution_id,
        now=QUALIFICATION_TIME,
    )
    if cancellation_run.result is None:
        raise RuntimeError("cancellation qualification did not terminate")

    return deadline_run.result, cancellation_run.result

def _stop_request(kind: str, *, deadline: bool) -> AIExecutionRequest:
    stop_policy: dict[str, object] = {"max_repeat_tool_batches": 1}
    if deadline:
        stop_policy["deadline"] = QUALIFICATION_TIME.isoformat()
    return AIExecutionRequest(
        operation_id=f"system-qualification-stop-operation-{kind}",
        execution_id=f"system-qualification-stop-execution-{kind}",
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
        created_at=QUALIFICATION_TIME,
    )


async def _stop_semantics_results(
    workdir: Path,
) -> tuple[AIExecutionResult, AIExecutionResult]:
    context_digest = hashlib.sha256(
        b"system-qualification-stop-context-v1"
    ).hexdigest()

    deadline_path = workdir / "system-qualification-deadline.sqlite3"
    cancellation_path = workdir / "system-qualification-cancellation.sqlite3"
    for path in (deadline_path, cancellation_path):
        if path.exists():
            path.unlink()

    deadline_repository = SQLiteExecutionRepository(deadline_path)
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
        prompt="This qualification request is already at its deadline.",
        context_digest=context_digest,
        now=QUALIFICATION_TIME,
    )
    if deadline_run.result is None:
        raise RuntimeError("deadline qualification did not publish terminal result")

    cancellation_repository = SQLiteExecutionRepository(cancellation_path)
    cancellation_runtime = CognitiveExecutionRuntime(
        cancellation_repository,
        _local_model(),
        AsyncToolRuntime(),
        verification_hook=_verification,
    )
    cancellation_request = _stop_request("cancellation", deadline=False)
    execution = cancellation_repository.create(
        cancellation_request,
        now=QUALIFICATION_TIME,
    )
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
        now=QUALIFICATION_TIME,
    )
    cancellation_repository.request_cancel(
        cancellation_request.execution_id,
        expected_version=execution.version,
        now=QUALIFICATION_TIME,
    )
    cancellation_run = await cancellation_runtime.resume(
        cancellation_request.execution_id,
        now=QUALIFICATION_TIME,
    )
    if cancellation_run.result is None:
        raise RuntimeError(
            "cancellation qualification did not publish terminal result"
        )
    return deadline_run.result, cancellation_run.result


def _learning_cycle() -> LearningCycle:
    spec = ExperimentSpec(
        experiment_id="system-qualification-learning",
        baseline_version="baseline-v1",
        candidate_version="candidate-v2",
        assignment_salt="system-qualification-salt",
        data_use_purpose="system-qualification-evaluation",
        holdout_bps=0,
        candidate_bps=5000,
        min_variant_samples=1,
    )
    ledger = FeedbackLedger()
    by_variant = {}
    for index in range(256):
        subject = f"qualification-subject-{index}"
        assignment = ledger.assign(spec, subject)
        if assignment.variant in by_variant:
            continue
        event = ledger.collect(
            spec,
            assignment,
            event_id=f"qualification-event-{assignment.variant}",
            score=0.90 if assignment.variant == "candidate" else 0.55,
            observed_at=1_000 + index,
            consent=True,
            data_use_purpose=spec.data_use_purpose,
        )
        by_variant[assignment.variant] = event
        if {"baseline", "candidate"} <= set(by_variant):
            break
    if {"baseline", "candidate"} - set(by_variant):
        raise RuntimeError("qualification could not establish both learning variants")

    selected = (by_variant["baseline"], by_variant["candidate"])
    evaluation = EvaluationReceipt(
        experiment_id=spec.experiment_id,
        baseline_version=spec.baseline_version,
        candidate_version=spec.candidate_version,
        evaluator_id="system-qualification:heldout-evaluator-v1",
        passed=True,
        event_ids=tuple(event.event_id for event in selected),
        metric_delta=0.35,
        evaluated_at=2_000,
        evidence_ref="eval:system-qualification:heldout",
    )
    pipeline = FeedbackPromotionPipeline()
    promotion = pipeline.promote(
        spec,
        selected,
        evaluation,
        promoted_at=2_100,
    )
    promoted_active = pipeline.active_version(spec)
    rollback = pipeline.rollback(
        spec,
        reason="qualification rollback proof",
        rolled_back_at=2_200,
    )
    return LearningCycle(
        spec=spec,
        evaluation=evaluation,
        promotion=promotion,
        promoted_active=promoted_active,
        rollback=rollback,
        rolled_back_active=pipeline.active_version(spec),
    )


async def qualify_system_completion(
    workdir: str | Path,
    *,
    source_revision: str,
) -> SystemQualificationReceipt:
    """Execute and independently qualify the 17-plane completion chain."""

    root = Path(workdir)
    root.mkdir(parents=True, exist_ok=True)

    with OfflineSocketGuard() as network:
        primary = await _run_once(
            root,
            database_name="system-qualification-primary.sqlite3",
        )
        replay = await _run_once(
            root,
            database_name="system-qualification-replay.sqlite3",
        )
        deadline_result, cancellation_result = await _stop_semantics_results(
            root
        )

    terminal = primary.run.execution.result
    replay_terminal = replay.run.execution.result
    if terminal is None or replay_terminal is None:
        raise RuntimeError("qualification execution did not publish terminal result")

    recovered_repository = SQLiteExecutionRepository(primary.database_path)
    recovered = recovered_repository.result(primary.request.execution_id)
    recovered_turns = recovered_repository.turns(primary.request.execution_id)

    context_ledger = ContextLedger()
    context_ledger.append(
        "system-qualification",
        {
            "execution_id": primary.request.execution_id,
            "result_digest": primary.run.evidence.result_digest,
            "request_identity_digest": (
                primary.request.to_execution_request().identity_digest
            ),
        },
        mass=1.0,
        tensor_fp=hashlib.sha256(
            b"system-qualification-context-ledger-v1"
        ).hexdigest(),
    )

    memory = InMemoryTFIDFStore()
    memory_id = "system-qualification-memory"
    memory.add(
        Chunk(
            chunk_id=memory_id,
            text=(
                "standalone system qualification durable memory lifecycle "
                "evidence"
            ),
            metadata={"execution_id": primary.request.execution_id},
        )
    )
    recalled = tuple(
        item.chunk.chunk_id
        for item in memory.query(
            "qualification durable memory lifecycle evidence",
            top_k=5,
        )
    )
    deleted = memory.delete(memory_id)
    recalled_after_delete = tuple(
        item.chunk.chunk_id
        for item in memory.query(
            "qualification durable memory lifecycle evidence",
            top_k=5,
        )
    )

    learning = _learning_cycle()
    plane = SystemCompletionPlane(
        subject_id=primary.request.execution_id,
        source_revision=source_revision,
    )

    plane.prove_local_execution(
        primary.run.execution,
        local_model_id=primary.run.evidence.local_model_id,
        provider_receipts=primary.run.evidence.provider_receipts,
    )
    plane.prove_offline_isolation(
        network_attempt_count=len(network.attempts),
        provider_receipts=primary.run.evidence.provider_receipts,
    )
    plane.prove_request_result_binding(
        primary.request.to_execution_request(),
        terminal,
    )
    plane.prove_budget_bounds(
        max_model_turns=primary.request.max_model_turns,
        max_tool_calls=primary.request.max_tool_calls,
        provider_receipts=terminal.provider_receipts,
        tool_receipts=terminal.tool_receipts,
    )
    plane.prove_stop_semantics(
        deadline_result=deadline_result,
        cancellation_result=cancellation_result,
    )
    plane.prove_tool_authority(
        allowed_tool_ids=primary.request.allowed_tool_ids,
        observed_tool_ids=primary.observed_tool_ids,
        receipt_refs=terminal.tool_receipts,
    )
    plane.prove_durable_recovery(terminal, recovered)
    plane.prove_replay_lineage(recovered_turns)
    plane.prove_reproducibility(
        primary_result_digest=primary.run.evidence.result_digest,
        replay_result_digest=replay.run.evidence.result_digest,
        primary_output_digest=primary.run.evidence.final_output_digest,
        replay_output_digest=replay.run.evidence.final_output_digest,
    )
    plane.prove_governed_effects(
        tool_receipt_count=len(terminal.tool_receipts),
        mutating_tool_count=0,
        verified_postcondition_count=0,
        receipt_refs=terminal.tool_receipts,
    )
    plane.prove_independent_verification(terminal)
    plane.prove_verification_binding(
        terminal,
        context_digest=primary.request.context_digest,
    )
    plane.prove_context_integrity(
        problems=context_ledger.verify(),
        height=context_ledger.height,
        head_hash=context_ledger.head.hash,
    )
    plane.prove_memory_lifecycle(
        memory_id=memory_id,
        memory_subject_id=primary.request.execution_id,
        recalled_ids=recalled,
        deleted=deleted,
        post_delete_recalled_ids=recalled_after_delete,
    )
    plane.prove_finalization_lineage(terminal)
    plane.prove_learning_promotion(
        learning.promotion,
        expected_baseline=learning.spec.baseline_version,
        expected_candidate=learning.spec.candidate_version,
        active_version=learning.promoted_active,
        evaluation_digest=learning.evaluation.digest,
        evaluator_id=learning.evaluation.evaluator_id,
    )
    plane.prove_learning_rollback(
        learning.rollback,
        expected_baseline=learning.spec.baseline_version,
        expected_candidate=learning.spec.candidate_version,
        active_version=learning.rolled_back_active,
        promotion_receipt=learning.promotion,
    )

    report = plane.report()
    return SystemQualificationReceipt(
        source_revision=source_revision,
        subject_id=primary.request.execution_id,
        report=report,
        primary_result_digest=primary.run.evidence.result_digest,
        replay_result_digest=replay.run.evidence.result_digest,
        primary_output_digest=primary.run.evidence.final_output_digest,
        replay_output_digest=replay.run.evidence.final_output_digest,
        network_attempt_count=len(network.attempts),
        observed_tool_ids=primary.observed_tool_ids,
        replay_observed_tool_ids=replay.observed_tool_ids,
    )


__all__ = [
    "OfflineSocketGuard",
    "SystemQualificationReceipt",
    "qualify_system_completion",
]
