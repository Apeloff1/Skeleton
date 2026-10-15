"""Manual, fail-closed executable acceptance suite for original-ROM AI training.

Intentionally NOT attached to normal PR/push workflow triggers. Executes the
repository's original DMG ROM, real instruction/rewind/Q/neural candidates
and original source-declared goal path; checks the *published bytes* as well
as process exit codes. Native libretro certification remains a separate
approved-core + lawful-ROM first-boot gate.

Invoke:
  python scripts/run_game_rom_acceptance_suite.py --output-directory /private/rom-acceptance-001

The parent directory must already exist; the output directory must not.
No network, external ROMs or BIOS. Never emit an acceptance claim before
all expected receipts have been checked and materialized.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SUITE_SCHEMA = "skeleton.game.original_rom_acceptance_suite.v1"
MAX_REPORT_BYTES = 32 * 1024 * 1024
MAX_STDOUT = 32768
TEST_MODULES = (
    "skeleton.testing.test_game_rom_mapper_expansion",
    "skeleton.testing.test_game_emulator_fleet_build",
    "skeleton.testing.test_game_emulator_training_lab",
    "skeleton.testing.test_game_emulator_advanced_experiments",
    "skeleton.testing.test_game_emulator_neural_world",
    "skeleton.testing.test_game_emulator_physical_planning",
    "skeleton.testing.test_game_emulator_operator_goals",
    "skeleton.testing.test_game_emulator_first_boot_audit",
    "skeleton.testing.test_game_original_rom_ai_acceptance",
    "skeleton.testing.test_game_original_rom_goal_training",
)


class AcceptanceSuiteError(ValueError):
    pass


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _json_file(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(path, Path) or path.is_symlink():
        raise AcceptanceSuiteError("evidence cannot be a symlink")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as source:
        before = os.fstat(source.fileno())
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_REPORT_BYTES:
            raise AcceptanceSuiteError("evidence file size or regular-file identity invalid")
        content = source.read(MAX_REPORT_BYTES + 1)
        after = os.fstat(source.fileno())
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
        ) or len(content) != before.st_size:
            raise AcceptanceSuiteError("evidence changed during verification")
    document = json.loads(content)
    if not isinstance(document, dict):
        raise AcceptanceSuiteError("typed JSON evidence object required")
    return document, {"file": path.name, "bytes": len(content), "sha256": _sha(content)}


def _verify_digest(document: dict[str, Any], key: str) -> None:
    claimed = document.get(key)
    if (
        not isinstance(claimed, str) or len(claimed) != 64
        or _sha(_canonical({k: v for k, v in document.items() if k != key})) != claimed
    ):
        raise AcceptanceSuiteError(f"{key} is not bound to its emitted canonical report")


def _verify_original_pipeline(directory: Path) -> dict[str, Any]:
    acceptance, acceptance_ref = _json_file(directory / "acceptance.json")
    _verify_digest(acceptance, "acceptance_digest")
    if (
        acceptance.get("schema_version") != "skeleton.game.original_rom_ai_acceptance.v1"
        or acceptance.get("acceptance_gate_passed") is not True
        or acceptance.get("source_model_holdout_gain_measured") is not True
        or acceptance.get("native_libretro_core_executed") is not False
        or acceptance.get("production_jeeves_weights_changed") is not False
        or acceptance.get("production_model_promotion_authorized") is not False
        or type(acceptance.get("actual_q_updates")) is not int
        or acceptance["actual_q_updates"] < 32
        or type(acceptance.get("actual_candidate_neural_optimizer_steps")) is not int
        or acceptance["actual_candidate_neural_optimizer_steps"] < 1
    ):
        raise AcceptanceSuiteError("original ROM Q/neural operator acceptance did not pass")
    expected = {
        "original-training.gb", "rom-policy.json", "rom-source-evidence.json",
        "neural-world-candidate.json", "neural-world-measurements.json",
    }
    records = acceptance.get("private_output_sha256_receipts")
    if not isinstance(records, list) or {row.get("name") for row in records if isinstance(row, dict)} != expected:
        raise AcceptanceSuiteError("original ROM acceptance did not declare all expected files")
    published = [acceptance_ref]
    for row in records:
        if not isinstance(row, dict) or row.get("private_create_only") is not True:
            raise AcceptanceSuiteError("report contains an untrusted output artifact entry")
        filename = row["name"]
        artifact = directory / filename
        if artifact.is_symlink() or not artifact.is_file():
            raise AcceptanceSuiteError("required original ROM pipeline artifact is missing")
        data = artifact.read_bytes()
        if len(data) != row["bytes"] or _sha(data) != row["sha256"]:
            raise AcceptanceSuiteError("published original ROM artifact checksum differs")
        published.append({"file": filename, "bytes": len(data), "sha256": _sha(data)})
    policy, _ = _json_file(directory / "rom-policy.json")
    source, _ = _json_file(directory / "rom-source-evidence.json")
    candidate, _ = _json_file(directory / "neural-world-candidate.json")
    metrics, _ = _json_file(directory / "neural-world-measurements.json")
    from skeleton.jeeves.game_emulator_neural_world import (
        validate_neural_world_checkpoint, verify_neural_training_sources,
    )
    from skeleton.jeeves.game_learning import _digest

    admitted, features, actions, original_digest = verify_neural_training_sources(source, policy)
    if (
        len(admitted) != acceptance["verified_neural_source_rows"]
        or original_digest != acceptance["source_q_report_digest"]
        or validate_neural_world_checkpoint(candidate) != acceptance["candidate_neural_model_sha256"]
        or metrics.get("report_digest") != acceptance["candidate_neural_measurement_sha256"]
        or metrics.get("candidate_status") != "candidate_predictive_gain_measured"
        or not isinstance(features, tuple) or not isinstance(actions, tuple)
        or _digest({k: v for k, v in metrics.items() if k != "report_digest"}) != metrics["report_digest"]
    ):
        raise AcceptanceSuiteError("published source, candidate and heldout neural reports disagree")
    return {
        "accepted": True,
        "rom_sha256": acceptance["original_game_rom_sha256"],
        "source_q_updates": acceptance["actual_q_updates"],
        "world_model_optimizer_steps": acceptance["actual_candidate_neural_optimizer_steps"],
        "world_model_heldout_improvement": acceptance["relative_holdout_mse_reduction"],
        "published_private_artifacts": published,
        "native_emulator_accuracy_proven": False,
        "production_jeeves_weights_updated": False,
    }


def _verify_game_goal(directory: Path) -> dict[str, Any]:
    goal, reference = _json_file(directory / "original-goal-q.json")
    _verify_digest(goal, "receipt_digest")
    snapshot = goal.get("q_policy_snapshot", {})
    if (
        goal.get("schema_version") != "skeleton.game.original_dmg_goal_q.v1"
        or goal.get("source_actual_goal_completion") is not True
        or goal.get("authored_game_specific_win_evidence") is not True
        or goal.get("observed_active_end", {}).get("completed") != 1
        or goal.get("observed_neutral_end", {}).get("completed") != 0
        or goal.get("observed_active_end", {}).get("score", 0) < 1
        or goal.get("native_libretro_execution") is not False
        or goal.get("production_policy_promotion") is not False
        or goal.get("neural_weights_updated") != 0
        or type(goal.get("real_goal_conditioned_q_updates")) is not int
        or goal["real_goal_conditioned_q_updates"] < 1
        or goal["real_goal_conditioned_q_updates"] != goal.get("executed_input_frames")
        or goal.get("independently_replayed_source_frames") != goal["executed_input_frames"]
        or not isinstance(snapshot, dict)
        or snapshot.get("committed_updates") != goal["real_goal_conditioned_q_updates"]
    ):
        raise AcceptanceSuiteError("original ROM game-mission score and Q training not physically established")
    from skeleton.jeeves.game_learning import _digest

    claimed_snapshot = snapshot.get("snapshot_digest")
    if not isinstance(claimed_snapshot, str) or _digest({
        k: v for k, v in snapshot.items() if k != "snapshot_digest"
    }) != claimed_snapshot:
        raise AcceptanceSuiteError("authored-game policy snapshot is not internally bound")
    return {
        "accepted": True,
        "original_rom_sha256": goal["rom_sha256"],
        "real_source_controller_frames": goal["executed_input_frames"],
        "real_goal_q_updates": goal["real_goal_conditioned_q_updates"],
        "authored_win_and_score_verified": True,
        "semantic_game_meaning_valid_only_for_authored_rom": True,
        "report_file": reference,
        "production_weights_updated": False,
    }


def _run(
    command: list[str], output_root: Path, label: str, *,
    seconds: int,
) -> dict[str, Any]:
    if (
        type(seconds) is not int or not 10 <= seconds <= 900
        or not isinstance(command, list) or not command
    ):
        raise AcceptanceSuiteError("bounded acceptance process command required")
    try:
        finished = subprocess.run(
            command, cwd=ROOT, capture_output=True, text=True,
            timeout=seconds, check=False,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
    except subprocess.TimeoutExpired as exc:
        raise AcceptanceSuiteError(f"{label}: bounded real executable process timed out") from exc
    receipt = {
        "label": label,
        "command": command,
        "exit_code": finished.returncode,
        "stdout_tail": finished.stdout[-MAX_STDOUT:],
        "stderr_tail": finished.stderr[-MAX_STDOUT:],
        "actual_process_executed": True,
    }
    receipt["receipt_digest"] = _sha(_canonical(receipt))
    if finished.returncode != 0:
        raise AcceptanceSuiteError(
            f"{label} returned {finished.returncode}: {finished.stderr[-1400:]}"
        )
    return receipt


def run_acceptance_suite(
    output_directory: Path, *, seed: int = 42,
    tests: bool = True, process_timeout_seconds: int = 600,
) -> dict[str, Any]:
    if (
        not isinstance(output_directory, Path)
        or output_directory.exists() or output_directory.is_symlink()
        or not output_directory.parent.is_dir()
        or type(seed) is not int or not 0 <= seed <= 2**63 - 1
        or type(tests) is not bool
    ):
        raise AcceptanceSuiteError("acceptance output must be a new local directory with bounded seed")
    if type(process_timeout_seconds) is not int or not 30 <= process_timeout_seconds <= 900:
        raise AcceptanceSuiteError("acceptance worker timeout must be 30..900 seconds")
    output_directory.mkdir(mode=0o700)
    processes = []
    try:
        if tests:
            processes.append(_run(
                [sys.executable, "-m", "unittest", "-v", *TEST_MODULES],
                output_directory, "focused_synthetic_and_real_original_rom_regressions",
                seconds=process_timeout_seconds,
            ))
        original_path = output_directory / "original"
        processes.append(_run(
            [
                sys.executable, "scripts/accept_original_rom_ai_pipeline.py",
                "--output-directory", str(original_path),
                "--seed", str(seed), "--max-runs", "12",
                "--episode-steps", "12", "--neural-epochs", "4",
                "--neural-width", "8",
            ],
            output_directory, "original_rom_cpu_q_neural_acceptance",
            seconds=process_timeout_seconds,
        ))
        original = _verify_original_pipeline(original_path)
        goal_path = output_directory / "original-goal-q.json"
        processes.append(_run(
            [
                sys.executable, "-m", "skeleton.jeeves.game_original_rom_goal_training",
                "--seed", str(seed), "--max-steps", "2048",
                "--max-frames-per-tile", "16",
                "--evidence-file", str(goal_path),
            ],
            output_directory, "authored_rom_cpu_goal_q_acceptance",
            seconds=process_timeout_seconds,
        ))
        goal = _verify_game_goal(output_directory)
        report = {
            "schema_version": SUITE_SCHEMA,
            "status": "original_cpu_rom_emulator_ai_acceptance_pass",
            "tests_requested": tests,
            "focused_tests_executed": tests,
            "source_cpu_interpreter_executed": True,
            "source_q_rewind_proven": True,
            "neural_candidate_optimized_and_scored": True,
            "source_goal_replay_and_neutral_control_verified": True,
            "original_training": original,
            "original_goal_training": goal,
            "bounded_worker_receipts": processes,
            "real_libretro_installed_core_tested": False,
            "independent_game_hardware_accuracy_certified": False,
            "production_jeeves_weights_modified": False,
            "production_model_promotion_authorized": False,
        }
        report["suite_digest"] = _sha(_canonical(report))
        payload = json.dumps(report, indent=2, sort_keys=True, allow_nan=False).encode("utf-8")
        if len(payload) > MAX_REPORT_BYTES:
            raise AcceptanceSuiteError("published acceptance suite evidence exceeds bounded capacity")
        fd = os.open(output_directory / "suite-acceptance.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        return report
    except BaseException:
        # Operator explicitly receives a nonzero command result and retains
        # partial real phase artifacts for debugging. Never publish a passing
        # acceptance receipt or auto-promote partial evidence.
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--without-tests", action="store_true")
    parser.add_argument("--process-timeout-seconds", type=int, default=600)
    args = parser.parse_args(argv)
    try:
        result = run_acceptance_suite(
            args.output_directory.resolve(strict=False), seed=args.seed,
            tests=not args.without_tests,
            process_timeout_seconds=args.process_timeout_seconds,
        )
    except (OSError, ValueError, RuntimeError) as exc:
        print(json.dumps({
            "status": "original_rom_ai_acceptance_failed",
            "reason": str(exc)[:1200],
            "production_jeeves_weights_modified": False,
            "receipt_published": False,
        }, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps({
        "status": result["status"],
        "suite_sha256": result["suite_digest"],
        "original_emulator_accepted": True,
        "native_libretro_hardware_accepted": False,
        "result_file": str(args.output_directory / "suite-acceptance.json"),
        "production_jeeves_weights_modified": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
