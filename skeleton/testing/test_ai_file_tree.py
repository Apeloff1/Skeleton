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


def test_repository_planning_runs_through_both_governed_import_paths() -> None:
    """A mirrored planner must preserve dependency release and replay fences."""
    import importlib
    from types import SimpleNamespace

    import pytest

    for namespace in ("skeleton.repo_machine", "skeleton.ai.build.repo_machine"):
        package = importlib.import_module(namespace)
        graph = package.WorkGraph(
            (
                package.WorkNode(
                    "root",
                    "architecture",
                    "core",
                    100,
                    "Repair root",
                    ("path:core",),
                    (),
                    ("fixture",),
                ),
                package.WorkNode(
                    "child",
                    "regression",
                    "tests",
                    90,
                    "Verify child",
                    ("path:tests",),
                    ("root",),
                    ("fixture",),
                ),
            )
        )
        model = SimpleNamespace(fingerprint="fixture-repository")
        coordination = package.select_next_work(model, graph=graph, limit=2)
        assert coordination.frontier_size == 1
        assert coordination.decisions[0].work_identity == "root"
        assert coordination.decisions[1].blocked is True

        plan = package.build_execution_plan(model, graph=graph, limit=2)
        assert plan.ready_work == ("root",)
        assert plan.blocked_work == ("child",)
        with pytest.raises(ValueError, match="prerequisites"):
            package.advance_execution(
                plan,
                step_identity="root:unlock",
                outcome="success",
                repository_fingerprint=model.fingerprint,
            )
        initial_fingerprint = plan.fingerprint
        for phase in ("prepare", "modify", "verify", "unlock"):
            plan = package.advance_execution(
                plan,
                step_identity=f"root:{phase}",
                outcome="success",
                repository_fingerprint=model.fingerprint,
                expected_plan_fingerprint=plan.fingerprint,
            )
        assert plan.state.verified_work == ("root",)
        assert plan.state.released_work == ("root",)
        assert package.replan_execution(
            model, plan, graph=graph, limit=2
        ).ready_work == ("child",)
        with pytest.raises(ValueError, match="fingerprint mismatch"):
            package.advance_execution(
                plan,
                step_identity="root:prepare",
                outcome="success",
                repository_fingerprint=model.fingerprint,
                expected_plan_fingerprint=initial_fingerprint,
            )


def test_repository_manifest_type_and_checksum_fences_in_both_paths(
    tmp_path: Path,
) -> None:
    import importlib
    import json

    import pytest

    malformed_states = (
        None,
        {"files": {}},
        {"files": [None]},
        {"files": [{"path": 42}]},
    )
    for namespace in ("skeleton.repo_machine", "skeleton.ai.build.repo_machine"):
        manifest = importlib.import_module(f"{namespace}.manifest")
        path = tmp_path / "invalid-manifest.json"
        path.write_text("[]", encoding="utf-8")
        with pytest.raises(TypeError, match="must be an object"):
            manifest.load_manifest(path)
        for state in malformed_states:
            payload = {
                "format": "skeleton-repository-machine-manifest",
                "version": 1,
                "state": state,
            }
            with pytest.raises(
                TypeError, match="state missing|inventory missing|invalid file record"
            ):
                manifest.validate_manifest(payload)
        payload = {
            "format": "skeleton-repository-machine-manifest",
            "version": 1,
            "state": {"files": [], "metadata": {"file_count": 0}},
            "checksum": "invalid",
        }
        with pytest.raises(ValueError, match="checksum mismatch"):
            manifest.validate_manifest(payload)
        path.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(ValueError, match="checksum mismatch"):
            manifest.load_manifest(path)


