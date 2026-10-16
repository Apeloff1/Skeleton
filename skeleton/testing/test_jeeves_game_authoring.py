"""Tests for Jeeves model-backed game design proposals; never call external AI."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from skeleton.developer.game_cli import run_game_cli
from skeleton.developer import jeeves_game_authoring as authoring


def workspace(tmp_path: Path) -> Path:
    result = run_game_cli(["init", "storygame", "--dir", str(tmp_path),
                           "--vision", "A wholly original branching RPG"])
    assert result["ok"], result
    return tmp_path / "storygame"


def model_response(*, kind: str = "quest", slug: str = "lost-map") -> str:
    return json.dumps({
        "kind": kind, "slug": slug, "title": "The Lost Map",
        "summary": "Discover how the cartographer disappeared.",
        "body": "The player discovers three clues. Choosing one changes the ending.",
        "rationale": "Offers a reversible choice and a distinct noncombat path.",
    })


def fake_model(monkeypatch, text: str | None = None):
    observed = []
    async def infer(prompt):
        observed.append(json.loads(prompt))
        return model_response() if text is None else text, {
            "provider": "fake-qualified-provider", "model": "test-fixture",
            "request_id": "fixture-1",
        }
    monkeypatch.setattr(authoring, "_infer", infer)
    return observed


def test_model_propose_review_apply_is_explicit_and_bound_to_digest(tmp_path, monkeypatch):
    root = workspace(tmp_path)
    observed = fake_model(monkeypatch)
    proposed = run_game_cli(["jeeves", "propose", "--project", str(root),
                             "--kind", "quest", "--brief", "An original branching quest"])
    assert proposed["ok"], proposed
    assert proposed["model_inference"] is True
    digest = proposed["proposal_sha256"]
    target = root / "design" / "quest" / "lost-map.md"
    assert not target.exists()
    assert observed[0]["requested_kind"] == "quest"
    assert observed[0]["untrusted_design_notes"] == []
    reviewed = run_game_cli(["jeeves", "review", "--project", str(root), "--digest", digest])
    assert reviewed["ok"] and reviewed["would_create"] and not reviewed["applied"]
    missing = run_game_cli(["jeeves", "apply", "--project", str(root), "--digest", digest])
    assert missing["ok"] is False
    invalid = run_game_cli(["jeeves", "apply", "--project", str(root),
                            "--digest", digest, "--approve", "0" * 64])
    assert invalid["ok"] is False
    assert not target.exists()
    applied = run_game_cli(["jeeves", "apply", "--project", str(root),
                            "--digest", digest, "--approve", digest])
    assert applied["ok"] and applied["applied"] is True
    assert digest in target.read_text(encoding="utf-8")
    assert run_game_cli(["jeeves", "apply", "--project", str(root),
                         "--digest", digest, "--approve", digest])["ok"] is False


@pytest.mark.parametrize("bad", [
    "", "not-json", "<fenced markdown>",
    '{"kind":"quest","kind":"quest"}',
    '{"kind":"quest","slug":"../escape","title":"x","summary":"y","body":"z","rationale":"ok"}',
    json.dumps({"kind": "quest", "slug": "unsafe", "title": "x", "summary": "y",
                "body": "z", "rationale": "ok", "command": "danger"}),
    model_response(kind="world"),
])
def test_invalid_proposal_fails_before_any_proposal_file(tmp_path, monkeypatch, bad):
    root = workspace(tmp_path)
    fake_model(monkeypatch, bad)
    result = run_game_cli(["jeeves", "propose", "--project", str(root),
                           "--kind", "quest", "--brief", "original"])
    assert result["ok"] is False
    assert not (root / ".jeeves").exists()


def test_model_proposal_tampering_is_detected(tmp_path, monkeypatch):
    root = workspace(tmp_path)
    fake_model(monkeypatch)
    proposed = run_game_cli(["jeeves", "propose", "--project", str(root),
                             "--kind", "quest", "--brief", "original"])
    digest = proposed["proposal_sha256"]
    path = root / ".jeeves" / "proposals" / (digest + ".json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["draft"]["body"] = "tampered"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert not run_game_cli(["jeeves", "review", "--project", str(root), "--digest", digest])["ok"]
    assert not run_game_cli(["jeeves", "apply", "--project", str(root),
                             "--digest", digest, "--approve", digest])["ok"]


def test_config_change_invalidates_pending_proposal(tmp_path, monkeypatch):
    root = workspace(tmp_path)
    fake_model(monkeypatch)
    proposed = run_game_cli(["jeeves", "propose", "--project", str(root),
                             "--kind", "quest", "--brief", "original"])
    manifest = root / "skeleton.game.json"
    cfg = json.loads(manifest.read_text(encoding="utf-8"))
    cfg["vision"] = "Different game now"
    manifest.write_text(json.dumps(cfg), encoding="utf-8")
    checked = run_game_cli(["jeeves", "review", "--project", str(root),
                            "--digest", proposed["proposal_sha256"]])
    assert checked["ok"] is False
    assert "configuration changed" in checked["error"]


def test_opted_in_notes_are_hashed_and_revalidated(tmp_path, monkeypatch):
    root = workspace(tmp_path)
    notes = root / "design" / "canon.md"
    notes.write_text("The kingdom has no hereditary monarchy.", encoding="utf-8")
    captured = fake_model(monkeypatch)
    proposed = run_game_cli(["jeeves", "propose", "--project", str(root), "--kind", "quest",
                             "--brief", "political intrigue", "--include-notes"])
    assert proposed["ok"]
    assert captured[0]["untrusted_design_notes"][0]["path"] == "design/canon.md"
    notes.write_text("The world is now a republic.", encoding="utf-8")
    result = run_game_cli(["jeeves", "review", "--project", str(root),
                           "--digest", proposed["proposal_sha256"]])
    assert not result["ok"] and "context changed" in result["error"]


def test_model_unavailable_does_not_fallback_to_fake_authoring(tmp_path, monkeypatch):
    root = workspace(tmp_path)
    async def unavailable(prompt):
        raise RuntimeError("no configured provider")
    monkeypatch.setattr(authoring, "_infer", unavailable)
    result = run_game_cli(["jeeves", "propose", "--project", str(root),
                           "--kind", "quest", "--brief", "original"])
    assert result["ok"] is False
    assert "unavailable" in result["error"]
    assert not (root / ".jeeves").exists()


def test_approved_draft_does_not_replace_existing_human_text(tmp_path, monkeypatch):
    root = workspace(tmp_path)
    fake_model(monkeypatch)
    current = root / "design" / "quest"
    current.mkdir(parents=True)
    original = current / "lost-map.md"
    original.write_text("Human-designed plot stays", encoding="utf-8")
    proposed = run_game_cli(["jeeves", "propose", "--project", str(root),
                             "--kind", "quest", "--brief", "original"])
    digest = proposed["proposal_sha256"]
    applied = run_game_cli(["jeeves", "apply", "--project", str(root),
                            "--digest", digest, "--approve", digest])
    assert applied["ok"] is False
    assert original.read_text(encoding="utf-8") == "Human-designed plot stays"


def test_no_model_inference_on_plan_or_audit(tmp_path, monkeypatch):
    root = workspace(tmp_path)
    async def unexpected(prompt):
        raise AssertionError("read-only planning should not call a provider")
    monkeypatch.setattr(authoring, "_infer", unexpected)
    assert run_game_cli(["jeeves", "plan", "--project", str(root)])["ok"]
    assert run_game_cli(["jeeves", "audit", "--project", str(root)])["action"] == "audit"
