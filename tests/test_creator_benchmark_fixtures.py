from __future__ import annotations

import ast
import json
from pathlib import Path

from scripts.check_creator_benchmark_fixtures import (
    CONFLICT_DOMAIN,
    CONSTRAINT_OPS,
    FIXTURE_DIR,
    NODE_KINDS,
    SCHEMA,
    SCHEMA_VERSION,
    TASK_KEY,
    catalog_paths,
    main,
    repo_root,
    validate_catalog,
    validate_creator_intent_fixture,
)

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_creator_benchmark_fixtures.py"
FORBIDDEN_IMPORT_ROOTS = (
    "skeleton.creator",
    "skeleton.eval",
    "openai",
    "anthropic",
    "litellm",
    "google",
    "httpx",
    "requests",
    "pydantic",
)


def _doc(**overrides):
    payload = {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "fixture_id": "lantern_watch_2d",
        "concept": {
            "title": "Lantern Watch",
            "statement": "A local 2D lantern-watch stealth loop.",
        },
        "expected_normalized": {
            "constraints": [
                {
                    "id": "c_presentation",
                    "field": "presentation",
                    "op": "equals",
                    "value": "2d",
                }
            ]
        },
        "expected_design_graph": {
            "nodes": [
                {
                    "id": "n_quay",
                    "kind": "world",
                    "title": "Quay rooms",
                    "depends_on": [],
                }
            ],
            "constraints": [{"id": "c_presentation", "applies_to": ["n_quay"]}],
        },
    }
    payload.update(overrides)
    return payload


def test_seed_contract_constants() -> None:
    assert TASK_KEY == "reserve-S039-creator-benchmark-fixtures"
    assert CONFLICT_DOMAIN == "eval.fixtures.creator_intent"
    assert SCHEMA == "eval.fixtures.creator_intent.v1"
    assert SCHEMA_VERSION == 1
    assert CONSTRAINT_OPS == frozenset({"require", "forbid", "equals", "min", "max"})
    assert "world" in NODE_KINDS
    assert "system" in NODE_KINDS


def test_committed_catalog_is_small_and_valid() -> None:
    root = repo_root()
    paths = catalog_paths(root)
    assert [path.name for path in paths] == [
        "hex_duel_turns.json",
        "lantern_watch_2d.json",
        "shore_forage_craft.json",
    ]
    assert validate_catalog(root) == []
    for path in paths:
        document = json.loads(path.read_text(encoding="utf-8"))
        assert validate_creator_intent_fixture(document) == []
        assert "provider" not in json.dumps(document)
        assert "model" not in json.dumps(document)


def test_valid_document_has_no_violations() -> None:
    assert validate_creator_intent_fixture(_doc()) == []


def test_unknown_document_fields_fail_closed() -> None:
    errors = validate_creator_intent_fixture(_doc(provider="openai"))
    assert any("creator-intent-fixture unknown field" in item for item in errors)
    assert any("provider" in item for item in errors)


def test_unknown_nested_fields_fail_closed() -> None:
    document = _doc(
        concept={"title": "Lantern Watch", "statement": "Local 2D loop.", "model": "gpt"}
    )
    errors = validate_creator_intent_fixture(document)
    assert any("creator-intent-fixture unknown field" in item for item in errors)
    assert any("model" in item for item in errors)


def test_bool_schema_version_fails_closed() -> None:
    errors = validate_creator_intent_fixture(_doc(schema_version=True))
    assert any("creator-intent-fixture unknown schema_version" in item for item in errors)


def test_unknown_constraint_op_fails_closed() -> None:
    document = _doc(
        expected_normalized={
            "constraints": [
                {"id": "c_guess", "field": "presentation", "op": "maybe", "value": "2d"}
            ]
        }
    )
    errors = validate_creator_intent_fixture(document)
    assert any("creator-intent-fixture unknown op" in item for item in errors)
    assert any("maybe" in item for item in errors)


def test_unknown_node_kind_fails_closed() -> None:
    document = _doc(
        expected_design_graph={
            "nodes": [{"id": "n_quay", "kind": "godot_scene", "title": "Quay", "depends_on": []}],
            "constraints": [{"id": "c_presentation", "applies_to": ["n_quay"]}],
        }
    )
    errors = validate_creator_intent_fixture(document)
    assert any("creator-intent-fixture unknown kind" in item for item in errors)
    assert any("godot_scene" in item for item in errors)


def test_dangling_design_graph_constraint_fails_closed() -> None:
    document = _doc(
        expected_design_graph={
            "nodes": [{"id": "n_quay", "kind": "world", "title": "Quay", "depends_on": []}],
            "constraints": [{"id": "c_missing", "applies_to": ["n_quay"]}],
        }
    )
    errors = validate_creator_intent_fixture(document)
    assert any("creator-intent-fixture unknown dangling" in item for item in errors)
    assert any("c_missing" in item for item in errors)


