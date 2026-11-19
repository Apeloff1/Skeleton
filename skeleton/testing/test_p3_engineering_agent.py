from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import threading

import pytest

from skeleton.ai.runtime.autonomous_engineering.agent import (
    EngineeringAgentError,
    EngineeringAgentRuntime,
    EngineeringObjective,
)
from skeleton.ai.runtime.autonomous_engineering.autonomy import (
    AutonomyGrant,
    AutonomyLevel,
    AutonomyState,
)
from skeleton.ai.runtime.autonomous_engineering.effects import EffectLedger
from skeleton.ai.runtime.autonomous_engineering.workflow import WorkflowCompiler
from skeleton.ai.runtime.inference import (
    CallableLocalModel,
    LocalInferenceEngine,
    LocalInferenceRequest,
    LocalInferenceResult,
    LocalModelAdapter,
)
from skeleton.repo_machine.model import FileRecord, RepositoryModel, SubsystemRecord
from skeleton.repo_machine.review import ReviewVerdict, VerificationVerdict
from skeleton.repo_machine.transaction import LeaseRegistry


NOW = datetime(2026, 10, 2, 4, 30, tzinfo=timezone.utc)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _workflow():
    return WorkflowCompiler().compile(
        {
            "workflow_id": "vs002.fixture",
            "version": "v1",
            "tasks": [
                {
                    "task_id": "edit",
                    "kind": "code",
                    "objective": "Apply one governed edit.",
                    "effect_class": "write",
                    "approval_required": True,
                    "required_capabilities": ["repo.write"],
                }
            ],
        }
    )


def _model(content: bytes) -> RepositoryModel:
    return RepositoryModel(
        schema_version=1,
        repository="fixture",
        files=(
            FileRecord(
                path="skeleton/core.py",
                zone="skeleton",
                owner="core",
                kind="source",
                language="python",
                size=len(content),
                lines=1,
                sha256=_sha(content),
            ),
        ),
        subsystems=(
            SubsystemRecord(
                name="skeleton",
                owner="core",
                criticality="medium",
                file_count=1,
                code_files=1,
                test_files=0,
                workflow_files=0,
                total_lines=1,
                total_bytes=len(content),
            ),
        ),
        edges=(),
        findings=(),
    )


def _local_model(before: bytes, *, path: str = "skeleton/core.py") -> LocalModelAdapter:
    digest = _sha(b"vs002-local-engineering-weights")

    def runner(
        request: LocalInferenceRequest,
        cancel: threading.Event,
    ) -> LocalInferenceResult:
        assert not cancel.is_set()
        assert "allowed_sources" in request.prompt
        return LocalInferenceResult(
            text=None,
            model_id="vs002-local-engineer",
            model_digest=digest,
            input_tokens=10,
            output_tokens=8,
            response_id="local:vs002-proposal",
            structured_output={
                "path": path,
                "expected_sha256": _sha(before),
                "content": "value = 2\n",
            },
        )

    return LocalModelAdapter(
        LocalInferenceEngine(
            CallableLocalModel(
                model_id="vs002-local-engineer",
                model_digest=digest,
                runner=runner,
            )
        )
    )


def _grant() -> AutonomyGrant:
    return AutonomyGrant(
        grant_id="grant-vs002",
        actor_id="agent",
        max_level=AutonomyLevel.WRITE,
        capabilities=("repo.write",),
        max_actions=4,
        max_risk_score=100,
        issued_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(hours=1),
        evidence_refs=("approval:vs002",),
    )


def _state() -> AutonomyState:
    return AutonomyState(
        actor_id="agent",
        level=AutonomyLevel.WRITE,
        revision=1,
        last_receipt_digest=_sha(b"escalation"),
    )


def _review(plan, _receipt):
    return ReviewVerdict(
        reviewer_id=plan.reviewer_id,
        decision="approve",
        evidence_refs=("review:approved",),
        reviewed_at_utc="2026-10-02T04:30:01Z",
    )


