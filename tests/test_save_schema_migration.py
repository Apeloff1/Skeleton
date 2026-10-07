from __future__ import annotations

import json
from pathlib import Path

from scripts.check_save_schema_migration import (
    COMPATIBLE_MIGRATIONS,
    CONFLICT_DOMAIN,
    DOCUMENT_FIELDS,
    KIND,
    S042_SAVE_STATE_FIELDS,
    S171_DURABLE_STATE_FIELDS,
    SAVE_SCHEMA_VERSIONS,
    SCHEMA_VERSION,
    TASK_ID,
    main,
    validate_save_schema_migration,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKER = REPO_ROOT / "scripts" / "check_save_schema_migration.py"


def _doc(**overrides):
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "fixture_id": "save-migration.v1-to-v2.inventory-rename",
        "from_version": 1,
        "to_version": 2,
        "outcome": "success",
        "source_digest": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "expected_digest": "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        "steps": [{"op": "rename_field", "path": "inv -> inventory"}],
        "evidence_refs": ["issue:#960"],
    }
    payload.update(overrides)
    return payload


def test_contract_is_migration_not_save_state_or_durable_state() -> None:
    assert TASK_ID == "reserve-S043-save-schema-migration"
    assert CONFLICT_DOMAIN == "game.spec.save_migration"
    assert SCHEMA_VERSION == 1
    assert KIND == "save_schema_migration"
    assert SAVE_SCHEMA_VERSIONS == (1, 2, 3)
    assert (1, 2) in COMPATIBLE_MIGRATIONS
    assert (2, 1) not in COMPATIBLE_MIGRATIONS
    assert "player" not in DOCUMENT_FIELDS
    assert "world" not in DOCUMENT_FIELDS
    assert "store_id" not in DOCUMENT_FIELDS
    assert "family" not in DOCUMENT_FIELDS
    assert "lease" not in DOCUMENT_FIELDS
    source = CHECKER.read_text(encoding="utf-8")
    assert "TASK_ID" in source
    assert "TASK_KEY" not in source
    assert "_FINDING_PREFIX = \"save-migration\"" in source
    assert "do not implement a game save system" in source.lower() or "not a game save system" in source.lower()


def test_valid_forward_migration_has_no_violations() -> None:
    assert validate_save_schema_migration(_doc()) == []
    assert validate_save_schema_migration(_doc(from_version=2, to_version=3, fixture_id="v2-to-v3")) == []
    assert validate_save_schema_migration(_doc(from_version=1, to_version=3, fixture_id="v1-to-v3")) == []


def test_identity_migration_with_evidence_is_accepted() -> None:
    errors = validate_save_schema_migration(
        _doc(
            from_version=1,
            to_version=1,
            steps=[{"op": "identity", "path": "."}],
            fixture_id="save-migration.v1-identity",
        )
    )
    assert errors == []


def test_unknown_from_version_fails_closed() -> None:
    errors = validate_save_schema_migration(_doc(from_version=99))
    assert any("save-migration unknown version" in item for item in errors)
    assert any("from_version" in item for item in errors)


def test_unknown_to_version_fails_closed() -> None:
    errors = validate_save_schema_migration(_doc(to_version=4))
    assert any("save-migration unknown version" in item for item in errors)
    assert any("to_version" in item for item in errors)


def test_non_integer_versions_fail_closed() -> None:
    errors = validate_save_schema_migration(_doc(from_version="1", to_version=True))
    version_errors = [item for item in errors if "save-migration unknown version" in item]
    assert len(version_errors) >= 2
    assert any("from_version" in item for item in version_errors)
    assert any("to_version" in item for item in version_errors)


def test_missing_from_and_to_fail_closed() -> None:
    document = _doc()
    del document["from_version"]
    del document["to_version"]
    errors = validate_save_schema_migration(document)
    assert any("save-migration missing_value from_version" in item for item in errors)
    assert any("save-migration missing_value to_version" in item for item in errors)
    assert any("save-migration missing_value field" in item for item in errors)


def test_null_from_and_to_fail_closed() -> None:
    errors = validate_save_schema_migration(_doc(from_version=None, to_version=None))
    assert any("save-migration missing_value from_version" in item for item in errors)
    assert any("save-migration missing_value to_version" in item for item in errors)


def test_incompatible_versions_fail_closed() -> None:
    errors = validate_save_schema_migration(_doc(from_version=2, to_version=1))
    assert any("save-migration unknown incompatible_version" in item for item in errors)
    assert any("2→1" in item for item in errors)
    errors_3_1 = validate_save_schema_migration(_doc(from_version=3, to_version=1))
    assert any("save-migration unknown incompatible_version" in item for item in errors_3_1)


def test_extra_fields_fail_closed() -> None:
    errors = validate_save_schema_migration(_doc(owner="studio", notes="skip"))
    assert any("save-migration unknown field" in item for item in errors)
    assert any("owner" in item for item in errors)
    assert any("notes" in item for item in errors)


