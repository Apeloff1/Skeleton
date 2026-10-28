"""Fail-closed compensation planning bound to the side-effect ledger."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from skeleton.contracts.canonical import canonical_json_bytes
from skeleton.ai.side_effect_ledger import EffectIdentity, EffectState, SideEffectLedger


@dataclass(frozen=True, slots=True)
class CompensationSpec:
    effect: EffectIdentity
    compensation_id: str
    action: str
    required_terminal_state: EffectState = EffectState.SUCCEEDED

    def __post_init__(self) -> None:
        if not self.compensation_id or not self.action:
            raise ValueError("compensation id and action are required")
        if self.required_terminal_state is not EffectState.SUCCEEDED:
            raise ValueError("compensation may only target succeeded effects")

    @property
    def digest(self) -> str:
        return hashlib.sha256(canonical_json_bytes({
            "effect_identity": self.effect.digest,
            "compensation_id": self.compensation_id,
            "action": self.action,
            "required_terminal_state": self.required_terminal_state.value,
        })).hexdigest()


@dataclass(frozen=True, slots=True)
class CompensationPermit:
    spec_digest: str
    effect_head_digest: str
    authority_scope: str

    @property
    def digest(self) -> str:
        return hashlib.sha256(canonical_json_bytes({
            "spec_digest": self.spec_digest,
            "effect_head_digest": self.effect_head_digest,
            "authority_scope": self.authority_scope,
        })).hexdigest()


class CompensationEngine:
    """Issues bounded permits; execution remains outside this component."""

    def __init__(self, ledger: SideEffectLedger) -> None:
        self._ledger = ledger

    def authorize(self, spec: CompensationSpec, *, authority_scope: str) -> CompensationPermit:
        if authority_scope != spec.effect.authority_scope:
            raise PermissionError("compensation authority scope mismatch")
        head = self._ledger.head(spec.effect.idempotency_key)
        if head.identity != spec.effect:
            raise PermissionError("compensation effect identity mismatch")
        if head.state is not EffectState.SUCCEEDED:
            raise PermissionError("only succeeded effects are compensable")
        return CompensationPermit(spec.digest, head.digest, authority_scope)

    def begin(self, spec: CompensationSpec, permit: CompensationPermit) -> None:
        expected = self.authorize(spec, authority_scope=permit.authority_scope)
        if permit != expected:
            raise PermissionError("stale or forged compensation permit")
        self._ledger.transition(spec.effect, EffectState.COMPENSATING, evidence_digest=permit.digest)
