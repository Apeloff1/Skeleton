"""Offline readiness editor: CSP, source leases, JSON and CLI round trips."""
from __future__ import annotations
import json
import os
import pytest

from skeleton.ai.game_builder.studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, start_quest,
)
from skeleton.ai.game_builder.studio_quest_readiness import compile_quest_readiness
from skeleton.ai.game_builder.studio_quest_readiness_editor import (
    EXPORT_SCHEMA, render_quest_readiness_editor,
    import_quest_readiness_editor_export,
)


def docs():
    return {
        "quest": {"project_id": "editor", "release_certified": False,
                  "stage_graph": [{
                      "id": "gate", "prerequisites": [],
                      "alternatives": ["go"], "reward": "open",
                  }]},
        "narrative": {"project_id": "editor", "release_certified": False,
                      "endings": [{"id": "win", "requires": ["open"]}]},
    }


def lease(source):
    return {
        "expected_source_digest": compile_quest_program(source).source_digest,
        "expected_initial_session_digest": start_quest(
            source, authorized=True).digest,
    }


def receipt(source):
    return compile_quest_readiness(
        source, {"max_states": 16, "max_depth": 1},
        authorized=True, **lease(source))


def export(source, path, authoring=None):
    data = {
        "schema": EXPORT_SCHEMA, "project_id": "editor",
        **lease(source),
        "authoring": authoring or {"max_states": 32, "max_depth": 1},
    }
    path.write_text(json.dumps(data), encoding="utf-8")
    path.chmod(0o600)
    return data


def test_html_has_hashed_csp_no_network_and_typed_edit_controls():
    source = docs()
    html, proof = render_quest_readiness_editor(
        source, receipt(source), authorized=True)
    assert proof["authoring_export_only"] is True
    assert proof["file_write_performed"] is False
    assert proof["release_certified"] is False
    assert b"script-src 'sha256-" in html
    assert b"connect-src 'none'" in html
    assert b"max_states" in html and b"max_depth" in html
    assert b"URL.createObjectURL" in html
    assert b"innerHTML" not in html
    assert b"eval(" not in html
    assert b"document.write" not in html
    assert (html, proof) == render_quest_readiness_editor(
        source, receipt(source), authorized=True)


def test_private_export_import_recompiles_canonical_joint_proof(tmp_path):
    source = docs()
    path = tmp_path / "budget.json"
    export(source, path)
    report = import_quest_readiness_editor_export(
        source, path, authorized=True, **lease(source))
    assert report["authoring"] == {"max_states": 32, "max_depth": 1}
    assert report["playable_handoff_allowed"] is True
    with pytest.raises(PermissionError):
        import_quest_readiness_editor_export(
            source, path, authorized=False, **lease(source))


def test_stale_leases_unknown_fields_bool_budget_and_duplicate_keys_rejected(tmp_path):
    source = docs()
    path = tmp_path / "budget.json"
    for mutation in (
        {"expected_source_digest": "0" * 64},
        {"expected_initial_session_digest": "0" * 64},
        {"project_id": "other"},
        {"authoring": {"max_states": True, "max_depth": 1}},
        {"authoring": {"max_states": 1, "max_depth": 2}},
        {"extra": "authority"},
    ):
        data = export(source, path)
        data.update(mutation)
        path.write_text(json.dumps(data))
        path.chmod(0o600)
        with pytest.raises(StudioQuestError):
            import_quest_readiness_editor_export(
                source, path, authorized=True, **lease(source))
    path.write_text('{"schema":"one","schema":"two"}')
    path.chmod(0o600)
    with pytest.raises(StudioQuestError):
        import_quest_readiness_editor_export(
            source, path, authorized=True, **lease(source))


def test_import_rejects_symlink_hardlink_public_file_and_fifo(tmp_path):
    source = docs()
    path = tmp_path / "budget.json"
    export(source, path)
    if os.name != "posix":
        pytest.skip("POSIX custody checks")
    path.chmod(0o644)
    with pytest.raises(StudioQuestError):
        import_quest_readiness_editor_export(
            source, path, authorized=True, **lease(source))
    path.chmod(0o600)
    hardlink = tmp_path / "alias.json"
    os.link(path, hardlink)
    with pytest.raises(StudioQuestError):
        import_quest_readiness_editor_export(
            source, path, authorized=True, **lease(source))
    hardlink.unlink()
    path.unlink()
    path.symlink_to(tmp_path / "missing")
    with pytest.raises(OSError):
        import_quest_readiness_editor_export(
            source, path, authorized=True, **lease(source))
    path.unlink()
    os.mkfifo(path, 0o600)
    with pytest.raises(StudioQuestError):
        import_quest_readiness_editor_export(
            source, path, authorized=True, **lease(source))


def test_readiness_cli_accepts_editor_export_and_html_preview(
    monkeypatch, tmp_path, capsys,
):
    from scripts import studio_quest_readiness_cli as cli
    source = docs()
    monkeypatch.setattr(cli, "read_blueprint", lambda _: source)
    path = tmp_path / "budget.json"
    export(source, path)
    args = ["--project", "editor",
            "--expected-source", lease(source)["expected_source_digest"],
            "--expected-session", lease(source)["expected_initial_session_digest"]]
    assert cli.main(args + ["--editor-export", str(path)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["readiness"]["playable_handoff_allowed"] is True
    assert cli.main(args + ["--prompt", "--editor-preview"]) == 0
    html = capsys.readouterr().out
    assert "Quest readiness editor" in html
    assert "script-src 'sha256-" in html


def test_playable_cli_accepts_same_editor_export(monkeypatch, tmp_path, capsys):
    from scripts import studio_quest_readiness_playable_cli as cli
    from skeleton.ai.game_builder import studio_quest_readiness_playable as owner
    from types import SimpleNamespace
    from hashlib import sha256
    source = docs()
    path = tmp_path / "budget.json"
    export(source, path)
    monkeypatch.setattr(cli, "read_blueprint", lambda _: source)
    monkeypatch.setattr(owner, "read_blueprint", lambda _: source)
    html = "<!doctype html><html><body>Editor game</body></html>"
    monkeypatch.setattr(owner, "compile_preview",
                        lambda _pid, *, authorized: SimpleNamespace(
                            playable=SimpleNamespace(html=html),
                            receipt=lambda: {
                                "project_id": "editor",
                                "validated_gameplay_proof": True,
                                "html_sha256": sha256(html.encode()).hexdigest(),
                            }))
    args = ["--project", "editor",
            "--expected-source", lease(source)["expected_source_digest"],
            "--expected-session", lease(source)["expected_initial_session_digest"],
            "--editor-export", str(path)]
    assert cli.main(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["manifest"]["canonical_quest_replay_verified"] is True
    assert result["manifest"]["release_certified"] is False
