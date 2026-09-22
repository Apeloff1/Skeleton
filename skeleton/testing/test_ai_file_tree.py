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


def test_ai_file_tree_move_preparation_tags_cover_all_governed_mappings() -> None:
    import json

    manifest = json.loads((ROOT / "machine/ai_file_tree.json").read_text(encoding="utf-8"))
    mappings = {item["source"]: item for item in manifest["mappings"]}

    promoted_sources = {
        "skeleton/state",
        "skeleton/network",
        "skeleton/kv",
        "skeleton/swarm",
        "skeleton/foundation",
        "skeleton/build",
        "skeleton/repo_machine",
        "skeleton/acquired/learning.py",
        "skeleton/persist",
        "skeleton/application",
        "skeleton/core",
        "skeleton/data",
        "skeleton/genesis.py",
        "skeleton/galaxy",
        "skeleton/pr_automation",
        "skeleton/school",
        "skeleton/social",
        "skeleton/viscera",
    }
    assert promoted_sources <= mappings.keys()
    assert manifest["next_move_assignments"] == []

    contract = manifest["move_tag_contract"]
    assert contract["global_state"] == "prepared_not_cutover_authorized"
    assert set(contract["batches"]) == {
        "B1-core-runtime",
        "B2-domain-build",
        "B3-owner-sensitive",
        "B3-compat-convergence",
        "B4-research-quarantine",
    }

    for item in mappings.values():
        assert item["move_tags"][0:2] == ["ai-tree:mapped", "migration:staged-mirror"]
        assert len([tag for tag in item["move_tags"] if tag.startswith("cutover:")]) == 1
        assert item["move_batch"] in contract["batches"]
        assert item["source_disposition"]

    assert mappings["skeleton/provider_runtime.py"]["move_batch"] == "B3-owner-sensitive"
    assert "cutover:owner-sensitive" in mappings["skeleton/provider_runtime.py"]["move_tags"]
    assert mappings["skeleton/viscera"]["move_batch"] == "B4-research-quarantine"
    assert "cutover:quarantine" in mappings["skeleton/viscera"]["move_tags"]
    assert mappings["skeleton/turn"]["move_batch"] == "B3-compat-convergence"
    assert "cutover:merge-required" in mappings["skeleton/turn"]["move_tags"]
    assert mappings["skeleton/telemetry"]["move_batch"] == "B3-compat-convergence"
    assert "cutover:merge-required" in mappings["skeleton/telemetry"]["move_tags"]


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


def test_ai_file_tree_overlay_children_are_separately_governed() -> None:
    import json

    manifest = json.loads((ROOT / "machine/ai_file_tree.json").read_text(encoding="utf-8"))
    mappings = manifest["mappings"]
    destinations = {item["destination"] for item in mappings}
    overlay_count = 0
    for item in mappings:
        for child in item.get("overlay_children", []):
            overlay_count += 1
            assert f"{item['destination']}/{child}" in destinations
    assert overlay_count >= 12


def test_ai_file_tree_preserves_remaining_acquired_lineage() -> None:
    import json

    manifest = json.loads((ROOT / "machine/ai_file_tree.json").read_text(encoding="utf-8"))
    mappings = {item["id"]: item for item in manifest["mappings"]}
    expected = {
        "AIFT-ACQUIRED-GAMING": (
            "skeleton/acquired/gaming",
            "skeleton/ai/research/acquired/gaming",
        ),
        "AIFT-ACQUIRED-GATES": (
            "skeleton/acquired/gates",
            "skeleton/ai/research/acquired/gates",
        ),
        "AIFT-ACQUIRED-GENOS": (
            "skeleton/acquired/genos",
            "skeleton/ai/research/acquired/genos",
        ),
        "AIFT-ACQUIRED-INGEST": (
            "skeleton/acquired/ingest.py",
            "skeleton/ai/research/acquired/ingest.py",
        ),
    }

    for mapping_id, (source, destination) in expected.items():
        item = mappings[mapping_id]
        assert item["source"] == source
        assert item["destination"] == destination
        assert item["move_batch"] == "B4-research-quarantine"
        assert "cutover:quarantine" in item["move_tags"]
        assert (ROOT / destination).exists()

    assert manifest["pre_move_readiness"]["governed_mapping_count"] == 134
    assert manifest["pre_move_readiness"]["batch_counts"]["B4-research-quarantine"] == 39
