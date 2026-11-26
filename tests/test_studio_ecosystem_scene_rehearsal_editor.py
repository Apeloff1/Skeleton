"""Offline editor: source/session/baseline lease, CSP and nofollow import."""
import json
import pytest
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_canon_proof import audit_canon_source
from skeleton.ai.game_builder.studio_ecosystem_dialogue_staging import compile_dialogue_staging
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError, replay_quest
from skeleton.ai.game_builder.studio_ecosystem_scene_rehearsal import compile_scene_rehearsal
from skeleton.ai.game_builder.studio_ecosystem_scene_rehearsal_editor import (
    EXPORT_SCHEMA, render_scene_rehearsal_editor, load_scene_rehearsal_export,
    publish_scene_rehearsal_editor,
)
PROJECT = "studio_arena_fighting_glacial_fjord"


def fixture():
    docs = read_blueprint(PROJECT)
    source = audit_canon_source(docs, authorized=True)["source_digest"]
    session = replay_quest(docs, [], authorized=True)
    cards = compile_dialogue_staging(
        docs, [], authorized=True, expected_source_digest=source)["cards"]
    schedule = {"scene_ticks": {card["scene_id"]: 5 for card in cards},
                "npc_turnaround_ticks": 1, "min_start_ticks": {}}
    report = compile_scene_rehearsal(
        docs, [], schedule, schedule, authorized=True,
        expected_source_digest=source, expected_session_digest=session.digest)
    return docs, source, session, report


def test_csp_offline_editor_is_deterministic_and_no_untrusted_html():
    docs, source, session, report = fixture()
    html, receipt = render_scene_rehearsal_editor(
        docs, [], report, authorized=True)
    assert b"Content-Security-Policy" in html
    assert b"innerHTML" not in html
    assert b"eval(" not in html
    assert b"createObjectURL" in html
    assert b"scene_rehearsal_export.v1" in html
    assert receipt["source_digest"] == source
    assert receipt["session_digest"] == session.digest
    assert receipt["authoring_export_only"] is True
    assert render_scene_rehearsal_editor(
        docs, [], report, authorized=True) == (html, receipt)
    with pytest.raises(StudioQuestError):
        render_scene_rehearsal_editor(
            docs, [], {**report, "critical_delta_ticks": 999}, authorized=True)


def test_private_editor_import_and_replay(tmp_path):
    docs, source, session, report = fixture()
    payload = {"schema": EXPORT_SCHEMA, "project_id": PROJECT,
               "source_digest": source, "session_digest": session.digest,
               "baseline_schedule_digest": report["baseline_schedule_digest"],
               "candidate_schedule": report["candidate_schedule"]}
    path = tmp_path / "candidate.json"
    path.write_text(json.dumps(payload))
    path.chmod(0o600)
    kwargs = {"authorized": True, "expected_project_id": PROJECT,
              "expected_source_digest": source,
              "expected_session_digest": session.digest,
              "expected_baseline_digest": report["baseline_schedule_digest"]}
    assert load_scene_rehearsal_export(path, **kwargs) == report["candidate_schedule"]
    with pytest.raises(StudioQuestError):
        load_scene_rehearsal_export(
            path, **{**kwargs, "expected_baseline_digest": "0" * 64})
    path.write_text('{"schema":"a","schema":"b"}')
    with pytest.raises(StudioQuestError):
        load_scene_rehearsal_export(path, **kwargs)
    path.unlink()
    path.symlink_to(tmp_path / "missing")
    with pytest.raises(OSError):
        load_scene_rehearsal_export(path, **kwargs)


def test_editor_publish_exclusive_and_cli_path(tmp_path, capsys):
    from scripts.studio_scene_rehearsal_cli import main
    docs, source, session, report = fixture()
    html, receipt = render_scene_rehearsal_editor(
        docs, [], report, authorized=True)
    published = publish_scene_rehearsal_editor(
        html, receipt, tmp_path, authorized=True,
        documents=docs, actions=[], report=report)
    assert published["file_write_performed"] is True
    assert (tmp_path / "scene_rehearsal_editor.html").read_bytes() == html
    with pytest.raises(FileExistsError):
        publish_scene_rehearsal_editor(
            html, receipt, tmp_path, authorized=True,
            documents=docs, actions=[], report=report)
    out = tmp_path / "new"
    out.mkdir()
    assert main(["--project", PROJECT, "--expected-source", source,
                 "--expected-session", session.digest,
                 "--baseline", json.dumps(report["baseline_schedule"]),
                 "--candidate", json.dumps(report["candidate_schedule"]),
                 "--editor-directory", str(out)]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["editor"]["file_write_performed"] is True
    assert (out / "scene_rehearsal_editor.html").is_file()

def test_editor_publication_refuses_self_signed_forged_html(tmp_path):
    docs, source, session, report = fixture()
    html, receipt = render_scene_rehearsal_editor(
        docs, [], report, authorized=True)
    forged = html.replace(b"Original scene timing editor", b"Forged scene timing editor")
    import hashlib
    import json as _json
    false_receipt = {**receipt, "html_sha256": hashlib.sha256(forged).hexdigest(),
                     "html_bytes": len(forged)}
    false_receipt["editor_digest"] = hashlib.sha256(_json.dumps(
        {k: v for k, v in false_receipt.items() if k != "editor_digest"},
        sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False).encode("ascii")).hexdigest()
    with pytest.raises(StudioQuestError):
        publish_scene_rehearsal_editor(
            forged, false_receipt, tmp_path, authorized=True,
            documents=docs, actions=[], report=report)
    assert not (tmp_path / "scene_rehearsal_editor.html").exists()