def test_repository_path_normalization_and_retrieval_work_in_both_paths() -> None:
    import importlib
    from types import SimpleNamespace

    for namespace in ("skeleton.repo_machine", "skeleton.ai.build.repo_machine"):
        model_module = importlib.import_module(f"{namespace}.model")
        retrieval = importlib.import_module(f"{namespace}.retrieval")
        impact = importlib.import_module(f"{namespace}.impact")
        planner = importlib.import_module(f"{namespace}.planner")
        for normalize in (impact._normalize_path, planner._normalize_finding_path):
            assert normalize(r".\\alpha\\nested\\module.py") == "alpha/nested/module.py"
        records = tuple(
            model_module.FileRecord(
                path, zone, "fixture", "source", "python", 10, 1, "a" * 64
            )
            for path, zone in (
                ("security/api.py", "security"),
                ("app/api_helper.py", "app"),
            )
        )
        index = retrieval.RepositoryRetrievalIndex(SimpleNamespace(files=records))
        assert index.search("api")[0].path == "security/api.py"
        filtered = index.search("api", zones=("app",))
        assert tuple(hit.path for hit in filtered) == ("app/api_helper.py",)
        assert index._zones_by_intent["security"] == {"security"}


def test_repository_graph_preserves_transitive_unlocks_in_both_paths() -> None:
    import importlib

    for namespace in ("skeleton.repo_machine", "skeleton.ai.build.repo_machine"):
        package = importlib.import_module(namespace)
        graph = package.WorkGraph(
            tuple(
                package.WorkNode(
                    identity,
                    "architecture",
                    identity,
                    10,
                    identity,
                    (),
                    dependencies,
                    ("fixture",),
                    topology_confidence=90,
                    blast_radius=2,
                )
                for identity, dependencies in (
                    ("root", ()),
                    ("child", ("root",)),
                    ("leaf", ("child",)),
                )
            )
        )
        assert graph.unlock_potential("root") == 2
        assert graph.unlock_potential("child") == 1
        assert graph.unlock_potential("leaf") == 0
        assert graph.downstream_value("root") >= graph.downstream_value("child")
        assert graph.downstream_value("child") >= graph.downstream_value("leaf")
        assert graph.bottleneck() == "root"


def test_repository_context_terminates_with_oversized_singletons_in_both_paths() -> (
    None
):
    import importlib
    import json

    payload = {
        "intent": "overview",
        "fingerprint": "a" * 64,
        "files": [{"detail": "f" * 10_000}],
        "intelligence": {"bridge_candidates": [{"detail": "b" * 10_000}]},
        "execution": {"steps": [{"detail": "e" * 10_000}]},
    }
    original = json.dumps(payload, sort_keys=True)
    for namespace in ("skeleton.repo_machine", "skeleton.ai.build.repo_machine"):
        context = importlib.import_module(f"{namespace}.context")
        result = context._bounded(payload, 4096)
        encoded = json.dumps(result, sort_keys=True, separators=(",", ":")).encode()
        assert len(encoded) <= 4096
        assert result["fingerprint"] == payload["fingerprint"]
        assert result["intent"] == payload["intent"]
        assert result["truncated_for_context"] is True
        assert json.dumps(payload, sort_keys=True) == original


def test_typed_slo_extensions_preserve_exact_window_authority_in_both_paths() -> None:
    import importlib

    import pytest

    for namespace in ("skeleton.observability", "skeleton.ai.runtime.observability"):
        slo = importlib.import_module(f"{namespace}.slo")
        window = slo.SLOWindow("window", 100, 1_000)
        objective = slo.SLO("availability", "assistant", "requests", 0.99, window)
        observation = slo.SLI("observation", "availability", 98, 100, 100, 900)
        result = slo.assess_slo(slo=objective, sli=observation)
        assert result.met is False
        assert result.slo_digest == objective.digest
        assert result.sli_digest == observation.digest
        with pytest.raises(slo.SLOError, match="declared SLO window"):
            slo.assess_slo(
                slo=objective,
                sli=slo.SLI("outside", "availability", 100, 100, 99, 900),
            )


