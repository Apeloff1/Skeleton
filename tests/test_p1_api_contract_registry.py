from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
from types import ModuleType


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/check_p1_api_contract_registry.py"
REGISTRY = ROOT / "machine/p1_api_contract_registry.json"
RUNTIME = ROOT / "machine/ai_runtime_schemas.json"
ROUTE = ROOT / "backend/routes/operation_stream.py"
ROUTE_REGISTRY = ROOT / "backend/core/routes_registry.py"


def _module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_p1_api_contract_registry", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _repo(tmp_path: Path) -> Path:
    for source in (REGISTRY, RUNTIME, ROUTE, ROUTE_REGISTRY):
        target = tmp_path / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    return tmp_path


def _mutate(path: Path, fn) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    fn(payload)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_repository_api_registry_covers_complete_operation_module() -> None:
    module = _module()
    summary = module.validate_repository(ROOT)

    assert summary["valid"] is True
    assert summary["contract_count"] == 6
    assert summary["migration_count"] == 0
    assert len(summary["registry_digest"]) == 64
    assert summary["route_inventory"] == [
        "GET /api/operations/{operation_id}",
        "GET /api/operations/{operation_id}/events",
        "GET /api/operations/{operation_id}/events/replay",
        "GET /api/operations/{operation_id}/events/resync",
        "POST /api/operations/{operation_id}/cancel",
        "POST /api/operations/{operation_id}/events/ack",
    ]


def test_missing_declared_endpoint_fails_closed(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    registry = root / "machine/p1_api_contract_registry.json"
    _mutate(registry, lambda payload: payload["contracts"].pop())

    module = _module()
    try:
        module.validate_repository(root)
    except module.RegistryValidationError as exc:
        assert "route inventory drift" in str(exc)
    else:
        raise AssertionError("missing route unexpectedly validated")


def test_stale_path_fails_closed(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    registry = root / "machine/p1_api_contract_registry.json"

    def mutate(payload: dict) -> None:
        payload["contracts"][0]["path"] = "/api/operations/{operation_id}/stale"

    _mutate(registry, mutate)
    module = _module()
    try:
        module.validate_repository(root)
    except module.RegistryValidationError as exc:
        assert "route inventory drift" in str(exc)
    else:
        raise AssertionError("stale route unexpectedly validated")


def test_unknown_runtime_schema_fails_closed(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    registry = root / "machine/p1_api_contract_registry.json"

    def mutate(payload: dict) -> None:
        payload["contracts"][0].pop("response_schema_ref")
        payload["contracts"][0]["response_schema_ref"] = "MissingRecord"

    _mutate(registry, mutate)
    module = _module()
    try:
        module.validate_repository(root)
    except module.RegistryValidationError as exc:
        assert "unknown runtime schema" in str(exc)
    else:
        raise AssertionError("unknown runtime schema unexpectedly validated")


def test_identical_machine_registries_are_compatible(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    baseline = root / "baseline.json"
    shutil.copyfile(root / "machine/p1_api_contract_registry.json", baseline)

    module = _module()
    result = module.compare_registries(
        root,
        baseline_path=Path("baseline.json"),
        observed_at_epoch=1_900_000_000,
    )

    assert result["accepted"] is True
    assert result["breaking"] == []
    assert len(result["decision_digest"]) == 64


def test_schema_drift_without_migration_is_rejected(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    baseline = root / "baseline.json"
    shutil.copyfile(root / "machine/p1_api_contract_registry.json", baseline)
    registry = root / "machine/p1_api_contract_registry.json"

    def mutate(payload: dict) -> None:
        row = payload["contracts"][0]
        row["version"] = 2
        row.pop("response_schema_ref")
        row["response_shape"] = {"changed": True}

    _mutate(registry, mutate)
    module = _module()
    result = module.compare_registries(
        root,
        baseline_path=Path("baseline.json"),
        observed_at_epoch=1_900_000_000,
    )

    assert result["accepted"] is False
    assert result["breaking"] == ["operation.status:missing-migration-rule"]


def test_route_source_drift_is_detected_independently_of_registry(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    route = root / "backend/routes/operation_stream.py"
    text = route.read_text(encoding="utf-8")
    text = text.replace(
        '@router.get("/{operation_id}/events/replay")',
        '@router.get("/{operation_id}/events/history")',
        1,
    )
    route.write_text(text, encoding="utf-8")

    module = _module()
    try:
        module.validate_repository(root)
    except module.RegistryValidationError as exc:
        assert "route inventory drift" in str(exc)
    else:
        raise AssertionError("route source drift unexpectedly validated")

def test_machine_mount_prefix_cannot_drift_from_route_registry(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    registry = root / "machine/p1_api_contract_registry.json"

    def mutate(payload: dict) -> None:
        payload["scope"]["mount_prefix"] = "/fake"
        for row in payload["contracts"]:
            row["path"] = row["path"].replace("/api/", "/fake/", 1)

    _mutate(registry, mutate)
    module = _module()
    try:
        module.validate_repository(root)
    except module.RegistryValidationError as exc:
        assert "mount_prefix" in str(exc)
    else:
        raise AssertionError("spoofed mount prefix unexpectedly validated")


def test_machine_router_prefix_cannot_drift_from_source(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    registry = root / "machine/p1_api_contract_registry.json"

    def mutate(payload: dict) -> None:
        payload["scope"]["router_prefix"] = "/other"

    _mutate(registry, mutate)
    module = _module()
    try:
        module.validate_repository(root)
    except module.RegistryValidationError as exc:
        assert "router_prefix" in str(exc)
    else:
        raise AssertionError("spoofed router prefix unexpectedly validated")
