from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/check_p1_reasoning_strategy_registry.py"
REGISTRY = ROOT / "machine/p1_reasoning_strategy_registry.json"
MASTER = ROOT / "machine/ai_master_plan.json"


def _module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "check_p1_reasoning_strategy_registry",
        SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _copy(tmp_path: Path) -> Path:
    machine = tmp_path / "machine"
    machine.mkdir(parents=True, exist_ok=True)
    target = machine / REGISTRY.name
    target.write_text(REGISTRY.read_text(encoding="utf-8"), encoding="utf-8")
    (machine / MASTER.name).write_text(
        MASTER.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    return target


def _mutate(tmp_path: Path, mutation) -> None:
    target = _copy(tmp_path)
    payload = json.loads(target.read_text(encoding="utf-8"))
    mutation(payload)
    target.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )


def test_repository_reasoning_strategy_registry_is_valid() -> None:
    module = _module()

    errors, summary = module.validate_repository(ROOT)

    assert errors == []
    assert summary["valid"] is True
    assert summary["strategy_count"] == 5
    assert len(summary["registry_digest"]) == 64


def test_registry_rejects_strategy_inventory_drift(tmp_path: Path) -> None:
    module = _module()
    _mutate(tmp_path, lambda payload: payload["strategies"].pop())

    errors, _ = module.validate_repository(tmp_path)

    assert any("strategy inventory drift" in error for error in errors)


def test_registry_rejects_selection_policy_drift(tmp_path: Path) -> None:
    module = _module()

    def mutation(payload: dict) -> None:
        payload["selection_policy"]["model_self_confidence_is_not_authority"] = False

    _mutate(tmp_path, mutation)
    errors, _ = module.validate_repository(tmp_path)

    assert "selection_policy drift" in errors


def test_registry_rejects_stop_policy_drift(tmp_path: Path) -> None:
    module = _module()

    def mutation(payload: dict) -> None:
        payload["stop_policy"]["over_budget"] = "continue"

    _mutate(tmp_path, mutation)
    errors, _ = module.validate_repository(tmp_path)

    assert "stop_policy drift" in errors


def test_registry_rejects_missing_verification_capability(
    tmp_path: Path,
) -> None:
    module = _module()

    def mutation(payload: dict) -> None:
        payload["strategies"][0]["capabilities"] = ["direct"]

    _mutate(tmp_path, mutation)
    errors, _ = module.validate_repository(tmp_path)

    assert any("verification capability is required" in error for error in errors)


def test_registry_rejects_duplicate_priority(tmp_path: Path) -> None:
    module = _module()

    def mutation(payload: dict) -> None:
        payload["strategies"][1]["priority"] = payload["strategies"][0]["priority"]

    _mutate(tmp_path, mutation)
    errors, _ = module.validate_repository(tmp_path)

    assert "strategy priorities must be unique" in errors


def test_registry_rejects_masterplan_pointer_drift(tmp_path: Path) -> None:
    module = _module()
    _copy(tmp_path)
    master = tmp_path / "machine" / MASTER.name
    payload = json.loads(master.read_text(encoding="utf-8"))
    payload["authority"]["p1_reasoning_strategy_registry"] = "machine/wrong.json"
    master.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )

    errors, _ = module.validate_repository(tmp_path)

    assert "master plan reasoning strategy registry pointer drift" in errors


def test_registry_rejects_invalid_budget(tmp_path: Path) -> None:
    module = _module()

    def mutation(payload: dict) -> None:
        payload["strategies"][0]["limits"]["iterations"] = 0

    _mutate(tmp_path, mutation)
    errors, _ = module.validate_repository(tmp_path)

    assert any("registry contract invalid" in error for error in errors)