def test_shared_pressure_expiry_remains_a_fence_in_both_governed_paths(
    tmp_path: Path,
) -> None:
    import importlib

    import pytest

    for index, namespace in enumerate(
        ("skeleton.intelligence", "skeleton.ai.runtime.intelligence")
    ):
        pressure = importlib.import_module(f"{namespace}.shared_pressure")
        ledger = pressure.SqliteSharedPressureLedger(
            tmp_path / f"pressure-{index}.sqlite3"
        )
        ledger.configure(
            pressure.SharedPressurePolicy(
                scope="work",
                max_concurrency=1,
                max_queue_depth=1,
                max_tenant_concurrency=1,
                max_tenant_queue_depth=1,
                default_lease_seconds=1.0,
            )
        )
        lease = ledger.acquire(
            "work", "tenant", "operation", "worker", priority=1, now=10.0
        )
        with pytest.raises(pressure.SharedPressureConflict, match="expired"):
            ledger.renew(lease.lease_id, "worker", now=11.0)
        assert ledger.lease_for_operation("work", "operation", now=11.0) is None


def test_ai_file_tree_contains_jeeves_and_build_planning() -> None:
    assert (ROOT / "skeleton/ai/agents/jeeves/__init__.py").is_file()
    assert (ROOT / "skeleton/ai/build/shift_supervisor/__init__.py").is_file()


def test_ai_file_tree_keeps_provider_boundary_explicit() -> None:
    assert (ROOT / "skeleton/ai/providers/contract.py").is_file()
    assert (ROOT / "skeleton/ai/providers/runtime.py").is_file()


def test_ai_file_tree_credential_surfaces_are_facades() -> None:
    provider = (ROOT / "skeleton/ai/providers/runtime.py").read_text(encoding="utf-8")
    gateway = (ROOT / "skeleton/ai/build/shift_supervisor/model_gateway.py").read_text(
        encoding="utf-8"
    )
    assert "from skeleton.provider_runtime import" in provider
    assert "from skeleton.automation.shift_supervisor.model_gateway import" in gateway
    for source in (provider, gateway):
        assert "OPENAI_API_KEY" not in source
        assert "api.openai.com" not in source
        assert "from openai import" not in source


def test_python_parity_allows_formatting_but_rejects_semantic_drift(
    tmp_path: Path,
) -> None:
    module = _module()
    source = tmp_path / "source.py"
    destination = tmp_path / "destination.py"

    source.write_text("def value(x: int) -> int:\n    return x + 1\n", encoding="utf-8")
    destination.write_text(
        "def value( x: int )->int:\n\n    return (x + 1)\n",
        encoding="utf-8",
    )
    assert module._content_equivalent(source, destination)

    destination.write_text(
        "def value(x: int) -> int:\n    return x + 2\n", encoding="utf-8"
    )
    assert not module._content_equivalent(source, destination)


def test_ai_file_tree_native_and_path_audit() -> None:
    import json

    manifest = json.loads(
        (ROOT / "machine/ai_file_tree.json").read_text(encoding="utf-8")
    )
    mapping_by_id = {item["id"]: item for item in manifest["mappings"]}
    assert mapping_by_id["AIFT-NATIVE"]["source"] == "skeleton/native"
    assert mapping_by_id["AIFT-NATIVE"]["destination"] == "skeleton/ai/runtime/native"
    assert mapping_by_id["AIFT-NATIVE"]["volume_refs"] == ["VOL-032"]
    assert (ROOT / "skeleton/ai/runtime/native/registry.py").is_file()

    audit = manifest["planned_path_audit"]
    external = {item["path"] for item in audit["intentionally_external"]}
    assert {
        "skeleton/app",
        "skeleton/config",
        "skeleton/deploy",
        "skeleton/testing",
    } <= external
    assert "skeleton/research" not in audit["planned_but_absent"]
    assert mapping_by_id["AIFT-RESEARCH"]["source"] == "skeleton/research/__init__.py"
    assert mapping_by_id["AIFT-RESEARCH"]["move_batch"] == "B4-research-quarantine"
    assert "skeleton/planning" in audit["planned_but_absent"]


