"""Canonical FLGB dialogue: actual choices, quests, replay and offline CLI."""
from __future__ import annotations
from copy import deepcopy
import json
from pathlib import Path
import pytest

from skeleton.app.dialogue_cli import main as dialogue_cli
from skeleton.game.gameplay.dialogue_graph import (
    DialogueSessionError, choose, replay, validate_source, verify_save,
)

FIXTURE = Path(__file__).parent / "fixtures" / "dialogue_original_lantern_harbor.json"

@pytest.fixture
def source():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))

def test_original_conversation_reaches_quest_ending(source):
    start = replay(source, [])
    assert start["state"]["node_id"] == "greeting"
    assert start["state"]["phase"] == "active"
    first = choose(source, start, "listen")
    assert first["state"]["node_id"] == "warning"
    assert first["state"]["flags"] == ["heard-tide-warning"]
    finished = choose(source, first, "promise-repair")
    assert finished["terminal"] is True
    assert finished["state"]["node_id"] == "pact"
    assert finished["state"]["quests"] == ["restore-western-lens"]
    assert finished["state"]["reputation"] == 7
    assert finished == replay(source, ["listen", "promise-repair"])
    assert verify_save(source, json.loads(json.dumps(finished))) == finished
    assert len(finished["trace"]) == 2
    assert finished["event_digest"] != start["event_digest"]

def test_alternate_ending_has_distinct_replay_and_consequences(source):
    pact = replay(source, ["listen", "promise-repair"])
    leave = replay(source, ["depart"])
    assert leave["state"]["phase"] == "ended"
    assert leave["state"]["node_id"] == "departure"
    assert leave["state"]["quests"] == []
    assert leave["state"]["reputation"] == -2
    assert leave["state_digest"] != pact["state_digest"]
    assert leave["event_digest"] != pact["event_digest"]
    with pytest.raises(DialogueSessionError, match="terminal"):
        choose(source, leave, "listen")

def test_missing_choice_and_prerequisites_fail_closed(source):
    with pytest.raises(DialogueSessionError, match="not offered"):
        replay(source, ["promise-repair"])
    forged = deepcopy(source)
    forged["nodes"][1]["choices"][0]["requires"] = ["unreachable-flag"]
    with pytest.raises(DialogueSessionError, match="prerequisite"):
        replay(forged, ["listen", "promise-repair"])
    with pytest.raises(DialogueSessionError, match="already ended"):
        replay(source, ["depart", "listen"])

def test_source_and_save_tamper_rejected(source):
    saved = replay(source, ["listen"])
    modified = deepcopy(source)
    modified["nodes"][0]["text"] = "Forged keeper speech."
    with pytest.raises(DialogueSessionError, match="mismatch"):
        verify_save(modified, saved)
    forged = deepcopy(saved)
    forged["state"]["reputation"] = 99
    with pytest.raises(DialogueSessionError, match="mismatch"):
        verify_save(source, forged)
    forged = deepcopy(saved)
    forged["trace"][0]["quests"] = ["unearned-quest"]
    with pytest.raises(DialogueSessionError, match="mismatch"):
        verify_save(source, forged)
    assert verify_save(source, saved) == saved

def test_invalid_source_rejected(source):
    malformed = deepcopy(source)
    malformed["nodes"][0]["choices"][0]["target"] = "nonexistent"
    with pytest.raises(DialogueSessionError, match="edges"):
        validate_source(malformed)
    malformed = deepcopy(source)
    malformed["nodes"][2]["choices"] = [{"id": "bad", "target": "greeting",
        "requires": [], "grants": [], "reputation_delta": 0}]
    with pytest.raises(DialogueSessionError, match="terminal"):
        validate_source(malformed)
    malformed = deepcopy(source)
    malformed["nodes"][0]["choices"][0]["reputation_delta"] = True
    with pytest.raises(DialogueSessionError, match="delta"):
        validate_source(malformed)
    malformed = deepcopy(source)
    malformed["unknown_authority"] = "provider"
    with pytest.raises(DialogueSessionError, match="fields"):
        validate_source(malformed)
    malformed = deepcopy(source)
    malformed["nodes"][0]["choices"][0]["requires"] = [{"not": "a flag"}]
    with pytest.raises(DialogueSessionError, match="id"):
        validate_source(malformed)

def test_cli_play_verify_resume_and_exclusive_output(tmp_path, capsys, source):
    path = tmp_path / "source.json"
    path.write_text(json.dumps(source), encoding="utf-8")
    one = tmp_path / "one.json"
    two = tmp_path / "two.json"
    assert dialogue_cli(["--source", str(path), "--choice", "listen", "--output", str(one)]) == 0
    assert json.loads(capsys.readouterr().out)["state"]["node_id"] == "warning"
    assert one.stat().st_mode & 0o777 == 0o600
    assert dialogue_cli(["--source", str(path), "--save", str(one), "--verify"]) == 0
    capsys.readouterr()
    assert dialogue_cli(["--source", str(path), "--save", str(one),
                         "--choice", "promise-repair", "--output", str(two)]) == 0
    assert json.loads(capsys.readouterr().out)["state"]["quests"] == ["restore-western-lens"]
    assert dialogue_cli(["--source", str(path), "--choice", "listen", "--output", str(one)]) == 1

def test_cli_rejects_symlink_and_duplicate_json(tmp_path, source):
    path = tmp_path / "source.json"
    path.write_text(json.dumps(source), encoding="utf-8")
    link = tmp_path / "source-link.json"
    link.symlink_to(path)
    assert dialogue_cli(["--source", str(link)]) == 1
    path.write_text('{"schema":"x","schema":"y"}', encoding="utf-8")
    assert dialogue_cli(["--source", str(path)]) == 1

def test_128_step_guard_and_cycle_replay(source):
    cycle = deepcopy(source)
    cycle["nodes"][1]["choices"].append({"id": "repeat", "target": "greeting",
        "requires": [], "grants": [], "reputation_delta": 0})
    commands = ["listen", "repeat"] * 64
    reached = replay(cycle, commands)
    assert reached["state"]["phase"] == "step_limit"
    assert reached["state"]["step"] == 128
    with pytest.raises(DialogueSessionError, match="limit"):
        replay(cycle, commands + ["listen"])
