"""Source-leased real HTML5 playable bundle and adversarial custody fixtures."""
from __future__ import annotations
import copy
from hashlib import sha256
import io
import json
import os
from types import SimpleNamespace
import zipfile

import pytest

from skeleton.ai.game_builder.studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, start_quest,
)
from skeleton.ai.game_builder.studio_quest_readiness import compile_quest_readiness
from skeleton.ai.game_builder import studio_quest_readiness_playable as playable


def source():
    return {
        "quest": {"project_id": "original", "release_certified": False,
                  "stage_graph": [{
                      "id": "gate", "prerequisites": [],
                      "alternatives": ["go"], "reward": "gate_open",
                  }]},
        "narrative": {"project_id": "original", "release_certified": False,
                      "endings": [{"id": "win", "requires": ["gate_open"]}]},
    }


def ready(docs):
    return compile_quest_readiness(
        docs, {"max_states": 32, "max_depth": 1}, authorized=True,
        expected_source_digest=compile_quest_program(docs).source_digest,
        expected_initial_session_digest=start_quest(
            docs, authorized=True).digest,
    )


def catalog(monkeypatch, docs):
    monkeypatch.setattr(playable, "read_blueprint", lambda _: docs)
    html = "<!doctype html><html><body>Original playable</body></html>"
    def compile_stub(project_id, *, authorized):
        assert project_id == "original" and authorized is True
        return SimpleNamespace(
            playable=SimpleNamespace(html=html),
            receipt=lambda: {
                "project_id": project_id,
                "validated_gameplay_proof": True,
                "html_sha256": sha256(html.encode("utf-8")).hexdigest(),
                "release_certified": False,
            },
        )
    monkeypatch.setattr(playable, "compile_preview", compile_stub)


def test_real_html5_compiler_proof_is_embedded_in_deterministic_zip(monkeypatch):
    docs = source()
    catalog(monkeypatch, docs)
    manifest, bundle = playable.compile_quest_readiness_playable(
        docs, ready(docs), authorized=True)
    assert manifest["canonical_quest_replay_verified"] is True
    assert manifest["canonical_html5_gameplay_replay_verified"] is True
    assert manifest["native_gameplay_verified"] is False
    assert manifest["release_certified"] is False
    assert sha256(bundle).hexdigest() == manifest["bundle_sha256"]
    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        assert sorted(archive.namelist()) == sorted(playable._MEMBERS)
        assert archive.read("index.html").startswith(b"<!doctype html")
        assert json.loads(archive.read("quest_readiness.json"))[
            "playable_handoff_allowed"] is True
        assert json.loads(archive.read("quest_readiness_handoff.json"))[
            "canonical_quest_replay_verified"] is True
        for name, digest in manifest["file_hashes"].items():
            assert sha256(archive.read(name)).hexdigest() == digest
    assert (manifest, bundle) == playable.compile_quest_readiness_playable(
        docs, ready(docs), authorized=True)


def test_unready_quest_blocks_real_game_even_with_valid_catalog(monkeypatch):
    docs = source()
    docs["quest"]["stage_graph"][0]["alternatives"].append("stop")
    catalog(monkeypatch, docs)
    report = ready(docs)
    assert report["playable_handoff_allowed"] is False
    with pytest.raises(StudioQuestError, match="unproved quest readiness"):
        playable.compile_quest_readiness_playable(docs, report, authorized=True)


