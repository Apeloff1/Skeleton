"""Finite native cartridge CPU checkpoints throughout a verified controller run.

This is executed emulator RAM evidence, not replayed Python-state fiction.
Each checkpoint corresponds to an actual action boundary and is bound to
the exact source trace; fail if flags/score/health/level behave impossibly.
Up to 128 observations per long game, every action for shorter games.
"""
from __future__ import annotations

from .contracts import canonical_digest

FIELDS = ("Level", "PlayerX", "PlayerY", "Health", "Score", "ScoreHigh",
          "GemsRemaining", "GameWon", "GameLost")
SCHEMA = "skeleton.game_builder.native_cpu_checkpoints.v1"
_MAX = 128
_LINE = re.compile(r"([0-9]{1,5})(?: ([0-9]{1,3})){9}\Z")


class NativeCheckpointError(ValueError):
    """Actual emulator progress evidence is invalid or diverges."""


def selected_checkpoints(actions: int) -> tuple[int, ...]:
    if type(actions) is not int or not 1 <= actions <= 20_000:
        raise NativeCheckpointError("bounded original game action count required")
    total = min(_MAX, actions)
    if total == 1:
        return (actions,)
    return tuple(sorted(set(
        1 + (idx * (actions - 1)) // (total - 1)
        for idx in range(total)
    )))


def make_checkpoint(index: int, state: dict) -> dict:
    if (type(index) is not int or not 1 <= index <= 20_000
            or type(state) is not dict or set(state) != set(FIELDS)
            or any(type(state[k]) is not int or not 0 <= state[k] <= 255
                   for k in FIELDS)
            or state["GameWon"] not in (0, 1)
            or state["GameLost"] not in (0, 1)):
        raise NativeCheckpointError("emulated 8-bit machine state malformed")
    return {"action": index, "state": {key: state[key] for key in FIELDS}}


def reference_cpu_checkpoints(engine_source: str | "Path") -> dict:
    """Rebuild actual signed Python world and independently replay all actions.

    This never guesses world geometry from graphics or trusts a browser-saved
    final state. The original seed/intent, regenerated world digest, embedded
    level maps and each canonical Python game transition must agree.
    """
    from pathlib import Path
    import json
    from .studio_runtime_qualification import _inputs
    from .studio_pixel_parity import _game_json
    from .playable_world import GameBuildIntent, generate_playable_world
    from .playable_simulation import initial_state, advance

    html, proof, identity = _inputs(Path(engine_source))
    game = _game_json(html.decode("utf-8"))
    data = json.loads(proof)
    try:
        intent = GameBuildIntent(**game["intent"])
        world = generate_playable_world(intent, authorized=True)
        levels = [
            {
                "width": level.width, "height": level.height,
                "rows": list(level.rows), "start": list(level.start),
                "exit": list(level.exit),
                "collectibles": [list(position) for position in level.collectibles],
            }
            for level in world.levels
        ]
    except (ValueError, TypeError, KeyError, PermissionError) as exc:
        raise NativeCheckpointError("original source world cannot regenerate") from exc
    if (world.digest != identity or game.get("world_digest") != identity
            or game.get("levels") != levels
            or data.get("world_digest") != identity):
        raise NativeCheckpointError("authored world and generated game sources diverged")
    actions = data.get("actions")
    if (type(actions) is not list or not actions
            or len(actions) > 20_000 or
            any(action not in ("up", "down", "left", "right") for action in actions)):
        raise NativeCheckpointError("original controller trace is not a bounded action list")
    indices = set(selected_checkpoints(len(actions)))
    state = initial_state(world, authorized=True)
    expected = []
    for index, action in enumerate(actions, 1):
        state = advance(world, state, action, authorized=True)
        if index not in indices:
            continue
        score = state.score
        if not 0 <= score <= 65535:
            raise NativeCheckpointError("game score exceeds two-byte cartridge capability")
        expected.append(make_checkpoint(index, {
            "Level": state.level_index + (1 if state.status == "won" else 0),
            "PlayerX": state.x, "PlayerY": state.y, "Health": state.health,
            "Score": score & 0xFF, "ScoreHigh": score >> 8,
            "GemsRemaining": (len(world.levels[state.level_index].collectibles)
                               - len(state.collected)),
            "GameWon": int(state.status == "won"),
            "GameLost": int(state.status == "lost"),
        }))
    final = data.get("final_state")
    if (type(final) is not dict or state.status != "won"
            or final.get("status") != state.status
            or final.get("level_index") != state.level_index
            or final.get("x") != state.x or final.get("y") != state.y
            or final.get("health") != state.health
            or final.get("score") != state.score
            or final.get("steps") != state.steps):
        raise NativeCheckpointError("Python canonical replay does not match signed game proof")
    return {
        "world_digest": identity,
        "proof_sha256": __import__("hashlib").sha256(proof).hexdigest(),
        "action_count": len(actions),
        "samples": expected,
    }