def _verify(plan, _receipt):
    return VerificationVerdict(
        verifier_id=plan.verifier_id,
        passed=True,
        evidence_refs=("verify:passed",),
        verified_at_utc="2026-10-02T04:30:02Z",
    )


def _runtime(tmp_path, before: bytes, *, model_path: str = "skeleton/core.py", verification=_verify):
    root = tmp_path / "repo"
    (root / "skeleton").mkdir(parents=True)
    (root / "skeleton/core.py").write_bytes(before)
    runtime = EngineeringAgentRuntime(
        repository_root=root,
        repository_model=_model(before),
        workflow=_workflow(),
        local_model=_local_model(before, path=model_path),
        effect_ledger=EffectLedger(tmp_path / "effects.sqlite3"),
        lease_registry=LeaseRegistry(),
        autonomy_grant=_grant(),
        review_hook=_review,
        verification_hook=verification,
        reviewer_candidates=("reviewer",),
        verifier_candidates=("verifier",),
    )
    return root, runtime


@pytest.mark.asyncio
async def test_vs002_local_model_to_verified_transaction(tmp_path) -> None:
    before = b"value = 1\n"
    root, runtime = _runtime(tmp_path, before)
    result, state = await runtime.execute(
        EngineeringObjective(
            request_id="run-1",
            objective="Update the fixture value safely.",
            task_id="edit",
            allowed_paths=("skeleton/core.py",),
        ),
        _state(),
        now=NOW,
        authorization_evidence_refs=("evidence:plan-reviewed",),
    )
    assert result.status == "completed"
    assert result.effect_status == "applied"
    assert result.model_id == "vs002-local-engineer"
    assert (root / "skeleton/core.py").read_text() == "value = 2\n"
    assert state.actions_used == 1


@pytest.mark.asyncio
async def test_vs002_rejects_model_path_outside_allowance(tmp_path) -> None:
    before = b"value = 1\n"
    root, runtime = _runtime(tmp_path, before, model_path="outside.py")
    with pytest.raises(EngineeringAgentError, match="outside objective allowance"):
        await runtime.execute(
            EngineeringObjective(
                request_id="run-2",
                objective="Attempt unsafe path.",
                task_id="edit",
                allowed_paths=("skeleton/core.py",),
            ),
            _state(),
            now=NOW,
        )
    assert (root / "skeleton/core.py").read_bytes() == before


@pytest.mark.asyncio
async def test_failed_verification_compensates_repository_change(tmp_path) -> None:
    before = b"value = 1\n"

    def blocked(plan, _receipt):
        return VerificationVerdict(
            verifier_id=plan.verifier_id,
            passed=False,
            evidence_refs=("verify:block",),
            verified_at_utc="2026-10-02T04:30:02Z",
        )

    root, runtime = _runtime(tmp_path, before, verification=blocked)
    result, state = await runtime.execute(
        EngineeringObjective(
            request_id="run-3",
            objective="Change then independently block.",
            task_id="edit",
            allowed_paths=("skeleton/core.py",),
        ),
        _state(),
        now=NOW,
    )
    assert result.status == "compensated"
    assert result.effect_status == "compensated"
    assert result.compensation_receipt_digest is not None
    assert (root / "skeleton/core.py").read_bytes() == before
    assert state.actions_used == 1


@pytest.mark.asyncio
async def test_autonomy_denial_prevents_mutation(tmp_path) -> None:
    before = b"value = 1\n"
    root, runtime = _runtime(tmp_path, before)
    with pytest.raises(EngineeringAgentError, match="autonomy denied"):
        await runtime.execute(
            EngineeringObjective(
                request_id="run-4",
                objective="No write level.",
                task_id="edit",
                allowed_paths=("skeleton/core.py",),
            ),
            AutonomyState("agent"),
            now=NOW,
        )
    assert (root / "skeleton/core.py").read_bytes() == before