def test_ai_file_tree_cortex_and_organism_keep_sensitive_owners_singular() -> None:
    import json

    manifest = json.loads(
        (ROOT / "machine/ai_file_tree.json").read_text(encoding="utf-8")
    )
    mapping_by_id = {item["id"]: item for item in manifest["mappings"]}

    cortex = mapping_by_id["AIFT-CORTEX"]
    organism = mapping_by_id["AIFT-ORGANISM"]
    assert cortex["source"] == "skeleton/cortex"
    assert cortex["destination"] == "skeleton/ai/runtime/cortex"
    assert organism["source"] == "skeleton/organism"
    assert organism["destination"] == "skeleton/ai/runtime/organism"

    cortex_interchange = (ROOT / "skeleton/ai/runtime/cortex/interchange.py").read_text(
        encoding="utf-8"
    )
    cortex_gates = (ROOT / "skeleton/ai/runtime/cortex/gates.py").read_text(
        encoding="utf-8"
    )
    organism_secrets = (
        ROOT / "skeleton/ai/runtime/organism/secret_manager.py"
    ).read_text(encoding="utf-8")

    assert "from skeleton.cortex.interchange import *" in cortex_interchange
    assert "from skeleton.cortex.gates import *" in cortex_gates
    assert "from skeleton.organism.secret_manager import *" in organism_secrets

    assert "KIMI_API_KEY" not in cortex_interchange
    assert "OPENAI_API_KEY" not in cortex_gates
    assert "SKELETON_MASTER_SECRET" not in organism_secrets


def test_ai_file_tree_move_preparation_tags_cover_all_governed_mappings() -> None:
    import json

    manifest = json.loads(
        (ROOT / "machine/ai_file_tree.json").read_text(encoding="utf-8")
    )
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
        assert (
            len([tag for tag in item["move_tags"] if tag.startswith("cutover:")]) == 1
        )
        assert item["move_batch"] in contract["batches"]
        assert item["source_disposition"]

    assert (
        mappings["skeleton/provider_runtime.py"]["move_batch"] == "B3-owner-sensitive"
    )
    assert (
        "cutover:owner-sensitive"
        in mappings["skeleton/provider_runtime.py"]["move_tags"]
    )
    assert mappings["skeleton/viscera"]["move_batch"] == "B4-research-quarantine"
    assert "cutover:quarantine" in mappings["skeleton/viscera"]["move_tags"]
    assert mappings["skeleton/turn"]["move_batch"] == "B3-compat-convergence"
    assert "cutover:merge-required" in mappings["skeleton/turn"]["move_tags"]
    assert mappings["skeleton/telemetry"]["move_batch"] == "B3-compat-convergence"
    assert "cutover:merge-required" in mappings["skeleton/telemetry"]["move_tags"]


def test_ai_file_tree_classifies_non_move_top_level_surfaces() -> None:
    import json

    manifest = json.loads(
        (ROOT / "machine/ai_file_tree.json").read_text(encoding="utf-8")
    )
    retained = {item["path"]: item for item in manifest["retained_outside_ai_tree"]}

    assert retained["skeleton/architecture.py"]["owner"] == "architecture authority"
    assert (
        retained["skeleton/foundation/architecture/index.py"]["owner"]
        == "architecture authority"
    )
    assert retained["skeleton/acquired"]["owner"] == "quarantine/provenance"
    assert retained["skeleton/release"]["owner"] == "release engineering"
    assert retained["skeleton/ubuntu"]["owner"] == "deployment/platform support"
    assert retained["skeleton/__main__.py"]["owner"] == "package CLI shell"


def test_ai_file_tree_overlay_children_are_separately_governed() -> None:
    import json

    manifest = json.loads(
        (ROOT / "machine/ai_file_tree.json").read_text(encoding="utf-8")
    )
    mappings = manifest["mappings"]
    destinations = {item["destination"] for item in mappings}
    sources = {item["source"] for item in mappings}
    overlay_count = 0
    for item in mappings:
        for child in item.get("overlay_children", []):
            overlay_count += 1
            full_destination = f"{item['destination']}/{child}"
            full_source = f"{item['source']}/{child}"
            source_governed = any(
                candidate == full_source
                or candidate.startswith(full_source.rstrip("/") + "/")
                for candidate in sources
            )
            assert full_destination in destinations or source_governed
    assert overlay_count >= 12