def test_extra_step_fields_fail_closed() -> None:
    errors = validate_save_schema_migration(
        _doc(steps=[{"op": "rename_field", "path": "inv", "transform": "custom"}])
    )
    assert any("save-migration unknown field" in item for item in errors)
    assert any("transform" in item for item in errors)


def test_successful_migration_without_evidence_fails_closed() -> None:
    empty = validate_save_schema_migration(_doc(evidence_refs=[]))
    assert any("save-migration missing_value evidence_refs" in item for item in empty)
    missing = _doc()
    del missing["evidence_refs"]
    missing_errors = validate_save_schema_migration(missing)
    assert any("save-migration missing_value evidence_refs" in item for item in missing_errors)
    blank = validate_save_schema_migration(_doc(evidence_refs=["", "  "]))
    assert any("save-migration unknown evidence_ref" in item for item in blank)


def test_successful_migration_without_expected_digest_fails_closed() -> None:
    errors = validate_save_schema_migration(_doc(expected_digest=""))
    assert any("save-migration missing_value expected_digest" in item for item in errors)


def test_s042_save_state_payload_fields_fail_closed() -> None:
    payload = _doc(player={"name": "hero"}, world={"seed": 1}, mechanics={"tick": 16})
    errors = validate_save_schema_migration(payload)
    assert any("save-migration unknown field" in item for item in errors)
    assert any("save-migration unknown save_state_field" in item for item in errors)
    for field in ("player", "world", "mechanics"):
        assert field in S042_SAVE_STATE_FIELDS
        assert any(field in item for item in errors)


def test_s171_durable_state_fields_fail_closed() -> None:
    payload = _doc(store_id="vault.worm_audit", family="vault", lease="worker-a", checkpoint={})
    errors = validate_save_schema_migration(payload)
    assert any("save-migration unknown field" in item for item in errors)
    assert any("save-migration unknown durable_state_field" in item for item in errors)
    for field in ("store_id", "family", "lease", "checkpoint"):
        assert field in S171_DURABLE_STATE_FIELDS
        assert any(field in item for item in errors)


def test_wrong_schema_version_and_kind_fail_closed() -> None:
    errors = validate_save_schema_migration(_doc(schema_version=2, kind="save_state"))
    assert any("save-migration unknown schema_version" in item for item in errors)
    assert any("save-migration unknown kind" in item for item in errors)


def test_unknown_outcome_and_step_op_fail_closed() -> None:
    errors = validate_save_schema_migration(
        _doc(outcome="migrated", steps=[{"op": "mutate_blob", "path": "root"}])
    )
    assert any("save-migration unknown outcome" in item for item in errors)
    assert any("save-migration unknown step_op" in item for item in errors)


def test_non_object_root_fails_closed() -> None:
    errors = validate_save_schema_migration(["not", "an", "object"])
    assert errors == ["save-migration unknown root_type: save-schema migration document must be an object"]


def test_empty_steps_fail_closed() -> None:
    errors = validate_save_schema_migration(_doc(steps=[]))
    assert any("save-migration missing_value steps" in item for item in errors)


def test_cli_accepts_valid_fixture(tmp_path: Path, capsys) -> None:
    path = tmp_path / "save-migration.json"
    path.write_text(json.dumps(_doc()), encoding="utf-8")
    assert main([str(path)]) == 0
    assert "Save-schema migration fixture v1 accepted" in capsys.readouterr().out


def test_cli_rejects_incompatible_and_unevidenced_fixtures(tmp_path: Path, capsys) -> None:
    path = tmp_path / "save-migration.json"
    path.write_text(json.dumps(_doc(from_version=3, to_version=2, evidence_refs=[])), encoding="utf-8")
    assert main([str(path)]) == 1
    stderr = capsys.readouterr().err
    assert "Save-schema migration validation failed:" in stderr
    assert "save-migration unknown incompatible_version" in stderr
    assert "save-migration missing_value evidence_refs" in stderr


def test_cli_rejects_unreadable_json(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{not-json", encoding="utf-8")
    try:
        main([str(path)])
    except SystemExit as exc:
        assert "save-migration unreadable json" in str(exc)
    else:
        raise AssertionError("unreadable JSON must fail closed")


def test_cli_rejects_missing_document(tmp_path: Path) -> None:
    path = tmp_path / "absent.json"
    try:
        main([str(path)])
    except SystemExit as exc:
        assert "save-migration unreadable missing_doc" in str(exc)
    else:
        raise AssertionError("missing document must fail closed")


def test_not_wired_into_quality_gates() -> None:
    quality_gates = (REPO_ROOT / "scripts" / "quality-gates.sh").read_text(encoding="utf-8")
    assert "check_save_schema_migration.py" not in quality_gates
    assert "test_save_schema_migration.py" not in quality_gates
