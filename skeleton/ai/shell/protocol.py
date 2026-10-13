"""Bounded provider-neutral protocol for model-proposed shell plans."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from types import MappingProxyType
from typing import Any, Mapping

from skeleton.shells.ai.types import AIAction, AIIntent, AIPlanProposal

AI_MODEL_PROTOCOL_VERSION = 1
_MAX_RESPONSE_BYTES = 2 * 1024 * 1024
_MAX_ACTIONS = 256
_MAX_ASSUMPTIONS = 64


class ModelProtocolError(ValueError):
    pass


@dataclass(frozen=True)
class AIModelRequest:
    request_id: str
    intent: AIIntent
    tool_catalog_digest: str
    policy_fingerprint: str
    tool_cards: tuple[Mapping[str, object], ...]
    prior_observations: tuple[Mapping[str, object], ...] = ()
    protocol_version: int = AI_MODEL_PROTOCOL_VERSION

    def __post_init__(self) -> None:
        if not self.request_id or len(self.request_id) > 160:
            raise ValueError("invalid request_id")
        if len(self.tool_catalog_digest) != 64 or len(self.policy_fingerprint) != 64:
            raise ValueError("request digests must be SHA-256 hex strings")
        if self.protocol_version != AI_MODEL_PROTOCOL_VERSION:
            raise ValueError("unsupported AI model protocol version")
        cards = tuple(MappingProxyType(dict(item)) for item in self.tool_cards)
        observations = tuple(MappingProxyType(dict(item)) for item in self.prior_observations)
        if len(cards) > 4096:
            raise ValueError("too many tool cards")
        if len(observations) > 128:
            raise ValueError("too many prior observations")
        object.__setattr__(self, "tool_cards", cards)
        object.__setattr__(self, "prior_observations", observations)

    def to_dict(self) -> dict[str, object]:
        return {
            "protocol_version": self.protocol_version,
            "request_id": self.request_id,
            "intent": self.intent.to_dict(),
            "tool_catalog_digest": self.tool_catalog_digest,
            "policy_fingerprint": self.policy_fingerprint,
            "tool_cards": [dict(item) for item in self.tool_cards],
            "prior_observations": [dict(item) for item in self.prior_observations],
        }


@dataclass(frozen=True)
class AIModelResponse:
    request_id: str
    proposal: AIPlanProposal
    warnings: tuple[str, ...] = ()
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.request_id or len(self.request_id) > 160:
            raise ValueError("invalid response request_id")
        warnings = tuple(self.warnings)
        if len(warnings) > 64 or any(not isinstance(item, str) or len(item) > 1024 for item in warnings):
            raise ValueError("invalid model warnings")
        metadata = dict(self.metadata)
        if len(metadata) > 64:
            raise ValueError("too many response metadata fields")
        if any(
            not isinstance(key, str)
            or not isinstance(value, str)
            or len(key) > 128
            or len(value) > 512
            for key, value in metadata.items()
        ):
            raise ValueError("invalid response metadata")
        object.__setattr__(self, "warnings", warnings)
        object.__setattr__(self, "metadata", MappingProxyType(metadata))

    def to_dict(self) -> dict[str, object]:
        return {
            "protocol_version": AI_MODEL_PROTOCOL_VERSION,
            "request_id": self.request_id,
            "proposal": self.proposal.to_dict(),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
        }


def _string_list(value: Any, *, name: str, max_items: int, max_length: int) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or len(value) > max_items:
        raise ModelProtocolError(f"{name} must be a bounded list")
    result = []
    for item in value:
        if not isinstance(item, str) or len(item) > max_length:
            raise ModelProtocolError(f"{name} contains invalid string")
        result.append(item)
    return tuple(result)


def _parse_action(raw: Any) -> AIAction:
    if not isinstance(raw, dict):
        raise ModelProtocolError("action must be an object")
    allowed = {
        "action_id",
        "command",
        "args",
        "cwd",
        "environment_refs",
        "timeout_seconds",
        "depends_on",
        "continue_on_failure",
        "purpose",
    }
    unknown = set(raw) - allowed
    if unknown:
        raise ModelProtocolError(f"unknown action field: {sorted(unknown)[0]}")
    args = raw.get("args", [])
    if not isinstance(args, list):
        raise ModelProtocolError("action args must be a list")
    env = raw.get("environment_refs", {})
    if not isinstance(env, dict):
        raise ModelProtocolError("environment_refs must be an object")
    depends = _string_list(raw.get("depends_on", []), name="depends_on", max_items=256, max_length=160)
    return AIAction(
        action_id=raw.get("action_id", ""),
        command=raw.get("command", ""),
        args=tuple(args),
        cwd=raw.get("cwd"),
        environment_refs=env,
        timeout_seconds=raw.get("timeout_seconds"),
        depends_on=frozenset(depends),
        continue_on_failure=bool(raw.get("continue_on_failure", False)),
        purpose=raw.get("purpose", ""),
    )


def parse_model_response(value: Mapping[str, object] | bytes | str) -> AIModelResponse:
    if isinstance(value, bytes):
        if len(value) > _MAX_RESPONSE_BYTES:
            raise ModelProtocolError("model response exceeds byte limit")
        try:
            raw = json.loads(value.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ModelProtocolError("model response is not valid UTF-8 JSON") from exc
    elif isinstance(value, str):
        encoded = value.encode("utf-8")
        if len(encoded) > _MAX_RESPONSE_BYTES:
            raise ModelProtocolError("model response exceeds byte limit")
        try:
            raw = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ModelProtocolError("model response is not valid JSON") from exc
    else:
        raw = dict(value)

    if not isinstance(raw, dict):
        raise ModelProtocolError("model response must be an object")
    allowed = {"protocol_version", "request_id", "proposal", "warnings", "metadata"}
    unknown = set(raw) - allowed
    if unknown:
        raise ModelProtocolError(f"unknown response field: {sorted(unknown)[0]}")
    if raw.get("protocol_version") != AI_MODEL_PROTOCOL_VERSION:
        raise ModelProtocolError("unsupported model response protocol version")

    proposal_raw = raw.get("proposal")
    if not isinstance(proposal_raw, dict):
        raise ModelProtocolError("proposal must be an object")
    proposal_allowed = {
        "proposal_id",
        "intent_id",
        "actions",
        "confidence",
        "uncertainty",
        "assumptions",
        "rationale_summary",
        "model_id",
        "protocol_version",
    }
    unknown_proposal = set(proposal_raw) - proposal_allowed
    if unknown_proposal:
        raise ModelProtocolError(f"unknown proposal field: {sorted(unknown_proposal)[0]}")
    actions_raw = proposal_raw.get("actions")
    if not isinstance(actions_raw, list) or not actions_raw or len(actions_raw) > _MAX_ACTIONS:
        raise ModelProtocolError("proposal actions must be a bounded non-empty list")
    actions = tuple(_parse_action(item) for item in actions_raw)
    assumptions = _string_list(
        proposal_raw.get("assumptions", []),
        name="assumptions",
        max_items=_MAX_ASSUMPTIONS,
        max_length=1024,
    )
    proposal = AIPlanProposal(
        proposal_id=proposal_raw.get("proposal_id", ""),
        intent_id=proposal_raw.get("intent_id", ""),
        actions=actions,
        confidence=float(proposal_raw.get("confidence", -1)),
        uncertainty=float(proposal_raw.get("uncertainty", -1)),
        assumptions=assumptions,
        rationale_summary=proposal_raw.get("rationale_summary", ""),
        model_id=proposal_raw.get("model_id", ""),
        protocol_version=int(proposal_raw.get("protocol_version", AI_MODEL_PROTOCOL_VERSION)),
    )
    warnings = _string_list(raw.get("warnings", []), name="warnings", max_items=64, max_length=1024)
    metadata = raw.get("metadata", {})
    if not isinstance(metadata, dict):
        raise ModelProtocolError("response metadata must be an object")
    return AIModelResponse(
        request_id=raw.get("request_id", ""),
        proposal=proposal,
        warnings=warnings,
        metadata=metadata,
    )
