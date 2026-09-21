"""Data governance and provider-transfer policy.

This module owns the application-wide data classification vocabulary and the
minimum fail-closed policy applied before data crosses into an external AI
provider. It contains no provider SDK code and no credentials.

The baseline hierarchy is:
PUBLIC < INTERNAL < CONFIDENTIAL < RESTRICTED.

Restricted data is never transferred by the generic provider path. Confidential
data requires a tenant identity and a declared purpose. More restrictive product
or tenant policies can be layered above this baseline, but no caller can weaken
it by passing a different label to the provider adapter.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
import hashlib
from typing import Any


class DataGovernanceError(RuntimeError):
    """Base data-governance failure."""


class DataGovernanceDenied(DataGovernanceError):
    """A data transfer is not permitted by the baseline governance policy."""


class DataClass(IntEnum):
    PUBLIC = 0
    INTERNAL = 1
    CONFIDENTIAL = 2
    RESTRICTED = 3

    @classmethod
    def parse(cls, value: "DataClass | str | int") -> "DataClass":
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            key = value.strip().upper().replace("-", "_")
            try:
                return cls[key]
            except KeyError as exc:
                raise DataGovernanceDenied("unknown data classification") from exc
        if isinstance(value, bool):
            raise DataGovernanceDenied("unknown data classification")
        try:
            return cls(int(value))
        except (TypeError, ValueError) as exc:
            raise DataGovernanceDenied("unknown data classification") from exc

    @property
    def label(self) -> str:
        return self.name.lower()

    @property
    def routing_privacy(self) -> str:
        return {
            DataClass.PUBLIC: "public",
            DataClass.INTERNAL: "private",
            DataClass.CONFIDENTIAL: "sensitive",
            DataClass.RESTRICTED: "local-only",
        }[self]


_ALLOWED_PROVIDER_PURPOSES = frozenset(
    {
        "model-inference",
        "code-assistance",
        "retrieval-synthesis",
        "verification",
        "evaluation",
        "image-generation",
        "image-variation",
        "image-edit",
        "speech-synthesis",
    }
)


def _normalized_identifier(value: Any, *, field: str, required: bool) -> str:
    if value is None:
        if required:
            raise DataGovernanceDenied(f"{field} is required")
        return ""
    text = str(value).strip()
    if required and not text:
        raise DataGovernanceDenied(f"{field} is required")
    if len(text) > 256:
        raise DataGovernanceDenied(f"{field} is too long")
    return text


@dataclass(frozen=True, slots=True)
class ProviderTransferRequest:
    provider_id: str
    data_class: DataClass | str | int = DataClass.INTERNAL
    purpose: str = "model-inference"
    tenant_id: str | None = None
    source: str = "application"

    def normalized(self) -> "ProviderTransferRequest":
        classification = DataClass.parse(self.data_class)
        provider = _normalized_identifier(
            self.provider_id,
            field="provider_id",
            required=True,
        ).lower()
        purpose = _normalized_identifier(
            self.purpose,
            field="purpose",
            required=True,
        ).lower()
        tenant = _normalized_identifier(
            self.tenant_id,
            field="tenant_id",
            required=False,
        )
        source = _normalized_identifier(
            self.source,
            field="source",
            required=True,
        )
        return ProviderTransferRequest(
            provider_id=provider,
            data_class=classification,
            purpose=purpose,
            tenant_id=tenant or None,
            source=source,
        )


@dataclass(frozen=True, slots=True)
class ProviderTransferDecision:
    decision_id: str
    permitted: bool
    provider_id: str
    data_class: str
    purpose: str
    tenant_bound: bool
    reason_code: str
    routing_privacy: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "permitted": self.permitted,
            "provider_id": self.provider_id,
            "data_class": self.data_class,
            "purpose": self.purpose,
            "tenant_bound": self.tenant_bound,
            "reason_code": self.reason_code,
            "routing_privacy": self.routing_privacy,
        }


def _decision_id(request: ProviderTransferRequest, reason_code: str) -> str:
    classification = DataClass.parse(request.data_class)
    material = "\x1f".join(
        (
            request.provider_id,
            classification.label,
            request.purpose,
            request.tenant_id or "",
            request.source,
            reason_code,
        )
    ).encode("utf-8")
    return "gov-" + hashlib.sha256(material).hexdigest()[:24]


def evaluate_provider_transfer(
    request: ProviderTransferRequest,
) -> ProviderTransferDecision:
    """Evaluate the baseline provider-transfer policy without provider I/O."""

    normalized = request.normalized()
    classification = DataClass.parse(normalized.data_class)

    if normalized.purpose not in _ALLOWED_PROVIDER_PURPOSES:
        reason = "purpose_not_allowed"
        permitted = False
    elif classification is DataClass.RESTRICTED:
        reason = "restricted_external_transfer_denied"
        permitted = False
    elif classification is DataClass.CONFIDENTIAL and not normalized.tenant_id:
        reason = "confidential_requires_tenant"
        permitted = False
    else:
        reason = "baseline_policy_permits"
        permitted = True

    return ProviderTransferDecision(
        decision_id=_decision_id(normalized, reason),
        permitted=permitted,
        provider_id=normalized.provider_id,
        data_class=classification.label,
        purpose=normalized.purpose,
        tenant_bound=bool(normalized.tenant_id),
        reason_code=reason,
        routing_privacy=classification.routing_privacy,
    )


def require_provider_transfer(
    request: ProviderTransferRequest,
) -> ProviderTransferDecision:
    """Return a receipt or fail closed without exposing transferred content."""

    decision = evaluate_provider_transfer(request)
    if not decision.permitted:
        raise DataGovernanceDenied(decision.reason_code)
    return decision


__all__ = [
    "DataClass",
    "DataGovernanceDenied",
    "DataGovernanceError",
    "ProviderTransferDecision",
    "ProviderTransferRequest",
    "evaluate_provider_transfer",
    "require_provider_transfer",
]
