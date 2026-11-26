"""Recovery diagnostics must not silently repair, approve, or overwrite custody."""
from __future__ import annotations

import json

import pytest

from skeleton.jeeves.worlds.world_canon import CanonError, canonical
from skeleton.testing.test_jeeves_world_laptop_flow import ready


def _snapshot(root):
    return {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}


@pytest.mark.parametrize("artifact,code", [
    ("builder_file", "laptop_builder_mismatch"),
    ("html_file", "laptop_html_mismatch"),
])
def test_diagnostic_reports_corrupt_handoff_without_repair(tmp_path, artifact, code):
    flow, _, _, receipt = ready(tmp_path)
    player = flow.create_session("lighthouse", "player")
    original = _snapshot(tmp_path)
    damaged = tmp_path / receipt[artifact]
    damaged.write_bytes(damaged.read_bytes() + b"\nCORRUPT")
    before = _snapshot(tmp_path)
    result = flow.diagnose("lighthouse", "player")
    assert result["checks"]["source"]["ok"] is True
    assert result["checks"]["review"]["ok"] is True
    assert result["checks"]["builder"] == {"ok": False, "error": code}
    assert result["next_action"] == "compile_and_verify_reviewed_source"
    assert _snapshot(tmp_path) == before
    assert (tmp_path / "lighthouse.player.session.json").read_bytes() == original[
        "lighthouse.player.session.json"]
    assert player["session_digest"]
    assert not (tmp_path / "lighthouse.lock").exists()


def test_diagnostic_does_not_approve_stale_review(tmp_path):
    flow, _, _, _ = ready(tmp_path)
    review_file = tmp_path / "lighthouse.laptop.review.json"
    review = json.loads(review_file.read_bytes())
    review["source_digest"] = "0" * 64
    review_file.write_bytes(canonical(review))
    before = _snapshot(tmp_path)
    result = flow.diagnose("lighthouse")
    assert result["checks"]["review"]["ok"] is False
    assert result["next_action"] == "review_and_approve_canonical_source"
    assert _snapshot(tmp_path) == before
    assert not (tmp_path / "lighthouse.lock").exists()


def test_diagnostic_respects_foreign_world_lock_without_unlink(tmp_path):
    flow, _, _, _ = ready(tmp_path)
    lock = tmp_path / "lighthouse.lock"
    lock.write_text("foreign writer", encoding="utf-8")
    before = _snapshot(tmp_path)
    result = flow.diagnose("lighthouse")
    assert result["checks"]["source"] == {"ok": False, "error": "lease_busy"}
    assert result["next_action"] == "retry_after_current_writer_finishes"
    assert _snapshot(tmp_path) == before
    assert lock.read_text(encoding="utf-8") == "foreign writer"


def test_diagnostic_acceptance_is_read_only_for_replayed_save(tmp_path):
    flow, _, _, _ = ready(tmp_path)
    first = flow.create_session("lighthouse", "player")
    flow.choose("lighthouse", "player", "rescue", first["session_digest"])
    before = _snapshot(tmp_path)
    result = flow.diagnose("lighthouse", "player")
    assert result["checks"]["builder"]["ok"] is True
    assert result["checks"]["session"]["ok"] is True
    assert result["checks"]["acceptance"]["ok"] is True
    assert result["checks"]["acceptance"]["portable_roundtrip_verified"] is True
    assert _snapshot(tmp_path) == before
    assert not (tmp_path / "lighthouse.lock").exists()