def test_unknown_dependency_node_fails_closed() -> None:
    document = _doc(
        expected_design_graph={
            "nodes": [
                {
                    "id": "n_watch",
                    "kind": "system",
                    "title": "Watch",
                    "depends_on": ["n_ghost"],
                }
            ],
            "constraints": [{"id": "c_presentation", "applies_to": ["n_watch"]}],
        }
    )
    errors = validate_creator_intent_fixture(document)
    assert any("creator-intent-fixture unknown dangling" in item for item in errors)
    assert any("n_ghost" in item for item in errors)


def test_cyclic_depends_on_fails_closed() -> None:
    document = _doc(
        expected_design_graph={
            "nodes": [
                {"id": "n_a", "kind": "world", "title": "A", "depends_on": ["n_b"]},
                {"id": "n_b", "kind": "system", "title": "B", "depends_on": ["n_a"]},
            ],
            "constraints": [{"id": "c_presentation", "applies_to": ["n_a"]}],
        }
    )
    errors = validate_creator_intent_fixture(document)
    assert any("creator-intent-fixture unknown cycle" in item for item in errors)


def test_self_dependency_fails_closed() -> None:
    document = _doc(
        expected_design_graph={
            "nodes": [
                {"id": "n_quay", "kind": "world", "title": "Quay", "depends_on": ["n_quay"]}
            ],
            "constraints": [{"id": "c_presentation", "applies_to": ["n_quay"]}],
        }
    )
    errors = validate_creator_intent_fixture(document)
    assert any("creator-intent-fixture unknown cycle" in item for item in errors)


def test_duplicate_constraint_ids_fail_closed() -> None:
    document = _doc(
        expected_normalized={
            "constraints": [
                {"id": "c_presentation", "field": "presentation", "op": "equals", "value": "2d"},
                {"id": "c_presentation", "field": "presentation", "op": "equals", "value": "2d"},
            ]
        }
    )
    errors = validate_creator_intent_fixture(document)
    assert any("creator-intent-fixture unknown duplicate" in item for item in errors)


def test_min_bool_value_fails_closed() -> None:
    document = _doc(
        expected_normalized={
            "constraints": [
                {"id": "c_players", "field": "players", "op": "min", "value": True}
            ]
        }
    )
    errors = validate_creator_intent_fixture(document)
    assert any("creator-intent-fixture unknown type" in item for item in errors)


def test_whitespace_title_fails_closed() -> None:
    document = _doc(concept={"title": " padded ", "statement": "Local 2D loop."})
    errors = validate_creator_intent_fixture(document)
    assert any("creator-intent-fixture missing_value title" in item for item in errors)


def test_checker_stays_stdlib_and_off_overlapping_surfaces() -> None:
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
            imported.add(node.module.split(".")[0])
    allowed = {
        "__future__",
        "argparse",
        "collections",
        "collections.abc",
        "json",
        "math",
        "pathlib",
        "re",
        "sys",
    }
    assert imported <= allowed
    source = SCRIPT.read_text(encoding="utf-8")
    assert "compile_intent" not in source
    assert "score_concept_to_release" not in source
    assert "creator.intent.v1" not in source
    assert "eval.concept_to_release" not in source
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                for forbidden in FORBIDDEN_IMPORT_ROOTS:
                    assert not alias.name.startswith(forbidden)
        elif isinstance(node, ast.ImportFrom) and node.module:
            for forbidden in FORBIDDEN_IMPORT_ROOTS:
                assert not node.module.startswith(forbidden)


def test_cli_accepts_committed_catalog(capsys) -> None:
    assert main([]) == 0
    assert "Creator-intent fixtures v1 accepted catalog" in capsys.readouterr().out


def test_cli_accepts_valid_fixture(tmp_path: Path, capsys) -> None:
    path = tmp_path / "lantern_watch_2d.json"
    path.write_text(json.dumps(_doc()), encoding="utf-8")
    assert main([str(path)]) == 0
    assert "Creator-intent fixtures v1 accepted" in capsys.readouterr().out


def test_cli_rejects_unreadable_json(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{not-json", encoding="utf-8")
    try:
        main([str(path)])
    except SystemExit as exc:
        assert "creator-intent-fixture unreadable json" in str(exc)
    else:
        raise AssertionError("unreadable JSON must fail closed")


def test_catalog_rejects_unknown_filename(tmp_path: Path) -> None:
    catalog = tmp_path / FIXTURE_DIR
    catalog.mkdir(parents=True)
    (catalog / "notes.md").write_text("not a fixture\n", encoding="utf-8")
    try:
        validate_catalog(tmp_path)
    except SystemExit as exc:
        assert "creator-intent-fixture unknown filename" in str(exc)
    else:
        raise AssertionError("unknown catalog entries must fail closed")


def test_catalog_fixture_id_must_match_filename(tmp_path: Path) -> None:
    catalog = tmp_path / FIXTURE_DIR
    catalog.mkdir(parents=True)
    path = catalog / "lantern_watch_2d.json"
    path.write_text(json.dumps(_doc(fixture_id="other_id")), encoding="utf-8")
    errors = validate_catalog(tmp_path)
    assert any("creator-intent-fixture unknown fixture_id" in item for item in errors)
