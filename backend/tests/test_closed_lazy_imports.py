"""Pin closed lazy-export dispatch to repository-owned literal module targets.

The canonical dynamic-import gate remains unchanged: only the eager call sites
are converted to a statically reviewable, lazy, deny-by-default dispatcher.
"""
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "skeleton_repo_dynamic_import_audit", ROOT / "scripts/check_repository_dynamic_import_safety.py"
)
assert spec is not None and spec.loader is not None
SCANNER = importlib.util.module_from_spec(spec)
spec.loader.exec_module(SCANNER)

TARGETS = (
    ("skeleton/__init__.py", "_LAZY_EXPORTS", "tuple"),
    ("skeleton/ai/agents/jeeves/ai/__init__.py", "_HOST_EXPORTS", "string"),
    ("skeleton/jeeves/ai/__init__.py", "_HOST_EXPORTS", "string"),
    ("skeleton/ai/game_builder/__init__.py", "_KNOWLEDGE_EXPORTS", "string"),
    ("skeleton/ai/model_runtime/__init__.py", "_LAZY_EXPORTS", "string"),
    ("skeleton/ai/runtime/inference/core/__init__.py", "_LAZY_EXPORTS", "tuple"),
    ("skeleton/inference/__init__.py", "_LAZY_EXPORTS", "tuple"),
    ("skeleton/ai/training/__init__.py", "_GOVERNANCE_EXPORTS", "string"),
    ("skeleton/ai/runtime/learning_foundation/__init__.py", "_LAZY_EXPORTS", "frozenset"),
    ("skeleton/ai/runtime/training/__init__.py", "_LAZY_EXPORTS", "frozenset"),
    ("skeleton/ai/runtime/inference/__init__.py", "_NATIVE_EXPORTS", "single"),
)


@pytest.mark.parametrize("path,table,mode", TARGETS)
def test_lazy_exports_are_backed_only_by_literal_module_dispatch(path: str, table: str, mode: str) -> None:
    file = ROOT / path
    tree = ast.parse(file.read_text(encoding="utf-8"))
    assignments = [
        node.value for node in tree.body
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == table for target in node.targets
        )
    ]
    assert len(assignments) == 1, path
    mapping = assignments[0]
    assert isinstance(mapping, ast.Dict), path
    expected: set[str] = set()
    for key, value in zip(mapping.keys, mapping.values):
        if mode == "frozenset":
            assert isinstance(key, ast.Constant) and isinstance(key.value, str)
            assert isinstance(value, ast.Call) and isinstance(value.func, ast.Name)
            assert value.func.id == "frozenset"
            expected.add("." + key.value)
        else:
            if mode == "tuple":
                assert isinstance(value, ast.Tuple) and value.elts
                value = value.elts[0]
            assert isinstance(value, ast.Constant) and isinstance(value.value, str)
            expected.add(value.value)
    assert expected, path
    if mode == "single":
        assert expected == {".native_transformer"}
        dispatcher = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "__getattr__")
    else:
        dispatchers = [
            node for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name in {"_load_reviewed_export_owner", "_load_trusted_lazy_module"}
        ]
        assert len(dispatchers) == 1, path
        dispatcher = dispatchers[0]
    literal_calls: set[str] = set()
    for node in ast.walk(dispatcher):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        if "import_module" not in node.func.id or not node.args:
            continue
        first = node.args[0]
        assert isinstance(first, ast.Constant) and isinstance(first.value, str)
        literal_calls.add(first.value)
    if mode == "single":
        assert literal_calls == {".native_transformer", ".native_runtime"}
    else:
        assert literal_calls == expected, path
    assert SCANNER.violations(file) == [], path


def test_governed_lazy_alias_mirrors_remain_byte_identical() -> None:
    for canonical, mirror in (
        ("skeleton/ai/agents/jeeves/ai/__init__.py", "skeleton/jeeves/ai/__init__.py"),
        ("skeleton/ai/runtime/inference/core/__init__.py", "skeleton/inference/__init__.py"),
    ):
        assert (ROOT / canonical).read_bytes() == (ROOT / mirror).read_bytes()


