"""Canonical offline crafting engine, finite economy and CLI acceptance."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from skeleton.game.gameplay.crafting_runtime import (
    CraftAction, CraftEngine, CraftPlan, CraftRecipe, CraftState, GameplayContractError,
)


def plan() -> CraftPlan:
    return CraftPlan(
        "lantern_harbor",
        (
            CraftRecipe("make_wick", (("fiber", 2),), (("wick", 1),), 1, (), ("wick_known",)),
            CraftRecipe("build_lantern", (("wick", 1), ("oil", 1)), (("lantern", 1),), 3,
                        ("wick_known",), ("light_available",)),
        ),
        (("fiber", 4), ("oil", 2)), 10,
    )


def actions() -> list[CraftAction]:
    return [CraftAction(0, "make_wick"), CraftAction(1, "build_lantern")]


def test_original_crafting_economy_and_deterministic_replay() -> None:
    engine = CraftEngine(plan())
    result = engine.replay(actions())
    assert result.inventory == (("fiber", 2), ("lantern", 1), ("oil", 1))
    assert result.currency == 6
    assert result.flags == ("light_available", "wick_known")
    assert engine.restore(json.loads(json.dumps(result.save_record()))) == result
    assert engine.replay(actions()).digest == result.digest


def test_craft_is_atomic_on_missing_ingredient_or_locked_recipe() -> None:
    engine = CraftEngine(plan())
    before = engine.start()
    with pytest.raises(GameplayContractError):
        engine.apply(before, CraftAction(0, "build_lantern"))
    assert before == engine.start()
    state = engine.apply(before, CraftAction(0, "make_wick"))
    with pytest.raises(GameplayContractError):
        engine.apply(state, CraftAction(1, "make_wick", 100))
    assert state.inventory == (("fiber", 2), ("oil", 2), ("wick", 1))


def test_forged_crafting_state_does_not_mint_inventory() -> None:
    engine = CraftEngine(plan())
    forged = CraftState(plan().world_id, plan().digest, (("fiber", 999),), 999, ())
    with pytest.raises(GameplayContractError, match="unverified"):
        engine.apply(forged, CraftAction(0, "make_wick"))


@pytest.mark.parametrize("event", [
    CraftAction(1, "make_wick"), CraftAction(0, "missing"),
    CraftAction(0, "build_lantern"),
])
def test_invalid_action_sequence_or_unlock(event: CraftAction) -> None:
    with pytest.raises(GameplayContractError):
        CraftEngine(plan()).replay([event])


def test_recipe_identity_and_input_bounds() -> None:
    with pytest.raises(GameplayContractError):
        CraftRecipe("bad\nid", (("fiber", 1),), (("wick", 1),))
    with pytest.raises(GameplayContractError):
        CraftRecipe("bad", (("fiber", True),), (("wick", 1),))
    with pytest.raises(GameplayContractError):
        CraftRecipe("bad", (("fiber", 1), ("fiber", 1)), (("wick", 1),))
    with pytest.raises(GameplayContractError):
        CraftPlan("world", [plan().recipes[0], plan().recipes[0]], [], 0)


def test_source_identity_and_tamper_rejected() -> None:
    engine = CraftEngine(plan())
    saved = engine.replay(actions()).save_record()
    saved["state"]["currency"] = 999
    with pytest.raises(GameplayContractError):
        engine.restore(saved)
    changed = CraftPlan("lantern_harbor", plan().recipes, plan().initial_inventory, 11)
    with pytest.raises(GameplayContractError):
        CraftEngine(changed).restore(engine.replay(actions()).save_record())


def test_installed_module_cli_run_verify_and_no_clobber(tmp_path: Path) -> None:
    p = tmp_path / "plan.json"
    events = tmp_path / "actions.json"
    save = tmp_path / "save.json"
    p.write_text(json.dumps(plan().record()))
    events.write_text(json.dumps([action.record() for action in actions()]))
    command = [sys.executable, "-m", "skeleton.game.gameplay.crafting_cli"]
    run = subprocess.run(command + ["run", "--plan", str(p), "--actions", str(events),
                                    "--save", str(save)], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout)["state"]["currency"] == 6
    verify = subprocess.run(command + ["verify", "--plan", str(p), "--save", str(save)],
                            capture_output=True, text=True)
    assert verify.returncode == 0, verify.stderr
    assert json.loads(verify.stdout)["state_digest"] == json.loads(run.stdout)["state_digest"]
    duplicate = subprocess.run(command + ["run", "--plan", str(p), "--actions", str(events),
                                          "--save", str(save)], capture_output=True, text=True)
    assert duplicate.returncode == 2


def test_crafting_installed_console_entrypoint() -> None:
    import tomllib
    metadata = tomllib.loads((Path(__file__).resolve().parents[2] / "pyproject.toml").read_text())
    assert metadata["project"]["scripts"]["skeleton-game-craft"] == (
        "skeleton.game.gameplay.crafting_cli:main"
    )


def test_interactive_play_and_resume(tmp_path: Path) -> None:
    p = tmp_path / "plan.json"
    p.write_text(json.dumps(plan().record()))
    a = tmp_path / "first.json"
    b = tmp_path / "second.json"
    command = [sys.executable, "-m", "skeleton.game.gameplay.crafting_cli",
               "play", "--plan", str(p)]
    first = subprocess.run(command + ["--save", str(a)], input="make_wick\nquit\n",
                           capture_output=True, text=True)
    assert first.returncode == 0, first.stderr
    second = subprocess.run(command + ["--resume", str(a), "--save", str(b)],
                            input="build_lantern\nquit\n", capture_output=True, text=True)
    assert second.returncode == 0, second.stderr
    assert json.loads(b.read_text())["state"]["inventory"] == [
        ["fiber", 2], ["lantern", 1], ["oil", 1],
    ]


def test_original_fixture_source_to_save_to_verify(tmp_path: Path) -> None:
    fixture = Path(__file__).resolve().parents[2] / "docs" / "game" / "fixtures"
    plan_file = fixture / "lantern_harbor_crafting.json"
    actions_file = fixture / "lantern_harbor_crafting_actions.json"
    save = tmp_path / "original-save.json"
    command = [sys.executable, "-m", "skeleton.game.gameplay.crafting_cli"]
    run = subprocess.run(command + ["run", "--plan", str(plan_file), "--actions",
                                    str(actions_file), "--save", str(save)],
                         capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout)["state"]["flags"] == ["light_available", "wick_known"]
    verified = subprocess.run(command + ["verify", "--plan", str(plan_file),
                                         "--save", str(save)], capture_output=True, text=True)
    assert verified.returncode == 0, verified.stderr


def test_identical_actions_produce_identical_portable_save_bytes(tmp_path: Path) -> None:
    p = tmp_path / "plan.json"
    a = tmp_path / "actions.json"
    p.write_text(json.dumps(plan().record()))
    a.write_text(json.dumps([action.record() for action in actions()]))
    command = [sys.executable, "-m", "skeleton.game.gameplay.crafting_cli",
               "run", "--plan", str(p), "--actions", str(a)]
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    assert subprocess.run(command + ["--save", str(first)], capture_output=True).returncode == 0
    assert subprocess.run(command + ["--save", str(second)], capture_output=True).returncode == 0
    assert first.read_bytes() == second.read_bytes()


def test_duplicate_keys_and_symlink_inputs_rejected(tmp_path: Path) -> None:
    import os
    p = tmp_path / "bad.json"
    p.write_text('{"schema_version":1,"schema_version":1}')
    command = [sys.executable, "-m", "skeleton.game.gameplay.crafting_cli",
               "inspect", "--plan"]
    result = subprocess.run(command + [str(p)], capture_output=True, text=True)
    assert result.returncode == 2
    assert "duplicate" in result.stderr
    if not hasattr(os, "O_NOFOLLOW"):
        pytest.skip("platform cannot qualify O_NOFOLLOW symlink rejection")
    real = tmp_path / "real.json"
    real.write_text(json.dumps(plan().record()))
    link = tmp_path / "link.json"
    link.symlink_to(real)
    assert subprocess.run(command + [str(link)], capture_output=True).returncode == 2


def test_batch_bounds_and_no_funds_cannot_mint() -> None:
    with pytest.raises(GameplayContractError):
        CraftAction(0, "make_wick", 101)
    low = CraftPlan("harbor", plan().recipes, plan().initial_inventory, 0)
    with pytest.raises(GameplayContractError):
        CraftEngine(low).replay([CraftAction(0, "make_wick")])
    assert CraftEngine(low).start().inventory == low.initial_inventory


def test_failed_no_clobber_preserves_existing_save(tmp_path: Path) -> None:
    p = tmp_path / "plan.json"
    a = tmp_path / "actions.json"
    save = tmp_path / "existing.json"
    p.write_text(json.dumps(plan().record()))
    a.write_text(json.dumps([action.record() for action in actions()]))
    save.write_text("do not overwrite")
    command = [sys.executable, "-m", "skeleton.game.gameplay.crafting_cli",
               "run", "--plan", str(p), "--actions", str(a), "--save", str(save)]
    assert subprocess.run(command, capture_output=True).returncode == 2
    assert save.read_text() == "do not overwrite"
