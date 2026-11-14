"""Catalog ownership, scope tiers, policy/route derivation."""

from __future__ import annotations

import pytest

from skeleton.gate_plane.s2s.authz import PolicyError, PolicyTable, Principal, RoutePolicy, default_gate_plane_policies
from skeleton.gate_plane.systems.catalog import (
    JEEVES_LEGACY_FAMILIES,
    CatalogError,
    SystemCatalog,
    SystemLimits,
    SystemProfile,
    default_catalog,
)
from skeleton.gate_plane.systems.policies import catalog_policies, catalog_routes, merge_into, system_routes


def P(service, *scopes, overlap=False):
    return Principal(service=service, scopes=frozenset(scopes), kid="test-k1", in_overlap=overlap)


def test_default_catalog_owns_the_four_recovered_systems():
    cat = default_catalog()
    assert cat.names() == ["gameforge", "hive", "jeeves", "local_ai"]
    assert cat.resolve("/api/jeeves/director/run").name == "jeeves"
    assert cat.resolve("/jeeves/health").name == "jeeves"
    for fam in JEEVES_LEGACY_FAMILIES:
        assert cat.resolve(f"/api/{fam}/x").name == "jeeves"
    assert cat.resolve("/api/gameforge/runtime/tick").name == "gameforge"
    assert cat.resolve("/api/llm-router/route").name == "local_ai"
    assert cat.resolve("/api/v1/local-ai/chat").name == "local_ai"
    assert cat.resolve("/api/v1/hive/verify").name == "hive"


@pytest.mark.parametrize("path", ["/api/v1/forge/x", "/api/jeevesx/a", "/api/v1/health", "/", "/api/gameforgex"])
def test_unowned_paths_resolve_to_none(path):
    assert default_catalog().resolve(path) is None


def test_scope_tiers():
    gf = default_catalog().get("gameforge")
    assert gf.required_scopes("GET", "/api/gameforge/map") == ("read", frozenset({"gameforge:read", "gameforge:write"}))
    assert gf.required_scopes("POST", "/api/gameforge/map") == ("write", frozenset({"gameforge:write"}))
    assert gf.required_scopes("GET", "/api/gameforge/build/7")[0] == "admin"
    la = default_catalog().get("local_ai")
    assert la.required_scopes("POST", "/api/v1/local-ai/chat") == ("write", frozenset({"local_ai:infer"}))
    assert la.loopback_only


def test_overlapping_systems_rejected():
    a = SystemProfile.build("alpha", "A", ["/api/a/**"])
    b = SystemProfile.build("beta", "B", ["/api/a/b/**"])
    with pytest.raises(CatalogError, match="overlaps"):
        SystemCatalog([a, b])
    with pytest.raises(CatalogError, match="duplicate"):
        SystemCatalog([a, SystemProfile.build("alpha", "A2", ["/api/z/**"])])
    with pytest.raises(CatalogError, match="share upstream"):
        SystemCatalog([a, SystemProfile.build("gamma", "G", ["/api/g/**"], upstream=a.upstream)])


@pytest.mark.parametrize(
    "kwargs, msg",
    [
        ({"name": "Bad"}, "invalid system name"),
        ({"patterns": []}, "at least one"),
        ({"patterns": ["nope"]}, "must start"),
        ({"admin_patterns": ["/elsewhere/**"]}, "not inside"),
        ({"methods": ["TRACE"]}, "unsupported"),
        ({"allow_services": ["svc"], "deny_services": ["svc"]}, "both allowed"),
        ({"priority": 12}, "priority"),
    ],
)
def test_profile_validation(kwargs, msg):
    base = {"name": "sys", "title": "t", "patterns": ["/api/sys/**"]}
    base.update(kwargs)
    with pytest.raises(CatalogError, match=msg):
        SystemProfile.build(base.pop("name"), base.pop("title"), base.pop("patterns"), **base)


@pytest.mark.parametrize(
    "kwargs",
    [{"max_body_bytes": 0}, {"max_concurrency": 0}, {"deadline_s": 0}, {"retry_attempts": 9}, {"breaker_failures": 0}],
)
def test_limits_validation(kwargs):
    with pytest.raises(CatalogError):
        SystemLimits(**kwargs)


def test_write_deadline():
    lim = SystemLimits(deadline_s=5.0, write_deadline_s=50.0)
    assert lim.deadline_for("GET") == 5.0
    assert lim.deadline_for("post") == 50.0


def test_round_trip_and_digest_stable():
    cat = default_catalog()
    again = SystemCatalog.from_dicts(cat.to_dicts())
    assert again.digest() == cat.digest()
    with pytest.raises(CatalogError, match="unknown profile keys"):
        SystemProfile.from_dict({"name": "x1", "patterns": ["/x/**"], "bogus": 1})
    with pytest.raises(CatalogError, match="bad limits"):
        SystemProfile.from_dict({"name": "x1", "patterns": ["/x/**"], "limits": {"nope": 1}})


def test_catalog_policies_are_default_deny_and_tiered():
    t = catalog_policies()
    assert not t.evaluate("GET", "/api/v1/forge/x", P("svc", "forge:read")).allowed
    assert t.evaluate("GET", "/api/jeeves/a", P("svc", "jeeves:read")).allowed
    assert not t.evaluate("POST", "/api/jeeves/a", P("svc", "jeeves:read")).allowed
    assert t.evaluate("POST", "/api/jeeves/a", P("svc", "jeeves:write")).allowed
    assert t.evaluate("GET", "/api/v1/hive/capabilities", Principal.anonymous_principal()).allowed
    assert not t.evaluate("GET", "/api/v1/hive/verify", Principal.anonymous_principal()).allowed
    d = t.evaluate("POST", "/api/gameforge/build/1", P("svc", "gameforge:write"))
    assert not d.allowed and d.reason.value == "missing_scope"
    assert t.evaluate("POST", "/api/gameforge/build/1", P("svc", "gameforge:build")).allowed
    assert not t.evaluate("POST", "/api/gameforge/build/1", P("svc", "gameforge:build", overlap=True)).allowed


def test_merge_into_extends_base_without_overriding():
    base = default_gate_plane_policies()
    merged = merge_into(base)
    assert len(merged) == len(base) + len(catalog_policies())
    assert {p.name for p in base.policies()} <= {p.name for p in merged.policies()}
    assert merged.evaluate("GET", "/api/v1/forge/x", P("svc", "forge:read")).allowed
    assert merged.evaluate("GET", "/api/gameforge/x", P("svc", "gameforge:read")).allowed


def test_merge_conflict_raises():
    clash = PolicyTable([RoutePolicy.build("x", "/api/v1/hive/**", methods=["GET", "HEAD", "OPTIONS"], scopes_any=["a:b"])])
    with pytest.raises(PolicyError, match="conflicts with base"):
        merge_into(clash)


def test_routes_per_system_upstream():
    table = catalog_routes()
    r = table.match("POST", "/api/v1/local-ai/chat")
    assert r.upstream == "system-local-ai" and r.timeout_s == 120.0 and r.retry.max_attempts == 1
    g = table.match("GET", "/api/gameforge/map")
    assert g.upstream == "system-gameforge" and g.timeout_s == 30.0
    assert table.match("GET", "/api/v1/forge/x") is None
    for route in system_routes(default_catalog().get("jeeves")):
        assert route.retry.max_attempts <= 2
