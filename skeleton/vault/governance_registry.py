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
from enum import Enum
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


def _normalized_string_values(
    values: Iterable[str],
    *,
    field: str,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise DataGovernanceDenied(f"{field} must be a collection, not a string")
    normalized = tuple(
        dict.fromkeys(
            _required_text(value, field).lower()
            for value in values
        )
    )
    if not normalized:
        raise DataGovernanceDenied(f"at least one {field} is required")
    return normalized


class CanonicalDataPlane(str, Enum):
    """Governed owner planes whose durable writes require lifecycle registration."""

    CONVERSATION = "conversation"
    MEMORY = "memory"
    RETRIEVAL = "retrieval"
    ARTIFACT = "artifact"

    @classmethod
    def parse(cls, value: "CanonicalDataPlane | str") -> "CanonicalDataPlane":
        if isinstance(value, cls):
            return value
        text = str(value).strip().lower().replace("_", "-")
        aliases = {
            "conversation": cls.CONVERSATION,
            "conversation-state": cls.CONVERSATION,
            "memory": cls.MEMORY,
            "retrieval": cls.RETRIEVAL,
            "artifact": cls.ARTIFACT,
            "artifact-plane": cls.ARTIFACT,
        }
        try:
            return aliases[text]
        except KeyError as exc:
            raise DataGovernanceDenied("unknown canonical data plane") from exc


@dataclass(frozen=True, slots=True)
class CanonicalWritePolicy:
    plane: CanonicalDataPlane
    owner_plane: str
    default_deletion_targets: tuple[str, ...]


_CANONICAL_WRITE_POLICIES = {
    CanonicalDataPlane.CONVERSATION: CanonicalWritePolicy(
        plane=CanonicalDataPlane.CONVERSATION,
        owner_plane="conversation",
        default_deletion_targets=("conversation",),
    ),
    CanonicalDataPlane.MEMORY: CanonicalWritePolicy(
        plane=CanonicalDataPlane.MEMORY,
        owner_plane="memory",
        default_deletion_targets=("memory",),
    ),
    CanonicalDataPlane.RETRIEVAL: CanonicalWritePolicy(
        plane=CanonicalDataPlane.RETRIEVAL,
        owner_plane="retrieval",
        default_deletion_targets=("retrieval",),
    ),
    CanonicalDataPlane.ARTIFACT: CanonicalWritePolicy(
        plane=CanonicalDataPlane.ARTIFACT,
        owner_plane="artifact",
        default_deletion_targets=("artifact",),
    ),
}


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

    def register_canonical_write(
        self,
        plane: CanonicalDataPlane | str,
        *,
        record_id: str,
        tenant_id: str,
        source_ref: str,
        data_class: DataClass | str | int,
        purposes: Iterable[str],
        deletion_targets: Iterable[str] | None = None,
        created_at: float | None = None,
        retention_until: float | None = None,
        exportable: bool = True,
    ) -> GovernedDataRecord:
        """Register lifecycle metadata for one canonical plane write.

        The registry stores metadata only. Callers must commit the actual durable
        write in the owning repository and use this record to drive export,
        retention and deletion propagation. Projection-specific deletion targets
        should be supplied explicitly when the write is copied beyond its owner
        plane; the default targets only the canonical owner.
        """

        canonical = CanonicalDataPlane.parse(plane)
        policy = _CANONICAL_WRITE_POLICIES[canonical]
        normalized_purposes = _normalized_string_values(
            purposes,
            field="purpose",
        )

        targets = (
            _normalized_string_values(
                deletion_targets,
                field="deletion target",
            )
            if deletion_targets is not None
            else policy.default_deletion_targets
        )
        kwargs: dict[str, Any] = {
            "record_id": _required_text(record_id, "record_id"),
            "tenant_id": _required_text(tenant_id, "tenant_id"),
            "owner_plane": policy.owner_plane,
            "source_ref": _required_text(source_ref, "source_ref"),
            "data_class": DataClass.parse(data_class),
            "purposes": normalized_purposes,
            "deletion_targets": targets,
            "retention_until": retention_until,
            "exportable": bool(exportable),
        }
        if created_at is not None:
            kwargs["created_at"] = created_at
        return self.lifecycle.ensure_registered(GovernedDataRecord(**kwargs))

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
    "CanonicalDataPlane",
    "CanonicalWritePolicy",
    "GovernanceContext",
    "GovernanceRegistry",
    "RegisteredProviderTransferDecision",
]