TRUSTED_TWIN_PAIRS = (
    ("skeleton/ai/learning/school/runtime_attestation.py", "skeleton/learning/school/runtime_attestation.py",
     "_load_trusted_named_module", (
         "skeleton.learning.school.decision_ledger", "skeleton.ai.learning.school.decision_ledger",
         "skeleton.learning.school.runtime_replay", "skeleton.ai.learning.school.runtime_replay",
         "skeleton.learning.school.runtime_attestation", "skeleton.ai.learning.school.runtime_attestation",
     )),
    ("skeleton/ai/learning/school/runtime_capsule.py", "skeleton/learning/school/runtime_capsule.py",
     "_load_trusted_twin_module", (
         "skeleton.ai.learning.school.decision_ledger", "skeleton.ai.learning.school.runtime_replay",
     )),
    ("skeleton/ai/learning/school/runtime_replay.py", "skeleton/learning/school/runtime_replay.py",
     "_load_trusted_twin_module", (
         "skeleton.ai.learning.school.decision_ledger", "skeleton.ai.learning.school.session_runtime",
         "skeleton.ai.learning.school.runtime_replay",
     )),
    ("skeleton/ai/runtime/observability/slo.py", "skeleton/observability/slo.py",
     "_load_trusted_slo_twin", (
         "skeleton.ai.runtime.observability.slo", "skeleton.observability.slo",
     )),
)


@pytest.mark.parametrize("canonical,mirror,helper,allowed", TRUSTED_TWIN_PAIRS)
def test_trusted_type_mirrors_retain_identical_literal_imports(
    canonical: str, mirror: str, helper: str, allowed: tuple[str, ...]
) -> None:
    source = (ROOT / canonical).read_bytes()
    assert source == (ROOT / mirror).read_bytes()
    tree = ast.parse(source.decode("utf-8"))
    candidates = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == helper]
    assert len(candidates) == 1
    imported: set[str] = set()
    for node in ast.walk(candidates[0]):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and (
            node.func.attr == "import_module"
        ):
            assert isinstance(node.args[0], ast.Constant)
            assert isinstance(node.args[0].value, str)
            imported.add(node.args[0].value)
    assert imported == set(allowed)
    assert SCANNER.violations(ROOT / canonical) == []
    assert SCANNER.violations(ROOT / mirror) == []


CATALOG_EXPORTS = (
    ("skeleton/ai/agents/jeeves/game_frontier_book_curriculum.py",
     "skeleton/jeeves/game_frontier_book_curriculum.py", "GENERATIONS", "forge", "_load_known_forge_module"),
    ("skeleton/ai/runtime/organism/operator_cli.py",
     "skeleton/organism/operator_cli.py", "_VIEWS", "views", "_load_organism_view_module"),
    ("skeleton/ai/webcrawler/dragon_mission_catalog.py",
     None, "_SPECS", "mission", "_load_mission_catalog_module"),
    ("skeleton/ai/webcrawler/game_scale_catalog.py",
     None, "_GROUPS", "scale", "_load_game_scale_module"),
)


@pytest.mark.parametrize("path,mirror,registry,kind,helper", CATALOG_EXPORTS)
def test_closed_catalog_dispatch_matches_complete_literal_registry(
    path: str, mirror: str | None, registry: str, kind: str, helper: str
) -> None:
    src = (ROOT / path).read_bytes()
    if mirror is not None:
        assert src == (ROOT / mirror).read_bytes()
        assert SCANNER.violations(ROOT / mirror) == []
    tree = ast.parse(src.decode("utf-8"))
    values = [
        node.value for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == registry for t in node.targets)
    ]
    assert len(values) == 1
    data = ast.literal_eval(values[0])
    if kind == "forge":
        expected = {"skeleton.forge." + row[1] for row in data}
    elif kind == "views":
        expected = {row[0] for row in data.values()}
    elif kind == "mission":
        expected = {"." + row[1] for row in data}
    else:
        expected = {"." + row[1] for row in data}
    assert expected
    dispatch = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == helper
    ]
    assert len(dispatch) == 1
    imported = set()
    for node in ast.walk(dispatch[0]):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        if "import_module" not in node.func.id:
            continue
        assert node.args and isinstance(node.args[0], ast.Constant)
        assert isinstance(node.args[0].value, str)
        imported.add(node.args[0].value)
    assert imported == expected
    assert SCANNER.violations(ROOT / path) == []


