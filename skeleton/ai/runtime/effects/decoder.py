"""Strict decoder for model-proposed effects.

The decoder understands proposals only. Authorization-like fields are forbidden
so model output cannot smuggle approvals or capabilities into the host plane.
"""
from __future__ import annotations

import json
from typing import Protocol, Sequence

from .contracts import CoreExecution, EffectContractError, EffectPostcondition, EffectProposal


class ProposalSource(Protocol):
    async def proposals(self, core: CoreExecution) -> Sequence[EffectProposal]: ...


class NoEffectProposalSource:
    async def proposals(self, core: CoreExecution) -> Sequence[EffectProposal]:
        return ()


class JsonEffectProposalSource:
    ROOT_FIELDS = frozenset({"effects"})
    EFFECT_FIELDS = frozenset({
        "proposal_id", "kind", "target", "payload", "required_capability",
        "idempotency_key", "postconditions", "reversible", "risk_class",
        "timeout_ms", "metadata",
    })
    FORBIDDEN_AUTHORITY_FIELDS = frozenset({
        "authorization", "authorized", "approval", "approvals", "subject_id",
        "policy_id", "allow", "decision", "capabilities", "permission",
        "principal", "signature",
    })

    def __init__(self, *, max_bytes: int = 262_144, max_effects: int = 32) -> None:
        self.max_bytes = max_bytes
        self.max_effects = max_effects

    async def proposals(self, core: CoreExecution) -> Sequence[EffectProposal]:
        raw = core.output_text
        if len(raw.encode("utf-8")) > self.max_bytes:
            raise EffectContractError("effect proposal document exceeds byte limit")
        try:
            doc = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise EffectContractError("effect mode requires exact JSON output") from exc
        if not isinstance(doc, dict):
            raise EffectContractError("effect document must be an object")
        unknown_root = set(doc) - self.ROOT_FIELDS
        if unknown_root:
            raise EffectContractError(f"unknown root fields: {sorted(unknown_root)}")
        effects = doc.get("effects", [])
        if not isinstance(effects, list):
            raise EffectContractError("effects must be a list")
        if len(effects) > self.max_effects:
            raise EffectContractError("too many effect proposals")
        built: list[EffectProposal] = []
        for index, item in enumerate(effects):
            if not isinstance(item, dict):
                raise EffectContractError(f"effect[{index}] must be an object")
            forbidden = set(item) & self.FORBIDDEN_AUTHORITY_FIELDS
            if forbidden:
                raise EffectContractError(f"authority fields forbidden in proposal: {sorted(forbidden)}")
            unknown = set(item) - self.EFFECT_FIELDS
            if unknown:
                raise EffectContractError(f"unknown effect fields: {sorted(unknown)}")
            required = {
                "proposal_id", "kind", "target", "payload", "required_capability",
                "idempotency_key", "postconditions",
            }
            missing = required - set(item)
            if missing:
                raise EffectContractError(f"missing effect fields: {sorted(missing)}")
            if not isinstance(item["payload"], dict):
                raise EffectContractError("payload must be an object")
            pcs_raw = item["postconditions"]
            if not isinstance(pcs_raw, list):
                raise EffectContractError("postconditions must be a list")
            pcs: list[EffectPostcondition] = []
            for pc in pcs_raw:
                if not isinstance(pc, dict) or set(pc) - {"name", "description", "required"}:
                    raise EffectContractError("invalid postcondition object")
                if "name" not in pc or "description" not in pc:
                    raise EffectContractError("postcondition requires name and description")
                pcs.append(EffectPostcondition(
                    name=str(pc["name"]),
                    description=str(pc["description"]),
                    required=bool(pc.get("required", True)),
                ))
            built.append(EffectProposal(
                proposal_id=str(item["proposal_id"]),
                tenant_id=core.tenant_id,
                operation_id=core.operation_id,
                kind=str(item["kind"]),
                target=str(item["target"]),
                payload=item["payload"],
                required_capability=str(item["required_capability"]),
                idempotency_key=str(item["idempotency_key"]),
                postconditions=tuple(pcs),
                reversible=bool(item.get("reversible", True)),
                risk_class=str(item.get("risk_class", "medium")),
                timeout_ms=int(item.get("timeout_ms", 30_000)),
                metadata=item.get("metadata", {}),
            ))
        return tuple(built)
