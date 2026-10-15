"""Original authored DMG game goal demonstration with actual source-memory rewards.

The generated maze source defines its own score/completion RAM addresses.
This module proves the emitted ROM really updates those registers under real
emulated controller inputs, independently rewinds the action sequence and
trains a small offline Q-policy on source-measured progress. Other ROMs MUST
NOT inherit these addresses or game semantics; no production weights change.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
from collections import deque
from collections.abc import Mapping
from typing import Any

from .game_learning import (
    TRACE_SCHEMA, GameLearningConfig, GamePolicyLearner, _digest, _descriptor, _json,
)
from .game_learning_runtime import GameEnvironmentSpec
from .game_rom_generation import build_original_dmg_game
from .game_rom_runtime import FRAME_CYCLES, GameBoyROMEnvironment

SCHEMA = "skeleton.game.original_dmg_goal_q.v1"
DIRECTIONS = {
    "right": (1, 0), "left": (-1, 0), "up": (0, -1), "down": (0, 1),
}
WIDTH, HEIGHT, ROW_STRIDE = 19, 17, 32
EXPECTED_REGISTERS = {"player_x": 0xC000, "player_y": 0xC001, "score": 0xC002, "completed": 0xC004}


class OriginalGameGoalError(ValueError):
    pass


def _generated(seed: int) -> tuple[bytes, dict[str, Any]]:
    generated = build_original_dmg_game(seed=seed, title="Goal Training World")
    rom = base64.b64decode(generated["rom_base64"], validate=True)
    manifest = generated["manifest"]
    if (
        hashlib.sha256(rom).hexdigest() != generated["rom_digest"]
        or manifest["rom_digest"] != generated["rom_digest"]
        or manifest.get("memory_observations") != EXPECTED_REGISTERS
        or manifest.get("target") != "game_boy"
        or manifest.get("mapper") != "rom_only"
        or manifest.get("seed") != seed
    ):
        raise OriginalGameGoalError("original authored ROM identity, mapper or known RAM bindings changed")
    return rom, manifest


def _actual_game_registers(env: GameBoyROMEnvironment) -> dict[str, int]:
    machine = env.machine
    result = {name: int(machine.read(address)) for name, address in EXPECTED_REGISTERS.items()}
    if (
        not 0 <= result["player_x"] < WIDTH
        or not 0 <= result["player_y"] < HEIGHT
        or result["completed"] not in (0, 1)
    ):
        raise OriginalGameGoalError("native source memory produced invalid player or completion state")
    return result


def _actual_map(env: GameBoyROMEnvironment) -> list[list[int]]:
    grid = [
        [int(env.machine.read(0x9800 + y * ROW_STRIDE + x)) for x in range(WIDTH)]
        for y in range(HEIGHT)
    ]
    if (
        any(value not in (0, 2, 3) for row in grid for value in row)
        or grid[1][1] != 0
        or sum(value == 3 for row in grid for value in row) != 1
        or grid[15][17] != 3
    ):
        raise OriginalGameGoalError("CPU-executed game tilemap differs from the original authored maze contract")
    return grid


def _route(grid: list[list[int]], start: tuple[int, int]) -> list[tuple[str, tuple[int, int]]]:
    target = (17, 15)
    queue = deque([start])
    previous: dict[tuple[int, int], tuple[tuple[int, int], str] | None] = {start: None}
    while queue:
        x, y = queue.popleft()
        if (x, y) == target:
            break
        for action, (dx, dy) in DIRECTIONS.items():
            nxt = (x + dx, y + dy)
            nx, ny = nxt
            if (
                0 <= nx < WIDTH and 0 <= ny < HEIGHT
                and grid[ny][nx] != 2 and nxt not in previous
            ):
                previous[nxt] = ((x, y), action)
                queue.append(nxt)
    if target not in previous:
        raise OriginalGameGoalError("original game has no traversable source maze path")
    reversed_route = []
    current = target
    while current != start:
        witness = previous[current]
        if witness is None:
            raise OriginalGameGoalError("maze route parent pointer failed")
        parent, action = witness
        reversed_route.append((action, current))
        current = parent
    return list(reversed(reversed_route))


def _observation(env: GameBoyROMEnvironment) -> dict[str, float]:
    state = _actual_game_registers(env)
    return {
        "player_x": float(state["player_x"]),
        "player_y": float(state["player_y"]),
        "score": float(state["score"]),
        "goal_complete": float(state["completed"]),
        "step_fraction": float(env.steps / env.max_steps),
    }


def _step_receipt(env: GameBoyROMEnvironment, action: str,
                  previous: dict[str, int], sequence: int) -> tuple[dict[str, Any], dict[str, int]]:
    before = _observation(env)
    step = env.step(action)
    after = _observation(env)
    actual = _actual_game_registers(env)
    position_changed = (previous["player_x"], previous["player_y"]) != (
        actual["player_x"], actual["player_y"]
    )
    completed_now = actual["completed"] == 1 and previous["completed"] == 0
    if actual["score"] < previous["score"] or (completed_now and actual["score"] <= previous["score"]):
        raise OriginalGameGoalError("source ROM score/completion counters changed inconsistently")
    rewards = {
        "position_change": 0.02 if position_changed else 0.0,
        "goal_completion": 1.0 if completed_now else 0.0,
    }
    row = {
        "sequence": sequence,
        "observation": before,
        "action": action,
        "next_observation": after,
        "reward": math.fsum(rewards.values()),
        "reward_components": rewards,
        "terminated": completed_now,
        "truncated": False,
        "info": {
            "source": "executed_generated_original_cartridge_memory",
            "source_frame_sha256": hashlib.sha256(env.machine.framebuffer).hexdigest(),
            "source_register_sha256": _digest(actual),
            "source_instruction_evidence": dict(step.info),
            "source_position_change": position_changed,
        },
    }
    return row, actual


def _physical_actions(
    env: GameBoyROMEnvironment, route: list[tuple[str, tuple[int, int]]],
    *, max_frames_per_tile: int,
) -> tuple[list[str], list[dict[str, Any]], dict[str, int]]:
    actions = []
    rows = []
    state = _actual_game_registers(env)
    for action, expected in route:
        reached = False
        for _ in range(max_frames_per_tile):
            if env.steps >= env.max_steps:
                raise OriginalGameGoalError("actual native interpreter step budget exhausted")
            row, state = _step_receipt(env, action, state, len(rows) + 1)
            rows.append(row)
            actions.append(action)
            position = (state["player_x"], state["player_y"])
            if position == expected:
                reached = True
                break
            if position != route[0][1] and position != expected:
                # Intermediate position is valid only if equal to the origin
                # of this movement attempt, checked below.
                pass
        if not reached:
            raise OriginalGameGoalError("actual cartridge never committed the declared maze move")
    return actions, rows, state


def train_original_rom_goal_policy(
    *, seed: int = 42, max_steps: int = 1024,
    max_frames_per_tile: int = 12,
) -> dict[str, Any]:
    if (
        type(seed) is not int or not 0 <= seed <= 2**63 - 1
        or type(max_steps) is not int or not 64 <= max_steps <= 2048
        or type(max_frames_per_tile) is not int or not 4 <= max_frames_per_tile <= 20
    ):
        raise OriginalGameGoalError("source goal game instruction and memory budgets invalid")
    rom, manifest = _generated(seed)
    env = GameBoyROMEnvironment(rom, max_steps=max_steps, cycles_per_step=FRAME_CYCLES)
    env.reset(0)
    # Run the ORIGINAL machine, not the authoring maze, to initialize VRAM,
    # sprite registers and the true in-game player coordinates.
    env.step("idle")
    starting = _actual_game_registers(env)
    if starting != {"player_x": 1, "player_y": 1, "score": 0, "completed": 0}:
        raise OriginalGameGoalError("booted ROM game state differs from its authored starting state")
    grid = _actual_map(env)
    route = _route(grid, (1, 1))
    if len(route) > 160 or 1 + len(route) * max_frames_per_tile > max_steps:
        raise OriginalGameGoalError("generated maze route exceeds source-controlled maximum step budget")
    original_state = env.snapshot()
    actions = []
    rows = []
    state = starting
    for index, (direction, expected) in enumerate(route):
        origin = (state["player_x"], state["player_y"])
        succeeded = False
        for _ in range(max_frames_per_tile):
            row, state = _step_receipt(env, direction, state, len(rows) + 1)
            actions.append(direction)
            rows.append(row)
            position = (state["player_x"], state["player_y"])
            if position not in (origin, expected):
                raise OriginalGameGoalError("actual source cartridge moved outside its planned adjacent maze cell")
            if position == expected:
                succeeded = True
                break
        if not succeeded:
            raise OriginalGameGoalError("actual ROM did not execute the expected authored maze action")
    if state["completed"] != 1 or state["score"] < 1:
        raise OriginalGameGoalError("original ROM did not actually signal authored game completion")
    if not rows or rows[-1]["reward_components"]["goal_completion"] != 1.0:
        raise OriginalGameGoalError("goal completion reward was not bound to actual native memory")
    final_digest = _digest(env.snapshot())
    for row in rows:
        row["truncated"] = False
    # Source-backed terminal state is the final verified register transition.
    rows[-1]["terminated"] = True
    policy_spec = GameEnvironmentSpec(
        environment_id="game_boy:original_goal:" + manifest["rom_digest"],
        environment_digest=_digest([
            SCHEMA, env.environment_digest, manifest["rom_digest"],
            "known_original_game_registers", EXPECTED_REGISTERS,
        ]),
        actions=("idle", "up", "down", "left", "right"),
        observation_bins={
            "player_x": (4.0, 8.0, 12.0, 16.0),
            "player_y": (4.0, 8.0, 12.0, 16.0),
            "score": (0.5, 1.5),
            "goal_complete": (0.5,),
            "step_fraction": (0.25, 0.5, 0.75),
        },
        reward_components=("position_change", "goal_completion"),
        max_episode_steps=max_steps,
    )
    source_lineage = {
        "rights_acknowledged": True,
        "source": "generated_original_cartridge_with_source_declared_goal_registers",
        "rom_sha256": manifest["rom_digest"],
        "generator_seed": seed,
        "source_memory_bindings": EXPECTED_REGISTERS,
        "no_external_gameplay_reward_labels": True,
    }
    learner = GamePolicyLearner(
        policy_spec,
        GameLearningConfig(
            seed=seed, max_episodes=1, max_updates=max_steps,
            trace_byte_limit=8 * 1024 * 1024,
        ),
        policy_id="original-rom-authored-objective-q-candidate",
        source_lineage=source_lineage,
    )
    source_trace = {
        "schema_version": TRACE_SCHEMA,
        "environment": _descriptor(policy_spec),
        "episode_id": "original-source-goal:" + _digest([seed, manifest["rom_digest"]]),
        "seed": 0,
        "source_lineage": source_lineage,
        "transitions": [learner._transition(row, row["sequence"]) for row in rows],
        "return": math.fsum(row["reward"] for row in rows),
        "steps": len(rows),
    }
    source_trace["trace_digest"] = _digest(source_trace)
    learner.validate_trace(source_trace)
    _json(source_trace, limit=learner.config.trace_byte_limit)
    # A second physical run begins at the EXACT prior source CPU+screen state
    # and must reproduce every measured RAM/reward/frame transition.
    env.restore(original_state)
    prior = starting
    replayed = 0
    for recorded in rows:
        actual, prior = _step_receipt(env, recorded["action"], prior, recorded["sequence"])
        actual["terminated"] = recorded["terminated"]
        if actual != recorded:
            raise OriginalGameGoalError("authored-goal state/reward/frame replay diverged")
        replayed += 1
    if final_digest != _digest(env.snapshot()):
        raise OriginalGameGoalError("game-mission replay final memory, CPU or raster state diverged")
    # Same source checkpoint; the baseline executes the same physical number
    # of steps but no controller movement. This establishes active-only
    # outcome rather than crediting an automatic idle completion.
    env.restore(original_state)
    for _ in actions:
        env.step("idle")
    passive = _actual_game_registers(env)
    if passive["completed"] or passive["score"] >= state["score"]:
        raise OriginalGameGoalError("neutral-control trial matched the claimed active-only goal")
    trained = learner.train_offline([source_trace])
    if trained.updates != len(rows):
        raise OriginalGameGoalError("source-measured goal Q update accounting differs")
    result = {
        "schema_version": SCHEMA,
        "status": "original_cpu_game_goal_physically_replayed_and_q_trained",
        "rom_sha256": manifest["rom_digest"],
        "known_authored_game_registers": EXPECTED_REGISTERS,
        "observed_start": starting,
        "observed_active_end": state,
        "observed_neutral_end": passive,
        "source_tilemap_sha256": _digest(grid),
        "source_planned_route_moves": len(route),
        "executed_input_frames": len(actions),
        "source_actual_goal_completion": True,
        "actual_source_goal_reward": rows[-1]["reward_components"]["goal_completion"],
        "independently_replayed_source_frames": replayed,
        "independently_replayed_final_state_sha256": final_digest,
        "q_policy_snapshot": trained.snapshot,
        "real_goal_conditioned_q_updates": trained.updates,
        "original_trace_digest": source_trace["trace_digest"],
        "authored_game_specific_win_evidence": True,
        "unrelated_rom_goal_addresses_authorized": False,
        "hardware_accuracy_certified": False,
        "native_libretro_execution": False,
        "neural_weights_updated": 0,
        "production_policy_promotion": False,
    }
    result["receipt_digest"] = _digest(result)
    return result
