"""Immutable handoff from product assistant routing to the cognitive runtime."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .contracts import AssistantRequest, CompiledContext, RoutingPlan, digest_json


@dataclass(frozen=True, slots=True)
class AssistantHandoff:
    request_id: str
    request_digest: str
    route_digest: str
    context_digest: str | None
    objective: str
    allowed_capability_ids: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    max_tool_calls: int

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "request_id": self.request_id,
            "request_digest": self.request_digest,
            "route_digest": self.route_digest,
            "context_digest": self.context_digest,
            "objective": self.objective,
            "allowed_capability_ids": list(self.allowed_capability_ids),
            "evidence_refs": list(self.evidence_refs),
            "max_tool_calls": self.max_tool_calls,
        }

    @property
    def digest(self) -> str:
        return digest_json(self.as_dict())


def build_handoff(
    request: AssistantRequest,
    route: RoutingPlan,
    *,
    context: CompiledContext | None = None,
    capability_ids: Iterable[str] = (),
    evidence_refs: Iterable[str] = (),
) -> AssistantHandoff:
    if route.request_digest != request.digest:
        raise ValueError("route is bound to a different request")
    if context is not None and context.request_digest != request.digest:
        raise ValueError("context is bound to a different request")

    capabilities = tuple(
        dict.fromkeys(
            str(item).strip() for item in capability_ids if str(item).strip()
        )
    )
    evidence = tuple(
        dict.fromkeys(str(item).strip() for item in evidence_refs if str(item).strip())
    )
    return AssistantHandoff(
        request_id=request.request_id,
        request_digest=request.digest,
        route_digest=route.digest,
        context_digest=None if context is None else context.digest,
        objective=request.text,
        allowed_capability_ids=capabilities,
        evidence_refs=evidence,
        max_tool_calls=request.max_tool_calls,
    )


__all__ = ["AssistantHandoff", "build_handoff"]
