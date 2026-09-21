"""Canonical registry-backed data governance for AI operations.

The lower-level modules intentionally remain small:
- data_governance defines classification and baseline provider-transfer policy;
- data_lifecycle owns tenant-scoped metadata, retention, export and deletion.

This registry composes them into the architecture boundary used by model routing
and provider execution. Callers reference governed record IDs; classification,
tenant binding and permitted purpose are derived from registered metadata rather
than trusted from a caller-supplied label.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Iterable

from skeleton.vault.data_governance import (
    DataClass,
    DataGovernanceDenied,
    ProviderTransferDecision,
    ProviderTransferRequest,
    evaluate_provider_transfer,
)
from skeleton.vault.data_lifecycle import (
    DataLifecycleRegistry,
    GovernedDataRecord,
    LifecycleState,
)


def _required_text(value: object, field: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text:
        raise DataGovernanceDenied(f"{field} is required")
    if len(text) > 256:
        raise DataGovernanceDenied(f"{field} is too long")
    return text


def _record_ids(values: Iterable[str]) -> tuple[str, ...]:
    normalized = tuple(
        dict.fromkeys(_required_text(value, "record_id") for value in values)
    )
    if not normalized:
        raise DataGovernanceDenied("at least one governed record is required")
    return normalized


@dataclass(frozen=True, slots=True)
class GovernanceContext:
    tenant_id: str
    record_ids: tuple[str, ...]
    data_class: DataClass
    routing_privacy: str
    purpose: str
    owner_planes: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "record_ids": list(self.record_ids),
            "data_class": self.data_class.label,
            "routing_privacy": self.routing_privacy,
            "purpose": self.purpose,
            "owner_planes": list(self.owner_planes),
        }


@dataclass(frozen=True, slots=True)
class RegisteredProviderTransferDecision:
    decision_id: str
    provider_decision_id: str
    permitted: bool
    provider_id: str
    tenant_id: str
    data_class: str
    purpose: str
    routing_privacy: str
    record_ids: tuple[str, ...]
    reason_code: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "provider_decision_id": self.provider_decision_id,
            "permitted": self.permitted,
            "provider_id": self.provider_id,
            "tenant_id": self.tenant_id,
            "data_class": self.data_class,
            "purpose": self.purpose,
            "routing_privacy": self.routing_privacy,
            "record_ids": list(self.record_ids),
            "reason_code": self.reason_code,
        }


class GovernanceRegistry:
    """Authoritative metadata-derived governance boundary."""

    def __init__(
        self,
        lifecycle: DataLifecycleRegistry | None = None,
    ) -> None:
        self.lifecycle = lifecycle or DataLifecycleRegistry()

    def register(self, record: GovernedDataRecord) -> GovernedDataRecord:
        return self.lifecycle.register(record)

    def context_for(
        self,
        record_ids: Iterable[str],
        *,
        tenant_id: str,
        purpose: str,
    ) -> GovernanceContext:
        ids = _record_ids(record_ids)
        tenant = _required_text(tenant_id, "tenant_id")
        normalized_purpose = _required_text(purpose, "purpose").lower()

        rows = [self.lifecycle.get(record_id) for record_id in ids]
        classes: list[DataClass] = []
        owner_planes: list[str] = []

        for row in rows:
            if row["tenant_id"] != tenant:
                raise DataGovernanceDenied("cross-tenant governed record access denied")
            if row["state"] != LifecycleState.ACTIVE.value:
                raise DataGovernanceDenied("governed record is not active")
            purposes = tuple(
                str(value).strip().lower()
                for value in row.get("purposes", ())
                if str(value).strip()
            )
            if normalized_purpose not in purposes:
                raise DataGovernanceDenied("purpose_not_registered_for_record")
            classes.append(DataClass.parse(row["data_class"]))
            owner_planes.append(_required_text(row["owner_plane"], "owner_plane"))

        classification = max(classes)
        return GovernanceContext(
            tenant_id=tenant,
            record_ids=ids,
            data_class=classification,
            routing_privacy=classification.routing_privacy,
            purpose=normalized_purpose,
            owner_planes=tuple(sorted(set(owner_planes))),
        )

    @staticmethod
    def _registered_decision_id(
        context: GovernanceContext,
        provider: ProviderTransferDecision,
    ) -> str:
        material = "\x1f".join(
            (
                provider.decision_id,
                context.tenant_id,
                context.data_class.label,
                context.purpose,
                ",".join(context.record_ids),
            )
        ).encode("utf-8")
        return "govr-" + hashlib.sha256(material).hexdigest()[:24]

    def evaluate_provider_transfer(
        self,
        provider_id: str,
        *,
        record_ids: Iterable[str],
        tenant_id: str,
        purpose: str,
        source: str = "governance-registry",
    ) -> RegisteredProviderTransferDecision:
        context = self.context_for(
            record_ids,
            tenant_id=tenant_id,
            purpose=purpose,
        )
        provider = evaluate_provider_transfer(
            ProviderTransferRequest(
                provider_id=provider_id,
                data_class=context.data_class,
                purpose=context.purpose,
                tenant_id=context.tenant_id,
                source=source,
            )
        )
        return RegisteredProviderTransferDecision(
            decision_id=self._registered_decision_id(context, provider),
            provider_decision_id=provider.decision_id,
            permitted=provider.permitted,
            provider_id=provider.provider_id,
            tenant_id=context.tenant_id,
            data_class=provider.data_class,
            purpose=provider.purpose,
            routing_privacy=provider.routing_privacy,
            record_ids=context.record_ids,
            reason_code=provider.reason_code,
        )

    def require_provider_transfer(
        self,
        provider_id: str,
        *,
        record_ids: Iterable[str],
        tenant_id: str,
        purpose: str,
        source: str = "governance-registry",
    ) -> RegisteredProviderTransferDecision:
        decision = self.evaluate_provider_transfer(
            provider_id,
            record_ids=record_ids,
            tenant_id=tenant_id,
            purpose=purpose,
            source=source,
        )
        if not decision.permitted:
            raise DataGovernanceDenied(decision.reason_code)
        return decision

    def routing_privacy_for(
        self,
        record_ids: Iterable[str],
        *,
        tenant_id: str,
        purpose: str,
    ) -> str:
        return self.context_for(
            record_ids,
            tenant_id=tenant_id,
            purpose=purpose,
        ).routing_privacy

    def export_inventory(self, tenant_id: str) -> dict[str, Any]:
        return self.lifecycle.export_inventory(tenant_id)

    def request_deletion(self, *args: Any, **kwargs: Any):
        return self.lifecycle.request_deletion(*args, **kwargs)

    def plan_retention_expiry(self, *args: Any, **kwargs: Any):
        return self.lifecycle.plan_retention_expiry(*args, **kwargs)

    def acknowledge_deletion(self, *args: Any, **kwargs: Any):
        return self.lifecycle.acknowledge_deletion(*args, **kwargs)


__all__ = [
    "GovernanceContext",
    "GovernanceRegistry",
    "RegisteredProviderTransferDecision",
]
