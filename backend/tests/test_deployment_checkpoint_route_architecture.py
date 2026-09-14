from __future__ import annotations

import ast
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[1]
ROUTE = BACKEND / "routes" / "deployment_checkpoint_trust.py"
REGISTRY = BACKEND / "core" / "routes_registry.py"


def test_witness_route_never_constructs_a_parallel_pin_runtime():
    source = ROUTE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    constructors = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (
            isinstance(node.func, ast.Name) and node.func.id == "DeploymentCheckpointPinRuntime"
            or isinstance(node.func, ast.Attribute) and node.func.attr == "DeploymentCheckpointPinRuntime"
        )
    ]
    assert constructors == []
    assert "_control_plane().deployment_checkpoint_pins" in source
    assert "external-checkpoint-pins" not in source


def test_witness_route_keeps_read_signing_target_and_external_receipt_ingestion():
    source = ROUTE.read_text(encoding="utf-8")
    for contract in (
        '@router.get("/target")',
        '@router.post("/receipts")',
        '@router.get("/status")',
        '@router.get("/diagnostics")',
        '@router.get("/policy")',
        '@router.get("/bundle")',
        '@router.get("/trust-advance")',
        '@router.get("/continuity")',
    ):
        assert contract in source
    assert "private_key" not in source
    assert "sign_deployment_checkpoint_pin" not in source
    assert '"authority": "out-of-band-digest-required"' in source


def test_witness_route_remains_registered_for_server_boot():
    source = REGISTRY.read_text(encoding="utf-8")
    assert '("routes.deployment_checkpoint_trust",      "router")' in source
