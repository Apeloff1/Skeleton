"""Canonical report-only route-domain catalog for staged API admission rollout.

This catalog deliberately does *not* install middleware. It classifies the
current API surface into stable governance domains so inventory coverage can be
measured before any global authentication/admission switch is enabled.

The final ``/api`` rule is an explicit migration bucket, not an authorization
shortcut. Routes landing in ``legacy_api`` remain protected in an eventual
fail-closed adapter, but should be promoted into narrower domains over time.
"""

from __future__ import annotations

from collections.abc import Sequence

from core.principal_seal import (
    RouteAdmission,
    RouteDomainPolicy,
    RouteRule,
    VerifiedPrincipal,
)

ROUTE_POLICY_CATALOG_VERSION = "2026-09-15.v2"

# Health/readiness may expose nested probe paths. Authentication bootstrap
# endpoints are exact-only so future descendants cannot accidentally inherit
# public admission.
OPEN_ROUTE_PREFIXES: tuple[str, ...] = (
    "/api/health",
    "/api/ready",
)
OPEN_EXACT_PATHS: tuple[str, ...] = (
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/session",
)

# Longest-prefix matching means specialized control-plane domains win before
# broader product domains and finally the explicit migration bucket.
ROUTE_DOMAIN_RULES: tuple[RouteRule, ...] = (
    RouteRule("/api/deployment", "deployment"),
    RouteRule("/api/ops", "operations"),
    RouteRule("/api/governance", "governance"),
    RouteRule("/api/orchestrator", "jeeves"),
    RouteRule("/api/jeeves", "jeeves"),
    RouteRule("/api/gameforge", "gameforge"),
    RouteRule("/api/galaxy-studio", "studio"),
    RouteRule("/api/worldforge", "worldforge"),
    RouteRule("/api/vault", "vault"),
    RouteRule("/api/binary", "build_artifacts"),
    RouteRule("/api/interpreter", "code_execution"),
    RouteRule("/api/tools", "tooling"),
    RouteRule("/api/compiler", "code_execution"),
    RouteRule("/api/playground", "code_execution"),
    RouteRule("/api/market", "market_intelligence"),
    RouteRule("/api/collab", "collaboration"),
    RouteRule("/api/learning", "learning"),
    RouteRule("/api/academy", "learning"),
    RouteRule("/api/auth", "identity"),
    RouteRule("/api", "legacy_api"),
)


class CatalogRouteDomainPolicy(RouteDomainPolicy):
    """Route policy with both prefix-open and exact-open public surfaces."""

    def __init__(
        self,
        *,
        exact_open_paths: Sequence[str],
        open_prefixes: Sequence[str],
        domain_rules: Sequence[RouteRule],
    ) -> None:
        super().__init__(open_prefixes=open_prefixes, domain_rules=domain_rules)
        self._exact_open_paths = frozenset(
            self._normalize_path(path) for path in exact_open_paths
        )

    @property
    def exact_open_paths(self) -> tuple[str, ...]:
        return tuple(sorted(self._exact_open_paths))

    def is_open(self, path: str) -> bool:
        normalized = self._normalize_path(path)
        return normalized in self._exact_open_paths or super().is_open(normalized)

    def admit(self, path: str, principal: VerifiedPrincipal | None) -> RouteAdmission:
        normalized = self._normalize_path(path)
        if self.is_open(normalized):
            return RouteAdmission(True, 200, "open route", open_route=True)
        domain = self.required_domain(normalized)
        if domain is None:
            return RouteAdmission(False, 404, "unwritten route is sealed")
        if principal is None:
            return RouteAdmission(False, 401, "verified principal required", domain=domain)
        return RouteAdmission(
            True,
            200,
            "verified principal admitted to written route",
            domain=domain,
            principal_id=principal.principal_id,
            attester_id=principal.attester_id,
        )


def default_route_domain_policy() -> CatalogRouteDomainPolicy:
    """Build the immutable default report-only domain policy."""

    return CatalogRouteDomainPolicy(
        exact_open_paths=OPEN_EXACT_PATHS,
        open_prefixes=OPEN_ROUTE_PREFIXES,
        domain_rules=ROUTE_DOMAIN_RULES,
    )


def catalog_summary() -> dict[str, object]:
    """Expose non-secret policy metadata for diagnostics and docs."""

    return {
        "version": ROUTE_POLICY_CATALOG_VERSION,
        "open_prefixes": list(OPEN_ROUTE_PREFIXES),
        "exact_open_paths": list(OPEN_EXACT_PATHS),
        "domain_rules": [
            {"prefix": rule.prefix, "domain": rule.domain} for rule in ROUTE_DOMAIN_RULES
        ],
        "enforcement": "report_only",
        "fallback_domain": "legacy_api",
    }
