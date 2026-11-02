"""Offline quest counterfactual editing and import regression."""
from __future__ import annotations
import copy
import json
import os
import pytest

from tests.test_studio_quest_consequence_diff import source, leases, fork
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_quest_consequence_diff import (
    compile_quest_consequence_diff,
)
from skeleton.ai.game_builder.studio_quest_consequence_editor import (
    EXPORT_SCHEMA, render_quest_consequence_editor,
    import_quest_consequence_editor_export,
)


def export(docs, authoring=None):
    return {
        "schema": EXPORT_SCHEMA, "project_id": "original",
        "expected_source_digest": leases(docs)["expected_source_digest"],
        "expected_initial_session_digest":
            leases(docs)["expected_initial_session_digest"],
        "authoring": authoring or fork(),
    }


def private_write(path, payload):
    path.write_text(json.dumps(payload))
    os.chmod(path, 0o600)


def test_editor_renders_csp_hash_and_no_untrusted_script():
    docs = source()
    receipt = compile_quest_consequence_diff(docs, fork(), **leases(docs))
    html, manifest = render_quest_consequence_editor(docs, receipt, authorized=True)
    assert b"script-src 'sha256-" in html
    assert b"connect-src 'none'" in html
    assert b"choice:gate:mercy" not in html
    assert b"gate" in html
    assert manifest["authoring_export_only"] is True
    assert manifest["file_write_performed"] is False


def test_editor_import_recompiles_actual_authored_choices(tmp_path):
    docs = source()
    path = tmp_path / "export.json"
    private_write(path, export(docs))
    checked = import_quest_consequence_editor_export(docs, path, **leases(docs))
    assert checked["ending_delta"]["gained"] == ["war"]
    assert checked["release_certified"] is False


@pytest.mark.parametrize("mutation", [
    lambda x: x.update({"unexpected": True}),
    lambda x: x.update({"schema": "wrong"}),
    lambda x: x.update({"project_id": "other"}),
    lambda x: x.update({"expected_source_digest": "0"*64}),
    lambda x: x.update({"expected_initial_session_digest": "0"*64}),
    lambda x: x.update({"authoring": {"baseline_actions": [], "candidate_actions": []}}),
])
def test_editor_rejects_forged_or_invalid_exports(tmp_path, mutation):
    docs = source()
    payload = export(docs)
    mutation(payload)
    path = tmp_path / "export.json"
    private_write(path, payload)
    with pytest.raises(StudioQuestError):
        import_quest_consequence_editor_export(docs, path, **leases(docs))


def test_editor_rejects_duplicate_keys_and_public_permissions(tmp_path):
    docs = source()
    path = tmp_path / "export.json"
    path.write_text('{"schema":"a","schema":"b"}')
    os.chmod(path, 0o600)
    with pytest.raises(StudioQuestError):
        import_quest_consequence_editor_export(docs, path, **leases(docs))
    private_write(path, export(docs))
    os.chmod(path, 0o644)
    with pytest.raises(StudioQuestError):
        import_quest_consequence_editor_export(docs, path, **leases(docs))


def test_editor_rejects_symlink_and_source_drift(tmp_path):
    docs = source()
    real = tmp_path / "real.json"
    private_write(real, export(docs))
    link = tmp_path / "link.json"
    link.symlink_to(real)
    with pytest.raises(OSError):
        import_quest_consequence_editor_export(docs, link, **leases(docs))
    stale = export(docs)
    docs["narrative"]["endings"][0]["id"] = "revised"
    private_write(real, stale)
    with pytest.raises(StudioQuestError):
        import_quest_consequence_editor_export(docs, real, **leases(docs))


def test_editor_authorization_required(tmp_path):
    docs = source()
    path = tmp_path / "export.json"
    private_write(path, export(docs))
    with pytest.raises(PermissionError):
        import_quest_consequence_editor_export(
            docs, path, **dict(leases(docs), authorized=False))
