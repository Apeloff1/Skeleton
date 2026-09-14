import pytest

from core.principal_seal import RouteDomainPolicy, RouteRule
from core.route_policy_coverage import (
    RoutePolicyCoverageError,
    build_route_policy_coverage,
    require_complete_route_policy,
)


def policy() -> RouteDomainPolicy:
    return RouteDomainPolicy(
        open_prefixes=("/api/health", "/api/ready"),
        domain_rules=(
            RouteRule("/api/jeeves", "jeeves"),
            RouteRule("/api/studio", "studio"),
            RouteRule("/api/studio/admin", "studio_admin"),
        ),
    )


def test_coverage_reports_open_protected_and_unwritten_routes_deterministically():
    report = build_route_policy_coverage(
        policy(),
        [
            "/api/studio/projects/{project_id}",
            "/api/health",
            "/api/unknown",
            "/api/studio/admin/jobs",
            "/api/jeeves/run",
            "/api/health",
        ],
    )

    assert report.total_routes == 5
    assert report.open_routes == 1
    assert report.protected_routes == 3
    assert report.unwritten_routes == 1
    assert report.coverage_ratio == pytest.approx(0.8)
    assert report.complete is False
    assert report.domain_counts == (("jeeves", 1), ("studio", 1), ("studio_admin", 1))
    assert report.unwritten_paths == ("/api/unknown",)
    assert report.protected_paths == (
        ("/api/jeeves/run", "jeeves"),
        ("/api/studio/admin/jobs", "studio_admin"),
        ("/api/studio/projects/{project_id}", "studio"),
    )


def test_exact_exclusions_do_not_create_unsafe_prefix_bypass():
    report = build_route_policy_coverage(
        policy(),
        ["/docs", "/docs/internal", "/api/ready"],
        excluded_paths=["/docs"],
    )
    assert report.total_routes == 2
    assert report.open_paths == ("/api/ready",)
    assert report.unwritten_paths == ("/docs/internal",)


def test_complete_report_can_be_promoted_to_enforcement_gate():
    report = build_route_policy_coverage(
        policy(),
        ["/api/health/live", "/api/jeeves/run", "/api/studio/assets"],
    )
    assert report.complete is True
    assert report.coverage_ratio == 1.0
    require_complete_route_policy(report)


def test_incomplete_report_fails_closed_with_bounded_route_sample():
    paths = ["/api/jeeves/run"] + [f"/unwritten/{index}" for index in range(12)]
    report = build_route_policy_coverage(policy(), paths)
    with pytest.raises(RoutePolicyCoverageError) as caught:
        require_complete_route_policy(report)
    message = str(caught.value)
    assert "12/13 unwritten" in message
    assert "/unwritten/0" in message
    assert "/unwritten/7" in message
    assert "/unwritten/8" not in message
    assert message.endswith(", ...")


def test_json_friendly_snapshot_preserves_domain_and_path_evidence():
    report = build_route_policy_coverage(
        policy(),
        ["/api/health", "/api/jeeves/run", "/api/studio/admin/jobs"],
    )
    snapshot = report.as_dict()
    assert snapshot == {
        "total_routes": 3,
        "open_routes": 1,
        "protected_routes": 2,
        "unwritten_routes": 0,
        "coverage_ratio": 1.0,
        "complete": True,
        "domain_counts": {"jeeves": 1, "studio_admin": 1},
        "open_paths": ["/api/health"],
        "protected_paths": [
            {"path": "/api/jeeves/run", "domain": "jeeves"},
            {"path": "/api/studio/admin/jobs", "domain": "studio_admin"},
        ],
        "unwritten_paths": [],
    }


def test_inventory_rejects_blank_non_path_and_query_bearing_entries():
    for paths in ([""], ["relative"], ["/api/studio?mode=admin"]):
        with pytest.raises(ValueError):
            build_route_policy_coverage(policy(), paths)
    with pytest.raises(TypeError):
        build_route_policy_coverage(policy(), [123])
