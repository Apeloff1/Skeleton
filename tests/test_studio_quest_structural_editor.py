"""Offline editor CSP, strict export import, private persistence and CLI."""
from __future__ import annotations

from base64 import b64encode
from hashlib import sha256
import json

import pytest

from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import _digest
from skeleton.ai.game_builder.studio_prompt_quest_plan import (
    PLAN_SCHEMA, compile_prompt_quest_plan, publish_prompt_quest_plan,
    restore_prompt_quest_plan,
)
from skeleton.ai.game_builder.studio_quest_structural_editor import (
    EXPORT_SCHEMA, FILENAME, render_quest_structural_editor,
    publish_quest_structural_editor, import_quest_structural_editor_export,
)


def baseline():
    plan = {
        "schema": PLAN_SCHEMA, "project_id": "lighthouse-archive",
        "prompt": "Original lantern archive mystery.",
        "originality_attested": True,
        "stages": [
            {"id": "beacon", "prerequisites": [], "alternatives": ["light"],
             "reward": "lit", "choice_effects": {}},
        ],
        "endings": [{"id": "safe", "requires": ["lit"]}],
    }
    return compile_prompt_quest_plan(
        plan, authorized=True, expected_plan_digest=_digest(plan))


def export(source, edits=None):
    return {
        "schema": EXPORT_SCHEMA, "project_id": source["project_id"],
        "baseline_digest": source["receipt_digest"],
        "edits": edits if edits is not None else [
            {"op": "replace_prompt", "id": "prompt",
             "value": "An original lantern archive mystery, revised."}],
    }


def test_csp_hashed_html_and_private_editor_publication(tmp_path):
    source = baseline()
    kw = {"authorized": True,
          "expected_baseline_digest": source["receipt_digest"]}
    html, proof = render_quest_structural_editor(source, **kw)
    assert b"script-src 'sha256-" in html
    assert b"connect-src 'none'" in html
    assert b"unsafe-inline" not in html
    assert b"Export typed edits" in html
    assert proof["html_sha256"] == sha256(html).hexdigest()
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    published = publish_quest_structural_editor(source, private, **kw)
    assert published["file_write_performed"]
    assert (private / FILENAME).read_bytes() == html
    with pytest.raises(FileExistsError):
        publish_quest_structural_editor(source, private, **kw)


def test_export_import_recompiles_actual_quest_and_rejects_forgery(tmp_path):
    source = baseline()
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    target = private / "quest_structural_edit.json"
    target.write_text(json.dumps(export(source)), encoding="utf-8")
    target.chmod(0o600)
    kw = {"authorized": True,
          "expected_baseline_digest": source["receipt_digest"]}
    result = import_quest_structural_editor_export(source, target, **kw)
    assert result["candidate_compilation"]["plan"]["prompt"].endswith("revised.")
    assert not result["source_changed"]  # prose-only change does not alter quest graph
    forged = export(source)
    forged["baseline_digest"] = "0" * 64
    target.write_text(json.dumps(forged), encoding="utf-8")
    with pytest.raises(StudioQuestError, match="stale or forged"):
        import_quest_structural_editor_export(source, target, **kw)
    target.write_text('{"schema":1,"schema":2}', encoding="utf-8")
    with pytest.raises(StudioQuestError, match="duplicate"):
        import_quest_structural_editor_export(source, target, **kw)
    target.unlink()
    target.symlink_to(private / "missing")
    with pytest.raises(OSError):
        import_quest_structural_editor_export(source, target, **kw)


def test_operator_cli_import_and_private_candidate(tmp_path, capsys):
    from scripts.studio_quest_structural_editor_cli import main
    source = baseline()
    old, exported, new = (
        tmp_path / "old", tmp_path / "export", tmp_path / "new")
    for folder in (old, exported, new):
        folder.mkdir(mode=0o700)
    publish_prompt_quest_plan(source, old, authorized=True)
    path = exported / "quest_structural_edit.json"
    path.write_text(json.dumps(export(source)), encoding="utf-8")
    path.chmod(0o600)
    assert main([
        "--baseline-dir", str(old), "--expected-baseline",
        source["receipt_digest"], "--import-export", str(path),
        "--publish-candidate", str(new),
    ]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["file_write_performed"]
    assert restore_prompt_quest_plan(new, authorized=True) == (
        result["edit_proof"]["candidate_compilation"])
    assert main([
        "--baseline-dir", str(old), "--expected-baseline",
        source["receipt_digest"], "--render-html",
    ]) == 0
    assert "Export typed edits" in capsys.readouterr().out
