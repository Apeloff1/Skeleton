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


def test_ai_file_tree_live_summary_counts_match_governed_collections() -> None:
    import json

    manifest = json.loads((ROOT / "machine/ai_file_tree.json").read_text(encoding="utf-8"))
    mappings = manifest["mappings"]
    native_owners = manifest["native_ai_owners"]
    readiness = manifest["pre_move_readiness"]

    expected_batches: dict[str, int] = {}
    for mapping in mappings:
        batch = mapping["move_batch"]
        expected_batches[batch] = expected_batches.get(batch, 0) + 1

    assert readiness["governed_mapping_count"] == len(mappings)
    assert readiness["native_ai_owner_count"] == len(native_owners)
    assert readiness["batch_counts"] == expected_batches
    assert manifest["object_audit"]["current_mapping_count"] == len(mappings)
    assert manifest["validation_state"].startswith(
        f"{len(mappings)}_mapping_plus_{len(native_owners)}_native_owner_"
    )
    assert f"{len(mappings)}-mapping" in manifest["implementation_signoff"]["statement"]


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
    assert "from skeleton.automation.shift_supervisor.model_gateway import" in gateway
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
    assert "skeleton/research" not in audit["planned_but_absent"]
    assert mapping_by_id["AIFT-RESEARCH"]["source"] == "skeleton/research/__init__.py"
    assert mapping_by_id["AIFT-RESEARCH"]["move_batch"] == "B4-research-quarantine"
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
    aliases = {
        item["planned_path"]
        for item in manifest["planned_path_audit"]["covered_aliases"]
        if isinstance(item, dict) and isinstance(item.get("planned_path"), str)
    }

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
        "skeleton/app/runtime",
        "skeleton/core",
        "skeleton/data",
        "skeleton/bootstrap/genesis.py",
        "skeleton/galaxy",
        "skeleton/pr_automation",
        "skeleton/school",
        "skeleton/social",
        "skeleton/viscera",
    }
    assert promoted_sources <= (mappings.keys() | aliases)
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
    assert retained["skeleton/foundation/architecture/index.py"]["owner"] == "architecture authority"
    assert retained["skeleton/acquired"]["owner"] == "quarantine/provenance"
    assert retained["skeleton/release"]["owner"] == "release engineering"
    assert retained["skeleton/ubuntu"]["owner"] == "deployment/platform support"
    assert retained["skeleton/__main__.py"]["owner"] == "package CLI shell"


def test_ai_file_tree_overlay_children_are_separately_governed() -> None:
    import json

    manifest = json.loads((ROOT / "machine/ai_file_tree.json").read_text(encoding="utf-8"))
    mappings = manifest["mappings"]
    destinations = {item["destination"] for item in mappings}
    sources = {item["source"] for item in mappings}
    native_owners = {item["path"] for item in manifest["native_ai_owners"]}
    overlay_count = 0
    for item in mappings:
        for child in item.get("overlay_children", []):
            overlay_count += 1
            full_destination = f"{item['destination']}/{child}"
            full_source = f"{item['source']}/{child}"
            source_governed = any(
                candidate == full_source or candidate.startswith(full_source.rstrip("/") + "/")
                for candidate in sources
            )
            assert (
                full_destination in destinations
                or full_destination in native_owners
                or source_governed
            )
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

    readiness = manifest["pre_move_readiness"]
    assert readiness["governed_mapping_count"] == len(manifest["mappings"])
    assert readiness["batch_counts"]["B4-research-quarantine"] == sum(
        item["move_batch"] == "B4-research-quarantine" for item in manifest["mappings"]
    )


