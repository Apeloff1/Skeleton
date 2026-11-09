"""Replayable saga coordinator contract for VOL-380.

This coordinator advances durable intent only after the caller supplies ledger
evidence for the exact expected effect. It never invokes external actions.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from skeleton.contracts.canonical import canonical_json_bytes
from skeleton.ai.side_effect_ledger import EffectIdentity, EffectState, SideEffectLedger


@dataclass(frozen=True, slots=True)
class SagaStep:
    step_id: str
    effect: EffectIdentity

    def __post_init__(self) -> None:
        if not self.step_id:
            raise ValueError("step_id required")


@dataclass(frozen=True, slots=True)
class SagaPlan:
    saga_id: str
    authority_scope: str
    steps: tuple[SagaStep, ...]

    def __post_init__(self) -> None:
        if not self.saga_id or not self.authority_scope or not self.steps:
            raise ValueError("saga identity, scope and steps are required")
        ids = [step.step_id for step in self.steps]
        keys = [step.effect.idempotency_key for step in self.steps]
        if len(ids) != len(set(ids)) or len(keys) != len(set(keys)):
            raise ValueError("saga steps and effect keys must be unique")
        if any(step.effect.authority_scope != self.authority_scope for step in self.steps):
            raise PermissionError("saga effect authority scope mismatch")

    @property
    def digest(self) -> str:
        return hashlib.sha256(canonical_json_bytes({
            "saga_id": self.saga_id,
            "authority_scope": self.authority_scope,
            "steps": [{"step_id": s.step_id, "effect": s.effect.digest} for s in self.steps],
        })).hexdigest()


@dataclass(frozen=True, slots=True)
class SagaCheckpoint:
    plan_digest: str
    cursor: int
    completed_effect_heads: tuple[str, ...]
    prior_checkpoint_digest: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.cursor, bool) or not isinstance(self.cursor, int) or self.cursor < 0:
            raise ValueError("cursor must be non-negative")

    @property
    def digest(self) -> str:
        return hashlib.sha256(canonical_json_bytes({
            "plan_digest": self.plan_digest,
            "cursor": self.cursor,
            "completed_effect_heads": list(self.completed_effect_heads),
            "prior_checkpoint_digest": self.prior_checkpoint_digest,
        })).hexdigest()


class SagaCoordinator:
    def __init__(self, plan: SagaPlan, ledger: SideEffectLedger) -> None:
        self.plan = plan
        self.ledger = ledger

    def initial(self) -> SagaCheckpoint:
        return SagaCheckpoint(self.plan.digest, 0, ())

    def advance(self, checkpoint: SagaCheckpoint) -> SagaCheckpoint:
        if checkpoint.plan_digest != self.plan.digest:
            raise PermissionError("checkpoint belongs to another saga plan")
        if checkpoint.cursor >= len(self.plan.steps):
            return checkpoint
        if checkpoint.cursor != len(checkpoint.completed_effect_heads):
            raise ValueError("checkpoint cursor/evidence mismatch")
        step = self.plan.steps[checkpoint.cursor]
        head = self.ledger.head(step.effect.idempotency_key)
        if head.identity != step.effect:
            raise PermissionError("saga effect identity mismatch")
        if head.state is EffectState.UNKNOWN or head.state is EffectState.RECONCILIATION_REQUIRED:
            raise PermissionError("saga blocked on effect reconciliation")
        if head.state is not EffectState.SUCCEEDED:
            raise PermissionError("saga cannot advance before successful effect evidence")
        return SagaCheckpoint(
            self.plan.digest,
            checkpoint.cursor + 1,
            checkpoint.completed_effect_heads + (head.digest,),
            checkpoint.digest,
        )

    def verify_replay(self, checkpoint: SagaCheckpoint) -> None:
        if checkpoint.plan_digest != self.plan.digest:
            raise PermissionError("replay plan digest mismatch")
        if checkpoint.cursor != len(checkpoint.completed_effect_heads) or checkpoint.cursor > len(self.plan.steps):
            raise ValueError("invalid replay cursor")
        for index, digest in enumerate(checkpoint.completed_effect_heads):
            step = self.plan.steps[index]
            history = self.ledger.history(step.effect.idempotency_key)
            if not any(event.digest == digest and event.state is EffectState.SUCCEEDED for event in history):
                raise PermissionError("checkpoint evidence missing from ledger")
