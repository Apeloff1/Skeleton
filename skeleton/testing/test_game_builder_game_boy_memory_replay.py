"""Regression for original-game generated hardware RAM replay against independent CPU state."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json

import pytest

from skeleton.ai.game_builder.game_boy_memory_replay import (
    GameBoyReplayError, plan_game_boy_memory_replay, export_game_boy_memory_replay,
)
from skeleton.ai.game_builder.playable_world import GameBuildIntent, generate_playable_world
from scripts.game_builder.emulate_game_boy_ci import (
    EmulatorAcceptanceError, drive_emulator, read_wram_symbols, validate_route,
)


def _original():
    world = generate_playable_world(GameBuildIntent(
        project_id="original-moon-light", title="Original Moonlight",
        subtitle="Homebrew native CPU replay", seed=71368,
        width=17, height=15, levels=3, collectibles_per_level=3,
        hazards_per_level=4, starting_health=4, theme="space",
    ), authorized=True)
    return world


def _symbols():
    names = ("Level", "PlayerX", "PlayerY", "Health", "Score", "GemsRemaining", "GameWon", "GameLost")
    lines = [f"00:{0xC000+n:04X} {name}" for n, name in enumerate(names)]
    return read_wram_symbols("\n".join(lines)), lines


def test_actual_ram_oracle_models_all_safe_moves_and_level_transitions():
    world = _original()
    plan = plan_game_boy_memory_replay(world)
    assert plan == plan_game_boy_memory_replay(world)
    assert plan["world_digest"] == world.digest
    assert plan["levels"] == len(world.levels)
    assert plan["initial"]["x"] == world.levels[0].start[0]
    assert plan["initial"]["y"] == world.levels[0].start[1]
    assert len(plan["steps"]) == sum(len(level.safe_solution) for level in world.levels)
    assert [row["button"] for row in plan["steps"]] == [
        step for level in world.levels for step in level.safe_solution
    ]
    assert plan["steps"][-1]["won"] == 1
    assert plan["steps"][-1]["lost"] == 0
    assert plan["steps"][-1]["score"] == 9
    assert all(row["health"] == 4 and row["lost"] == 0 for row in plan["steps"])
    assert sorted(set(row["level"] for row in plan["steps"])) == [0, 1, 2]
    assert sum(plan["steps"][i]["score"] < plan["steps"][i+1]["score"]
               for i in range(len(plan["steps"])-1)) == 9
    assert validate_route(plan) == plan


def test_ram_oracle_exports_without_overwriting_or_falsely_certifying(tmp_path):
    world = _original()
    target = tmp_path / "original-game-replay.json"
    exported = export_game_boy_memory_replay(world, target)
    data = json.loads(exported.read_text(encoding="utf-8"))
    assert data["world_digest"] == world.digest
    assert data["hardware_verified"] is False
    assert data["emulator_executed"] is False
    assert data["binary_compiled"] is False
    assert data["release_approved"] is False
    with pytest.raises(FileExistsError):
        export_game_boy_memory_replay(world, target)


def test_reference_ram_route_fails_closed_when_tampered_even_if_last_status_claims_win():
    original = plan_game_boy_memory_replay(_original())
    for mutate in (
        lambda d: d["steps"][0].update(x=200),
        lambda d: d["steps"][1].update(button="force-won"),
        lambda d: d["steps"][-1].update(won=0),
        lambda d: d.update(binary_compiled=True),
        lambda d: d.update(world_digest="x"*64),
        lambda d: d.update(emulator_executed=True),
    ):
        broken = deepcopy(original)
        mutate(broken)
        with pytest.raises(EmulatorAcceptanceError):
            validate_route(broken)


def test_native_wram_symbols_are_addressed_on_real_cartridge_cpu_not_host_ram():
    symbols, sample = _symbols()
    assert symbols["GameWon"] == 0xC006
    assert symbols["GameLost"] == 0xC007
    for broken in (
        sample[:-1],
        [*sample, sample[0]],
        [sample[0].replace("C000", "4000"), *sample[1:]],
        [sample[0].replace("C000", "DFFF"), *sample[1:-1], sample[-1].replace("C007", "DFFF")],
        [sample[0].replace("00:C000", "01:C000"), *sample[1:]],
    ):
        with pytest.raises(EmulatorAcceptanceError):
            read_wram_symbols("\n".join(broken))


class _FakeCPU:
    """In-memory *unit test double* only; real ROM is checked by GitHub's PyBoy job."""

    def __init__(self, states, symbol_addresses):
        self.states = states
        self.symbol_addresses = symbol_addresses
        self.index = 0
        self.tick_count = 0
        self.pressed = None
        self.actions = []

    def set_emulation_speed(self, speed):
        assert speed == 0

    def tick(self, count, render=False, sound=False):
        assert not render and not sound
        self.tick_count += count
        if count == 9:
            self.index += 1
        if self.index >= len(self.states):
            raise AssertionError("unexpected extra hardware input")

    def button_press(self, button):
        self.pressed = button
        self.actions.append(button)

    def button_release(self, button):
        assert button == self.pressed
        self.pressed = None

    @property
    def memory(self):
        state = self.states[self.index]
        return {
            self.symbol_addresses[label]: state[field]
            for field, label in {
                "level": "Level", "x": "PlayerX", "y": "PlayerY",
                "health": "Health", "score": "Score",
                "gems_remaining": "GemsRemaining",
                "won": "GameWon", "lost": "GameLost",
            }.items()
        }


def test_hardware_driver_does_not_force_states_and_rejects_a_stale_native_engine():
    plan = plan_game_boy_memory_replay(_original())
    symbols, _ = _symbols()
    cpu = _FakeCPU([plan["initial"], *plan["steps"]], symbols)
    result = drive_emulator(cpu, symbols, plan)
    assert result["emulator_gameplay_passed"] is True
    assert cpu.actions == [row["button"] for row in plan["steps"]]
    assert result["final_ram"]["won"] == 1
    assert result["final_ram"]["lost"] == 0
    assert cpu.tick_count == 120 + 11 * len(plan["steps"])
    stale = deepcopy(plan["steps"])
    stale[5] = {**stale[5], "score": stale[5]["score"] + 1}
    cpu = _FakeCPU([plan["initial"], *stale], symbols)
    with pytest.raises(EmulatorAcceptanceError, match="diverged"):
        drive_emulator(cpu, symbols, plan)
