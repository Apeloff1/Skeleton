"""DOS replay reference and fail-closed 8086 RAM-symbol trust boundary."""
from __future__ import annotations

from copy import deepcopy
import json
from struct import pack

import pytest

from skeleton.ai.game_builder.dos_memory_replay import reference_dos_replay, export_dos_replay
from skeleton.ai.game_builder.playable_world import GameBuildIntent, generate_playable_world
from scripts.game_builder.emulate_dos_ci import (
    DOSExecutionError, parse_guest_offsets, validate_reference,
)


def _world():
    return generate_playable_world(GameBuildIntent(
        project_id="real-8086-source", title="Original Maze",
        subtitle="Native CPU gameplay", seed=1018806,
        width=19, height=17, levels=3, collectibles_per_level=3,
        hazards_per_level=4, starting_health=4, theme="arcade",
    ), authorized=True)


def test_dos_reference_derives_valid_original_full_victory_and_hud_quantities(tmp_path):
    world = _world()
    trace = reference_dos_replay(world)
    assert trace == reference_dos_replay(world)
    assert validate_reference(trace) == trace
    assert trace["world_digest"] == world.digest
    assert trace["levels"] == 3
    assert len(trace["steps"]) == sum(len(level.safe_solution) for level in world.levels)
    assert trace["steps"][-1]["score"] == 390
    assert trace["steps"][-1]["won"] == 1
    assert trace["steps"][-1]["lost"] == 0
    assert trace["steps"][-1]["gems_remaining"] == 0
    assert all(row["health"] == 4 for row in trace["steps"])
    assert all(row["level"] in (0,1,2) for row in trace["steps"])
    out = tmp_path / "real-machine-trace.json"
    assert export_dos_replay(world, out) == out
    assert json.loads(out.read_text(encoding="utf-8")) == trace
    with pytest.raises(FileExistsError):
        export_dos_replay(world, out)
    assert not trace["binary_compiled"] and not trace["cpu_emulator_executed"]


def test_dos_reference_fails_closed_if_attacker_rewrites_source_or_fakes_success():
    correct = reference_dos_replay(_world())
    changes = (
        lambda p: p["steps"][4].update(score=1000),
        lambda p: p["steps"][0].update(key="escape"),
        lambda p: p["steps"][-1].update(won=0),
        lambda p: p.update(world_digest="bad"),
        lambda p: p.update(cpu_emulator_executed=True),
        lambda p: p.update(binary_compiled=True),
        lambda p: p["initial"].update(gems_remaining=-1),
    )
    for mutate in changes:
        bad = deepcopy(correct)
        mutate(bad)
        with pytest.raises(DOSExecutionError):
            validate_reference(bad)


def _fake_header():
    # Only a deliberately manufactured parsing fixture, not a build receipt.
    header = b"\x0e\x1f\xfc\xb8\x03\x00\xcd\x10"
    return header + b"\x00" * 300


def test_native_8086_guest_symbols_are_distinct_bounded_and_self_locating():
    binary = _fake_header() + b"SKELDOSSTATE" + pack("<8H", *range(0x105, 0x10D))
    decoded = parse_guest_offsets(binary)
    assert decoded["level"] == 0x105
    assert decoded["score"] == 0x109
    for bad in (
        binary.replace(b"SKELDOSSTATE", b"WRONG-DOS-KEY"),
        binary + b"SKELDOSSTATE",
        _fake_header() + b"SKELDOSSTATE" + pack("<8H", *([0x110] * 8)),
        _fake_header() + b"SKELDOSSTATE" + pack("<8H", *([0xF000] * 8)),
        binary[:-1],
    ):
        with pytest.raises(DOSExecutionError):
            parse_guest_offsets(bad)
