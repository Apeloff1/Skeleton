"""Fail-closed integration of vertical and surface specification into app assembly."""
from __future__ import annotations

from unittest.mock import patch

from scripts import check_app_assembly as assembly


def test_vertical_contract_failure_is_not_silently_dropped(monkeypatch):
    monkeypatch.setattr(assembly, "FAILURES", [])
    monkeypatch.setattr(assembly, "CHECKS", 0)
    with patch.object(
        assembly,
        "validate_vertical_readiness",
        return_value=(["missing governed action"], {
            "target_grade": "S",
            "vertical_count": 7,
            "operation_count": 21,
            "contract_qualified": False,
        }),
    ):
        assembly.audit_product_vertical_readiness()
    assert any("product vertical readiness contract failed" in item for item in assembly.FAILURES)
    assert any("not qualified" in item for item in assembly.FAILURES)
    assert assembly.CHECKS >= 5


def test_surface_contract_failure_is_not_silently_dropped(monkeypatch):
    monkeypatch.setattr(assembly, "FAILURES", [])
    monkeypatch.setattr(assembly, "CHECKS", 0)
    with patch.object(
        assembly,
        "validate_surface_specification",
        return_value=["unregistered route", "unbound hub modal"],
    ):
        assembly.audit_product_surface_specification()
    assert any("product surface specification failed" in item for item in assembly.FAILURES)
    assert assembly.CHECKS == 1


def test_entrypoint_runs_both_contracts_and_retains_preinstall_audit(monkeypatch):
    calls = []
    for name in (
        "audit_preinstall_docker_sources",
        "audit_manifest",
        "audit_topology_alignment",
        "audit_backend_public_identity",
        "audit_no_competing_root_launchers",
        "audit_endpoint_boundary",
        "audit_compose_modes",
        "audit_production_ingress",
        "audit_launcher_convergence",
        "audit_product_catalog_alignment",
        "audit_public_app_bootstrap_contract",
        "audit_product_health_contract",
        "audit_public_product_readiness_contract",
        "audit_product_control_contract",
        "audit_product_route_registry",
        "audit_product_vertical_readiness",
        "audit_product_surface_specification",
    ):
        monkeypatch.setattr(assembly, name, lambda name=name: calls.append(name))
    monkeypatch.setattr(assembly, "FAILURES", [])
    monkeypatch.setattr(assembly, "CHECKS", 0)
    assert assembly.main() == 0
    assert calls[0] == "audit_preinstall_docker_sources"
    assert calls[-2:] == ["audit_product_vertical_readiness", "audit_product_surface_specification"]
    assert len(calls) == 17
