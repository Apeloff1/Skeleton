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

def test_ai_file_tree_cortex_and_organism_keep_sensitive_owners_singular() -> None:
    import json

    manifest = json.loads((ROOT / "machine/ai_file_tree.json").read_text(encoding="utf-8"))
    mapping_by_id = {item["id"]: item for item in manifest["mappings"]}

    cortex = mapping_by_id["AIFT-CORTEX"]
    organism = mapping_by_id["AIFT-ORGANISM"]
    assert cortex["source"] == "skeleton/cortex"
    assert cortex["destination"] == "skeleton/ai/runtime/cortex"
    assert organism["source"] == "skeleton/organism"
    assert organism["destination"] == "skeleton/ai/runtime/organism"

    cortex_interchange = (ROOT / "skeleton/ai/runtime/cortex/interchange.py").read_text(encoding="utf-8")
    cortex_gates = (ROOT / "skeleton/ai/runtime/cortex/gates.py").read_text(encoding="utf-8")
    organism_secrets = (ROOT / "skeleton/ai/runtime/organism/secret_manager.py").read_text(encoding="utf-8")

    assert "from skeleton.cortex.interchange import *" in cortex_interchange
    assert "from skeleton.cortex.gates import *" in cortex_gates
    assert "from skeleton.organism.secret_manager import *" in organism_secrets

    assert "KIMI_API_KEY" not in cortex_interchange
    assert "OPENAI_API_KEY" not in cortex_gates
    assert "SKELETON_MASTER_SECRET" not in organism_secrets


def test_ai_file_tree_pending_assignments_follow_masterplan() -> None:
    import json

    manifest = json.loads((ROOT / "machine/ai_file_tree.json").read_text(encoding="utf-8"))
    assignments = {item["source"]: item for item in manifest["next_move_assignments"]}

    assert assignments["skeleton/state"]["destination"] == "skeleton/ai/runtime/state"
    assert assignments["skeleton/network"]["destination"] == "skeleton/ai/runtime/distributed/network"
    assert assignments["skeleton/kv"]["destination"] == "skeleton/ai/runtime/inference/kv"
    assert assignments["skeleton/swarm"]["destination"] == "skeleton/ai/agents/swarm"
    assert assignments["skeleton/foundation"]["destination"] == "skeleton/ai/runtime/foundation"
    assert assignments["skeleton/build"]["destination"] == "skeleton/ai/build/core"
    assert assignments["skeleton/repo_machine"]["destination"] == "skeleton/ai/build/repo_machine"
    assert assignments["skeleton/acquired/learning.py"]["action"] == "split_then_mirror"
    assert assignments["skeleton/persist"]["action"] == "merge_into_existing_owner"
    assert assignments["skeleton/application"]["destination"] == "skeleton/ai/runtime/application"
    assert assignments["skeleton/core"]["destination"] == "skeleton/ai/runtime/core"
    assert assignments["skeleton/data"]["destination"] == "skeleton/ai/runtime/data"
    assert assignments["skeleton/genesis.py"]["destination"] == "skeleton/ai/runtime/bootstrap/genesis.py"
    assert assignments["skeleton/galaxy"]["destination"] == "skeleton/ai/runtime/distributed/galaxy"
    assert assignments["skeleton/pr_automation"]["destination"] == "skeleton/ai/build/pr_automation"
    assert assignments["skeleton/school"]["destination"] == "skeleton/ai/learning/school"
    assert assignments["skeleton/social"]["destination"] == "skeleton/ai/research/social"
    assert assignments["skeleton/viscera"]["action"] == "quarantine_then_characterize"

    for item in assignments.values():
        assert item["destination"].startswith("skeleton/ai/")
        assert item["work_package_refs"]
        assert item["preconditions"]
        assert len(item["source_git_object_sha"]) == 40


def test_ai_file_tree_classifies_non_move_top_level_surfaces() -> None:
    import json

    manifest = json.loads((ROOT / "machine/ai_file_tree.json").read_text(encoding="utf-8"))
    retained = {item["path"]: item for item in manifest["retained_outside_ai_tree"]}

    assert retained["skeleton/architecture.py"]["owner"] == "architecture authority"
    assert retained["skeleton/architecture_index.py"]["owner"] == "architecture authority"
    assert retained["skeleton/acquired"]["owner"] == "quarantine/provenance"
    assert retained["skeleton/release"]["owner"] == "release engineering"
    assert retained["skeleton/ubuntu"]["owner"] == "deployment/platform support"
    assert retained["skeleton/__main__.py"]["owner"] == "package CLI shell"
