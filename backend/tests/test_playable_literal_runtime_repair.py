"""One canonical model proposal publishes through the scoped source/version CAS."""
from copy import deepcopy
from dataclasses import replace
import json
from types import SimpleNamespace

import pytest

from backend.tests.test_playable_engine_bridge import bridge, HTML
from backend.tests.test_playable_private_creation import project_boundary, _matches
from backend.tests.test_private_memory_boundary import memory_boundary
from core import databases
from core.playable_literal_patch import RESPONSE_SCHEMA
from routes import playable, playable_repair
from routes.playable_htmlutils import playable_html_digest


@pytest.fixture
def patch_boundary(bridge, project_boundary, monkeypatch):
    client, headers, db, engine, commands, contexts = bridge
    users = project_boundary[2]
    original = {"playable_id": "patch-game", "owner_id": "alice@example.test", "tenant_id": "tenant-a",
                "html": HTML, "html_digest": playable_html_digest(HTML), "version": 7,
                "repair_trail": [], "repair_count": 0, "status": "ready", "playability_score": 82,
                "evaluation": {"available": True, "source_digest": playable_html_digest(HTML),
                               "overall": 100, "verdict": "ship", "shippable": True}}
    db.playables.rows.append(deepcopy(original))
    class SyncPlayables:
        def find_one(self, query):
            return next((deepcopy(row) for row in db.playables.rows if _matches(row, query)), None)
    monkeypatch.setattr(databases, "get_sync_db", lambda name: SimpleNamespace(playables=SyncPlayables()))
    return client, headers, db, engine, commands, users, original


def _repair(client, headers):
    return client.post("/api/playable/patch-game/repair", headers=headers["alice"],
                       json={"error": "Repair the reported runtime error without removing working controls"})


