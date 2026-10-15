"""First real ROM boot/rewind acceptance gate for approved native libretro cores.

This is an explicit OPERATOR command only, not a CI automatic job or game
ROM downloader. Each supplied original/lawful ROM boots through the genuine
existing isolated libretro worker and is reexecuted from an actual savestate.
No sample-game fallback can masquerade as emulator readiness. Approval,
accuracy and licensing remain independent checks beyond this first boot.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from collections.abc import Mapping
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SCHEMA = "skeleton.game.native_emulator_first_boot_matrix.v1"
MAX_CONTENT = 2 * 1024 * 1024
MAX_CASES = 32
MAX_REPORT = 8 * 1024 * 1024


class FirstBootError(ValueError):
    pass


def _digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
    ).hexdigest()


def _read(path: Path, limit: int) -> bytes:
    if not isinstance(path, Path) or type(limit) is not int or limit < 1:
        raise FirstBootError("bounded local path required")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        start = os.fstat(stream.fileno())
        if not stat.S_ISREG(start.st_mode) or start.st_size > limit:
            raise FirstBootError("native ROM must be a bounded regular local file")
        chunks, total = [], 0
        while total <= limit:
            data = stream.read(min(65536, limit + 1 - total))
            if not data:
                break
            total += len(data)
            chunks.append(data)
        finish = os.fstat(stream.fileno())
        by_path = os.stat(path, follow_symlinks=False)
        identity = lambda value: (
            value.st_dev, value.st_ino, value.st_size,
            value.st_mtime_ns, value.st_ctime_ns,
        )
        if (
            total > limit
            or not stat.S_ISREG(by_path.st_mode)
            or identity(start) != identity(finish)
            or identity(finish) != identity(by_path)
        ):
            raise FirstBootError("content changed or exceeded bounds during exact source read")
        return b"".join(chunks)


def _manifest(path: Path) -> list[dict[str, str]]:
    raw = json.loads(_read(path, 128 * 1024))
    if not isinstance(raw, Mapping) or set(raw) != {"schema_version", "cases"}:
        raise FirstBootError("first-boot matrix must have exact schema and cases")
    if raw["schema_version"] != SCHEMA:
        raise FirstBootError("unsupported first-boot matrix schema")
    cases = raw["cases"]
    if not isinstance(cases, list) or not 1 <= len(cases) <= MAX_CASES:
        raise FirstBootError("first-boot cases exceed bounded capacity")
    clean, identities = [], set()
    for case in cases:
        if not isinstance(case, dict) or set(case) != {
            "core_id", "target_id", "rom_path", "filename", "rom_sha256",
        }:
            raise FirstBootError("native core case schema differs")
        for key in ("core_id", "target_id", "filename", "rom_path"):
            value = case[key]
            if type(value) is not str or not 1 <= len(value) <= 256 or "\x00" in value:
                raise FirstBootError("invalid first-boot case value")
        if (
            "/" in case["filename"]
            or "\\" in case["filename"]
            or case["filename"] in (".", "..")
            or not Path(case["rom_path"]).is_absolute()
        ):
            raise FirstBootError("native content must be an explicit absolute local ROM and flat filename")
        claimed = case["rom_sha256"]
        if type(claimed) is not str or len(claimed) != 64 or any(ch not in "0123456789abcdef" for ch in claimed):
            raise FirstBootError("SHA256 of exact private ROM required")
        identity = (case["core_id"], case["target_id"], claimed)
        if identity in identities:
            raise FirstBootError("duplicate emulator core/content probe cannot inflate readiness")
        identities.add(identity)
        clean.append(case)
    return clean


def _run_case(case: Mapping[str, str], registry_digest: str, *, timeout: float) -> dict:
    from skeleton.jeeves.game_emulator_host import create_emulator_environment

    rom = _read(Path(case["rom_path"]), MAX_CONTENT)
    digest = hashlib.sha256(rom).hexdigest()
    if digest != case["rom_sha256"]:
        raise FirstBootError("actual owned ROM hash differs from approved test case")
    environment = create_emulator_environment(
        "emulator:" + case["target_id"],
        core_id=case["core_id"],
        expected_registry_digest=registry_digest,
        rom_source=rom,
        filename=case["filename"],
        max_steps=8,
        frames_per_step=1,
        timeout_seconds=timeout,
    )
    try:
        first = environment.reset(seed=0)
        preview = environment.preview()
        if not isinstance(preview, Mapping) or preview.get("render_kind") != "actual_native_frame_preview":
            raise FirstBootError("real native boot did not produce an actual captured visual frame")
        initial_frame = preview.get("source_pixel_digest")
        if type(initial_frame) is not str or len(initial_frame) != 64:
            raise FirstBootError("native first boot lacks exact frame digest")
        first_step = environment.step("idle")
        starting_snapshot = environment.snapshot()
        next_step = environment.step("a")
        ahead = environment.snapshot()
        restored = environment.restore(starting_snapshot)
        if restored != first_step.observation:
            raise FirstBootError("native observation differs immediately after rewind")
        repeated = environment.step("a")
        second = environment.snapshot()
        if (
            repeated.observation != next_step.observation
            or repeated.reward_components != next_step.reward_components
            or repeated.transition_digest != next_step.transition_digest
            or ahead["snapshot_digest"] != second["snapshot_digest"]
        ):
            raise FirstBootError("actual libretro input, frame/audio or savestate replay diverged")
        result = {
            "core_id": case["core_id"],
            "target_id": case["target_id"],
            "rom_sha256": digest,
            "registry_digest": registry_digest,
            "native_library_sha256": environment.core.library_sha256,
            "native_environment_digest": environment.spec.environment_digest,
            "boot_frame_sha256": initial_frame,
            "first_observation": first,
            "real_first_input": "idle",
            "real_second_input": "a",
            "first_transition_digest": first_step.transition_digest,
            "second_transition_digest": next_step.transition_digest,
            "replayed_transition_digest": repeated.transition_digest,
            "source_before_rewind_sha256": ahead["snapshot_digest"],
            "source_after_rewind_sha256": second["snapshot_digest"],
            "actual_emulator_steps": 3,
            "actual_savestate_roundtrip": True,
            "actual_native_boot": True,
            "metadata_frame_width": preview.get("width"),
            "metadata_frame_height": preview.get("height"),
            "native_boot_and_replay_accepted": True,
            "hardware_accuracy_certified": False,
            "license_cleared_by_this_probe": False,
            "legal_rom_authority_independently_verified": False,
            "model_weights_updated": 0,
        }
        result["receipt_digest"] = _digest(result)
        return result
    finally:
        environment.close()


def run_matrix(
    cases: list[dict[str, str]], *, timeout: float = 5.0,
) -> dict:
    from skeleton.jeeves.game_emulator_catalog import GameEmulatorRegistry

    if (
        not isinstance(cases, list) or not 1 <= len(cases) <= MAX_CASES
        or type(timeout) not in (int, float) or not 0.1 <= timeout <= 30
    ):
        raise FirstBootError("first-boot execution budget invalid")
    registry = GameEmulatorRegistry.from_environment()
    checked = []
    successes = failures = 0
    for case in cases:
        try:
            outcome = _run_case(case, registry.registry_digest, timeout=timeout)
            checked.append({"status": "actual_native_replay_pass", "case": outcome})
            successes += 1
        except (ValueError, TypeError, OSError, RuntimeError) as exc:
            failures += 1
            checked.append({
                "status": "first_boot_rejected",
                "core_id": case["core_id"],
                "target_id": case["target_id"],
                "rom_sha256": case["rom_sha256"],
                "error_type": type(exc).__name__,
                "error": str(exc)[:400],
                "native_boot_and_replay_accepted": False,
            })
    report = {
        "schema_version": "skeleton.game.native_emulator_first_boot_report.v1",
        "source_rights_assertion_from_operator": True,
        "core_registry_sha256": registry.registry_digest,
        "input_case_count": len(cases),
        "actual_verified_first_boots": successes,
        "unverified_or_failed_cases": failures,
        "all_cases_passed": failures == 0,
        "cases": checked,
        "promotion_authorized": False,
        "machine_hardware_accuracy_certified": False,
        "neural_weights_trained": False,
    }
    report["report_digest"] = _digest(report)
    if len(json.dumps(report, allow_nan=False).encode()) > MAX_REPORT:
        raise FirstBootError("bounded result receipt capacity exceeded")
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest-file", type=Path, required=True)
    parser.add_argument("--evidence-file", type=Path, required=True)
    parser.add_argument("--rights-acknowledged", action="store_true")
    parser.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args(argv)
    if not args.rights_acknowledged:
        parser.error("explicit rights-cleared private emulator content acknowledgement required")
    try:
        if args.manifest_file.resolve(strict=False) == args.evidence_file.resolve(strict=False):
            raise FirstBootError("input matrix and evidence destination must differ")
        if args.evidence_file.exists() or args.evidence_file.is_symlink():
            raise FirstBootError("evidence destination must be a new non-symlink file")
        rows = _manifest(args.manifest_file)
        result = run_matrix(rows, timeout=args.timeout)
        # Safe atomic create-only publication; never clobber prior receipts.
        args.evidence_file.parent.mkdir(parents=True, exist_ok=True)
        encoded = (json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
        fd = os.open(args.evidence_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as output:
            output.write(encoded)
            output.flush()
            os.fsync(output.fileno())
        print(json.dumps({
            "evidence_file": str(args.evidence_file),
            "report_digest": result["report_digest"],
            "actual_verified_first_boots": result["actual_verified_first_boots"],
            "unverified_or_failed_cases": result["unverified_or_failed_cases"],
            "production_model_promotion": False,
        }, sort_keys=True))
        return 0 if result["all_cases_passed"] else 2
    except (ValueError, TypeError, OSError, RuntimeError) as exc:
        print(json.dumps({"status": "first_boot_matrix_rejected", "error": str(exc)[:400]}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