def test_catalog_source_substitution_and_forged_html_proof_rejected(monkeypatch):
    docs = source()
    catalog(monkeypatch, docs)
    report = ready(docs)
    changed = copy.deepcopy(docs)
    changed["quest"]["stage_graph"][0]["reward"] = "forged"
    monkeypatch.setattr(playable, "read_blueprint", lambda _: changed)
    with pytest.raises(StudioQuestError, match="catalog differs"):
        playable.compile_quest_readiness_playable(docs, report, authorized=True)
    catalog(monkeypatch, docs)
    monkeypatch.setattr(playable, "compile_preview", lambda *_args, **_kwargs:
                        SimpleNamespace(
                            playable=SimpleNamespace(html="<html>evil</html>"),
                            receipt=lambda: {
                                "project_id": "original",
                                "validated_gameplay_proof": True,
                                "html_sha256": "0" * 64,
                            }))
    with pytest.raises(StudioQuestError, match="playable proof mismatch"):
        playable.compile_quest_readiness_playable(docs, report, authorized=True)
    with pytest.raises(PermissionError):
        playable.compile_quest_readiness_playable(docs, report, authorized=False)


def test_private_publication_restore_and_forgery_rejection(monkeypatch, tmp_path):
    docs = source()
    catalog(monkeypatch, docs)
    report = ready(docs)
    manifest, bundle = playable.compile_quest_readiness_playable(
        docs, report, authorized=True)
    result = playable.publish_quest_readiness_playable(
        docs, report, manifest, bundle, tmp_path, authorized=True)
    assert result["file_write_performed"] is True
    assert (tmp_path / playable.FILENAME).stat().st_mode & 0o077 == 0
    assert playable.verify_quest_readiness_playable(
        docs, report, tmp_path, authorized=True) == manifest
    with pytest.raises(FileExistsError):
        playable.publish_quest_readiness_playable(
            docs, report, manifest, bundle, tmp_path, authorized=True)
    forged = dict(manifest)
    forged["native_gameplay_verified"] = True
    with pytest.raises(StudioQuestError):
        playable.publish_quest_readiness_playable(
            docs, report, forged, bundle, tmp_path, authorized=True)
    (tmp_path / playable.FILENAME).write_bytes(bundle[:-1])
    with pytest.raises(StudioQuestError):
        playable.verify_quest_readiness_playable(
            docs, report, tmp_path, authorized=True)


def test_restore_rejects_symlink_hardlink_and_world_readable(monkeypatch, tmp_path):
    docs = source()
    catalog(monkeypatch, docs)
    report = ready(docs)
    _, bundle = playable.compile_quest_readiness_playable(
        docs, report, authorized=True)
    path = tmp_path / playable.FILENAME
    path.write_bytes(bundle)
    path.chmod(0o600)
    if os.name != "posix":
        pytest.skip("POSIX custody checks")
    path.chmod(0o644)
    with pytest.raises(StudioQuestError):
        playable.verify_quest_readiness_playable(
            docs, report, tmp_path, authorized=True)
    path.chmod(0o600)
    link = tmp_path / "hardlink"
    os.link(path, link)
    with pytest.raises(StudioQuestError):
        playable.verify_quest_readiness_playable(
            docs, report, tmp_path, authorized=True)
    link.unlink()
    path.unlink()
    path.symlink_to(tmp_path / "missing")
    with pytest.raises(OSError):
        playable.verify_quest_readiness_playable(
            docs, report, tmp_path, authorized=True)


def test_cli_source_to_private_bundle_and_verify(monkeypatch, tmp_path, capsys):
    from scripts import studio_quest_readiness_playable_cli as cli
    docs = source()
    catalog(monkeypatch, docs)
    monkeypatch.setattr(cli, "read_blueprint", lambda _: docs)
    lease = compile_quest_program(docs).source_digest
    session = start_quest(docs, authorized=True).digest
    args = ["--project", "original", "--expected-source", lease,
            "--expected-session", session, "--prompt"]
    assert cli.main(args + ["--publish", str(tmp_path)]) == 0
    response = json.loads(capsys.readouterr().out)
    assert response["file_write_performed"] is True
    assert response["manifest"]["canonical_html5_gameplay_replay_verified"] is True
    assert cli.main(args + ["--verify", str(tmp_path)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["verified_existing_bundle"] is True
    assert result["file_write_performed"] is False