def test_ai_file_tree_preserves_remaining_acquired_lineage() -> None:
    import json

    manifest = json.loads(
        (ROOT / "machine/ai_file_tree.json").read_text(encoding="utf-8")
    )
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


def test_ai_file_tree_ignores_runtime_generated_membership_noise(
    tmp_path: Path,
) -> None:
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


def test_ai_file_tree_source_exclusions_are_explicit_and_bounded(
    tmp_path: Path,
) -> None:
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

    manifest = json.loads(
        (ROOT / "machine/ai_file_tree.json").read_text(encoding="utf-8")
    )
    mappings = {item["id"]: item for item in manifest["mappings"]}

    assert mappings["AIFT-APPLICATION"]["source"] == "skeleton/app/runtime"
    assert (
        mappings["AIFT-BUILD-PLANNING"]["source"]
        == "skeleton/automation/shift_supervisor"
    )
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

    manifest = json.loads(
        (ROOT / "machine/ai_file_tree.json").read_text(encoding="utf-8")
    )
    mappings = manifest["mappings"]
    audit = manifest["planned_path_audit"]

    def root(path: str) -> str:
        return "/".join(path.split("/")[:2])

    classified = {manifest["canonical_root"]}
    classified.update(
        root(item["source"])
        for item in mappings
        if item.get("source", "").startswith("skeleton/")
    )
    classified.update(root(item["path"]) for item in audit["intentionally_external"])
    classified.update(
        root(item["planned_path"])
        for item in audit["covered_aliases"]
        if item.get("planned_path", "").startswith("skeleton/")
    )
    classified.update(root(path) for path in audit["planned_but_absent"])
    classified.update(
        root(path)
        for path in audit["non_engine_root_exclusions"]
        if path.startswith("skeleton/")
    )

    planned = set()
    for authority in (
        "machine/ai_master_plan.json",
        "machine/ai_app_construction.json",
    ):
        text = (ROOT / authority).read_text(encoding="utf-8")
        planned.update(re.findall(r"\\bskeleton/[A-Za-z0-9_.-]+", text))

    assert planned <= classified, sorted(planned - classified)


def test_planned_but_absent_roots_are_really_absent() -> None:
    import json

    manifest = json.loads(
        (ROOT / "machine/ai_file_tree.json").read_text(encoding="utf-8")
    )
    for path in manifest["planned_path_audit"]["planned_but_absent"]:
        assert not (ROOT / path).exists(), path


def test_cost_usage_metering_mirrors_remain_in_semantic_parity() -> None:
    module = _module()
    pairs = (
        (
            "skeleton/intelligence/admission_runtime.py",
            "skeleton/ai/runtime/intelligence/admission_runtime.py",
        ),
        ("skeleton/intelligence/quota.py", "skeleton/ai/runtime/intelligence/quota.py"),
        (
            "skeleton/intelligence/quota_sqlite.py",
            "skeleton/ai/runtime/intelligence/quota_sqlite.py",
        ),
        ("skeleton/skills/__init__.py", "skeleton/ai/runtime/skills/__init__.py"),
        ("skeleton/skills/usage.py", "skeleton/ai/runtime/skills/usage.py"),
        (
            "skeleton/artifact_plane/__init__.py",
            "skeleton/ai/runtime/artifact_plane/__init__.py",
        ),
        (
            "skeleton/artifact_plane/usage.py",
            "skeleton/ai/runtime/artifact_plane/usage.py",
        ),
        ("skeleton/turn/delta.py", "skeleton/ai/compat/turn/delta.py"),
    )
    for source, destination in pairs:
        assert module._content_equivalent(ROOT / source, ROOT / destination), (
            source,
            destination,
        )


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


def test_namespace_composition_rejects_unmapped_members(
    tmp_path: Path, monkeypatch
) -> None:
    module = _module()
    monkeypatch.setattr(module, "ROOT", tmp_path)
    parent = tmp_path / "skeleton/research"
    parent.mkdir(parents=True)
    members = {
        "__init__.py": parent / "__init__.py",
        "social/core.py": parent / "social/core.py",
    }
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
