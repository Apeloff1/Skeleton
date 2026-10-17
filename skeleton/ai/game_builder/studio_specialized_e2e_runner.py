"""Operator-owned offline, bounded execution of registered Jeeves native test suites.

No GitHub Actions workflow, background job, arbitrary shell, dynamic command,
model training, emulator success or release claim. This is a synchronous,
opt-in source-contract pytest runner and source-snapshot evidence writer.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import monotonic

from .contracts import canonical_digest

SCHEMA = "skeleton.game_builder.specialized_native_e2e_test_receipt.v1"
SUITE_ID = "jeeves-native-cartridge-emulator-full-e2e"
_BASE = ("python", "-m", "pytest", "-q", "-ra", "--tb=short", "--noconftest")
_TEST = re.compile(r"tests/test_[A-Za-z0-9_]+\.py\Z")
_SOURCE = re.compile(r"(?:skeleton/[A-Za-z0-9_/]+|tests/test_[A-Za-z0-9_]+\.py)\Z")


class SpecializedTestError(ValueError):
    """The selected registered tests or source snapshot could not be trusted."""


def _regular(root: Path, name: str, *, budget: int = 4_000_000) -> bytes:
    if (type(name) is not str or not _SOURCE.fullmatch(name)
            or ".." in name.split("/") or "\\" in name):
        raise SpecializedTestError("registered source path is outside allowlisted tree")
    target = root / name
    if (any(part.is_symlink() for part in
            [target, *list(target.parents)[:-1]]
            if part != root and root in part.parents)
            or not target.is_file() or target.is_symlink()):
        raise SpecializedTestError("native test source must be a regular original file")
    try:
        if not 0 < target.stat().st_size <= budget:
            raise SpecializedTestError("native test source exceeds file budget")
        return target.read_bytes()
    except OSError as exc:
        raise SpecializedTestError("native test source inaccessible") from exc


def _registered_suite(root: Path) -> tuple[tuple[str, ...], tuple[str, ...], int]:
    registry_path = root / "machine/e2e_suites.json"
    if registry_path.is_symlink() or not registry_path.is_file():
        raise SpecializedTestError("canonical suite registry missing or linked")
    try:
        if not 0 < registry_path.stat().st_size <= 2_000_000:
            raise SpecializedTestError("registered suite exceeds manifest budget")
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError) as exc:
        raise SpecializedTestError("unreadable native E2E registry") from exc
    if type(registry) is not dict or type(registry.get("suites")) is not list:
        raise SpecializedTestError("invalid canonical E2E registry")
    suites = [entry for entry in registry["suites"]
              if type(entry) is dict and entry.get("id") == SUITE_ID]
    if len(suites) != 1:
        raise SpecializedTestError("exactly one named original native suite required")
    suite = suites[0]
    command = suite.get("command")
    required = suite.get("required_files")
    timeout = suite.get("timeout_seconds")
    if (suite.get("tier") != "offline" or suite.get("cwd") != "."
            or type(command) is not list or len(command) > 72
            or command[:len(_BASE)] != list(_BASE)
            or type(required) is not list or not 1 <= len(required) <= 128
            or type(timeout) is not int or not 1 <= timeout <= 3600):
        raise SpecializedTestError("suite execution policy is not allowlisted")
    tests = command[len(_BASE):]
    if (not 1 <= len(tests) <= 64
            or any(type(name) is not str or not _TEST.fullmatch(name)
                   for name in tests)
            or len(set(tests)) != len(tests)
            or any(name not in required for name in tests)
            or len(set(required)) != len(required)):
        raise SpecializedTestError("suite tests must be unique registered local files")
    for file in required:
        _regular(root, file)
    return tuple(tests), tuple(required), timeout


def _fingerprint(root: Path, names: tuple[str, ...]) -> str:
    inventory = {
        name: sha256(_regular(root, name)).hexdigest()
        for name in sorted(names)
    }
    return canonical_digest(inventory)


def _execute(root: Path, test_files: tuple[str, ...], timeout_seconds: int,
             log_dir: Path) -> tuple[str, int | None, int, int]:
    argv = [sys.executable, "-m", "pytest",
            "-q", "-ra", "--tb=short", "--noconftest", *test_files]
    # Keep the exact selected interpreter. Never invoke the shell or arbitrary
    # subprocess arguments from the user, environment, registry, or model.
    env = dict(os.environ)
    for key in ("PYTHONSTARTUP", "PYTHONINSPECT", "PYTHONBREAKPOINT"):
        env.pop(key, None)
    env["PYTHONPATH"] = str(root)
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    stdout = log_dir / "stdout.log"
    stderr = log_dir / "stderr.log"
    with stdout.open("wb") as output, stderr.open("wb") as errors:
        try:
            completed = subprocess.run(
                argv, cwd=root, env=env, stdin=subprocess.DEVNULL,
                stdout=output, stderr=errors,
                timeout=timeout_seconds, check=False, shell=False,
            )
        except subprocess.TimeoutExpired:
            status, return_code = "timeout", None
        except OSError:
            status, return_code = "not_started", None
        else:
            return_code = completed.returncode
            status = "passed" if return_code == 0 else "failed"
    return status, return_code, stdout.stat().st_size, stderr.stat().st_size


def run_registered_native_e2e(
    root: str | Path, *, authorized: bool, execute: bool,
    receipt_path: str | Path, timeout_seconds: int = 1200,
) -> dict:
    if authorized is not True or execute is not True:
        raise PermissionError("native E2E tests need explicit execution authority")
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 3600:
        raise SpecializedTestError("bounded test runtime required")
    project = Path(root)
    if project.is_symlink() or not project.is_dir():
        raise SpecializedTestError("actual original repository checkout required")
    project = project.resolve()
    destination = Path(receipt_path)
    if (destination.is_symlink() or not destination.parent.is_dir()
            or destination.parent.is_symlink() or destination.exists()
            or destination.suffix.lower() != ".json"):
        raise SpecializedTestError("new external JSON receipt path required")
    destination = destination.absolute()
    if project == destination or project in destination.parents:
        raise SpecializedTestError("test receipts must not modify the checked source tree")
    tests, files, suite_timeout = _registered_suite(project)
    original_digest = _fingerprint(project, files)
    effective_timeout = min(timeout_seconds, suite_timeout)
    start = monotonic()
    with TemporaryDirectory(prefix="original-native-tests-") as tmp:
        state, code, stdout_size, stderr_size = _execute(
            project, tests, effective_timeout, Path(tmp),
        )
        source_changed = _fingerprint(project, files) != original_digest
        result = {
            "schema": SCHEMA,
            "suite": SUITE_ID,
            "selected_test_files": len(tests),
            "registered_source_files": len(files),
            "source_fingerprint": original_digest,
            "source_changed_during_execution": source_changed,
            "timeout_seconds": effective_timeout,
            "elapsed_milliseconds": int((monotonic() - start) * 1000),
            "process_status": state,
            "process_return_code": code,
            "stdout_bytes": stdout_size,
            "stderr_bytes": stderr_size,
            "source_contract_tests_passed": state == "passed" and not source_changed,
            "genuine_rom_emulator_execution_proven": False,
            "hardware_audio_video_qualified": False,
            "first_install_qualified": False,
            "model_weights_changed": False,
            "release_approved": False,
        }
    result["receipt_digest"] = canonical_digest(result)
    encoded = (json.dumps(result, sort_keys=True, indent=2) + "\n").encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(destination, flags, 0o600)
    with os.fdopen(fd, "wb") as output:
        output.write(encoded)
        output.flush()
        os.fsync(output.fileno())
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    parser.add_argument("--authorize-local-operation", action="store_true")
    parser.add_argument("--execute-tests", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = run_registered_native_e2e(
            args.repo_root, authorized=args.authorize_local_operation,
            execute=args.execute_tests, receipt_path=args.receipt,
            timeout_seconds=args.timeout_seconds,
        )
    except (ValueError, PermissionError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0 if result["source_contract_tests_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