def test_ai_file_tree_ignores_runtime_generated_membership_noise(tmp_path: Path) -> None:
    module = _module()
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    destination.mkdir()
    (source / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    (destination / "module.py").write_text("VALUE = 1\n", encoding="utf-8")

    generated = source / "__pycache__"
    generated.mkdir()
    (generated / "module.cpython-311.pyc").write_bytes(b"runtime-only")

    assert module._compare(source, destination) == []


def test_ai_file_tree_source_exclusions_are_explicit_and_bounded(tmp_path: Path) -> None:
    module = _module()
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    destination.mkdir()
    (source / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    (destination / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    excluded = source / "history"
    excluded.mkdir()
    (excluded / "legacy.py").write_text("LEGACY = True\n", encoding="utf-8")

    assert module._compare(source, destination) != []
    assert module._compare(source, destination, source_exclusions={"history"}) == []


def test_ai_file_tree_canonical_migration_sources_are_current() -> None:
    import json

    manifest = json.loads((ROOT / "machine/ai_file_tree.json").read_text(encoding="utf-8"))
    mappings = {item["id"]: item for item in manifest["mappings"]}

    assert mappings["AIFT-APPLICATION"]["source"] == "skeleton/app/runtime"
    assert mappings["AIFT-BUILD-PLANNING"]["source"] == "skeleton/automation/shift_supervisor"
    assert mappings["AIFT-PERSISTENCE"]["source_exclusions"] == ["core"]
    assert mappings["AIFT-CONTEXT"]["source_exclusions"] == ["domains"]
    assert mappings["AIFT-AUTOMATION"]["source_exclusions"] == [
        "agents",
        "hive",
        "overseer",
        "shift_supervisor",
        "swarm",
    ]
    assert mappings["AIFT-FOUNDATION"]["source_exclusions"] == ["architecture"]
    assert mappings["AIFT-PROVENANCE"]["source_exclusions"] == ["chronicle"]
    assert mappings["AIFT-KNOWLEDGE"]["source_exclusions"] == ["graphs"]
    assert mappings["AIFT-TOOLS"]["source_exclusions"] == ["integrations"]
    assert mappings["AIFT-DISTRIBUTED"]["source_exclusions"] == [
        "galaxy",
        "mesh",
        "network",
    ]

    aliases = {
        item["planned_path"]: item["implemented_path"]
        for item in manifest["planned_path_audit"]["covered_aliases"]
    }
    assert aliases["skeleton/application"] == "skeleton/app/runtime"
    assert aliases["skeleton/genesis.py"] == "skeleton/bootstrap/genesis.py"
    assert aliases["skeleton/provider_contract.py"] == "skeleton/providers/contract.py"
    assert aliases["skeleton/creator"] == "skeleton/forge/creator"


def test_ai_file_tree_classifies_all_machine_authority_roots() -> None:
    import json
    import re

    manifest = json.loads((ROOT / "machine/ai_file_tree.json").read_text(encoding="utf-8"))
    mappings = manifest["mappings"]
    audit = manifest["planned_path_audit"]

    def root(path: str) -> str:
        return "/".join(path.split("/")[:2])

    classified = {manifest["canonical_root"]}
    classified.update(root(item["source"]) for item in mappings if item.get("source", "").startswith("skeleton/"))
    classified.update(root(item["path"]) for item in audit["intentionally_external"])
    classified.update(root(item["planned_path"]) for item in audit["covered_aliases"] if item.get("planned_path", "").startswith("skeleton/"))
    classified.update(root(path) for path in audit["planned_but_absent"])
    classified.update(root(path) for path in audit["non_engine_root_exclusions"] if path.startswith("skeleton/"))

    planned = set()
    for authority in ("machine/ai_master_plan.json", "machine/ai_app_construction.json"):
        text = (ROOT / authority).read_text(encoding="utf-8")
        planned.update(re.findall(r"\\bskeleton/[A-Za-z0-9_.-]+", text))

    assert planned <= classified, sorted(planned - classified)


def test_planned_but_absent_roots_are_really_absent() -> None:
    import json

    manifest = json.loads((ROOT / "machine/ai_file_tree.json").read_text(encoding="utf-8"))
    for path in manifest["planned_path_audit"]["planned_but_absent"]:
        assert not (ROOT / path).exists(), path


def test_cost_usage_metering_mirrors_remain_in_semantic_parity() -> None:
    module = _module()
    pairs = (
        ("skeleton/intelligence/admission_runtime.py", "skeleton/ai/runtime/intelligence/admission_runtime.py"),
        ("skeleton/intelligence/quota.py", "skeleton/ai/runtime/intelligence/quota.py"),
        ("skeleton/intelligence/quota_sqlite.py", "skeleton/ai/runtime/intelligence/quota_sqlite.py"),
        ("skeleton/skills/__init__.py", "skeleton/ai/runtime/skills/__init__.py"),
        ("skeleton/skills/usage.py", "skeleton/ai/runtime/skills/usage.py"),
        ("skeleton/artifact_plane/__init__.py", "skeleton/ai/runtime/artifact_plane/__init__.py"),
        ("skeleton/artifact_plane/usage.py", "skeleton/ai/runtime/artifact_plane/usage.py"),
        ("skeleton/turn/delta.py", "skeleton/ai/compat/turn/delta.py"),
    )
    for source, destination in pairs:
        assert module._content_equivalent(ROOT / source, ROOT / destination), (source, destination)



def test_planned_implementation_file_is_governed_by_parent_tree_mapping() -> None:
    module = _module()
    tree_mapping = {
        "source": "skeleton/persistence",
        "destination": "skeleton/ai/runtime/persistence",
        "kind": "tree",
    }
    file_mapping = {
        "source": "skeleton/provider_runtime.py",
        "destination": "skeleton/ai/providers/runtime.py",
        "kind": "file",
    }

    assert module._mapping_covers_planned_source(
        tree_mapping, "skeleton/persistence/execution_repository.py"
    )
    assert module._mapping_covers_planned_source(
        file_mapping, "skeleton/provider_runtime.py"
    )
    assert not module._mapping_covers_planned_source(
        file_mapping, "skeleton/provider_runtime.py/child"
    )
    assert not module._mapping_covers_planned_source(
        tree_mapping, "skeleton/persist/execution_repository.py"
    )


def test_namespace_composition_rejects_unmapped_members(tmp_path: Path, monkeypatch) -> None:
    module = _module()
    monkeypatch.setattr(module, "ROOT", tmp_path)
    parent = tmp_path / "skeleton/research"
    parent.mkdir(parents=True)
    members = {"__init__.py": parent / "__init__.py", "social/core.py": parent / "social/core.py"}
    monkeypatch.setattr(module, "_tree_files", lambda _: members)
    mappings = [
        {"source": "skeleton/research/__init__.py", "kind": "file"},
        {"source": "skeleton/research/social", "kind": "tree"},
    ]
    assert module._mappings_cover_planned_source(mappings, "skeleton/research")
    members["social_extra.py"] = parent / "social_extra.py"
    assert not module._mappings_cover_planned_source(mappings, "skeleton/research")
    members.clear()
    assert not module._mappings_cover_planned_source(mappings, "skeleton/research")


def test_mature_volume_paths_are_traceable_to_governed_ai_tree_owners() -> None:
    import json

    module = _module()
    manifest = json.loads((ROOT / "machine/ai_file_tree.json").read_text(encoding="utf-8"))
    master_plan = json.loads((ROOT / "machine/ai_master_plan.json").read_text(encoding="utf-8"))
    mappings = manifest["mappings"]
    native_owners = manifest["native_ai_owners"]
    mature = {"implemented", "hardened", "verified", "complete", "completed"}

    for volume in master_plan["volumes"]:
        if volume.get("implementation_status") not in mature:
            continue
        owners = set()
        for implementation_path in volume.get("implementation_paths", []):
            if not isinstance(implementation_path, str) or implementation_path.startswith("planned:"):
                continue
            if not implementation_path.startswith(("skeleton/", "backend/")):
                continue
            owner = module._owned_mapping_for_implementation_path(mappings, implementation_path)
            if owner is not None:
                owners.add(("mapping", owner["id"]))
                continue
            native_owner = module._owned_native_ai_path(native_owners, implementation_path)
            if native_owner is not None:
                owners.add(("native", native_owner["id"]))
                continue
            if implementation_path.startswith("skeleton/ai/"):
                raise AssertionError((volume["key"], implementation_path))
        for owner_kind, owner_id in owners:
            collection = mappings if owner_kind == "mapping" else native_owners
            owner = next(item for item in collection if item["id"] == owner_id)
            assert volume["key"] in owner.get("volume_refs", []), (volume["key"], owner_id)


def test_native_ai_owners_are_canonical_and_residual_where_needed() -> None:
    import json

    manifest = json.loads((ROOT / "machine/ai_file_tree.json").read_text(encoding="utf-8"))
    owners = {item["id"]: item for item in manifest["native_ai_owners"]}
    assert owners["AIFT-NATIVE-AGENTS-ROOT"]["residual_only"] is True
    assert owners["AIFT-NATIVE-BUILD-ROOT"]["residual_only"] is True
    assert owners["AIFT-NATIVE-EXTENSIONS-ROOT"]["residual_only"] is True
    assert owners["AIFT-NATIVE-DEFERRED-RUNTIME"]["residual_only"] is False
    assert "VOL-209" in owners["AIFT-NATIVE-ARTIFACT-REVIEW"]["volume_refs"]


def test_every_tracked_ai_file_has_governed_owner() -> None:
    import json
    import subprocess

    module = _module()
    manifest = json.loads((ROOT / "machine/ai_file_tree.json").read_text(encoding="utf-8"))
    destinations = {
        item["destination"]
        for item in manifest["mappings"]
        if isinstance(item, dict) and isinstance(item.get("destination"), str)
    }
    native_owners = manifest["native_ai_owners"]
    tracked = subprocess.run(
        ["git", "ls-files", "-z", "skeleton/ai"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split("\0")
    unowned = []
    for path in tracked:
        if not path:
            continue
        mapping_owned = any(module._path_within(path, destination) for destination in destinations)
        native_owned = module._owned_native_ai_path(native_owners, path) is not None
        if not mapping_owned and not native_owned:
            unowned.append(path)
    assert unowned == []
