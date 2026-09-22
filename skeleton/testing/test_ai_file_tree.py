from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / "scripts/check_ai_file_tree.py"


def _module():
    spec = importlib.util.spec_from_file_location("check_ai_file_tree", CHECK)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ai_file_tree_manifest_is_valid_and_drift_free() -> None:
    assert _module().validate() == []


def test_ai_file_tree_contains_jeeves_and_build_planning() -> None:
    assert (ROOT / "skeleton/ai/agents/jeeves/__init__.py").is_file()
    assert (ROOT / "skeleton/ai/build/shift_supervisor/__init__.py").is_file()


def test_ai_file_tree_keeps_provider_boundary_explicit() -> None:
    assert (ROOT / "skeleton/ai/providers/contract.py").is_file()
    assert (ROOT / "skeleton/ai/providers/runtime.py").is_file()


def test_ai_file_tree_credential_surfaces_are_facades() -> None:
    provider = (ROOT / "skeleton/ai/providers/runtime.py").read_text(encoding="utf-8")
    gateway = (ROOT / "skeleton/ai/build/shift_supervisor/model_gateway.py").read_text(encoding="utf-8")
    assert "from skeleton.provider_runtime import" in provider
    assert "from core.shift_supervisor.model_gateway import" in gateway
    for source in (provider, gateway):
        assert "OPENAI_API_KEY" not in source
        assert "api.openai.com" not in source
        assert "from openai import" not in source


def test_python_parity_allows_formatting_but_rejects_semantic_drift(tmp_path: Path) -> None:
    module = _module()
    source = tmp_path / "source.py"
    destination = tmp_path / "destination.py"

    source.write_text("def value(x: int) -> int:\n    return x + 1\n", encoding="utf-8")
    destination.write_text(
        "def value( x: int )->int:\n\n    return (x + 1)\n",
        encoding="utf-8",
    )
    assert module._content_equivalent(source, destination)

    destination.write_text("def value(x: int) -> int:\n    return x + 2\n", encoding="utf-8")
    assert not module._content_equivalent(source, destination)


def test_ai_file_tree_native_and_path_audit() -> None:
    import json

    manifest = json.loads((ROOT / "machine/ai_file_tree.json").read_text(encoding="utf-8"))
    mapping_by_id = {item["id"]: item for item in manifest["mappings"]}
    assert mapping_by_id["AIFT-NATIVE"]["source"] == "skeleton/native"
    assert mapping_by_id["AIFT-NATIVE"]["destination"] == "skeleton/ai/runtime/native"
    assert mapping_by_id["AIFT-NATIVE"]["volume_refs"] == ["VOL-032"]
    assert (ROOT / "skeleton/ai/runtime/native/registry.py").is_file()

    audit = manifest["planned_path_audit"]
    external = {item["path"] for item in audit["intentionally_external"]}
    assert {"skeleton/app", "skeleton/config", "skeleton/deploy", "skeleton/testing"} <= external
    assert "skeleton/research" in audit["planned_but_absent"]
    assert "skeleton/planning" in audit["planned_but_absent"]
