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


def validate_checkpoints(
    samples: list[dict] | tuple[dict, ...], *,
    actions: int, source_world: str, source_proof: str,
    expected_final: dict,
) -> dict:
    selected = selected_checkpoints(actions)
    if (type(samples) not in (list, tuple) or len(samples) != len(selected)
            or type(source_world) is not str or len(source_world) != 64
            or type(source_proof) is not str or len(source_proof) != 64
            or type(expected_final) is not dict):
        raise NativeCheckpointError("source-bound exact replay checkpoint inventory required")
    rows = [make_checkpoint(row["action"], row["state"]) for row in samples]
    if tuple(row["action"] for row in rows) != selected:
        raise NativeCheckpointError("missing, duplicated or reordered CPU samples")
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
    "make_checkpoint", "validate_checkpoints", "parse_nes_samples",
]
