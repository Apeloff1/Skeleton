from core.route_policy_catalog import (
    OPEN_ROUTE_PREFIXES,
    ROUTE_DOMAIN_RULES,
    ROUTE_POLICY_CATALOG_VERSION,
    catalog_summary,
    default_route_domain_policy,
)
from core.principal_seal import VerifiedPrincipal


def principal() -> VerifiedPrincipal:
    return VerifiedPrincipal(
        principal_id="operator",
        attester_id="control",
        key_id="k1",
        issued_at=1,
        expires_at=2,
    )


def test_catalog_version_and_summary_are_stable_and_report_only():
    assert ROUTE_POLICY_CATALOG_VERSION == "2026-09-15.v1"
    summary = catalog_summary()
    assert summary["version"] == ROUTE_POLICY_CATALOG_VERSION
    assert summary["enforcement"] == "report_only"
    assert summary["fallback_domain"] == "legacy_api"
    assert summary["open_prefixes"] == list(OPEN_ROUTE_PREFIXES)
    assert len(summary["domain_rules"]) == len(ROUTE_DOMAIN_RULES)


def test_open_routes_are_narrow_bootstrap_surfaces_only():
    policy = default_route_domain_policy()
    for path in (
        "/api/health",
        "/api/health/live",
        "/api/ready",
        "/api/auth/login",
        "/api/auth/register",
        "/api/auth/session",
    ):
        admitted = policy.admit(path, None)
        assert admitted.allowed is True
        assert admitted.open_route is True

    # Adjacent identity/admin paths must not inherit public access.
    for path in ("/api/auth/me", "/api/auth/users", "/api/auth/set-role"):
        admitted = policy.admit(path, None)
        assert admitted.allowed is False
        assert admitted.status_code == 401
        assert admitted.domain == "identity"


def test_specific_domains_win_before_legacy_fallback():
    policy = default_route_domain_policy()
    expectations = {
        "/api/deployment/checkpoint": "deployment",
        "/api/ops/status": "operations",
        "/api/governance/policy": "governance",
        "/api/orchestrator/jeeves/status": "jeeves",
        "/api/gameforge/rooms": "gameforge",
        "/api/galaxy-studio/build": "studio",
        "/api/worldforge/worlds": "worldforge",
        "/api/vault/stats": "vault",
        "/api/interpreter/run": "code_execution",
        "/api/compiler/compile": "code_execution",
        "/api/tools/invoke": "tooling",
        "/api/unknown-legacy-surface": "legacy_api",
    }
    actor = principal()
    for path, domain in expectations.items():
        assert policy.required_domain(path) == domain
        admitted = policy.admit(path, actor)
        assert admitted.allowed is True
        assert admitted.domain == domain
        assert admitted.principal_id == actor.principal_id


def test_non_api_paths_remain_sealed_even_with_verified_identity():
    policy = default_route_domain_policy()
    admitted = policy.admit("/internal/debug", principal())
    assert admitted.allowed is False
    assert admitted.status_code == 404
    assert admitted.reason == "unwritten route is sealed"
