"""Canonical report-only route-domain catalog for staged API admission rollout.

This catalog deliberately does *not* install middleware. It classifies the
current API surface into stable governance domains so inventory coverage can be
measured before any global authentication/admission switch is enabled.

The final ``/api`` rule is an explicit migration bucket, not an authorization
shortcut. Routes landing in ``legacy_api`` remain protected in an eventual
fail-closed adapter, but should be promoted into narrower domains over time.
"""

from __future__ import annotations

from core.principal_seal import RouteDomainPolicy, RouteRule

ROUTE_POLICY_CATALOG_VERSION = "2026-09-15.v1"

# Public/bootstrap surfaces. Prefix semantics are intentional and bounded to
# narrow endpoint roots; broad application areas are never declared open.
OPEN_ROUTE_PREFIXES: tuple[str, ...] = (
    "/api/health",
    "/api/ready",
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/session",
)

# Longest-prefix matching in RouteDomainPolicy means specialized control-plane
# domains win before broader product domains and finally the migration bucket.
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


def default_route_domain_policy() -> RouteDomainPolicy:
    """Build the immutable default report-only domain policy."""

    return RouteDomainPolicy(
        open_prefixes=OPEN_ROUTE_PREFIXES,
        domain_rules=ROUTE_DOMAIN_RULES,
    )


def catalog_summary() -> dict[str, object]:
    """Expose non-secret policy metadata for diagnostics and docs."""

    return {
        "version": ROUTE_POLICY_CATALOG_VERSION,
        "open_prefixes": list(OPEN_ROUTE_PREFIXES),
        "domain_rules": [
            {"prefix": rule.prefix, "domain": rule.domain} for rule in ROUTE_DOMAIN_RULES
        ],
        "enforcement": "report_only",
        "fallback_domain": "legacy_api",
    }
