"""Provider availability policy and auditable redundancy routing.

The canonical ProviderRegistry owns adapters and credentials. This module owns
only availability strategy: a deployment may explicitly accept a single-
provider SLO or declare ordered failover candidates. No undeclared provider is
ever selected and no provider-native credential/network logic is duplicated.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from typing import Any

from skeleton.provider_runtime import ProviderRegistry, ProviderUnavailableError


class ProviderAvailabilityStrategy(str, Enum):
    SINGLE_PROVIDER_SLO = "single-provider-slo"
    MULTI_PROVIDER_FAILOVER = "multi-provider-failover"


def _digest(payload: dict[str, Any]) -> str:
    raw = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True, slots=True)
class ProviderAvailabilityPolicy:
    strategy: ProviderAvailabilityStrategy
    primary_provider: str
    fallback_providers: tuple[str, ...] = ()
    availability_target: float = 0.99
    privacy_ceiling: str = "confidential"
    credential_owner: str = "skeleton/provider_runtime.py"
    network_policy: str = "provider-runtime-only"

    def __post_init__(self) -> None:
        primary = self.primary_provider.strip().lower()
        if not primary or len(primary) > 128:
            raise ValueError("primary_provider is invalid")
        if not 0.0 < float(self.availability_target) <= 1.0:
            raise ValueError("availability_target must be in (0, 1]")
        if any(
            not item.strip()
            or len(item) > 128
            or item.strip().lower() == primary
            for item in self.fallback_providers
        ):
            raise ValueError("fallback_providers contains an invalid provider")
        normalized_fallbacks = tuple(
            item.strip().lower() for item in self.fallback_providers
        )
        if len(set(normalized_fallbacks)) != len(normalized_fallbacks):
            raise ValueError("fallback_providers must be unique")
        if (
            self.strategy is ProviderAvailabilityStrategy.SINGLE_PROVIDER_SLO
            and normalized_fallbacks
        ):
            raise ValueError(
                "single-provider SLO policy cannot declare fallback providers"
            )
        if (
            self.strategy
            is ProviderAvailabilityStrategy.MULTI_PROVIDER_FAILOVER
            and not normalized_fallbacks
        ):
            raise ValueError(
                "multi-provider failover requires at least one fallback"
            )
        if not self.privacy_ceiling or len(self.privacy_ceiling) > 128:
            raise ValueError("privacy_ceiling is invalid")
        if self.credential_owner != "skeleton/provider_runtime.py":
            raise ValueError(
                "provider credentials must remain owned by provider_runtime"
            )
        if self.network_policy != "provider-runtime-only":
            raise ValueError(
                "provider network policy must remain provider-runtime-only"
            )

    @property
    def declared_providers(self) -> tuple[str, ...]:
        return (
            self.primary_provider.strip().lower(),
            *(item.strip().lower() for item in self.fallback_providers),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy.value,
            "primary_provider": self.primary_provider.strip().lower(),
            "fallback_providers": [
                item.strip().lower() for item in self.fallback_providers
            ],
            "availability_target": float(self.availability_target),
            "privacy_ceiling": self.privacy_ceiling,
            "credential_owner": self.credential_owner,
            "network_policy": self.network_policy,
        }


@dataclass(frozen=True, slots=True)
class ProviderRouteReceipt:
    strategy: str
    primary_provider: str
    declared_providers: tuple[str, ...]
    selected_provider: str | None
    failover_used: bool
    availability_target: float
    provider_states: tuple[dict[str, Any], ...]
    reason: str
    policy_digest: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "primary_provider": self.primary_provider,
            "declared_providers": list(self.declared_providers),
            "selected_provider": self.selected_provider,
            "failover_used": self.failover_used,
            "availability_target": self.availability_target,
            "provider_states": [dict(item) for item in self.provider_states],
            "reason": self.reason,
            "policy_digest": self.policy_digest,
        }

    @property
    def digest(self) -> str:
        return _digest(self.to_dict())


class ProviderAvailabilityController:
    """Select only declared, configured, architecture-acknowledged providers."""

    def __init__(
        self,
        registry: ProviderRegistry,
        policy: ProviderAvailabilityPolicy,
    ) -> None:
        self.registry = registry
        self.policy = policy
        self._route_count = 0
        self._failover_count = 0
        self._unavailable_count = 0
        self._selected_counts: dict[str, int] = {}

    def _declared_states(self) -> tuple[dict[str, Any], ...]:
        statuses = {
            str(item.get("id") or "").strip().lower(): item
            for item in self.registry.statuses()
        }
        rows: list[dict[str, Any]] = []
        for provider_id in self.policy.declared_providers:
            status = statuses.get(provider_id)
            if status is None:
                rows.append(
                    {
                        "provider_id": provider_id,
                        "available": False,
                        "architecture_acknowledged": False,
                        "configured": False,
                    }
                )
                continue
            rows.append(
                {
                    "provider_id": provider_id,
                    "available": bool(status.get("available")),
                    "architecture_acknowledged": bool(
                        status.get("architecture_acknowledged")
                    ),
                    "configured": True,
                    "active": bool(status.get("active")),
                    "model": str(status.get("model") or ""),
                }
            )
        return tuple(rows)

    def plan(self) -> ProviderRouteReceipt:
        states = self._declared_states()
        selected: str | None = None
        for state in states:
            if (
                state["configured"]
                and state["available"]
                and state["architecture_acknowledged"]
            ):
                selected = str(state["provider_id"])
                break

        primary = self.policy.declared_providers[0]
        failover_used = selected is not None and selected != primary
        if selected is None:
            reason = (
                "declared provider set is unavailable; fail closed"
                if self.policy.strategy
                is ProviderAvailabilityStrategy.MULTI_PROVIDER_FAILOVER
                else "single-provider SLO accepted; primary unavailable"
            )
            self._unavailable_count += 1
        elif failover_used:
            reason = "primary unavailable; selected declared fallback"
            self._failover_count += 1
        else:
            reason = "selected declared primary provider"

        self._route_count += 1
        if selected is not None:
            self._selected_counts[selected] = (
                self._selected_counts.get(selected, 0) + 1
            )

        return ProviderRouteReceipt(
            strategy=self.policy.strategy.value,
            primary_provider=primary,
            declared_providers=self.policy.declared_providers,
            selected_provider=selected,
            failover_used=failover_used,
            availability_target=float(self.policy.availability_target),
            provider_states=states,
            reason=reason,
            policy_digest=_digest(self.policy.to_dict()),
        )

    def require_route(self) -> ProviderRouteReceipt:
        receipt = self.plan()
        if receipt.selected_provider is None:
            raise ProviderUnavailableError(receipt.reason)
        return receipt

    def telemetry(self) -> dict[str, Any]:
        return {
            "strategy": self.policy.strategy.value,
            "availability_target": float(self.policy.availability_target),
            "route_count": self._route_count,
            "failover_count": self._failover_count,
            "unavailable_count": self._unavailable_count,
            "selected_counts": dict(sorted(self._selected_counts.items())),
            "declared_provider_count": len(self.policy.declared_providers),
        }


__all__ = [
    "ProviderAvailabilityController",
    "ProviderAvailabilityPolicy",
    "ProviderAvailabilityStrategy",
    "ProviderRouteReceipt",
]
