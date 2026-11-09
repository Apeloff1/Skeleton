"""Provider-independent VS-002 autonomous engineering transaction.

The runtime composes P2 local inference with P3 workflow, safe-change, autonomy,
transaction, review/verification and effect-ledger primitives.  One bounded run
may edit exactly one declared repository path.  Failed independent review or
verification triggers compensating rollback before the run returns.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Awaitable, Callable, Iterable, Mapping

from skeleton.ai.runtime.inference import LocalModelAdapter
from skeleton.provider_runtime import ProviderRequest
from skeleton.repo_machine.model import RepositoryModel
from skeleton.repo_machine.review import (
    ReviewRoute,
    ReviewRoutingError,
    ReviewVerdict,
    VerificationVerdict,
    validate_verdicts,
)
from skeleton.repo_machine.transaction import LeaseRegistry, PatchReceipt

from .autonomy import AutonomyGrant, AutonomyState, authorize_change_plan
from .effects import EffectLedger, EffectLedgerError
from .safe_change import (
    SafeChangePlan,
    acquire_change_lease,
    open_change_transaction,
    plan_safe_change,
)
from .workflow import CompiledWorkflow


ReviewHook = Callable[
    [SafeChangePlan, PatchReceipt],
    ReviewVerdict | Awaitable[ReviewVerdict],
]
VerificationHook = Callable[
    [SafeChangePlan, PatchReceipt],
    VerificationVerdict | Awaitable[VerificationVerdict],
]


class EngineeringAgentError(RuntimeError):
    pass


def _id(value: str, field: str, *, maximum: int = 192) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be text")
    text = value.strip()
    if not text or len(text) > maximum:
        raise ValueError(f"{field} must be non-empty bounded text")
    return text


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _aware(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return value.astimezone(timezone.utc)


async def _await(value):
    return await value if inspect.isawaitable(value) else value


def _safe_target(root: Path, relative: str) -> Path:
    pure = PurePosixPath(relative)
    if (
        pure.is_absolute()
        or not pure.parts
        or any(part in {"", ".", ".."} for part in pure.parts)
        or "\\" in relative
        or "\\x00" in relative
    ):
        raise EngineeringAgentError("proposal path is not canonical")
    candidate = root.joinpath(*pure.parts)
    cursor = root
    for part in pure.parts[:-1]:
        cursor = cursor / part
        if cursor.is_symlink():
            raise EngineeringAgentError("proposal parent crosses symlink")
    if candidate.is_symlink():
        raise EngineeringAgentError("proposal target must not be a symlink")
    resolved = candidate.resolve(strict=False)
    if not resolved.is_relative_to(root):
        raise EngineeringAgentError("proposal target escapes repository root")
    if not candidate.is_file():
        raise EngineeringAgentError("proposal target must already exist")
    return candidate


def _patch_digest(receipt: PatchReceipt) -> str:
    return _json_digest(
        {
            "transaction_id": receipt.transaction_id,
            "lease_id": receipt.lease_id,
            "owner_id": receipt.owner_id,
            "entries": [
                {
                    "path": entry.path,
                    "before_sha256": entry.before_sha256,
                    "after_sha256": entry.after_sha256,
                }
                for entry in receipt.entries
            ],
            "committed_at": receipt.committed_at,
        }
    )


@dataclass(frozen=True, slots=True)
class EngineeringObjective:
    request_id: str
    objective: str
    task_id: str
    allowed_paths: tuple[str, ...]
    max_source_bytes: int = 128 * 1024
    max_patch_bytes: int = 256 * 1024

    def __post_init__(self) -> None:
        object.__setattr__(self, "request_id", _id(self.request_id, "request_id"))
        object.__setattr__(self, "objective", _id(self.objective, "objective", maximum=4096))
        object.__setattr__(self, "task_id", _id(self.task_id, "task_id"))
        paths = tuple(sorted({_id(item, "allowed_path", maximum=1024) for item in self.allowed_paths}))
        if not paths or len(paths) > 32:
            raise ValueError("allowed_paths must contain 1..32 paths")
        object.__setattr__(self, "allowed_paths", paths)
        for field, maximum in (
            ("max_source_bytes", 2 * 1024 * 1024),
            ("max_patch_bytes", 2 * 1024 * 1024),
        ):
            value = getattr(self, field)
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
                raise ValueError(f"{field} must be a positive bounded integer")


@dataclass(frozen=True, slots=True)
class EngineeringRunResult:
    request_id: str
    status: str
    path: str
    before_sha256: str
    after_sha256: str
    model_id: str
    model_digest: str
    plan_digest: str
    autonomy_receipt_digest: str
    effect_id: str
    effect_status: str
    patch_receipt_digest: str
    compensation_receipt_digest: str | None
    review_evidence_refs: tuple[str, ...]
    verification_evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.status not in {"completed", "compensated"}:
            raise ValueError("unsupported engineering run status")
        for field in (
            "before_sha256",
            "after_sha256",
            "model_digest",
            "plan_digest",
            "autonomy_receipt_digest",
            "patch_receipt_digest",
        ):
            value = getattr(self, field)
            if len(value) != 64:
                raise ValueError(f"{field} must be sha256")
        if self.compensation_receipt_digest is not None and len(self.compensation_receipt_digest) != 64:
            raise ValueError("compensation_receipt_digest must be sha256")


class EngineeringAgentRuntime:
    def __init__(
        self,
        *,
        repository_root: str | Path,
        repository_model: RepositoryModel,
        workflow: CompiledWorkflow,
        local_model: LocalModelAdapter,
        effect_ledger: EffectLedger,
        lease_registry: LeaseRegistry,
        autonomy_grant: AutonomyGrant,
        review_hook: ReviewHook,
        verification_hook: VerificationHook,
        reviewer_candidates: Iterable[str],
        verifier_candidates: Iterable[str],
    ) -> None:
        root = Path(repository_root).resolve()
        if not root.is_dir():
            raise ValueError("repository_root must be a directory")
        if not isinstance(repository_model, RepositoryModel):
            raise TypeError("repository_model must be RepositoryModel")
        if not isinstance(workflow, CompiledWorkflow):
            raise TypeError("workflow must be CompiledWorkflow")
        if not isinstance(local_model, LocalModelAdapter):
            raise TypeError("VS-002 requires LocalModelAdapter")
        if local_model.provider_id != "local":
            raise ValueError("VS-002 requires provider-independent local model")
        if not isinstance(effect_ledger, EffectLedger):
            raise TypeError("effect_ledger must be EffectLedger")
        if not isinstance(lease_registry, LeaseRegistry):
            raise TypeError("lease_registry must be LeaseRegistry")
        if not isinstance(autonomy_grant, AutonomyGrant):
            raise TypeError("autonomy_grant must be AutonomyGrant")
        if not callable(review_hook) or not callable(verification_hook):
            raise TypeError("independent review and verification hooks are required")
        self.root = root
        self.repository_model = repository_model
        self.workflow = workflow
        self.local_model = local_model
        self.effect_ledger = effect_ledger
        self.lease_registry = lease_registry
        self.grant = autonomy_grant
        self.review_hook = review_hook
        self.verification_hook = verification_hook
        self.reviewers = tuple(reviewer_candidates)
        self.verifiers = tuple(verifier_candidates)

    async def execute(
        self,
        objective: EngineeringObjective,
        state: AutonomyState,
        *,
        now: datetime,
        authorization_evidence_refs: Iterable[str] = (),
    ) -> tuple[EngineeringRunResult, AutonomyState]:
        instant = _aware(now)
        if objective.task_id not in self.workflow.task_map:
            raise EngineeringAgentError("objective task is not in compiled workflow")
        task = self.workflow.task_map[objective.task_id]
        if task.effect_class not in {"write", "external"}:
            raise EngineeringAgentError("engineering objective must target an effectful task")
        if state.actor_id != self.grant.actor_id:
            raise EngineeringAgentError("autonomy state actor mismatch")

        sources: list[dict[str, str]] = []
        for relative in objective.allowed_paths:
            target = _safe_target(self.root, relative)
            raw = target.read_bytes()
            if len(raw) > objective.max_source_bytes:
                raise EngineeringAgentError("source exceeds objective read bound")
            try:
                content = raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise EngineeringAgentError("engineering source must be UTF-8 text") from exc
            sources.append(
                {
                    "path": relative,
                    "sha256": _sha(raw),
                    "content": content,
                }
            )

        prompt = json.dumps(
            {
                "objective": objective.objective,
                "task_id": objective.task_id,
                "allowed_sources": sources,
                "required_output": {
                    "path": "one path from allowed_sources",
                    "expected_sha256": "exact current source digest",
                    "content": "complete replacement UTF-8 text",
                },
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        response = await self.local_model.generate(
            ProviderRequest(
                instructions=(
                    "Act as a bounded autonomous engineering planner. "
                    "Return structured_output only. Do not request network access. "
                    "Choose exactly one allowed path and provide a complete replacement."
                ),
                prompt=prompt,
                max_output_tokens=4096,
            )
        )
        if response.provider != "local":
            raise EngineeringAgentError("VS-002 crossed into hosted provider")
        proposal = response.structured_output
        if not isinstance(proposal, Mapping):
            raise EngineeringAgentError("local model did not return structured change proposal")
        relative = proposal.get("path")
        content = proposal.get("content")
        expected = proposal.get("expected_sha256")
        if not isinstance(relative, str) or relative not in objective.allowed_paths:
            raise EngineeringAgentError("proposal path is outside objective allowance")
        if not isinstance(content, str) or not content:
            raise EngineeringAgentError("proposal content must be non-empty text")
        encoded = content.encode("utf-8")
        if len(encoded) > objective.max_patch_bytes:
            raise EngineeringAgentError("proposal exceeds patch byte bound")
        if not isinstance(expected, str) or len(expected) != 64:
            raise EngineeringAgentError("proposal expected_sha256 is invalid")

        target = _safe_target(self.root, relative)
        original = target.read_bytes()
        before = _sha(original)
        if before != expected:
            raise EngineeringAgentError("proposal source digest is stale")

        plan = plan_safe_change(
            self.workflow,
            self.repository_model,
            task_id=objective.task_id,
            changed_paths=(relative,),
            author_id=state.actor_id,
            reviewer_candidates=self.reviewers,
            verifier_candidates=self.verifiers,
        )
        decision, next_state = authorize_change_plan(
            self.grant,
            state,
            plan,
            capability="repo.write",
            now=instant,
            evidence_refs=authorization_evidence_refs,
        )
        if not decision.permitted:
            raise EngineeringAgentError(
                f"autonomy denied engineering change: {decision.reason_code}"
            )

        proposal_digest = _json_digest(
            {
                "request_id": objective.request_id,
                "path": relative,
                "expected_sha256": expected,
                "content_sha256": _sha(encoded),
                "plan_digest": plan.plan_digest,
                "model_id": response.model,
                "model_digest": self.local_model.engine.model.model_digest,
            }
        )
        effect_id = "eng-" + hashlib.sha256(
            objective.request_id.encode("utf-8")
        ).hexdigest()[:32]
        effect = self.effect_ledger.reserve(
            effect_id=effect_id,
            operation_id=objective.request_id,
            effect_kind="repository.patch",
            resource_ref=relative,
            idempotency_key="vs002:" + objective.request_id,
            request_digest=proposal_digest,
            compensable=True,
            now=instant,
        )
        if effect.status != "reserved":
            raise EngineeringAgentError(
                f"engineering effect already exists in terminal state: {effect.status}"
            )

        lease = acquire_change_lease(plan, self.lease_registry)
        patch_receipt: PatchReceipt | None = None
        patch_digest: str | None = None
        try:
            transaction = open_change_transaction(
                self.root,
                plan,
                self.lease_registry,
                lease,
            )
            transaction.stage_text(
                relative,
                content,
                expected_sha256=before,
            )
            patch_receipt = transaction.commit()
            patch_digest = _patch_digest(patch_receipt)
            self.effect_ledger.mark_applied(
                effect_id,
                receipt_digest=patch_digest,
                now=instant,
            )

            review = await _await(self.review_hook(plan, patch_receipt))
            verification = await _await(
                self.verification_hook(plan, patch_receipt)
            )
            if not isinstance(review, ReviewVerdict):
                raise EngineeringAgentError("review hook returned invalid verdict")
            if not isinstance(verification, VerificationVerdict):
                raise EngineeringAgentError("verification hook returned invalid verdict")
            route = ReviewRoute(
                author_id=plan.author_id,
                reviewer_id=plan.reviewer_id,
                verifier_id=plan.verifier_id,
            )
            try:
                validate_verdicts(route, review, verification)
            except ReviewRoutingError:
                rollback = open_change_transaction(
                    self.root,
                    plan,
                    self.lease_registry,
                    lease,
                )
                rollback.stage_bytes(
                    relative,
                    original,
                    expected_sha256=_sha(encoded),
                )
                rollback_receipt = rollback.commit()
                compensation_digest = _patch_digest(rollback_receipt)
                compensated = self.effect_ledger.mark_compensated(
                    effect_id,
                    compensation_digest=compensation_digest,
                    now=instant,
                )
                return (
                    EngineeringRunResult(
                        request_id=objective.request_id,
                        status="compensated",
                        path=relative,
                        before_sha256=before,
                        after_sha256=_sha(encoded),
                        model_id=response.model,
                        model_digest=self.local_model.engine.model.model_digest,
                        plan_digest=plan.plan_digest,
                        autonomy_receipt_digest=decision.receipt_digest,
                        effect_id=effect_id,
                        effect_status=compensated.status,
                        patch_receipt_digest=patch_digest,
                        compensation_receipt_digest=compensation_digest,
                        review_evidence_refs=review.evidence_refs,
                        verification_evidence_refs=verification.evidence_refs,
                    ),
                    next_state,
                )

            applied = self.effect_ledger.get(effect_id)
            if applied is None or applied.status != "applied":
                raise EngineeringAgentError("effect ledger lost applied state")
            actual_after = _sha(target.read_bytes())
            expected_after = _sha(encoded)
            if actual_after != expected_after:
                raise EngineeringAgentError("repository state diverged after verified patch")
            return (
                EngineeringRunResult(
                    request_id=objective.request_id,
                    status="completed",
                    path=relative,
                    before_sha256=before,
                    after_sha256=expected_after,
                    model_id=response.model,
                    model_digest=self.local_model.engine.model.model_digest,
                    plan_digest=plan.plan_digest,
                    autonomy_receipt_digest=decision.receipt_digest,
                    effect_id=effect_id,
                    effect_status=applied.status,
                    patch_receipt_digest=patch_digest,
                    compensation_receipt_digest=None,
                    review_evidence_refs=review.evidence_refs,
                    verification_evidence_refs=verification.evidence_refs,
                ),
                next_state,
            )
        except Exception:
            current = self.effect_ledger.get(effect_id)
            if current is not None and current.status == "reserved":
                self.effect_ledger.mark_failed(
                    effect_id,
                    error_code="engineering_execution_failed",
                    now=instant,
                )
            raise
        finally:
            self.lease_registry.release(lease.lease_id, plan.author_id)


__all__ = [
    "EngineeringAgentError",
    "EngineeringAgentRuntime",
    "EngineeringObjective",
    "EngineeringRunResult",
]
