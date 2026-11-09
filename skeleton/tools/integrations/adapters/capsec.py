"""Bridge tool-adapter authorization onto the canonical kernel capsec gate.

This module intentionally does *not* define a second checker hierarchy.
Authority is the frozen skeleton.kernel.capsec contract:

    CapabilityGate.check(serialised_token, Action) -> Decision

Every tool invocation requires an explicit tool.<name>:invoke action plus
every capability declared by the tool. Resource-sensitive tools bind each
declared capability to a canonical ("resource", value) constraint so a
narrow token can authorize one resource without authorizing another.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from skeleton.kernel.capsec import Action, CapabilityGate, Decision, DenyAllGate

from .errors import CapabilityDeniedError

__all__ = [
    "ToolAuthorization",
    "KernelToolAuthorizer",
    "declared_capability_action",
    "tool_actions",
]


def declared_capability_action(capability: str, *, resource: str | None = None) -> Action:
    """Translate scope.verb adapter capabilities into kernel actions."""

    raw = str(capability).strip()
    if not raw:
        raise ValueError("declared capability must be non-empty")
    if "." in raw:
        scope, verb = raw.rsplit(".", 1)
    else:
        scope, verb = raw, "use"
    if not scope or not verb:
        raise ValueError(f"invalid declared capability: {capability!r}")
    constraints = frozenset({("resource", resource)}) if resource else frozenset()
    return Action(scope=scope, verb=verb, resource=resource, constraints=constraints)


def tool_actions(
    tool_name: str,
    capabilities: Iterable[str],
    resources: Iterable[str] = (),
) -> tuple[Action, ...]:
    """Canonical action set required for one tool invocation."""

    name = str(tool_name).strip()
    if not name:
        raise ValueError("tool name must be non-empty")
    actions: list[Action] = [
        Action(scope=f"tool.{name}", verb="invoke", resource=name),
    ]
    caps = tuple(sorted({str(item).strip() for item in capabilities if str(item).strip()}))
    resource_values = tuple(sorted({str(item) for item in resources if str(item)}))
    for capability in caps:
        if resource_values:
            actions.extend(
                declared_capability_action(capability, resource=resource)
                for resource in resource_values
            )
        else:
            actions.append(declared_capability_action(capability))
    return tuple(actions)


@dataclass(frozen=True)
class ToolAuthorization:
    subject: str
    actions: tuple[Action, ...]
    decisions: tuple[Decision, ...]

    @property
    def audit_record_ids(self) -> tuple[str, ...]:
        return tuple(decision.audit.record_id for decision in self.decisions)


class KernelToolAuthorizer:
    """Fail-closed adapter around the canonical kernel capability gate."""

    def __init__(self, gate: CapabilityGate | None = None) -> None:
        self.gate: CapabilityGate = gate if gate is not None else DenyAllGate()

    def authorize(
        self,
        cap: str | None,
        *,
        tool_name: str,
        capabilities: Iterable[str] = (),
        resources: Iterable[str] = (),
    ) -> ToolAuthorization:
        actions = tool_actions(tool_name, capabilities, resources)
        decisions: list[Decision] = []
        for action in actions:
            decision = self.gate.check(cap, action)
            decisions.append(decision)
            if not decision.allowed:
                raise CapabilityDeniedError(
                    f"tool {tool_name!r} denied by canonical capability policy",
                    capability=f"{action.scope}.{action.verb}",
                    reason=decision.reason,
                    details={
                        "record_id": decision.audit.record_id,
                        "scope": action.scope,
                        "verb": action.verb,
                        "resource": action.resource,
                    },
                )

        subjects = {decision.subject for decision in decisions if decision.subject}
        if len(subjects) != 1:
            raise CapabilityDeniedError(
                f"tool {tool_name!r} authorization lacks one verified subject",
                capability=f"tool.{tool_name}.invoke",
                reason="unbound_subject",
                details={"record_ids": [d.audit.record_id for d in decisions]},
            )
        return ToolAuthorization(
            subject=next(iter(subjects)),
            actions=actions,
            decisions=tuple(decisions),
        )
