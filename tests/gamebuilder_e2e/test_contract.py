"""Frozen ``skeleton.game_builder_run.v1`` result contract."""
from __future__ import annotations

import json

from skeleton.forge.game_builder import RESULT_FIELDS, RUN_SCHEMA, STUBBED, public_payload
from tests.gamebuilder_e2e.conftest import build, golden


def test_every_contract_field_present(genre):
    result = build(golden(genre))
    # ``qa`` is attached only when a QA hook is supplied (see _attach_qa).
    missing = [key for key in RESULT_FIELDS if key not in result and key != "qa"]
    assert missing == []
    assert result["schema_version"] == RUN_SCHEMA


def test_build_succeeds_and_proves_core_loop(genre):
    result = build(golden(genre))
    assert result["ok"] is True, result.get("error")
    assert result["check"] == {"ok": True, "problems": []}
    assert result["core_loop"]["passed"] is True
    assert result["core_loop"]["marker"] == result["marker"]
    assert result["proof"].startswith("CORE_LOOP_OK")
    assert f"genre={genre}" in result["proof"]


def test_stubbed_disclosure_is_honest(genre):
    assert build(golden(genre))["stubbed"] == list(STUBBED)


def test_public_payload_strips_operator_and_files(genre):
    body = public_payload(build(golden(genre)))
    assert "_operator" not in body
    assert "files" not in body
    assert body["file_names"] == sorted(body["file_names"])
    json.dumps(body, default=str)


def test_public_payload_includes_files_on_request(genre):
    result = build(golden(genre))
    body = public_payload(result, include_files=True)
    assert set(body["files"]) == set(result["files"])
    assert all(isinstance(v, str) for v in body["files"].values())


def test_identity_fields_default_to_none(genre):
    result = build(golden(genre))
    for key in ("actor_id", "tenant_id", "execution_id", "project_id", "structured_brief", "project"):
        assert result[key] is None


def test_playtest_off_records_no_playtest(genre):
    assert build(golden(genre))["playtest"] is None
