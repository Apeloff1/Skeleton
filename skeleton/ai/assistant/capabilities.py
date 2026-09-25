"""Capability registry and least-authority admission for assistant tools."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from .contracts import (
    AssistantRequest,
    CapabilityDescriptor,
    CapabilityGrant,
    CapabilityKind,
    SideEffectClass,
)


class CapabilityAdmissionError(PermissionError):
    """A capability cannot be invoked under the supplied authority."""


@dataclass(frozen=True, slots=True)
class CapabilityDecision:
    allowed: bool
    capability_id: str
    reason_code: str
    missing_scopes: tuple[str, ...] = ()
    requires_user_action: bool = False


class CapabilityRegistry:
    """Deterministic registry; replacement requires exact descriptor identity."""

    def __init__(self) -> None:
        self._descriptors: dict[str, CapabilityDescriptor] = {}

    def register(self, descriptor: CapabilityDescriptor) -> None:
        if not isinstance(descriptor, CapabilityDescriptor):
            raise TypeError("descriptor must be CapabilityDescriptor")
        existing = self._descriptors.get(descriptor.capability_id)
        if existing is not None and existing != descriptor:
            raise ValueError(
                f"capability {descriptor.capability_id!r} cannot be silently redefined"
            )
        self._descriptors[descriptor.capability_id] = descriptor

    def unregister(self, capability_id: str) -> bool:
        return self._descriptors.pop(capability_id, None) is not None

    def get(self, capability_id: str) -> CapabilityDescriptor:
        try:
            return self._descriptors[capability_id]
        except KeyError as exc:
            raise KeyError(f"unknown capability: {capability_id}") from exc

    def by_kind(self, kind: CapabilityKind) -> tuple[CapabilityDescriptor, ...]:
        normalized = kind if isinstance(kind, CapabilityKind) else CapabilityKind(str(kind))
        return tuple(
            sorted(
                (
                    descriptor
                    for descriptor in self._descriptors.values()
                    if descriptor.kind is normalized
                ),
                key=lambda item: item.capability_id,
            )
        )

    def snapshot(self) -> tuple[CapabilityDescriptor, ...]:
        return tuple(
            self._descriptors[key] for key in sorted(self._descriptors)
        )


class CapabilityAuthorizer:
    """Authorize one registry capability against request-bound grants."""

    def decide(
        self,
        descriptor: CapabilityDescriptor,
        request: AssistantRequest,
        *,
        grants: Iterable[CapabilityGrant] = (),
        requested_scopes: Iterable[str] = (),
        explicit_user_action: bool = False,
        now: datetime | None = None,
    ) -> CapabilityDecision:
        if not isinstance(descriptor, CapabilityDescriptor):
            raise TypeError("descriptor must be CapabilityDescriptor")
        if not isinstance(request, AssistantRequest):
            raise TypeError("request must be AssistantRequest")

        instant = datetime.now(timezone.utc) if now is None else now.astimezone(timezone.utc)
        requested = frozenset(str(item).strip() for item in requested_scopes if str(item).strip())
        if not requested:
            requested = descriptor.required_scopes

        if not requested <= descriptor.required_scopes:
            return CapabilityDecision(
                allowed=False,
                capability_id=descriptor.capability_id,
                reason_code="scope-escalation",
                missing_scopes=tuple(sorted(requested - descriptor.required_scopes)),
            )

        matching = [
            grant
            for grant in grants
            if grant.capability_id == descriptor.capability_id
            and grant.request_digest == request.digest
            and grant.valid_at(instant)
        ]
        granted_scopes = frozenset().union(*(grant.granted_scopes for grant in matching))
        missing = tuple(sorted(requested - granted_scopes))

        user_action_is_explicit = (
            explicit_user_action
            or descriptor.kind in request.explicitly_allowed_capabilities
        )
        if descriptor.requires_explicit_user_action and not user_action_is_explicit:
            return CapabilityDecision(
                allowed=False,
                capability_id=descriptor.capability_id,
                reason_code="explicit-user-action-required",
                missing_scopes=missing,
                requires_user_action=True,
            )

        # Read-only/no-effect capabilities may be selected by deterministic
        # routing without a grant, but declared scopes are still enforced.
        grant_required = descriptor.side_effect not in {
            SideEffectClass.NONE,
            SideEffectClass.READ_ONLY,
        }
        if grant_required and missing:
            return CapabilityDecision(
                allowed=False,
                capability_id=descriptor.capability_id,
                reason_code="missing-request-bound-grant",
                missing_scopes=missing,
            )

        if not grant_required and matching and missing:
            return CapabilityDecision(
                allowed=False,
                capability_id=descriptor.capability_id,
                reason_code="partial-grant-scope-mismatch",
                missing_scopes=missing,
            )

        return CapabilityDecision(
            allowed=True,
            capability_id=descriptor.capability_id,
            reason_code="authorized",
        )

    def require(
        self,
        descriptor: CapabilityDescriptor,
        request: AssistantRequest,
        **kwargs,
    ) -> None:
        decision = self.decide(descriptor, request, **kwargs)
        if not decision.allowed:
            detail = ",".join(decision.missing_scopes)
            suffix = f" missing={detail}" if detail else ""
            raise CapabilityAdmissionError(
                f"{descriptor.capability_id}: {decision.reason_code}{suffix}"
            )


__all__ = [
    "CapabilityAdmissionError",
    "CapabilityAuthorizer",
    "CapabilityDecision",
    "CapabilityRegistry",
]
