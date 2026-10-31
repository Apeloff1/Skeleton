"""Canonical quest-transaction integration and adversarial replay tests."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

import pytest

from skeleton.game.gameplay.quest_graph import (
    GameplayContractError, QuestEngine, QuestPlan, QuestReward,
    QuestSession, QuestSpec, QuestTrigger,
)


def digest(text: str) -> str:
    return sha256(text.encode()).hexdigest()


def make_plan() -> QuestPlan:
    return QuestPlan("harbor", [
        QuestSpec("arrival", (), "interact", "harbor_gate", digest("greet"), QuestReward("map", 1, 5)),
        QuestSpec("beacon", ("arrival",), "activate", "lighthouse", digest("light"), QuestReward("star", 2, 9), "safe_harbor"),
    ])


def events() -> list[QuestTrigger]:
    return [
        QuestTrigger(0, "arrival", "interact", "harbor_gate", digest("greet")),
        QuestTrigger(1, "beacon", "activate", "lighthouse", digest("light")),
    ]


def test_original_gameplay_quest_to_ending_and_save_replay() -> None:
    engine = QuestEngine(make_plan())
    session = engine.replay(events())
    assert session.completed == ("arrival", "beacon")
    assert session.inventory == (("map", 1), ("star", 2))
    assert session.currency == 14
    assert session.ending_id == "safe_harbor"
    assert engine.restore(json.loads(json.dumps(session.save_record()))) == session
    assert engine.replay(events()).state_digest == session.state_digest
    assert session.save_metadata.state_digest == session.state_digest


def test_order_independent_plan_identity() -> None:
    plan = make_plan()
    assert QuestPlan(plan.world_id, tuple(reversed(plan.quests))).digest == plan.digest
    assert plan.order == ("arrival", "beacon")


@pytest.mark.parametrize("triggers", [
    [events()[1]],
    [events()[0], events()[0]],
    [QuestTrigger(1, "arrival", "interact", "harbor_gate", digest("greet"))],
    [QuestTrigger(0, "arrival", "interact", "harbor_gate", digest("wrong"))],
    [QuestTrigger(0, "unknown", "interact", "harbor_gate", digest("greet"))],
])
def test_unearned_or_replayed_rewards_rejected(triggers: list[QuestTrigger]) -> None:
    with pytest.raises(GameplayContractError):
        QuestEngine(make_plan()).replay(triggers)


def test_forged_in_memory_session_cannot_claim_rewards() -> None:
    engine = QuestEngine(make_plan())
    forged = QuestSession(
        engine.plan.world_id, engine.plan.digest,
        completed=("arrival",), inventory=(("map", 999),), currency=999,
    )
    with pytest.raises(GameplayContractError, match="verified event history"):
        engine.apply(forged, events()[1])
    genuine = engine.apply(engine.new_session(), events()[0])
    assert genuine.completed == ("arrival",)
    assert engine.apply(genuine, events()[1]).ending_id == "safe_harbor"


def test_no_mutation_on_failed_event() -> None:
    engine = QuestEngine(make_plan())
    before = engine.new_session()
    with pytest.raises(GameplayContractError):
        engine.apply(before, events()[1])
    assert before == engine.new_session()


def test_source_tamper_and_save_tamper_fail_closed() -> None:
    plan = make_plan()
    engine = QuestEngine(plan)
    saved = engine.replay(events()).save_record()
    saved["state"]["currency"] = 9999
    with pytest.raises(GameplayContractError):
        engine.restore(saved)
    saved = engine.replay(events()).save_record()
    changed = QuestPlan("harbor", [
        QuestSpec("arrival", (), "interact", "harbor_gate", digest("greet"), QuestReward("map", 1, 6)),
        plan.by_id["beacon"],
    ])
    with pytest.raises(GameplayContractError):
        QuestEngine(changed).restore(saved)


def test_quest_control_character_injection_and_invalid_runtime_types() -> None:
    with pytest.raises(GameplayContractError, match="control character"):
        QuestSpec("line\\nbreak", (), "interact", "gate", digest("greet"))
    with pytest.raises(GameplayContractError, match="control character"):
        QuestPlan("world\\x00id", [QuestSpec("a", (), "interact", "gate", digest("greet"))])
    with pytest.raises(GameplayContractError, match="invalid reward"):
        QuestSpec("a", (), "interact", "gate", digest("greet"), reward={})
    with pytest.raises(GameplayContractError, match="invalid quest contract"):
        QuestPlan("world", [object()])


def test_invalid_plan_and_reward_contracts() -> None:
    plan = make_plan().as_record()
    plan["quests"][0]["dependencies"] = ["missing"]
    with pytest.raises(GameplayContractError):
        QuestPlan.from_record(plan)
    with pytest.raises(GameplayContractError):
        QuestReward("map", True, 0)
    with pytest.raises(GameplayContractError):
        QuestPlan("harbor", [QuestSpec("a", ("b",), "e", "s", digest("a")),
                            QuestSpec("b", ("a",), "e", "s", digest("b"))])


def test_cli_offline_run_verify_and_no_clobber(tmp_path: Path) -> None:
    plan_path = tmp_path / "plan.json"
    events_path = tmp_path / "events.json"
    save_path = tmp_path / "save.json"
    plan_path.write_text(json.dumps(make_plan().as_record()), encoding="utf-8")
    events_path.write_text(json.dumps([e.as_record() for e in events()]), encoding="utf-8")
    cmd = [sys.executable, "-m", "scripts.game.quest_journal"]
    inspect = subprocess.run(cmd + ["inspect", "--plan", str(plan_path)], capture_output=True, text=True)
    assert inspect.returncode == 0, inspect.stderr
    run = subprocess.run(cmd + ["run", "--plan", str(plan_path), "--events", str(events_path),
                                "--save", str(save_path)], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout)["state"]["ending_id"] == "safe_harbor"
    verify = subprocess.run(cmd + ["verify", "--plan", str(plan_path), "--save", str(save_path)],
                            capture_output=True, text=True)
    assert verify.returncode == 0, verify.stderr
    assert json.loads(verify.stdout)["save_digest"] == json.loads(run.stdout)["save_digest"]
    repeated = subprocess.run(cmd + ["run", "--plan", str(plan_path), "--events", str(events_path),
                                 "--save", str(save_path)], capture_output=True, text=True)
    assert repeated.returncode == 2
    assert json.loads(save_path.read_text())["state"]["currency"] == 14


def test_installed_skeleton_quest_command(tmp_path: Path) -> None:
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps(make_plan().as_record()), encoding="utf-8")
    result = subprocess.run([sys.executable, "-m", "skeleton", "quest", "inspect",
                             "--plan", str(plan)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["world_id"] == "harbor"


def test_original_fixture_cli_journey(tmp_path: Path) -> None:
    fixture_dir = Path(__file__).resolve().parents[2] / "docs" / "game" / "fixtures"
    plan = fixture_dir / "lantern_harbor_quests.json"
    events = fixture_dir / "lantern_harbor_events.json"
    save = tmp_path / "original-save.json"
    command = [sys.executable, "-m", "skeleton", "quest"]
    run = subprocess.run(command + ["run", "--plan", str(plan), "--events", str(events),
                                 "--save", str(save)], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout)["state"]["ending_id"] == "safe_harbor"
    verify = subprocess.run(command + ["verify", "--plan", str(plan), "--save", str(save)],
                            capture_output=True, text=True)
    assert verify.returncode == 0, verify.stderr
    assert json.loads(run.stdout)["save_digest"] == json.loads(verify.stdout)["save_digest"]


def test_interactive_choice_play_save_resume_and_replay(tmp_path: Path) -> None:
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps(make_plan().as_record()), encoding="utf-8")
    first_save = tmp_path / "first.json"
    second_save = tmp_path / "second.json"
    command = [sys.executable, "-m", "skeleton", "quest", "play", "--plan", str(plan)]
    first = subprocess.run(command + ["--save", str(first_save)], input="arrival\nquit\n",
                           capture_output=True, text=True)
    assert first.returncode == 0, first.stderr
    assert json.loads(first_save.read_text())["state"]["completed"] == ["arrival"]
    resumed = subprocess.run(command + ["--resume", str(first_save), "--save", str(second_save)],
                             input="beacon\n", capture_output=True, text=True)
    assert resumed.returncode == 0, resumed.stderr
    saved = json.loads(second_save.read_text())
    assert saved["state"]["ending_id"] == "safe_harbor"
    assert QuestEngine(make_plan()).restore(saved).completed == ("arrival", "beacon")


def test_cli_duplicate_json_and_tampered_save_rejected(tmp_path: Path) -> None:
    plan = tmp_path / "plan.json"
    plan.write_text('{"schema_version":1,"schema_version":1,"world_id":"w","quests":[]}')
    run = subprocess.run([sys.executable, "-m", "scripts.game.quest_journal", "inspect",
                          "--plan", str(plan)], capture_output=True, text=True)
    assert run.returncode == 2
    assert "duplicate" in run.stderr


def test_cli_rejects_symlink_plan(tmp_path: Path) -> None:
    import os
    if not hasattr(os, "O_NOFOLLOW"):
        pytest.skip("OS lacks O_NOFOLLOW; symlink rejection is not qualified")
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps(make_plan().as_record()))
    link = tmp_path / "link.json"
    link.symlink_to(plan)
    run = subprocess.run([sys.executable, "-m", "scripts.game.quest_journal", "inspect",
                          "--plan", str(link)], capture_output=True, text=True)
    assert run.returncode == 2