def test_webcrawler_lazy_registry_includes_literal_and_derived_game_milestones() -> None:
    crawler = ROOT / "skeleton/ai/webcrawler/__init__.py"
    tree = ast.parse(crawler.read_text(encoding="utf-8"))
    assignments = [
        node.value for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "_SPINE_EXPORTS" for t in node.targets)
    ]
    assert len(assignments) == 1
    primary = ast.literal_eval(assignments[0])
    expected = set(primary.values())
    literal_updates = []
    derived_updates = []
    for node in tree.body:
        if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
            continue
        call = node.value
        if not isinstance(call.func, ast.Attribute) or call.func.attr != "update":
            continue
        if not isinstance(call.func.value, ast.Name) or call.func.value.id != "_SPINE_EXPORTS":
            continue
        assert len(call.args) == 1
        if isinstance(call.args[0], ast.Dict):
            literal_updates.append(ast.literal_eval(call.args[0]))
        else:
            assert isinstance(call.args[0], ast.DictComp)
            derived_updates.append(call.args[0])
    assert len(literal_updates) == 1 and len(derived_updates) == 1
    expected.update(literal_updates[0].values())
    catalog = ast.parse((ROOT / "skeleton/ai/webcrawler/game_scale_catalog.py").read_text(encoding="utf-8"))
    groups = next(
        ast.literal_eval(node.value) for node in catalog.body
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "_GROUPS" for t in node.targets
        )
    )
    expected.update("." + row[1] for row in groups)
    loader = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_load_trusted_crawler_module"
    )
    found = {
        node.args[0].value for node in ast.walk(loader)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        and node.func.id == "_crawler_import_module"
        and node.args and isinstance(node.args[0], ast.Constant)
    }
    assert found == expected
    assert SCANNER.violations(crawler) == []


def test_standalone_dragon_import_names_a_literal_isolated_namespace() -> None:
    file = ROOT / "skeleton/ai/webcrawler/dragon_native_release.py"
    tree = ast.parse(file.read_text(encoding="utf-8"))
    imports = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        and node.func.id == "import_module"
    ]
    assert len(imports) == 1
    assert isinstance(imports[0].args[0], ast.Constant)
    assert imports[0].args[0].value == "_dragon_native_standalone.dragon_native_puzzle"
    assert SCANNER.violations(file) == []


def test_cs300_dispatch_matches_thirty_shipped_literal_strata() -> None:
    file = ROOT / "skeleton/cs300/registry.py"
    tree = ast.parse(file.read_text(encoding="utf-8"))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_registered_stratum")
    allowed = {
        n.args[0].value for n in ast.walk(fn) if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute) and n.func.attr == "import_module"
        and n.args and isinstance(n.args[0], ast.Constant)
    }
    expected = {"skeleton.cs300.strata.s%02d" % i for i in range(1, 31)}
    assert allowed == expected
    assert SCANNER.violations(file) == []


def test_frozen_package_regression_uses_only_three_literal_import_targets() -> None:
    file = ROOT / "skeleton/testing/test_persistence_freeze_guard.py"
    tree = ast.parse(file.read_text(encoding="utf-8"))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "test_frozen_packages_import_without_warnings")
    imports = {
        n.args[0].value for n in ast.walk(fn) if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute) and n.func.attr == "import_module"
        and n.args and isinstance(n.args[0], ast.Constant)
    }
    assert imports == {"skeleton.persist", "skeleton.storage", "skeleton.state"}
    assert SCANNER.violations(file) == []


def test_deferred_165_loader_matches_literal_handlers() -> None:
    from skeleton.ai.runtime.deferred.catalog import DEFERRED_165_SPECS

    path = ROOT / "scripts/check_ai_deferred_165_runtime.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    loader = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_registered_handler_module"
    )
    named = {
        node.args[0].value for node in ast.walk(loader)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute) and node.func.attr == "import_module"
        and node.args and isinstance(node.args[0], ast.Constant)
    }
    expected = {row.handler.rsplit(".", 1)[0] for row in DEFERRED_165_SPECS}
    assert len(DEFERRED_165_SPECS) == 165
    assert len(expected) == 10
    assert named == expected
    assert SCANNER.violations(path) == []


