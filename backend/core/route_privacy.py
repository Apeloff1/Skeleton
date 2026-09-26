"""Request-scoped privacy ceilings for backend application routes.

The route-domain catalog answers *where* a request is executing. This module
adds the data-transfer ceiling for that domain and binds it to a ContextVar so
central provider/tool boundaries can enforce one policy without endpoint-local
copies.

Absence of a route context means non-HTTP/internal execution. In that case the
canonical Skeleton data-governance policy still applies, but no HTTP-domain
ceiling is invented.
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass

from core.route_policy_catalog import default_route_domain_policy
from skeleton.vault.data_governance import (
    DataClass,
    DataGovernanceDenied,
    ProviderTransferDecision,
    ProviderTransferRequest,
    ToolTransferDecision,
    ToolTransferRequest,
    require_provider_transfer,
    require_tool_transfer,
)


@dataclass(frozen=True, slots=True)
class DomainPrivacyPolicy:
    max_data_class: DataClass
    allow_external_provider: bool
    allow_network_tools: bool


@dataclass(frozen=True, slots=True)
class RoutePrivacyContext:
    path: str
    domain: str
    max_data_class: DataClass
    allow_external_provider: bool
    allow_network_tools: bool
    open_route: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "domain": self.domain,
            "max_data_class": self.max_data_class.label,
            "allow_external_provider": self.allow_external_provider,
            "allow_network_tools": self.allow_network_tools,
            "open_route": self.open_route,
        }


# Product domains may use tenant-bound confidential data with the canonical
# provider/tool gates. Identity/governance/vault and deployment/operations
# remain local for provider transfer. Legacy routes are capped at INTERNAL
# until promoted into a narrower written domain.
DOMAIN_PRIVACY_POLICIES: dict[str, DomainPrivacyPolicy] = {
    "deployment": DomainPrivacyPolicy(DataClass.CONFIDENTIAL, False, False),
    "operations": DomainPrivacyPolicy(DataClass.CONFIDENTIAL, False, False),
    "governance": DomainPrivacyPolicy(DataClass.RESTRICTED, False, False),
    "jeeves": DomainPrivacyPolicy(DataClass.CONFIDENTIAL, True, True),
    "gameforge": DomainPrivacyPolicy(DataClass.CONFIDENTIAL, True, True),
    "studio": DomainPrivacyPolicy(DataClass.CONFIDENTIAL, True, True),
    "worldforge": DomainPrivacyPolicy(DataClass.CONFIDENTIAL, True, True),
    "vault": DomainPrivacyPolicy(DataClass.RESTRICTED, False, False),
    "build_artifacts": DomainPrivacyPolicy(DataClass.CONFIDENTIAL, False, False),
    "code_execution": DomainPrivacyPolicy(DataClass.CONFIDENTIAL, True, False),
    "tooling": DomainPrivacyPolicy(DataClass.CONFIDENTIAL, True, True),
    "market_intelligence": DomainPrivacyPolicy(DataClass.CONFIDENTIAL, True, True),
    "collaboration": DomainPrivacyPolicy(DataClass.CONFIDENTIAL, True, True),
    "learning": DomainPrivacyPolicy(DataClass.CONFIDENTIAL, True, True),
    "identity": DomainPrivacyPolicy(DataClass.RESTRICTED, False, False),
    "legacy_api": DomainPrivacyPolicy(DataClass.INTERNAL, True, True),
}

_OPEN_POLICY = DomainPrivacyPolicy(DataClass.PUBLIC, False, False)
_CURRENT_ROUTE_PRIVACY: ContextVar[RoutePrivacyContext | None] = ContextVar(
    "backend_route_privacy",
    default=None,
)


def resolve_route_privacy(path: str) -> RoutePrivacyContext:
    policy = default_route_domain_policy()
    normalized = policy._normalize_path(path)
    if policy.is_open(normalized):
        return RoutePrivacyContext(
            path=normalized,
            domain="open",
            max_data_class=_OPEN_POLICY.max_data_class,
            allow_external_provider=False,
            allow_network_tools=False,
            open_route=True,
        )

    domain = policy.required_domain(normalized)
    if domain is None:
        raise DataGovernanceDenied("route_privacy_unwritten")
    try:
        ceiling = DOMAIN_PRIVACY_POLICIES[domain]
    except KeyError as exc:
        raise DataGovernanceDenied("route_privacy_domain_unwritten") from exc
    return RoutePrivacyContext(
        path=normalized,
        domain=domain,
        max_data_class=ceiling.max_data_class,
        allow_external_provider=ceiling.allow_external_provider,
        allow_network_tools=ceiling.allow_network_tools,
    )


def bind_route_privacy(path: str) -> Token[RoutePrivacyContext | None]:
    return _CURRENT_ROUTE_PRIVACY.set(resolve_route_privacy(path))


def reset_route_privacy(token: Token[RoutePrivacyContext | None]) -> None:
    _CURRENT_ROUTE_PRIVACY.reset(token)


def current_route_privacy() -> RoutePrivacyContext | None:
    return _CURRENT_ROUTE_PRIVACY.get()


def _enforce_data_ceiling(data_class: DataClass | str | int) -> DataClass:
    classification = DataClass.parse(data_class)
    route = current_route_privacy()
    if route is not None and classification > route.max_data_class:
        raise DataGovernanceDenied("route_data_ceiling_exceeded")
    return classification


def require_route_provider_transfer(
    *,
    provider_id: str,
    data_class: DataClass | str | int = DataClass.INTERNAL,
    purpose: str = "model-inference",
    tenant_id: str | None = None,
    source: str = "backend-route",
) -> ProviderTransferDecision:
    classification = _enforce_data_ceiling(data_class)
    route = current_route_privacy()
    if route is not None and not route.allow_external_provider:
        raise DataGovernanceDenied("route_provider_transfer_denied")
    return require_provider_transfer(
        ProviderTransferRequest(
            provider_id=provider_id,
            data_class=classification,
            purpose=purpose,
            tenant_id=tenant_id,
            source=source,
        )
    )


def require_route_tool_transfer(
    *,
    tool_id: str,
    data_policy: str,
    network_policy: str,
    data_class: DataClass | str | int = DataClass.INTERNAL,
    purpose: str = "tool-execution",
    tenant_id: str | None = None,
    source: str = "backend-route",
) -> ToolTransferDecision:
    classification = _enforce_data_ceiling(data_class)
    route = current_route_privacy()
    normalized_network = str(network_policy or "").strip().lower()
    if (
        route is not None
        and normalized_network != "none"
        and not route.allow_network_tools
    ):
        raise DataGovernanceDenied("route_network_tool_denied")
    return require_tool_transfer(
        ToolTransferRequest(
            tool_id=tool_id,
            data_policy=data_policy,
            network_policy=network_policy,
            data_class=classification,
            purpose=purpose,
            tenant_id=tenant_id,
            source=source,
        )
    )


def validate_domain_privacy_coverage() -> None:
    route_domains = {
        rule.domain
        for rule in default_route_domain_policy().domain_rules
    }
    missing = route_domains - set(DOMAIN_PRIVACY_POLICIES)
    extra = set(DOMAIN_PRIVACY_POLICIES) - route_domains
    if missing or extra:
        detail = []
        if missing:
            detail.append("missing=" + ",".join(sorted(missing)))
        if extra:
            detail.append("extra=" + ",".join(sorted(extra)))
        raise DataGovernanceDenied(
            "route_privacy_catalog_mismatch:" + ";".join(detail)
        )


validate_domain_privacy_coverage()


__all__ = [
    "DOMAIN_PRIVACY_POLICIES",
    "DomainPrivacyPolicy",
    "RoutePrivacyContext",
    "bind_route_privacy",
    "current_route_privacy",
    "require_route_provider_transfer",
    "require_route_tool_transfer",
    "reset_route_privacy",
    "resolve_route_privacy",
    "validate_domain_privacy_coverage",
]