def validate_checkpoints(
    samples: list[dict] | tuple[dict, ...], *,
    actions: int, source_world: str, source_proof: str,
    expected_final: dict, expected_samples: list[dict] | None = None,
) -> dict:
    selected = selected_checkpoints(actions)
    hexdigits = frozenset("0123456789abcdef")
    if (type(samples) not in (list, tuple) or len(samples) != len(selected)
            or type(source_world) is not str or len(source_world) != 64
            or set(source_world) - hexdigits
            or type(source_proof) is not str or len(source_proof) != 64
            or set(source_proof) - hexdigits
            or type(expected_final) is not dict):
        raise NativeCheckpointError("source-bound exact replay checkpoint inventory required")
    if any(type(row) is not dict or set(row) != {"action", "state"}
           for row in samples):
        raise NativeCheckpointError("sample rows must have exact action/CPU state fields")
    rows = [make_checkpoint(row["action"], row["state"]) for row in samples]
    if tuple(row["action"] for row in rows) != selected:
        raise NativeCheckpointError("missing, duplicated or reordered CPU samples")
    if expected_samples is not None:
        if (type(expected_samples) is not list
                or len(expected_samples) != len(rows)
                or any(make_checkpoint(check["action"], check["state"]) != actual
                       for check, actual in zip(expected_samples, rows))):
            raise NativeCheckpointError("emulator CPU state diverged from real Python action replay")
    prev = None
    for row in rows:
        state = row["state"]
        score = state["Score"] + 256 * state["ScoreHigh"]
        if state["GameLost"] != 0 or state["GameWon"] != (1 if row["action"] == actions else 0):
            raise NativeCheckpointError("machine code lost or declared victory prematurely")
        if state["Health"] <= 0:
            raise NativeCheckpointError("CPU trace lost player health before victory")
        if prev is not None:
            last = prev["state"]
            last_score = last["Score"] + 256 * last["ScoreHigh"]
            if (state["Health"] > last["Health"]
                    or score < last_score
                    or state["Level"] < last["Level"]
                    or state["Level"] > last["Level"] + (row["action"] - prev["action"])):
                raise NativeCheckpointError("noncanonical health, score or level progression")
        prev = row
    final = rows[-1]["state"]
    if (final["Level"] != expected_final.get("level_index", -2) + 1
            or final["PlayerX"] != expected_final.get("x")
            or final["PlayerY"] != expected_final.get("y")
            or final["Health"] != expected_final.get("health")
            or final["Score"] + 256 * final["ScoreHigh"] != expected_final.get("score")
            or final["GemsRemaining"] != 0):
        raise NativeCheckpointError("native sampled finale disagrees with Python source replay")
    body = {
        "schema": SCHEMA,
        "source_world_digest": source_world,
        "source_proof_sha256": source_proof,
        "input_action_count": actions,
        "sampled_boundaries": len(rows),
        "first_observed_action": rows[0]["action"],
        "last_observed_action": rows[-1]["action"],
        "samples": rows,
        "physical_controller_verified": False,
        "checkpoint_weight_training_done": False,
    }
    return {**body, "checkpoint_digest": canonical_digest(body)}


def parse_nes_samples(raw: bytes, actions: int) -> list[dict]:
    if type(raw) is not bytes or not 0 < len(raw) <= 48_000:
        raise NativeCheckpointError("NES sample log missing or above resource budget")
    try:
        lines = raw.decode("ascii").splitlines()
    except UnicodeDecodeError as exc:
        raise NativeCheckpointError("NES CPU log contains non-ASCII data") from exc
    if len(lines) != len(selected_checkpoints(actions)):
        raise NativeCheckpointError("emulated CPU checkpoint count is not complete")
    samples = []
    for line in lines:
        # Fixed integer fields, not executable Lua or untrusted JSON.
        parts = line.split(" ")
        if (len(parts) != 1 + len(FIELDS)
                or any(not part.isascii() or not part.isdecimal()
                       or len(part) > 5 for part in parts)):
            raise NativeCheckpointError("NES CPU log has malformed action/state record")
        action = int(parts[0])
        values = list(map(int, parts[1:]))
        samples.append(make_checkpoint(action, dict(zip(FIELDS, values))))
    return samples


__all__ = [
    "NativeCheckpointError", "SCHEMA", "FIELDS", "selected_checkpoints",
    "make_checkpoint", "reference_cpu_checkpoints",
    "validate_checkpoints", "parse_nes_samples",
]
