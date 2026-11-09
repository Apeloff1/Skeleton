"""Executable qualification for the governed effect plane."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
import tempfile
from typing import Any

from .contracts import (
    ApplyResult, BatchState, CompensationResult, CoreExecution, EffectBatchResult,
    VerificationResult, digest_json,
)
from .decoder import JsonEffectProposalSource
from .ledger import SQLiteEffectLedger
from .policy import CapabilityAuthorizer, EffectPolicy
from .registry import CallbackEffectHandler, CallbackEffectVerifier, EffectContext, EffectHandlerRegistry
from .runtime import GovernedEffectRuntime


@dataclass(slots=True)
class _Core:
    output: str

    async def run(self, request: Any) -> CoreExecution:
        return CoreExecution(
            execution_id="qual-execution-001",
            operation_id="qual-operation-001",
            tenant_id="qualification",
            output_text=self.output,
            evidence_digest=digest_json({"request": request, "core": "qualification"}),
            evidence_refs=("qual:core:001",),
        )


@dataclass(slots=True)
class _Sink:
    calls: list[str] = field(default_factory=list)

    async def commit(self, result: EffectBatchResult) -> None:
        self.calls.append(result.digest)


def _document() -> str:
    import json

    return json.dumps(
        {
            "effects": [
                {
                    "proposal_id": "set-alpha",
                    "kind": "kv.set",
                    "target": "alpha",
                    "payload": {"value": 7},
                    "required_capability": "state.write",
                    "idempotency_key": "qual-alpha-v1",
                    "postconditions": [
                        {
                            "name": "value_matches",
                            "description": "stored value equals proposal",
                        }
                    ],
                    "reversible": True,
                    "risk_class": "low",
                },
                {
                    "proposal_id": "set-beta",
                    "kind": "kv.set",
                    "target": "beta",
                    "payload": {"value": 11},
                    "required_capability": "state.write",
                    "idempotency_key": "qual-beta-v1",
                    "postconditions": [
                        {
                            "name": "value_matches",
                            "description": "stored value equals proposal",
                        }
                    ],
                    "reversible": True,
                    "risk_class": "low",
                },
            ]
        },
        sort_keys=True,
        separators=(",", ":"),
    )


async def qualify(path: str) -> dict[str, Any]:
    state: dict[str, Any] = {}

    async def apply(proposal, context: EffectContext) -> ApplyResult:
        old = state.get(proposal.target, {"__missing__": True})
        state[proposal.target] = proposal.payload["value"]
        return ApplyResult(
            executor_id="qual.kv.executor",
            status="applied",
            output={"target": proposal.target, "value": state[proposal.target]},
            compensation_token={"old": old},
            evidence_refs=(f"qual:apply:{proposal.proposal_id}",),
        )

    async def compensate(proposal, receipt, context: EffectContext) -> CompensationResult:
        token = receipt.compensation_token or {}
        old = token.get("old", {"__missing__": True})
        if hasattr(old, "get") and old.get("__missing__") is True:
            state.pop(proposal.target, None)
        else:
            state[proposal.target] = old
        return CompensationResult(
            executor_id="qual.kv.executor",
            compensated=True,
            output={"target": proposal.target},
            evidence_refs=(f"qual:rollback:{proposal.proposal_id}",),
        )

    async def verify(proposal, receipt, context: EffectContext) -> VerificationResult:
        passed = state.get(proposal.target) == proposal.payload["value"]
        return VerificationResult(
            verifier_id="qual.kv.verifier",
            passed=passed,
            postconditions={"value_matches": passed},
            observed={"actual": state.get(proposal.target)},
            reason="independent state read matched" if passed else "state mismatch",
            evidence_refs=(f"qual:verify:{proposal.proposal_id}",),
        )

    registry = EffectHandlerRegistry()
    registry.register(
        "kv.set",
        handler=CallbackEffectHandler("qual.kv.executor", apply, compensate),
        verifier=CallbackEffectVerifier("qual.kv.verifier", verify),
    )
    ledger = SQLiteEffectLedger(path)
    memory = _Sink()
    learning = _Sink()
    runtime = GovernedEffectRuntime(
        core=_Core(_document()),
        proposal_source=JsonEffectProposalSource(),
        authorizer=CapabilityAuthorizer(
            {"qualifier": frozenset({"state.write"})}
        ),
        registry=registry,
        ledger=ledger,
        policy=EffectPolicy(
            max_effects=4,
            allowed_risk_classes=frozenset({"low"}),
        ),
        memory_sink=memory,
        learning_sink=learning,
        worker_id="qualifier",
    )
    try:
        result = await runtime.execute(
            {"objective": "qualification"},
            subject_id="qualifier",
        )
        replay = await runtime.execute(
            {"objective": "qualification"},
            subject_id="qualifier",
        )
        chain = ledger.verify_chain(result.transaction_id)
        proofs = {
            "committed": result.state is BatchState.COMMITTED,
            "two_effects_verified": len(result.effects) == 2
            and all(e.verification.passed for e in result.effects),
            "executor_verifier_separated": all(
                e.execution.executor_id != e.verification.verifier_id
                for e in result.effects
            ),
            "postconditions_declared": all(
                e.proposal.postconditions for e in result.effects
            ),
            "authority_bound_to_digest": all(
                e.authorization.proposal_digest == e.proposal.digest
                for e in result.effects
            ),
            "capability_bound": all(
                e.proposal.required_capability in e.authorization.capabilities
                for e in result.effects
            ),
            "event_chain_verified": bool(chain),
            "memory_commit_only": memory.calls == [result.digest],
            "learning_commit_only": learning.calls == [result.digest],
            "idempotent_replay": replay.replayed
            and replay.state is BatchState.COMMITTED,
            "state_effective": state == {"alpha": 7, "beta": 11},
        }
        return {
            "schema_version": "skeleton.ai.effect.qualification.v1",
            "passed": all(proofs.values()),
            "proofs": proofs,
            "transaction_id": result.transaction_id,
            "result_digest": result.digest,
            "event_chain_digest": chain,
            "state": dict(state),
        }
    finally:
        ledger.close()


def run_qualification(path: str | None = None) -> dict[str, Any]:
    if path is not None:
        return asyncio.run(qualify(path))
    with tempfile.TemporaryDirectory(
        prefix="skeleton-effect-qualification-"
    ) as directory:
        return asyncio.run(
            qualify(str(Path(directory) / "effects.sqlite3"))
        )
