"""Canonical NPC schedule and offline replay acceptance tests."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from skeleton.game.gameplay.flgb_gameplay_runtime import GameplayContractError
from skeleton.game.gameplay.npc_schedule import NpcCommand, NpcSchedule, NpcSession, play
from scripts.npc_schedule_cli import main, read_json, save_new

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "skeleton/testing/fixtures/lantern_harbor_npc_schedule.json"
COMMANDS = ROOT / "skeleton/testing/fixtures/lantern_harbor_npc_commands.json"


def source():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def schedule():
    return NpcSchedule.parse(source())


def commands():
    return json.loads(COMMANDS.read_text(encoding="utf-8"))


def test_original_lantern_harbor_end_to_end():
    spec = schedule()
    session = play(spec, commands())
    assert session.tick == 12
    assert session.facts == ("beacon_lit", "harbor_arrival", "lens_repaired",
                             "lens_request", "tide_gate_open")
    assert len(session.events.events) == 6
    assert [e.event_type for e in session.events.events].count("npc.schedule.interact") == 4
    restored = NpcSession.restore(spec, session.snapshot())
    assert restored.state_digest == session.state_digest
    assert restored.snapshot() == session.snapshot()


def test_deterministic_source_and_command_order():
    a = play(schedule(), commands())
    b = play(NpcSchedule.parse(source()), commands())
    assert a.state_digest == b.state_digest
    assert a.events.digest == b.events.digest
    assert a.schedule.digest == b.schedule.digest


def test_interaction_cannot_be_farmed():
    spec = schedule()
    session = NpcSession.start(spec)
    session = session.apply(NpcCommand.parse(commands()[0]))
    with pytest.raises(GameplayContractError, match="consumed"):
        session.apply(NpcCommand.parse(commands()[0]))


def test_missing_prerequisite_is_fail_closed():
    with pytest.raises(GameplayContractError, match="prerequisites"):
        play(schedule(), [commands()[1]])


def test_interaction_not_at_location_is_rejected():
    command = commands()[0]
    command["interaction_id"] = "restore_beacon"
    with pytest.raises(GameplayContractError, match="unavailable"):
        play(schedule(), [command])


def test_time_rewind_and_same_tick_advance_rejected():
    spec = schedule()
    for command in ({"kind": "advance", "tick": 0},
                    {"kind": "advance", "tick": 25},
                    {"kind": "advance", "tick": True}):
        with pytest.raises(GameplayContractError):
            play(spec, [command])
    with pytest.raises(GameplayContractError):
        play(spec, [{"kind": "advance", "tick": 8},
                    {"kind": "advance", "tick": 7}])


def test_source_digest_binding_and_save_tamper():
    spec = schedule()
    snapshot = play(spec, commands()).snapshot()
    changed = source()
    changed["world_id"] = "other_world"
    with pytest.raises(GameplayContractError, match="source mismatch"):
        NpcSession.restore(NpcSchedule.parse(changed), snapshot)
    for key, replacement in (("state_digest", "0" * 64),
                             ("save_digest", "f" * 64)):
        corrupted = copy.deepcopy(snapshot)
        corrupted[key] = replacement
        with pytest.raises(GameplayContractError):
            NpcSession.restore(spec, corrupted)
    corrupted = copy.deepcopy(snapshot)
    corrupted["commands"][0]["interaction_id"] = "forged"
    with pytest.raises(GameplayContractError):
        NpcSession.restore(spec, corrupted)


def test_schema_is_strict_and_finite():
    base = source()
    for mutation in (
        lambda s: s.update(schema_version=True),
        lambda s: s.update(extra=1),
        lambda s: s.update(horizon_ticks=1_000_001),
        lambda s: s["routes"].append(copy.deepcopy(s["routes"][0])),
        lambda s: s["routes"][0]["stops"][1].update(start_tick=5),
        lambda s: s["routes"][0]["stops"][0].update(grants=["x", "x"]),
        lambda s: s["routes"][0]["stops"][0].update(interaction_id=" "),
    ):
        value = copy.deepcopy(base)
        mutation(value)
        with pytest.raises(GameplayContractError):
            NpcSchedule.parse(value)


def test_reject_unknown_commands_and_malformed_saves():
    spec = schedule()
    for bad in ({"kind": "interact", "tick": 0},
                {"kind": "advance", "tick": 1, "npc_id": "forged"},
                {"kind": "advance", "tick": -1},
                {"kind": "advance", "tick": 1.5}):
        with pytest.raises(GameplayContractError):
            play(spec, [bad])
    snapshot = play(spec, commands()).snapshot()
    snapshot["save"]["parent_save_digest"] = "broken"
    with pytest.raises(GameplayContractError):
        NpcSession.restore(spec, snapshot)


def test_cli_offline_replay_and_immutable_save(tmp_path, capsys):
    save_path = tmp_path / "npc-session.json"
    args = ["--schedule", str(FIXTURE), "--commands", str(COMMANDS),
            "--save", str(save_path)]
    assert main(args) == 0
    first = json.loads(capsys.readouterr().out)
    assert "tide_gate_open" in first["facts"]
    assert first["save_digest"] == read_json(str(save_path))["save_digest"]
    assert main(["--schedule", str(FIXTURE), "--resume", str(save_path)]) == 0
    assert json.loads(capsys.readouterr().out)["state_digest"] == first["state_digest"]
    assert main(args) == 2
    assert "File exists" in capsys.readouterr().err


def test_cli_rejects_symlinked_inputs_and_oversized_json(tmp_path):
    link = tmp_path / "schedule-link.json"
    link.symlink_to(FIXTURE)
    assert main(["--schedule", str(link)]) == 2
    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b" " * 2_000_001)
    assert main(["--schedule", str(oversized)]) == 2


def test_atomic_save_is_no_clobber(tmp_path):
    target = tmp_path / "immutable.json"
    save_new(str(target), b"{}")
    with pytest.raises(FileExistsError):
        save_new(str(target), b"forged")
    assert target.read_bytes() == b"{}"
    assert not list(tmp_path.glob(".npc-save-*"))


def test_resume_appends_without_mutating_prior_snapshot():
    spec = schedule()
    first = play(spec, commands()[:2])
    snapshot = first.snapshot()
    resumed = play(spec, commands()[2:], NpcSession.restore(spec, snapshot))
    assert resumed.state_digest == play(spec, commands()).state_digest
    assert snapshot == first.snapshot()


def test_direct_command_construction_cannot_bypass_authority():
    spec = schedule()
    for bad in (
        lambda: NpcCommand("interact", 0, "mira_keeper", "ask_for_lens", None),
        lambda: NpcCommand("advance", 1, npc_id="forged"),
        lambda: NpcCommand("advance", True),
        lambda: NpcCommand("unknown", 0),
    ):
        with pytest.raises(GameplayContractError):
            play(spec, [bad()])
