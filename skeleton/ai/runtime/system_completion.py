"""Non-compensable system-completion plane for standalone AI.

This module does not count subsystem checkboxes.  It composes independently
verified proofs from the real runtime planes and refuses to publish a terminal
completion verdict while any required proof is missing or failed.

The plane is intentionally small in authority: it cannot execute tools, mutate
memory, promote learning candidates, or repair evidence.  It only validates
proofs emitted by those planes and binds them to one subject + source revision.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import re
from typing import Iterable, Mapping, Sequence

from skeleton.contracts.ai_execution import AIExecutionRequest, AIExecutionResult, AgentTurn
from skeleton.intelligence.execution_runtime import ExecutionRunResult
from skeleton.ai.learning.promotion import PromotionReceipt


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")


class CompletionPlaneError(ValueError):
    """Raised when completion evidence is malformed or authority is violated."""


class CompletionRequirement(str, Enum):
    LOCAL_EXECUTION = "execution.local_model"
    OFFLINE_ISOLATION = "execution.offline_isolation"
    REQUEST_RESULT_BINDING = "execution.request_result_binding"
    BUDGET_BOUNDS = "execution.budget_bounds"
    STOP_SEMANTICS = "execution.stop_semantics"
    TOOL_AUTHORITY = "execution.tool_authority"
    DURABLE_RECOVERY = "execution.durable_recovery"
    STAGED_FINALIZATION_RECOVERY = "execution.staged_finalization_recovery"
    REPLAY_LINEAGE = "execution.replay_lineage"
    REPRODUCIBILITY = "execution.reproducibility"
    GOVERNED_EFFECTS = "execution.governed_effects"
    INDEPENDENT_VERIFICATION = "verification.independent"
    VERIFICATION_BINDING = "verification.claim_binding"
    CONTEXT_INTEGRITY = "context.integrity"
    MEMORY_LIFECYCLE = "memory.lifecycle"
    FINALIZATION_LINEAGE = "finalization.lineage"
    LEARNING_PROMOTION = "learning.promotion"
    LEARNING_ROLLBACK = "learning.rollback"
    SANDBOX_FILESYSTEM = "security.sandbox_filesystem"
    SANDBOX_PROCESS = "security.sandbox_process"
    INJECTION_SANITIZATION = "security.injection_sanitization"
    PROVIDER_FALLBACK_PRIVACY = "privacy.provider_fallback"
    MEMORY_POISONING_RESISTANCE = "memory.poisoning_resistance"
    OUTBOUND_NETWORK_BOUNDARY = "security.outbound_network_boundary"


REQUIRED_COMPLETION_REQUIREMENTS: tuple[CompletionRequirement, ...] = tuple(
    CompletionRequirement
)


def _text(name: str, value: object, *, maximum: int = 2048) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CompletionPlaneError(f"{name} must be non-empty text")
    normalized = value.strip()
    if normalized != value or len(normalized) > maximum:
        raise CompletionPlaneError(f"{name} is not normalized")
    return normalized


def _canonical(value: object) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise CompletionPlaneError("completion evidence must be canonical JSON") from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def completion_learning_experiment_id(
    subject_id: str,
    result_digest: str,
) -> str:
    """Return the only learning-experiment identity valid for this run result."""

    subject = _text("subject_id", subject_id)
    if not isinstance(result_digest, str) or _SHA256.fullmatch(result_digest) is None:
        raise CompletionPlaneError("result_digest must be lowercase sha256")
    binding = hashlib.sha256(
        (subject + ":" + result_digest).encode("utf-8")
    ).hexdigest()
    return "system-completion-" + binding[:32]


def _refs(values: Iterable[str], *, name: str = "evidence_refs") -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise CompletionPlaneError(f"{name} must be an iterable of references")
    result: list[str] = []
    for raw in values:
        value = _text(name, raw)
        if value not in result:
            result.append(value)
    return tuple(result)


def _details(value: Mapping[str, object] | None) -> dict[str, object]:
    result = dict(value or {})
    # Validate canonical serialization now, not at receipt publication.
    _canonical(result)
    return result


@dataclass(frozen=True, slots=True)
class RequirementProof:
    """One independently witnessed proof for a non-compensable requirement."""

    requirement: CompletionRequirement
    subject_id: str
    source_revision: str
    passed: bool
    producer_id: str
    verifier_id: str
    evidence_refs: tuple[str, ...]
    details: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        try:
            requirement = CompletionRequirement(self.requirement)
        except ValueError as exc:
            raise CompletionPlaneError("unknown completion requirement") from exc
        object.__setattr__(self, "requirement", requirement)
        object.__setattr__(self, "subject_id", _text("subject_id", self.subject_id))
        revision = _text("source_revision", self.source_revision, maximum=40)
        if _GIT_SHA.fullmatch(revision) is None:
            raise CompletionPlaneError(
                "proof source_revision must be a lowercase 40-char git sha"
            )
        object.__setattr__(self, "source_revision", revision)
        object.__setattr__(self, "producer_id", _text("producer_id", self.producer_id))
        object.__setattr__(self, "verifier_id", _text("verifier_id", self.verifier_id))
        if self.producer_id == self.verifier_id:
            raise CompletionPlaneError(
                f"{requirement.value} proof requires independent verifier identity"
            )
        if not isinstance(self.passed, bool):
            raise CompletionPlaneError("passed must be boolean")
        refs = _refs(self.evidence_refs)
        if self.passed and not refs:
            raise CompletionPlaneError(
                f"{requirement.value} passed proof requires evidence references"
            )
        object.__setattr__(self, "evidence_refs", refs)
        object.__setattr__(self, "details", _details(self.details))

    @property
    def digest(self) -> str:
        return _digest(
            {
                "requirement": self.requirement.value,
                "subject_id": self.subject_id,
                "source_revision": self.source_revision,
                "passed": self.passed,
                "producer_id": self.producer_id,
                "verifier_id": self.verifier_id,
                "evidence_refs": list(self.evidence_refs),
                "details": dict(self.details),
            }
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "requirement": self.requirement.value,
            "subject_id": self.subject_id,
            "source_revision": self.source_revision,
            "passed": self.passed,
            "producer_id": self.producer_id,
            "verifier_id": self.verifier_id,
            "evidence_refs": list(self.evidence_refs),
            "details": dict(self.details),
            "digest": self.digest,
        }


@dataclass(frozen=True, slots=True)
class SystemCompletionReport:
    """Deterministic closure report.  Missing proof can never be compensated."""

    subject_id: str
    source_revision: str
    proofs: tuple[RequirementProof, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "subject_id", _text("subject_id", self.subject_id))
        revision = _text("source_revision", self.source_revision, maximum=40)
        if _GIT_SHA.fullmatch(revision) is None:
            raise CompletionPlaneError("source_revision must be a lowercase 40-char git sha")
        object.__setattr__(self, "source_revision", revision)

        seen: set[CompletionRequirement] = set()
        normalized: list[RequirementProof] = []
        for proof in self.proofs:
            if not isinstance(proof, RequirementProof):
                raise CompletionPlaneError("proofs must contain RequirementProof values")
            if proof.subject_id != self.subject_id:
                raise CompletionPlaneError("proof subject does not match report subject")
            if proof.source_revision != self.source_revision:
                raise CompletionPlaneError(
                    "proof source revision does not match report source revision"
                )
            if proof.requirement in seen:
                raise CompletionPlaneError(
                    f"duplicate completion proof: {proof.requirement.value}"
                )
            seen.add(proof.requirement)
            normalized.append(proof)
        normalized.sort(key=lambda item: item.requirement.value)
        object.__setattr__(self, "proofs", tuple(normalized))

    @property
    def missing(self) -> tuple[str, ...]:
        present = {proof.requirement for proof in self.proofs}
        return tuple(
            requirement.value
            for requirement in REQUIRED_COMPLETION_REQUIREMENTS
            if requirement not in present
        )

    @property
    def failed(self) -> tuple[str, ...]:
        return tuple(
            proof.requirement.value for proof in self.proofs if not proof.passed
        )

    @property
    def valid(self) -> bool:
        return not self.missing and not self.failed

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema_version": "skeleton.ai.system_completion.v1",
                "subject_id": self.subject_id,
                "source_revision": self.source_revision,
                "required": [item.value for item in REQUIRED_COMPLETION_REQUIREMENTS],
                "proof_digests": [proof.digest for proof in self.proofs],
                "missing": list(self.missing),
                "failed": list(self.failed),
                "valid": self.valid,
            }
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "skeleton.ai.system_completion.v1",
            "subject_id": self.subject_id,
            "source_revision": self.source_revision,
            "required": [item.value for item in REQUIRED_COMPLETION_REQUIREMENTS],
            "proofs": [proof.as_dict() for proof in self.proofs],
            "missing": list(self.missing),
            "failed": list(self.failed),
            "valid": self.valid,
            "digest": self.digest,
        }


class SystemCompletionPlane:
    """Collect one proof per required plane and derive a fail-closed verdict."""

    def __init__(
        self,
        *,
        subject_id: str,
        source_revision: str,
        verifier_id: str = "ai-system-completion:independent",
    ) -> None:
        self.subject_id = _text("subject_id", subject_id)
        revision = _text("source_revision", source_revision, maximum=40)
        if _GIT_SHA.fullmatch(revision) is None:
            raise CompletionPlaneError("source_revision must be a lowercase 40-char git sha")
        self.source_revision = revision
        self.verifier_id = _text("verifier_id", verifier_id)
        self._proofs: dict[CompletionRequirement, RequirementProof] = {}

    def add(self, proof: RequirementProof) -> RequirementProof:
        if proof.subject_id != self.subject_id:
            raise CompletionPlaneError("cannot mix completion subjects")
        if proof.source_revision != self.source_revision:
            raise CompletionPlaneError("cannot mix completion source revisions")
        if proof.verifier_id != self.verifier_id:
            raise CompletionPlaneError("proof verifier is outside completion authority")
        if proof.requirement in self._proofs:
            raise CompletionPlaneError(
                f"requirement already proved: {proof.requirement.value}"
            )
        self._proofs[proof.requirement] = proof
        return proof

    def report(self) -> SystemCompletionReport:
        return SystemCompletionReport(
            subject_id=self.subject_id,
            source_revision=self.source_revision,
            proofs=tuple(self._proofs.values()),
        )

    def _proof(
        self,
        requirement: CompletionRequirement,
        *,
        passed: bool,
        producer_id: str,
        evidence_refs: Iterable[str],
        details: Mapping[str, object],
    ) -> RequirementProof:
        return self.add(
            RequirementProof(
                requirement=requirement,
                subject_id=self.subject_id,
                source_revision=self.source_revision,
                passed=passed,
                producer_id=producer_id,
                verifier_id=self.verifier_id,
                evidence_refs=_refs(evidence_refs),
                details=dict(details),
            )
        )

    def prove_local_execution(
        self,
        run: ExecutionRunResult,
        *,
        local_model_id: str,
        provider_receipts: Sequence[str],
    ) -> RequirementProof:
        result = run.result
        receipts = tuple(provider_receipts)
        passed = bool(
            run.execution_id == self.subject_id
            and run.completed
            and result is not None
            and result.execution_id == self.subject_id
            and result.status == "completed"
            and result.final_output
            and receipts
            and all(ref.startswith("provider:local:") for ref in receipts)
        )
        refs = list(receipts)
        if result is not None and result.stream_terminal_event:
            refs.append("stream:" + result.stream_terminal_event)
        return self._proof(
            CompletionRequirement.LOCAL_EXECUTION,
            passed=passed,
            producer_id="functional-ai-runtime",
            evidence_refs=refs,
            details={
                "local_model_id": _text("local_model_id", local_model_id),
                "execution_id": run.execution_id,
                "subject_bound": (
                    run.execution_id == self.subject_id
                    and result is not None
                    and result.execution_id == self.subject_id
                ),
                "state": run.state.value,
                "provider_receipt_count": len(receipts),
            },
        )

    def prove_offline_isolation(
        self,
        *,
        execution_id: str,
        network_attempt_count: int,
        provider_receipts: Sequence[str],
    ) -> RequirementProof:
        if (
            isinstance(network_attempt_count, bool)
            or not isinstance(network_attempt_count, int)
            or network_attempt_count < 0
        ):
            raise CompletionPlaneError(
                "network_attempt_count must be a non-negative integer"
            )
        execution_id = _text("execution_id", execution_id)
        receipts = tuple(provider_receipts)
        passed = bool(
            execution_id == self.subject_id
            and network_attempt_count == 0
            and receipts
            and all(ref.startswith("provider:local:") for ref in receipts)
        )
        return self._proof(
            CompletionRequirement.OFFLINE_ISOLATION,
            passed=passed,
            producer_id="functional-ai-runtime",
            evidence_refs=receipts,
            details={
                "execution_id": execution_id,
                "subject_bound": execution_id == self.subject_id,
                "network_attempt_count": network_attempt_count,
                "provider_receipt_count": len(receipts),
                "all_provider_receipts_local": bool(receipts)
                and all(ref.startswith("provider:local:") for ref in receipts),
            },
        )

    def prove_request_result_binding(
        self,
        request: AIExecutionRequest,
        result: AIExecutionResult,
    ) -> RequirementProof:
        if not isinstance(request, AIExecutionRequest):
            raise CompletionPlaneError("request must be AIExecutionRequest")
        if not isinstance(result, AIExecutionResult):
            raise CompletionPlaneError("result must be AIExecutionResult")
        passed = bool(
            request.execution_id == self.subject_id
            and result.execution_id == request.execution_id
            and result.operation_id == request.operation_id
            and result.status == "completed"
        )
        return self._proof(
            CompletionRequirement.REQUEST_RESULT_BINDING,
            passed=passed,
            producer_id="cognitive-execution-runtime",
            evidence_refs=(
                "request-identity:" + request.identity_digest,
                "execution-result:" + result.execution_id,
            ),
            details={
                "request_execution_id": request.execution_id,
                "result_execution_id": result.execution_id,
                "request_operation_id": request.operation_id,
                "result_operation_id": result.operation_id,
                "request_identity_digest": request.identity_digest,
            },
        )

    def prove_budget_bounds(
        self,
        *,
        execution_id: str,
        max_model_turns: int,
        max_tool_calls: int,
        provider_receipts: Sequence[str],
        tool_receipts: Sequence[str],
    ) -> RequirementProof:
        for name, value in (
            ("max_model_turns", max_model_turns),
            ("max_tool_calls", max_tool_calls),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise CompletionPlaneError(f"{name} must be a positive integer")
        execution_id = _text("execution_id", execution_id)
        providers = tuple(provider_receipts)
        tools = tuple(tool_receipts)
        passed = bool(
            execution_id == self.subject_id
            and providers
            and len(providers) <= max_model_turns
            and len(tools) <= max_tool_calls
        )
        refs = list(providers) + list(tools)
        return self._proof(
            CompletionRequirement.BUDGET_BOUNDS,
            passed=passed,
            producer_id="cognitive-execution-runtime",
            evidence_refs=refs,
            details={
                "execution_id": execution_id,
                "subject_bound": execution_id == self.subject_id,
                "max_model_turns": max_model_turns,
                "observed_model_turns": len(providers),
                "max_tool_calls": max_tool_calls,
                "observed_tool_calls": len(tools),
            },
        )

    def prove_stop_semantics(
        self,
        *,
        deadline_result: AIExecutionResult,
        cancellation_result: AIExecutionResult,
    ) -> RequirementProof:
        if not isinstance(deadline_result, AIExecutionResult):
            raise CompletionPlaneError("deadline_result must be AIExecutionResult")
        if not isinstance(cancellation_result, AIExecutionResult):
            raise CompletionPlaneError(
                "cancellation_result must be AIExecutionResult"
            )
        deadline_error = deadline_result.usage.get("error_code")
        cancellation_error = cancellation_result.usage.get("error_code")
        deadline_fenced = bool(
            deadline_result.status == "failed"
            and deadline_error == "execution_deadline_exceeded"
            and deadline_result.final_output is None
            and not deadline_result.provider_receipts
            and not deadline_result.tool_receipts
            and deadline_result.stream_terminal_event
        )
        cancellation_fenced = bool(
            cancellation_result.status == "cancelled"
            and cancellation_error == "cancellation_requested"
            and cancellation_result.final_output is None
            and not cancellation_result.provider_receipts
            and not cancellation_result.tool_receipts
            and cancellation_result.stream_terminal_event
        )
        refs = [
            "execution-result:" + deadline_result.execution_id,
            "execution-result:" + cancellation_result.execution_id,
        ]
        if deadline_result.stream_terminal_event:
            refs.append("stream:" + deadline_result.stream_terminal_event)
        if cancellation_result.stream_terminal_event:
            refs.append("stream:" + cancellation_result.stream_terminal_event)
        return self._proof(
            CompletionRequirement.STOP_SEMANTICS,
            passed=deadline_fenced and cancellation_fenced,
            producer_id="cognitive-execution-runtime",
            evidence_refs=refs,
            details={
                "deadline_status": deadline_result.status,
                "deadline_error_code": deadline_error,
                "deadline_fenced": deadline_fenced,
                "cancellation_status": cancellation_result.status,
                "cancellation_error_code": cancellation_error,
                "cancellation_fenced": cancellation_fenced,
            },
        )

    def prove_tool_authority(
        self,
        *,
        execution_id: str,
        allowed_tool_ids: Sequence[str],
        observed_tool_ids: Sequence[str],
        receipt_refs: Sequence[str],
    ) -> RequirementProof:
        execution_id = _text("execution_id", execution_id)
        allowed = tuple(
            dict.fromkeys(
                _text("allowed_tool_id", item) for item in allowed_tool_ids
            )
        )
        observed = tuple(
            _text("observed_tool_id", item) for item in observed_tool_ids
        )
        receipts = tuple(_text("tool_receipt", item) for item in receipt_refs)
        passed = bool(
            execution_id == self.subject_id
            and observed
            and len(observed) == len(receipts)
            and all(tool_id in allowed for tool_id in observed)
        )
        return self._proof(
            CompletionRequirement.TOOL_AUTHORITY,
            passed=passed,
            producer_id="tool-runtime",
            evidence_refs=receipts,
            details={
                "execution_id": execution_id,
                "subject_bound": execution_id == self.subject_id,
                "allowed_tool_ids": list(allowed),
                "observed_tool_ids": list(observed),
                "observed_call_count": len(observed),
                "receipt_count": len(receipts),
                "all_calls_authorized": all(tool_id in allowed for tool_id in observed),
            },
        )

    def prove_durable_recovery(
        self,
        live: AIExecutionResult,
        recovered: AIExecutionResult | None,
    ) -> RequirementProof:
        live_payload = live.as_dict()
        recovered_payload = None if recovered is None else recovered.as_dict()
        subject_bound = bool(
            live.execution_id == self.subject_id
            and recovered is not None
            and recovered.execution_id == self.subject_id
        )
        passed = subject_bound and recovered_payload == live_payload
        refs = (
            "execution-result:" + live.execution_id,
            "recovery-digest:" + _digest(recovered_payload),
        )
        return self._proof(
            CompletionRequirement.DURABLE_RECOVERY,
            passed=passed,
            producer_id="execution-repository",
            evidence_refs=refs,
            details={
                "subject_bound": subject_bound,
                "live_execution_id": live.execution_id,
                "recovered_execution_id": (
                    None if recovered is None else recovered.execution_id
                ),
                "live_digest": _digest(live_payload),
                "recovered_digest": _digest(recovered_payload),
                "exact_match": passed,
            },
        )

    def prove_staged_finalization_recovery(
        self,
        *,
        staged_result: AIExecutionResult,
        recovered_result: AIExecutionResult | None,
        staged_intent_digest: str,
        intent_cleared: bool,
    ) -> RequirementProof:
        if _SHA256.fullmatch(staged_intent_digest) is None:
            raise CompletionPlaneError(
                "staged_intent_digest must be lowercase sha256"
            )
        if not isinstance(intent_cleared, bool):
            raise CompletionPlaneError("intent_cleared must be boolean")
        staged_payload = staged_result.as_dict()
        recovered_payload = (
            None
            if recovered_result is None
            else recovered_result.as_dict()
        )
        subject_bound = bool(
            staged_result.execution_id == self.subject_id
            and recovered_result is not None
            and recovered_result.execution_id == self.subject_id
        )
        exact_match = recovered_payload == staged_payload
        passed = subject_bound and exact_match and intent_cleared
        return self._proof(
            CompletionRequirement.STAGED_FINALIZATION_RECOVERY,
            passed=passed,
            producer_id="execution-repository",
            evidence_refs=(
                "finalization-intent:" + staged_intent_digest,
                "staged-result:" + _digest(staged_payload),
                "recovered-result:" + _digest(recovered_payload),
            ),
            details={
                "subject_bound": subject_bound,
                "exact_match": exact_match,
                "intent_cleared": intent_cleared,
                "staged_execution_id": staged_result.execution_id,
                "recovered_execution_id": (
                    None
                    if recovered_result is None
                    else recovered_result.execution_id
                ),
            },
        )

    def prove_replay_lineage(
        self,
        turns: Sequence[AgentTurn],
    ) -> RequirementProof:
        sequence = tuple(turns)
        contiguous = all(
            turn.turn_index == index for index, turn in enumerate(sequence)
        )
        subject_bound = bool(sequence) and all(
            turn.execution_id == self.subject_id for turn in sequence
        )
        operation_bound = bool(sequence) and len(
            {turn.operation_id for turn in sequence}
        ) == 1
        unique_turn_ids = len({turn.turn_id for turn in sequence}) == len(sequence)
        parent_linked = bool(sequence)
        for index, turn in enumerate(sequence):
            if index == 0:
                parent_linked = parent_linked and turn.parent_turn_id is None
            else:
                parent_linked = (
                    parent_linked
                    and turn.parent_turn_id == sequence[index - 1].turn_id
                )
        checkpoints_bound = bool(sequence) and all(
            bool(turn.checkpoint_ref) for turn in sequence
        )
        passed = bool(
            sequence
            and contiguous
            and subject_bound
            and operation_bound
            and unique_turn_ids
            and parent_linked
            and checkpoints_bound
        )
        refs = [
            "turn:" + turn.turn_id for turn in sequence
        ] + [
            turn.checkpoint_ref for turn in sequence if turn.checkpoint_ref
        ]
        return self._proof(
            CompletionRequirement.REPLAY_LINEAGE,
            passed=passed,
            producer_id="execution-repository",
            evidence_refs=refs,
            details={
                "turn_count": len(sequence),
                "contiguous": contiguous,
                "subject_bound": subject_bound,
                "operation_bound": operation_bound,
                "unique_turn_ids": unique_turn_ids,
                "parent_linked": parent_linked,
                "checkpoints_bound": checkpoints_bound,
            },
        )

    def prove_reproducibility(
        self,
        *,
        primary_execution_id: str,
        replay_execution_id: str,
        primary_result_digest: str,
        replay_result_digest: str,
        primary_output_digest: str,
        replay_output_digest: str,
    ) -> RequirementProof:
        primary_execution_id = _text(
            "primary_execution_id",
            primary_execution_id,
        )
        replay_execution_id = _text(
            "replay_execution_id",
            replay_execution_id,
        )
        digests = {
            "primary_result_digest": primary_result_digest,
            "replay_result_digest": replay_result_digest,
            "primary_output_digest": primary_output_digest,
            "replay_output_digest": replay_output_digest,
        }
        for name, value in digests.items():
            if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
                raise CompletionPlaneError(f"{name} must be lowercase sha256")
        subject_bound = (
            primary_execution_id == self.subject_id
            and replay_execution_id == self.subject_id
        )
        result_equal = primary_result_digest == replay_result_digest
        output_equal = primary_output_digest == replay_output_digest
        return self._proof(
            CompletionRequirement.REPRODUCIBILITY,
            passed=subject_bound and result_equal and output_equal,
            producer_id="functional-ai-runtime",
            evidence_refs=(
                "run-result:" + primary_result_digest,
                "replay-result:" + replay_result_digest,
                "run-output:" + primary_output_digest,
                "replay-output:" + replay_output_digest,
            ),
            details={
                "primary_execution_id": primary_execution_id,
                "replay_execution_id": replay_execution_id,
                "subject_bound": subject_bound,
                "result_equal": result_equal,
                "output_equal": output_equal,
            },
        )

    def prove_governed_effects(
        self,
        *,
        execution_id: str,
        tool_receipt_count: int,
        mutating_tool_count: int,
        verified_postcondition_count: int,
        receipt_refs: Iterable[str],
    ) -> RequirementProof:
        execution_id = _text("execution_id", execution_id)
        counts = (
            tool_receipt_count,
            mutating_tool_count,
            verified_postcondition_count,
        )
        if any(isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in counts):
            raise CompletionPlaneError("tool effect counts must be non-negative integers")
        passed = (
            execution_id == self.subject_id
            and mutating_tool_count <= tool_receipt_count
            and verified_postcondition_count == mutating_tool_count
        )
        return self._proof(
            CompletionRequirement.GOVERNED_EFFECTS,
            passed=passed,
            producer_id="tool-runtime",
            evidence_refs=receipt_refs,
            details={
                "execution_id": execution_id,
                "subject_bound": execution_id == self.subject_id,
                "tool_receipt_count": tool_receipt_count,
                "mutating_tool_count": mutating_tool_count,
                "verified_postcondition_count": verified_postcondition_count,
            },
        )

    def prove_independent_verification(
        self,
        result: AIExecutionResult,
    ) -> RequirementProof:
        receipt = result.verification_receipt
        receipt_mapping = dict(receipt) if isinstance(receipt, Mapping) else {}
        evidence = tuple(result.evidence_refs)
        passed = bool(
            result.execution_id == self.subject_id
            and receipt_mapping.get("outcome") == "passed"
            and receipt_mapping.get("policy_satisfied") is True
            and evidence
        )
        refs = list(evidence)
        refs.append("verification-receipt:" + _digest(receipt_mapping))
        return self._proof(
            CompletionRequirement.INDEPENDENT_VERIFICATION,
            passed=passed,
            producer_id="execution-verification-stage",
            evidence_refs=refs,
            details={
                "execution_id": result.execution_id,
                "subject_bound": result.execution_id == self.subject_id,
                "outcome": receipt_mapping.get("outcome"),
                "policy_satisfied": receipt_mapping.get("policy_satisfied"),
                "evidence_count": len(evidence),
            },
        )

    def prove_verification_binding(
        self,
        result: AIExecutionResult,
        *,
        context_digest: str,
    ) -> RequirementProof:
        if not isinstance(context_digest, str) or _SHA256.fullmatch(context_digest) is None:
            raise CompletionPlaneError("context_digest must be lowercase sha256")
        receipt = (
            dict(result.verification_receipt)
            if isinstance(result.verification_receipt, Mapping)
            else {}
        )
        candidate_digest = (
            None
            if result.final_output is None
            else hashlib.sha256(result.final_output.encode("utf-8")).hexdigest()
        )
        receipt_candidate_digest = receipt.get("candidate_digest")
        receipt_context_digest = receipt.get("context_digest")
        passed = bool(
            result.execution_id == self.subject_id
            and candidate_digest
            and receipt_candidate_digest == candidate_digest
            and receipt_context_digest == context_digest
            and receipt.get("outcome") == "passed"
            and receipt.get("policy_satisfied") is True
        )
        return self._proof(
            CompletionRequirement.VERIFICATION_BINDING,
            passed=passed,
            producer_id="execution-verification-stage",
            evidence_refs=(
                "verification-receipt:" + _digest(receipt),
                "candidate:" + (candidate_digest or _digest(None)),
                "context:" + context_digest,
            ),
            details={
                "execution_id": result.execution_id,
                "subject_bound": result.execution_id == self.subject_id,
                "candidate_digest": candidate_digest,
                "receipt_candidate_digest": receipt_candidate_digest,
                "context_digest": context_digest,
                "receipt_context_digest": receipt_context_digest,
            },
        )

    def prove_context_integrity(
        self,
        *,
        context_subject_id: str,
        problems: Sequence[str],
        height: int,
        head_hash: str,
    ) -> RequirementProof:
        context_subject_id = _text(
            "context_subject_id",
            context_subject_id,
        )
        if isinstance(height, bool) or not isinstance(height, int) or height < 0:
            raise CompletionPlaneError("context ledger height is invalid")
        if not isinstance(head_hash, str) or _SHA256.fullmatch(head_hash) is None:
            raise CompletionPlaneError("context ledger head_hash must be sha256")
        passed = (
            context_subject_id == self.subject_id
            and height > 0
            and not problems
        )
        return self._proof(
            CompletionRequirement.CONTEXT_INTEGRITY,
            passed=passed,
            producer_id="context-ledger",
            evidence_refs=("context-ledger:" + head_hash,),
            details={
                "context_subject_id": context_subject_id,
                "subject_bound": context_subject_id == self.subject_id,
                "height": height,
                "problem_count": len(problems),
                "problems": list(problems),
            },
        )

    def prove_memory_lifecycle(
        self,
        *,
        memory_id: str,
        memory_subject_id: str,
        recalled_ids: Sequence[str],
        deleted: bool,
        post_delete_recalled_ids: Sequence[str],
    ) -> RequirementProof:
        memory_id = _text("memory_id", memory_id)
        memory_subject_id = _text("memory_subject_id", memory_subject_id)
        before = tuple(str(item) for item in recalled_ids)
        after = tuple(str(item) for item in post_delete_recalled_ids)
        passed = (
            memory_subject_id == self.subject_id
            and memory_id in before
            and deleted is True
            and memory_id not in after
        )
        return self._proof(
            CompletionRequirement.MEMORY_LIFECYCLE,
            passed=passed,
            producer_id="memory-runtime",
            evidence_refs=(
                "memory:" + memory_id,
                "memory-lifecycle:" + _digest({"before": before, "after": after}),
            ),
            details={
                "memory_subject_id": memory_subject_id,
                "subject_bound": memory_subject_id == self.subject_id,
                "recalled_before_delete": memory_id in before,
                "delete_acknowledged": bool(deleted),
                "absent_after_delete": memory_id not in after,
            },
        )

    def prove_finalization_lineage(
        self,
        result: AIExecutionResult,
    ) -> RequirementProof:
        memory_refs = tuple(result.memory_refs)
        artifact_refs = tuple(result.artifact_refs)
        passed = bool(
            result.execution_id == self.subject_id
            and result.status == "completed"
            and result.stream_terminal_event
            and memory_refs
            and artifact_refs
        )
        refs = list(memory_refs) + list(artifact_refs)
        if result.stream_terminal_event:
            refs.append("stream:" + result.stream_terminal_event)
        return self._proof(
            CompletionRequirement.FINALIZATION_LINEAGE,
            passed=passed,
            producer_id="execution-finalizer",
            evidence_refs=refs,
            details={
                "execution_id": result.execution_id,
                "subject_bound": result.execution_id == self.subject_id,
                "memory_ref_count": len(memory_refs),
                "artifact_ref_count": len(artifact_refs),
                "stream_terminal_bound": result.stream_terminal_event is not None,
            },
        )

    def prove_sandbox_filesystem(
        self,
        *,
        execution_id: str,
        safe_roundtrip: bool,
        traversal_rejected: bool,
        outside_untouched: bool,
        evidence_refs: Iterable[str],
    ) -> RequirementProof:
        execution_id = _text("execution_id", execution_id)
        passed = bool(
            execution_id == self.subject_id
            and safe_roundtrip
            and traversal_rejected
            and outside_untouched
        )
        return self._proof(
            CompletionRequirement.SANDBOX_FILESYSTEM,
            passed=passed,
            producer_id="sandbox-filesystem",
            evidence_refs=evidence_refs,
            details={
                "execution_id": execution_id,
                "subject_bound": execution_id == self.subject_id,
                "safe_roundtrip": bool(safe_roundtrip),
                "traversal_rejected": bool(traversal_rejected),
                "outside_untouched": bool(outside_untouched),
            },
        )

    def prove_sandbox_process(
        self,
        *,
        execution_id: str,
        clean_environment: bool,
        shell_string_rejected: bool,
        bounded_execution: bool,
        network_fail_closed: bool,
        evidence_refs: Iterable[str],
    ) -> RequirementProof:
        execution_id = _text("execution_id", execution_id)
        passed = bool(
            execution_id == self.subject_id
            and clean_environment
            and shell_string_rejected
            and bounded_execution
            and network_fail_closed
        )
        return self._proof(
            CompletionRequirement.SANDBOX_PROCESS,
            passed=passed,
            producer_id="sandbox-process",
            evidence_refs=evidence_refs,
            details={
                "execution_id": execution_id,
                "subject_bound": execution_id == self.subject_id,
                "clean_environment": bool(clean_environment),
                "shell_string_rejected": bool(shell_string_rejected),
                "bounded_execution": bool(bounded_execution),
                "network_fail_closed": bool(network_fail_closed),
            },
        )

    def prove_injection_sanitization(
        self,
        *,
        execution_id: str,
        prompt_attack_blocked: bool,
        shell_attack_blocked: bool,
        secret_redacted: bool,
        duplicate_json_rejected: bool,
        evidence_refs: Iterable[str],
    ) -> RequirementProof:
        execution_id = _text("execution_id", execution_id)
        passed = bool(
            execution_id == self.subject_id
            and prompt_attack_blocked
            and shell_attack_blocked
            and secret_redacted
            and duplicate_json_rejected
        )
        return self._proof(
            CompletionRequirement.INJECTION_SANITIZATION,
            passed=passed,
            producer_id="sandbox-sanitization",
            evidence_refs=evidence_refs,
            details={
                "execution_id": execution_id,
                "subject_bound": execution_id == self.subject_id,
                "prompt_attack_blocked": bool(prompt_attack_blocked),
                "shell_attack_blocked": bool(shell_attack_blocked),
                "secret_redacted": bool(secret_redacted),
                "duplicate_json_rejected": bool(duplicate_json_rejected),
            },
        )

    def prove_provider_fallback_privacy(
        self,
        *,
        execution_id: str,
        required_boundary: str,
        routed_boundaries: Sequence[str],
        routed_model_ids: Sequence[str],
        evidence_refs: Iterable[str],
    ) -> RequirementProof:
        execution_id = _text("execution_id", execution_id)
        boundary = _text("required_boundary", required_boundary)
        boundaries = tuple(
            _text("routed_boundary", item) for item in routed_boundaries
        )
        models = tuple(_text("routed_model_id", item) for item in routed_model_ids)
        rank = {"local": 0, "private_remote": 1, "external": 2}
        allowed_rank = rank.get(boundary)
        all_within = bool(
            allowed_rank is not None
            and boundaries
            and len(boundaries) == len(models)
            and all(
                item in rank and rank[item] <= allowed_rank
                for item in boundaries
            )
        )
        passed = bool(
            execution_id == self.subject_id
            and all_within
        )
        return self._proof(
            CompletionRequirement.PROVIDER_FALLBACK_PRIVACY,
            passed=passed,
            producer_id="provider-router",
            evidence_refs=evidence_refs,
            details={
                "execution_id": execution_id,
                "subject_bound": execution_id == self.subject_id,
                "required_boundary": boundary,
                "routed_boundaries": list(boundaries),
                "routed_model_ids": list(models),
                "all_within_boundary": all_within,
            },
        )

    def prove_memory_poisoning_resistance(
        self,
        *,
        execution_id: str,
        valid_write_committed: bool,
        missing_provenance_denied: bool,
        conflicting_replay_rejected: bool,
        committed_subject_id: str,
        evidence_refs: Iterable[str],
    ) -> RequirementProof:
        execution_id = _text("execution_id", execution_id)
        committed_subject_id = _text(
            "committed_subject_id",
            committed_subject_id,
        )
        passed = bool(
            execution_id == self.subject_id
            and committed_subject_id == self.subject_id
            and valid_write_committed
            and missing_provenance_denied
            and conflicting_replay_rejected
        )
        return self._proof(
            CompletionRequirement.MEMORY_POISONING_RESISTANCE,
            passed=passed,
            producer_id="governed-memory-writer",
            evidence_refs=evidence_refs,
            details={
                "execution_id": execution_id,
                "subject_bound": execution_id == self.subject_id,
                "committed_subject_id": committed_subject_id,
                "memory_subject_bound": committed_subject_id == self.subject_id,
                "valid_write_committed": bool(valid_write_committed),
                "missing_provenance_denied": bool(missing_provenance_denied),
                "conflicting_replay_rejected": bool(conflicting_replay_rejected),
            },
        )

    def prove_outbound_network_boundary(
        self,
        *,
        execution_id: str,
        private_target_rejected: bool,
        mixed_dns_rejected: bool,
        peer_rebinding_rejected: bool,
        canonical_public_resolution: bool,
        evidence_refs: Iterable[str],
    ) -> RequirementProof:
        execution_id = _text("execution_id", execution_id)
        passed = bool(
            execution_id == self.subject_id
            and private_target_rejected
            and mixed_dns_rejected
            and peer_rebinding_rejected
            and canonical_public_resolution
        )
        return self._proof(
            CompletionRequirement.OUTBOUND_NETWORK_BOUNDARY,
            passed=passed,
            producer_id="outbound-network-policy",
            evidence_refs=evidence_refs,
            details={
                "execution_id": execution_id,
                "subject_bound": execution_id == self.subject_id,
                "private_target_rejected": bool(private_target_rejected),
                "mixed_dns_rejected": bool(mixed_dns_rejected),
                "peer_rebinding_rejected": bool(peer_rebinding_rejected),
                "canonical_public_resolution": bool(
                    canonical_public_resolution
                ),
            },
        )

    def prove_learning_promotion(
        self,
        receipt: PromotionReceipt,
        *,
        expected_baseline: str,
        expected_candidate: str,
        active_version: str,
        evaluation_digest: str,
        evaluator_id: str,
        bound_result_digest: str,
        failed_evaluation_rejected: bool,
        cross_experiment_rejected: bool,
    ) -> RequirementProof:
        evaluator_id = _text("evaluator_id", evaluator_id)
        if not isinstance(failed_evaluation_rejected, bool):
            raise CompletionPlaneError(
                "failed_evaluation_rejected must be boolean"
            )
        if not isinstance(cross_experiment_rejected, bool):
            raise CompletionPlaneError(
                "cross_experiment_rejected must be boolean"
            )
        expected_experiment_id = completion_learning_experiment_id(
            self.subject_id,
            bound_result_digest,
        )
        if not isinstance(evaluation_digest, str) or _SHA256.fullmatch(evaluation_digest) is None:
            raise CompletionPlaneError("evaluation_digest must be lowercase sha256")
        passed = bool(
            receipt.rollback is False
            and receipt.from_version == expected_baseline
            and receipt.to_version == expected_candidate
            and active_version == expected_candidate
            and receipt.evaluation_digest == evaluation_digest
            and receipt.experiment_id == expected_experiment_id
            and evaluator_id != "learning-promotion-pipeline"
            and failed_evaluation_rejected
            and cross_experiment_rejected
        )
        return self._proof(
            CompletionRequirement.LEARNING_PROMOTION,
            passed=passed,
            producer_id="learning-promotion-pipeline",
            evidence_refs=("learning-promotion:" + receipt.digest,),
            details={
                "from_version": receipt.from_version,
                "to_version": receipt.to_version,
                "active_version": active_version,
                "evaluation_digest": evaluation_digest,
                "evaluator_id": evaluator_id,
                "expected_experiment_id": expected_experiment_id,
                "experiment_id": receipt.experiment_id,
                "result_bound": receipt.experiment_id == expected_experiment_id,
                "evaluation_bound": (
                    receipt.evaluation_digest == evaluation_digest
                ),
                "failed_evaluation_rejected": failed_evaluation_rejected,
                "cross_experiment_rejected": cross_experiment_rejected,
                "rollback": receipt.rollback,
            },
        )

    def prove_learning_rollback(
        self,
        receipt: PromotionReceipt,
        *,
        expected_baseline: str,
        expected_candidate: str,
        active_version: str,
        promotion_receipt: PromotionReceipt,
        bound_result_digest: str,
        rollback_without_promotion_rejected: bool,
    ) -> RequirementProof:
        if not isinstance(rollback_without_promotion_rejected, bool):
            raise CompletionPlaneError(
                "rollback_without_promotion_rejected must be boolean"
            )
        expected_experiment_id = completion_learning_experiment_id(
            self.subject_id,
            bound_result_digest,
        )
        passed = bool(
            receipt.rollback is True
            and receipt.from_version == expected_candidate
            and receipt.to_version == expected_baseline
            and active_version == expected_baseline
            and bool(receipt.reason)
            and promotion_receipt.rollback is False
            and receipt.experiment_id == expected_experiment_id
            and promotion_receipt.experiment_id == expected_experiment_id
            and receipt.evaluation_digest == promotion_receipt.evaluation_digest
            and rollback_without_promotion_rejected
        )
        return self._proof(
            CompletionRequirement.LEARNING_ROLLBACK,
            passed=passed,
            producer_id="learning-promotion-pipeline",
            evidence_refs=("learning-rollback:" + receipt.digest,),
            details={
                "from_version": receipt.from_version,
                "to_version": receipt.to_version,
                "active_version": active_version,
                "reason": receipt.reason,
                "expected_experiment_id": expected_experiment_id,
                "promotion_experiment_id": promotion_receipt.experiment_id,
                "rollback_experiment_id": receipt.experiment_id,
                "result_bound": (
                    receipt.experiment_id == expected_experiment_id
                    and promotion_receipt.experiment_id == expected_experiment_id
                ),
                "promotion_evaluation_digest": promotion_receipt.evaluation_digest,
                "rollback_evaluation_digest": receipt.evaluation_digest,
                "evaluation_lineage_preserved": (
                    receipt.evaluation_digest
                    == promotion_receipt.evaluation_digest
                ),
                "rollback_without_promotion_rejected": (
                    rollback_without_promotion_rejected
                ),
                "rollback": receipt.rollback,
            },
        )


__all__ = [
    "CompletionPlaneError",
    "CompletionRequirement",
    "REQUIRED_COMPLETION_REQUIREMENTS",
    "completion_learning_experiment_id",
    "RequirementProof",
    "SystemCompletionPlane",
    "SystemCompletionReport",
]
