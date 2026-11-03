"""Source-bound laptop acceptance: real ending witnesses and portable save roundtrips."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from skeleton.jeeves.worlds.laptop_cli import run
from skeleton.jeeves.worlds.laptop_flow import LaptopFlow
from skeleton.jeeves.worlds.world_canon import CanonError, digest

EXAMPLES = Path(__file__).resolve().parents[2] / "examples" / "jeeves"


def ready(tmp_path):
    flow = LaptopFlow(tmp_path)
    brief = json.loads((EXAMPLES / "lighthouse_brief.json").read_text())
    operation = json.loads((EXAMPLES / "lighthouse_review.json").read_text())
    proposal = flow.propose(brief)
    reviewed = flow.review(
        "lighthouse", proposal["source_digest"], operation,
        "Reviewed the original lighthouse rescue and consequences.")
    flow.compile("lighthouse", reviewed["source_digest"])
    return flow


def test_acceptance_replays_every_ending_and_roundtrips_without_writes(tmp_path):
    flow = ready(tmp_path)
    before = sorted(p.name for p in tmp_path.iterdir())
    result = flow.acceptance("lighthouse")
    assert result["schema"] == "jeeves.world.laptop_acceptance.v1"
    assert result["verified_save_restore"] is True
    assert result["existing_session"] is None
    assert result["source_digest"] == digest(flow.worlds.read("lighthouse"))
    assert any(item["ending_scene"] == "resolution" for item in result["ending_witnesses"])
    assert all(item["session_digest"] for item in result["ending_witnesses"])
    assert "not_engine_or_device_certified" in result["qualification"]
    assert sorted(p.name for p in tmp_path.iterdir()) == before


def test_acceptance_checks_existing_persisted_session_and_cli(tmp_path, capsys):
    flow = ready(tmp_path)
    created = flow.create_session("lighthouse", "player")
    chosen = flow.choose("lighthouse", "player", "rescue", created["session_digest"])
    before = sorted(p.name for p in tmp_path.iterdir())
    result = flow.acceptance("lighthouse", "player")
    assert result["existing_session"]["session_digest"] == chosen["session_digest"]
    assert result["existing_session"]["revision"] == 1
    assert result["existing_session"]["restorable"] is True
    assert run(["--store", str(tmp_path), "acceptance", "--world-id",
                "lighthouse", "--slot", "player"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["ok"] is True
    assert printed["result"] == result
    assert sorted(p.name for p in tmp_path.iterdir()) == before


def test_acceptance_fails_closed_for_tampered_playable(tmp_path):
    flow = ready(tmp_path)
    artifact = tmp_path / "lighthouse.laptop.playable.html"
    artifact.write_text("tampered", encoding="utf-8")
    with pytest.raises(CanonError) as error:
        flow.acceptance("lighthouse")
    assert error.value.code == "laptop_html_mismatch"


def test_acceptance_rejects_unreviewed_source_and_missing_slot(tmp_path):
    flow = ready(tmp_path)
    with pytest.raises(CanonError) as missing:
        flow.acceptance("lighthouse", "absent")
    assert missing.value.code == "not_found"
    source = flow.worlds.read("lighthouse")
    altered = dict(source, prompt=source["prompt"] + " altered")
    flow.worlds.publish(altered, expected_digest=digest(source))
    with pytest.raises(CanonError) as stale:
        flow.acceptance("lighthouse")
    assert stale.value.code == "review_stale_source"