def test_real_model_response_publishes_exact_patch_version_bytes_and_pinned_receipts_atomically(patch_boundary):
    client, headers, db, _, commands, _, original = patch_boundary
    response = _repair(client, headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["repaired"] is True and len(commands) == 1
    command = commands[0]
    assert command.execution_request.resource_budget["max_model_turns"] == 1
    assert command.execution_request.resource_budget["max_output_tokens"] == 1024
    assert command.execution_request.context_policy["structured_output_schema"] == RESPONSE_SCHEMA
    assert HTML in command.compiled_context.prompt
    assert playable_html_digest(HTML) in command.compiled_context.prompt
    expected = HTML.replace("ctx.fillStyle='#123';", "ctx.fillStyle='#124';")
    row = db.playables.rows[0]
    assert row["html"] == expected
    assert row["version"] == data["version"] == 8
    assert row["bytes"] == len(expected.encode()) == data["bytes"]
    assert row["html_digest"] == data["result_sha256"] == playable_html_digest(expected)
    assert data["source_sha256"] == playable_html_digest(HTML)
    assert row["last_repair"]["engine_execution_id"] == command.execution_request.execution_id
    assert row["last_repair"]["engine_provider_receipts"] == ["provider:one"]
    assert row["last_repair"] == row["repair_trail"][-1]
    assert row["last_repair"]["patch_fingerprint"] == data["patch_fingerprint"]
    updates = db.playables.writes
    assert len(updates) == 1
    query, update = updates[0]
    assert query["html"] == original["html"] and query["version"] == 7
    assert query["owner_id"] == "alice@example.test" and query["tenant_id"] == "tenant-a"
    assert query["revoked"] == {"$ne": True}
    assert update["$set"]["html"] == expected and update["$set"]["version"] == 8
    review = client.get("/api/playable/patch-game", headers=headers["alice"]).json()["evaluation"]
    assert review["stale"] is True and review["available"] is False and review["shippable"] is False


@pytest.mark.parametrize("concurrent_edit", [False, True])
def test_repeated_model_edit_preserves_raw_counts_and_source_cas(patch_boundary, monkeypatch, concurrent_edit):
    client, headers, db, engine, commands, _, original = patch_boundary
    execute = engine.execute
    edited = HTML.replace("ctx.fillStyle='#123';", "ctx.fillStyle='#ff0';")
    async def repeat_after_generation(command):
        terminal = await execute(command)
        edit = {"find": "ctx.fillStyle='#123';", "replace": "ctx.fillStyle='#124';"}
        if concurrent_edit:
            db.playables.rows[0].update(html=edited, version=8, html_digest=playable_html_digest(edited))
        return replace(terminal, final_output=json.dumps({"schema_version": 1, "edits": [edit] * 3}))
    monkeypatch.setattr(engine, "execute", repeat_after_generation)
    response = _repair(client, headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert len(commands) == 1
    if concurrent_edit:
        assert data["repaired"] is False and data["error_code"] == "repair_source_changed"
        assert db.playables.rows[0]["html"] == edited and db.playables.rows[0]["version"] == 8
        assert db.playables.rows[0]["repair_trail"] == []
    else:
        row = db.playables.rows[0]
        assert data["repaired"] is True and data["version"] == 8
        assert data["proposal_edit_count"] == row["last_repair"]["proposal_edit_count"] == 3
        assert data["edit_count"] == row["last_repair"]["edit_count"] == 1
        assert row["html"] == original["html"].replace("ctx.fillStyle='#123';", "ctx.fillStyle='#124';")
        assert row["last_repair"]["engine_provider_receipts"] == ["provider:one"]


def test_foreign_actor_cannot_dispatch_a_patch_model(patch_boundary):
    client, headers, db, _, commands, _, original = patch_boundary
    response = client.post("/api/playable/patch-game/repair", headers=headers["bob"], json={"error": "not mine"})
    assert response.status_code == 404 and commands == []
    assert db.playables.rows[0] == original


@pytest.mark.parametrize("revocation", ["account", "source"])
def test_current_account_and_source_are_rechecked_after_model_response(patch_boundary, monkeypatch, revocation):
    client, headers, db, engine, commands, users, original = patch_boundary
    execute = engine.execute
    async def revoked_after_generation(command):
        terminal = await execute(command)
        if revocation == "account":
            users["alice@example.test"]["role"] = "viewer"
        else:
            db.playables.rows[0]["revoked"] = True
        return terminal
    monkeypatch.setattr(engine, "execute", revoked_after_generation)
    response = _repair(client, headers)
    assert response.status_code == (403 if revocation == "account" else 404)
    assert len(commands) == 1
    assert db.playables.rows[0]["html"] == original["html"]
    assert db.playables.rows[0]["version"] == original["version"]
    assert not any(operation == "update" for operation, _ in db.playables.calls)


def test_concurrent_source_edit_is_not_overwritten_and_does_not_dispatch_again(patch_boundary, monkeypatch):
    client, headers, db, engine, commands, _, _ = patch_boundary
    execute = engine.execute
    edited = HTML.replace("ctx.fillStyle='#123';", "ctx.fillStyle='#ff0';")
    async def edit_during_generation(command):
        terminal = await execute(command)
        db.playables.rows[0].update(html=edited, version=8, html_digest=playable_html_digest(edited))
        return terminal
    monkeypatch.setattr(engine, "execute", edit_during_generation)
    response = _repair(client, headers)
    assert response.status_code == 200, response.text
    assert response.json()["repaired"] is False
    assert response.json()["error_code"] == "repair_source_changed"
    assert db.playables.rows[0]["html"] == edited and db.playables.rows[0]["version"] == 8
    assert db.playables.rows[0]["repair_trail"] == []
    assert len(commands) == 1


@pytest.mark.parametrize("content", [
    "not JSON",
    json.dumps({"schema_version": 1, "source_sha256": "0" * 64,
                "edits": [{"find": "ctx.fillStyle='#123';", "replace": "ctx.fillStyle='#124';"}]}),
    json.dumps({"schema_version": 1, "edits": [{"find": "not in source", "replace": "anything"}]}),
    json.dumps({"schema_version": 1, "edits": [{"find": "</html>", "replace": "<script>unfinished("}]}),
], ids=["malformed", "wrong-digest-echo", "missing-anchor", "incomplete-candidate"])
def test_rejected_model_proposal_preserves_entire_old_record_without_fallback(patch_boundary, monkeypatch, content):
    client, headers, db, _, commands, _, original = patch_boundary
    calls = []
    def proposal(*args, **kwargs):
        calls.append(kwargs)
        return {"content": content}
    monkeypatch.setattr(playable_repair, "_llm_in_thread", proposal)
    response = _repair(client, headers)
    assert response.status_code == 200, response.text
    assert response.json()["repaired"] is False
    assert len(calls) == 1 and commands == []
    assert calls[0]["max_model_turns"] == 1 and calls[0]["max_output_tokens"] == 1024
    assert db.playables.rows[0] == original
    assert not any(operation == "update" for operation, _ in db.playables.calls)


def test_missing_canonical_lineage_cannot_publish_an_otherwise_valid_patch(patch_boundary, monkeypatch):
    client, headers, db, _, commands, _, original = patch_boundary
    def proposal(*args, **kwargs):
        return {"content": json.dumps({"schema_version": 1, "edits": [
            {"find": "ctx.fillStyle='#123';", "replace": "ctx.fillStyle='#124';"},
        ]})}
    monkeypatch.setattr(playable_repair, "_llm_in_thread", proposal)
    response = _repair(client, headers)
    assert response.status_code == 200
    assert response.json()["error_code"] == "repair_engine_lineage_unavailable"
    assert response.json()["repaired"] is False
    assert db.playables.rows[0] == original and commands == []


@pytest.mark.parametrize("version", [None, True, 0])
def test_unversioned_or_malformed_sources_fail_before_model_dispatch(patch_boundary, version):
    client, headers, db, _, commands, _, _ = patch_boundary
    db.playables.rows[0]["version"] = version
    before = deepcopy(db.playables.rows[0])
    response = _repair(client, headers)
    assert response.status_code == 200 and response.json()["repaired"] is False
    assert response.json()["error_code"] == "repair_source_version_unavailable"
    assert commands == [] and db.playables.rows[0] == before


def test_bounded_repair_history_keeps_lifetime_count_and_latest_receipt(patch_boundary):
    client, headers, db, _, commands, _, _ = patch_boundary
    db.playables.rows[0].update(repair_count=100_000, repair_trail=[{"attempt": index} for index in range(80)])
    response = _repair(client, headers)
    assert response.status_code == 200 and response.json()["repaired"] is True
    row = db.playables.rows[0]
    assert len(row["repair_trail"]) == 64
    assert row["repair_count"] == row["last_repair"]["attempt"] == 100_001
    assert row["repair_trail"][0] == {"attempt": 17}
    assert len(commands) == 1