def test_local_ai_seam_dispatch_covers_index_and_two_hundred_numbered_targets() -> None:
    file = ROOT / "skeleton/local_ai/gap_filler.py"
    tree = ast.parse(file.read_text(encoding="utf-8"))
    loader = next(
        node.value for node in tree.body if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "_REGISTERED_SEAM_LOADERS" for target in node.targets)
    )
    assert isinstance(loader, ast.Dict)
    imported = {
        node.args[0].value for node in ast.walk(loader)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and node.func.attr == "import_module" and node.args
        and isinstance(node.args[0], ast.Constant)
    }
    index_tree = ast.parse((ROOT / "skeleton/local_ai/local_ai_index.py").read_text(encoding="utf-8"))
    listed = next(
        ast.literal_eval(node.value) for node in index_tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "SEAMS" for t in node.targets)
    )
    expected = {"skeleton.local_ai." + name for name in listed}
    expected.update("skeleton.local_ai.seam_%03d" % i for i in range(200))
    assert len(expected) == 245
    assert imported == expected
    assert SCANNER.violations(file) == []


def test_repo_build_evidence_module_dispatch_matches_fixed_ten_batch_inventory() -> None:
    file = ROOT / "skeleton/repo_intelligence/build_lane_evidence.py"
    tree = ast.parse(file.read_text(encoding="utf-8"))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_registered_build_module")
    imports = {
        n.args[0].value for n in ast.walk(fn)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and n.func.attr == "import_module" and n.args
        and isinstance(n.args[0], ast.Constant)
    }
    assert imports == {
        "skeleton.build.asset_pipeline", "skeleton.build.build_observability",
        "skeleton.build.cache_contract", "skeleton.build.incremental_graph",
        "skeleton.build.parallel_scheduler", "skeleton.build.release_graph",
        "skeleton.build.remote_build", "skeleton.repo_intelligence.batch_plan",
        "skeleton.repo_intelligence.git_index",
    }
    assert SCANNER.violations(file) == []


def test_optional_decoder_negative_case_never_monkeypatches_global_import() -> None:
    file = ROOT / "skeleton/testing/test_multimodal_media_validation.py"
    tree = ast.parse(file.read_text(encoding="utf-8"))
    assert SCANNER.violations(file) == []
    assert "original_import(" not in file.read_text(encoding="utf-8")
    assert 'missing.setitem(sys.modules, "PIL", None)' in file.read_text(encoding="utf-8")


def test_swarm_module_provider_uses_only_governed_literal_default() -> None:
    from skeleton.gate_plane.agent_edge.swarm_adapter import ModuleSwarmDirectory

    with pytest.raises(ValueError, match="unknown swarm provider; inject CallableSwarmDirectory"):
        ModuleSwarmDirectory(module="not.a.trusted.module").snapshot()
    for file in (
        ROOT / "skeleton/gate_plane/agent_edge/swarm_adapter.py",
        ROOT / "skeleton/ai/runtime/policy/gate_plane/agent_edge/swarm_adapter.py",
    ):
        assert SCANNER.violations(file) == []
        assert 'importlib.import_module("skeleton.swarm.capabilities")' in file.read_text(encoding="utf-8")
    assert (
        (ROOT / "skeleton/gate_plane/agent_edge/swarm_adapter.py").read_bytes()
        == (ROOT / "skeleton/ai/runtime/policy/gate_plane/agent_edge/swarm_adapter.py").read_bytes()
    )


def test_generated_cue_dispatch_is_exhaustive_and_fail_closed() -> None:
    from skeleton.cue.gb46._dispatch import _IMPORTERS, load_organ_module
    from skeleton.cue.gb46.caps import names

    assert len(_IMPORTERS) == 2560
    assert set(_IMPORTERS) == {module for _cid, _family, module in names()}
    assert load_organ_module("c0001_house_001").Organ is not None
    with pytest.raises(KeyError, match="unregistered cue capability"):
        load_organ_module("../untrusted")


def test_audio_era_dispatch_matches_first_capability_per_era() -> None:
    from skeleton.audio.eras.conductor import _ERA_LOADERS
    from skeleton.audio.eras.caps import names

    first_by_era = {}
    for _cid, era, module in names():
        first_by_era.setdefault(era, module)
    assert set(_ERA_LOADERS) == set(first_by_era.values())
    assert len(_ERA_LOADERS) == 16
    with pytest.raises(TypeError):
        _ERA_LOADERS["arbitrary"] = lambda: None


def test_formal_bindings_cannot_dynamically_import_unloaded_code() -> None:
    from skeleton.contracts.formal_methods import FormalMethodError, ImplementationBinding

    binding = ImplementationBinding(
        contract_id="safe-binding",
        module_path="untrusted_missing_impl_123",
        symbol="target",
        source_sha256="0" * 64,
    )
    with pytest.raises(FormalMethodError, match="not loaded"):
        binding.resolve()
