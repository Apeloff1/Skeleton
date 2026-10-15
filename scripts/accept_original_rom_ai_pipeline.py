"""Run a REAL generated-original DMG ROM -> audited Q -> neural candidate acceptance.

No external ROM, emulator binary, BIOS, network call, provider model, or game
asset is fetched. The original ROM's instruction execution, screen frames,
savestates, replay audits, tabular Q updates, and a bounded CPU neural fit
are measured using their existing owners.

The final receipt is written ONLY after all independently verified phases.
This is original-DMG software-integration evidence, NOT native libretro,
physical-hardware compatibility, game-mastery proof, or Jeeves weight promotion.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SCHEMA = "skeleton.game.original_rom_ai_acceptance.v1"
MAX_FILE_BYTES = 32 * 1024 * 1024


class OriginalAcceptanceError(ValueError):
    pass


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(data: object) -> bytes:
    return json.dumps(
        data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _save(directory: Path, name: str, content: bytes) -> dict[str, object]:
    if (
        not name or len(name) > 96 or name in (".", "..")
        or any(char in name for char in ("/", "\\", "\x00"))
        or type(content) is not bytes or len(content) > MAX_FILE_BYTES
    ):
        raise OriginalAcceptanceError("output identity or bounded payload is invalid")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(directory / name, flags, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    return {
        "name": name, "bytes": len(content), "sha256": _sha(content),
        "private_create_only": True,
    }


def _json_save(directory: Path, name: str, value: object) -> dict[str, object]:
    return _save(directory, name, _canonical(value) + b"\n")


def run_original_rom_ai_pipeline(
    *, seed: int = 42, max_runs: int = 12, episode_steps: int = 12,
    neural_epochs: int = 4, neural_width: int = 8,
) -> tuple[bytes, dict[str, object], dict[str, object], dict[str, object], dict[str, object], dict[str, object]]:
    from skeleton.jeeves.game_rom_generation import build_original_dmg_game
    from skeleton.jeeves.game_learning_parallel import GameEnvironmentRequest
    from skeleton.jeeves.game_emulator_training_lab import EmulatorLabConfig, run_emulator_training_lab
    from skeleton.jeeves.game_emulator_neural_world import (
        NeuralWorldConfig, train_neural_world_from_evidence, verify_neural_training_sources,
        validate_neural_world_checkpoint,
    )
    if (
        type(seed) is not int or not 0 <= seed <= 2**63 - 1
        or type(max_runs) is not int or not 10 <= max_runs <= 32
        or type(episode_steps) is not int or not 4 <= episode_steps <= 32
        or type(neural_epochs) is not int or not 1 <= neural_epochs <= 16
        or type(neural_width) is not int or not 4 <= neural_width <= 32
    ):
        raise OriginalAcceptanceError("source episode/neural acceptance bounds invalid")
    generated = build_original_dmg_game(seed=seed, title="Original Training Garden")
    raw = base64.b64decode(generated["rom_base64"], validate=True)
    rom_sha = _sha(raw)
    if rom_sha != generated["rom_digest"]:
        raise OriginalAcceptanceError("generated original cartridge SHA256 differs")
    request = GameEnvironmentRequest(
        target_id="game_boy", kind="builtin",
        rom_source=raw, max_steps=episode_steps,
    )
    source_lineage = {
        "rights_acknowledged": True,
        "source": "original_generated_homebrew_rom",
        "generator": "skeleton.jeeves.game_rom_generation.build_original_dmg_game",
        "generator_seed": seed,
        "rom_sha256": rom_sha,
        "operator": "explicit_local_acceptance_command",
        "not_an_independent_commercial_rights_certificate": True,
    }
    q_report = run_emulator_training_lab(
        request,
        source_lineage=source_lineage,
        policy_id="original-rom-ai-acceptance-candidate",
        config=EmulatorLabConfig(
            max_runs=max_runs, steps_per_run=episode_steps,
            stagnation_runs=10,
            checkpoint_stride=min(4, episode_steps),
            counterfactual_actions=2,
            boomerang_interval=3,
            boomerang_retained=4, heldout_episodes=2,
            seed=seed,
        ),
    )
    if (
        q_report["run_count"] < 1
        or q_report["actual_q_table_updates"] != q_report["actual_training_steps"]
        or q_report["actual_training_steps"] < 32
        or not q_report["audited_run_receipts"]
        or q_report["actual_neural_parameter_updates"] != 0
    ):
        raise OriginalAcceptanceError("measured source Q receipts failed required accounting")
    policy = q_report["policy_snapshot"]
    evidence = {key: val for key, val in q_report.items() if key != "policy_snapshot"}
    evidence["policy_snapshot_digest"] = policy["snapshot_digest"]
    from skeleton.jeeves.game_learning import _digest

    evidence["evidence_digest"] = _digest(evidence)
    validated, features, actions, original_report_digest = verify_neural_training_sources(
        evidence, policy,
    )
    if len(validated) != q_report["actual_training_steps"]:
        raise OriginalAcceptanceError("replay-verified candidate rows differ from executed ROM steps")
    model, neural_report = train_neural_world_from_evidence(
        evidence, policy,
        config=NeuralWorldConfig(
            seed=seed, holdout_seed=seed + 1,
            width=neural_width, epochs=neural_epochs,
            minibatch=8, max_samples=512,
            max_compute_units=8_000_000,
        ),
    )
    validate_neural_world_checkpoint(model)
    if (
        neural_report["world_model_digest"] != model["model_digest"]
        or model["real_optimizer_steps"] < 1
        or model["gradient_evaluations"] < 16
        or model["not_a_jeeves_transformer_update"] is not True
        or model["production_model_promotion_authorized"] is not False
    ):
        raise OriginalAcceptanceError("neural model optimizer or production boundary differs")
    quality = neural_report["candidate_status"] == "candidate_predictive_gain_measured"
    result = {
        "schema_version": SCHEMA,
        "status": (
            "original_rom_training_measured_gain"
            if quality else "original_rom_trained_but_heldout_gain_not_proven"
        ),
        "source_mode": "actual_original_rom_interpreter",
        "native_libretro_core_executed": False,
        "physical_hardware_execution": False,
        "original_game_rom_sha256": rom_sha,
        "generator_manifest": generated["manifest"],
        "generated_rom_bytes": len(raw),
        "environment_request_digest": request.digest,
        "source_q_report_digest": original_report_digest,
        "candidate_neural_model_sha256": model["model_digest"],
        "candidate_neural_measurement_sha256": neural_report["report_digest"],
        "actual_replay_audited_q_runs": q_report["run_count"],
        "actual_learning_state_action_steps": q_report["actual_training_steps"],
        "verified_neural_source_rows": len(validated),
        "actual_q_updates": q_report["actual_q_table_updates"],
        "actual_candidate_neural_optimizer_steps": model["real_optimizer_steps"],
        "actual_candidate_gradient_evaluations": model["gradient_evaluations"],
        "holdout_source_groups": neural_report["partition"]["heldout_trace_groups"],
        "source_model_holdout_gain_measured": quality,
        "relative_holdout_mse_reduction": neural_report["relative_reduction_vs_mean_baseline"],
        "game_objective_or_win_proven": False,
        "native_hardware_accuracy_proven": False,
        "production_jeeves_weights_changed": False,
        "production_model_promotion_authorized": False,
        "acceptance_gate_passed": quality,
    }
    result["acceptance_digest"] = _digest(result)
    return raw, policy, evidence, model, neural_report, result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-directory", required=True, type=Path)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-runs", type=int, default=12)
    parser.add_argument("--episode-steps", type=int, default=12)
    parser.add_argument("--neural-epochs", type=int, default=4)
    parser.add_argument("--neural-width", type=int, default=8)
    args = parser.parse_args(argv)
    try:
        # A requested destination must be private, new and not a symlink.
        # The caller has to choose a distinct output folder for each run.
        if args.output_directory.exists() or args.output_directory.is_symlink():
            raise OriginalAcceptanceError("acceptance output directory must not exist")
        if not args.output_directory.parent.is_dir():
            raise OriginalAcceptanceError("acceptance parent directory must already exist")
        raw, policy, evidence, model, neural_report, acceptance = run_original_rom_ai_pipeline(
            seed=args.seed, max_runs=args.max_runs, episode_steps=args.episode_steps,
            neural_epochs=args.neural_epochs, neural_width=args.neural_width,
        )
        args.output_directory.mkdir(mode=0o700, parents=False, exist_ok=False)
        outputs = [
            _save(args.output_directory, "original-training.gb", raw),
            _json_save(args.output_directory, "rom-policy.json", policy),
            _json_save(args.output_directory, "rom-source-evidence.json", evidence),
            _json_save(args.output_directory, "neural-world-candidate.json", model),
            _json_save(args.output_directory, "neural-world-measurements.json", neural_report),
        ]
        acceptance["private_output_sha256_receipts"] = outputs
        acceptance["acceptance_digest"] = _sha(_canonical({
            k: v for k, v in acceptance.items() if k != "acceptance_digest"
        }))
        _json_save(args.output_directory, "acceptance.json", acceptance)
        print(json.dumps({
            "status": acceptance["status"],
            "accepted": acceptance["acceptance_gate_passed"],
            "q_steps": acceptance["actual_q_updates"],
            "neural_optimizer_steps": acceptance["actual_candidate_neural_optimizer_steps"],
            "holdout_relative_improvement": acceptance["relative_holdout_mse_reduction"],
            "acceptance_file": str(args.output_directory / "acceptance.json"),
            "production_jeeves_weights_changed": False,
        }, sort_keys=True, allow_nan=False))
        return 0 if acceptance["acceptance_gate_passed"] else 2
    except (ValueError, TypeError, OSError, RuntimeError) as exc:
        print(json.dumps({
            "status": "original_rom_pipeline_rejected",
            "reason": str(exc)[:800],
            "accepted": False,
        }, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
