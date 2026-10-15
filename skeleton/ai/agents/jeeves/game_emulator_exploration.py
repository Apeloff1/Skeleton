"""Bounded boomerang exploration of real operator-approved libretro cores.

Revisits old action tapes, compares fresh sandboxed native replay evidence and
stops on observed *audiovisual* novelty plateau, not on model learning.
No background jobs, licensed content acquisition or automatic weight updates.
"""

from __future__ import annotations

import hashlib
import json
import random
from collections.abc import Callable, Sequence

from .game_emulator_qualification import run_emulator_qualification

SCHEMA = "skeleton.game.emulator_boomerang_exploration.v1"
MAX_SCENARIOS = 80
MAX_TOTAL_REQUESTED_FRAMES = 131072
MAX_SEED = 2**63 - 1

_MIRROR = {
    "left": "right", "right": "left",
    "a_left": "a_right", "a_right": "a_left",
    "b_left": "b_right", "b_right": "b_left",
    "key_left": "key_right", "key_right": "key_left",
    "up": "down", "down": "up",
    "key_up": "key_down", "key_down": "key_up",
    "key_w": "key_s", "key_s": "key_w",
}


class EmulatorExplorationError(ValueError):
    """Requested native replay-exploration work is outside its finite budget."""


def _sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def _variants(actions: tuple[str, ...], seed: int) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Deterministically select structurally varied but declared policy actions."""
    from .game_emulator_host import _ACTIONS, _KEY_ACTIONS

    available = tuple((*_ACTIONS, *_KEY_ACTIONS))
    if not actions or len(actions) > 64 or any(a not in available for a in actions):
        raise EmulatorExplorationError("Action tape must contain 1–64 actual declared libretro policy actions")
    rng = random.Random(seed)
    output = []
    seen: set[tuple[str, ...]] = set()

    def admit(label: str, tape: Sequence[str]) -> None:
        normalized = tuple(tape)
        if len(normalized) == len(actions) and normalized not in seen:
            output.append((label, normalized))
            seen.add(normalized)

    admit("baseline", actions)
    admit("reverse_input_order", actions[::-1])
    admit("mirrored_directions", tuple(_MIRROR.get(action, action) for action in actions))
    if len(actions) > 1:
        admit("rotate_one", (*actions[1:], actions[0]))
        half = len(actions) // 2
        admit("rotate_half", (*actions[half:], *actions[:half]))
        interleaved = []
        for i in range((len(actions) + 1) // 2):
            interleaved.append(actions[i])
            if len(actions) - 1 - i > i:
                interleaved.append(actions[-1 - i])
        admit("edge_to_center_order", interleaved)
    # One-action perturbations deliberately explore controls absent in the
    # original tape without inventing unbounded/unsupported input vectors.
    for attempt in range(min(24, len(actions) * 5)):
        index = rng.randrange(len(actions))
        replacement = available[rng.randrange(len(available))]
        mutated = list(actions)
        mutated[index] = replacement
        admit("bounded_single_action_perturbation", mutated)
        if len(output) >= 24:
            break
    return tuple(output)


def run_emulator_exploration(
    target_id: str,
    *,
    core_id: str,
    expected_registry_digest: str,
    actions: Sequence[str],
    rom_source: bytes | None = None,
    content: object | None = None,
    filename: str = "game.bin",
    reader: Callable | None = None,
    runs_per_scenario: int = 2,
    max_scenarios: int = 24,
    stagnation_window: int = 10,
    seed: int = 0,
    frames_per_step: int = 1,
    controller_devices: Sequence[str] | None = None,
    timeout_seconds: float = 5,
    rights_evidence_digest: str | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> dict[str, object]:
    """Run deterministic exploration, reversing and boomeranging old scenarios.

    Every scenario is executed by the existing bounded native qualifier, which
    launches a fresh sandboxed worker on every replay. A novel audiovisual
    signature is only an observed frame/audio difference, never a learned model
    parameter or a game-state success.
    """
    if (
        not isinstance(actions, (list, tuple))
        or any(type(action) is not str for action in actions)
        or type(seed) is not int or not 0 <= seed <= MAX_SEED
        or type(runs_per_scenario) is not int or not 2 <= runs_per_scenario <= 10
        or type(max_scenarios) is not int or not 2 <= max_scenarios <= MAX_SCENARIOS
        or type(stagnation_window) is not int or not 3 <= stagnation_window <= 20
        or type(frames_per_step) is not int or not 1 <= frames_per_step <= 8
    ):
        raise EmulatorExplorationError("Exploration input domain or replay budget is invalid")
    tapes = _variants(tuple(actions), seed)
    requested_per_scenario = runs_per_scenario * (len(actions) * frames_per_step + 32)
    if requested_per_scenario * max_scenarios > MAX_TOTAL_REQUESTED_FRAMES:
        raise EmulatorExplorationError("Total possible native step/reset frames exceed 131,072")
    rng = random.Random(seed ^ 0xB00A3E)
    pending = list(range(len(tapes)))
    seen_outcomes: set[str] = set()
    completed: list[dict[str, object]] = []
    exhausted = 0
    novelty = 0
    boomerang_runs = 0
    stops = "scenario_capacity_exhausted"
    while len(completed) < max_scenarios:
        if cancelled is not None and cancelled():
            raise EmulatorExplorationError("Explicit native exploration was cancelled")
        if len(completed) >= 4 and len(completed) % 4 == 0:
            # Reinsert prior evaluations before exhausting new candidates.
            visited_indices = sorted({row["tape_index"] for row in completed})
            pending.insert(0, visited_indices[rng.randrange(len(visited_indices))])
        if not pending:
            # Boomerang already visited scenarios on seeded, shuffled intervals.
            # The original baseline always re-enters every second shuffle,
            # enabling a control re-parse even after "completed" scenarios.
            pending = list(range(len(tapes)))
            rng.shuffle(pending)
            if len(completed) // max(1, len(tapes)) % 2 == 0:
                pending.insert(0, 0)
        tape_index = pending.pop(0)
        label, tape = tapes[tape_index]
        is_boomerang = any(entry["tape_index"] == tape_index for entry in completed)
        if is_boomerang:
            boomerang_runs += 1
        result = run_emulator_qualification(
            target_id,
            core_id=core_id,
            expected_registry_digest=expected_registry_digest,
            actions=list(tape),
            content=content,
            rom_source=rom_source,
            filename=filename,
            reader=reader,
            runs=runs_per_scenario,
            seed=seed,
            frames_per_step=frames_per_step,
            controller_devices=controller_devices,
            timeout_seconds=timeout_seconds,
            rights_evidence_digest=rights_evidence_digest,
            include_traces=False,
            cancelled=cancelled,
        )
        receipts = result["run_receipts"]
        # Ignore capture nonces and native callback counts for *novelty*:
        # only different observed final video/audio data counts as new.
        # Callback and replay divergences remain independently visible.
        signature = _sha([
            {
                "frame": row["last_video_sha256"],
                "audio": row["last_audio_sha256"],
            }
            for row in receipts
        ])
        found = signature not in seen_outcomes
        if found:
            seen_outcomes.add(signature)
            novelty += 1
            exhausted = 0
        else:
            exhausted += 1
        completed.append({
            "scenario_index": len(completed) + 1,
            "tape_index": tape_index,
            "transform": label,
            "action_tape_sha256": _sha(tape),
            "revisited_prior_scenario": is_boomerang,
            "outcome_signature_sha256": signature,
            "observed_outcome_novel": found,
            "native_replay_status": result["status"],
            "replay_audit_sha256": result["mirror_audit"]["audit_digest"],
            "first_replay_divergence": result["mirror_audit"]["first_divergent_step"],
            "run_receipts": receipts,
        })
        if exhausted >= stagnation_window:
            stops = "observed_audiovisual_novelty_plateau"
            break
    response: dict[str, object] = {
        "schema_version": SCHEMA,
        "status": "operator_native_exploration_completed",
        "stop_reason": stops,
        "core_id": core_id,
        "target_id": target_id,
        "source_registry_sha256": expected_registry_digest,
        "scenario_count": len(completed),
        "native_replay_attempts_completed": len(completed) * runs_per_scenario,
        "boomerang_revisits": boomerang_runs,
        "unique_observed_av_outcomes": novelty,
        "consecutive_without_new_av_outcome": exhausted,
        "stagnation_window": stagnation_window,
        "max_scenarios": max_scenarios,
        "initial_policy_tape_sha256": _sha(actions),
        "seed": seed,
        "scenarios": completed,
        "interpretation": "An audiovisual novelty plateau is not proof that the AI learned everything, that the game is solved or that the emulator is accurate.",
        "native_rights_independently_verified": False,
        "hardware_compatibility_verified": False,
        "model_weights_trained": False,
        "model_weight_promotion_authorized": False,
    }
    response["exploration_digest"] = _sha(response)
    return response
