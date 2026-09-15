#!/usr/bin/env python3
"""Run the canonical security scanner suite with explicit fail-closed semantics."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TIMEOUT_SECONDS = 180.0

# Keep the merge-blocking scanner surface explicit and reviewable.  A scanner
# added here is executed by canonical quality-gates.sh through this runner.
CANONICAL_SCANNERS: tuple[str, ...] = (
    "backend/scripts/check_process_safety.py",
    "scripts/check_repository_process_safety.py",
    "backend/scripts/check_deserialization_safety.py",
    "backend/scripts/check_dynamic_import_safety.py",
    "backend/scripts/check_archive_extraction_safety.py",
    "backend/scripts/check_sast_security.py",
    "scripts/check_repository_python_sast.py",
    "backend/scripts/check_js_process_alias_safety.py",
    "backend/scripts/check_workflow_security.py",
    "backend/scripts/check_secret_hygiene.py",
    "backend/scripts/check_malware_iocs.py",
)


def _resolve_scanner(relative_path: str) -> Path:
    candidate = Path(relative_path)
    if candidate.is_absolute():
        raise ValueError("scanner path must be repository-relative")

    resolved = (REPO_ROOT / candidate).resolve()
    try:
        resolved.relative_to(REPO_ROOT)
    except ValueError as exc:
        raise ValueError("scanner path escapes repository root") from exc

    if resolved.suffix != ".py":
        raise ValueError("scanner must be a Python source file")
    if not resolved.is_file():
        raise ValueError("scanner file does not exist")
    return resolved


def run_scanner(relative_path: str, *, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> int:
    """Execute one scanner and normalize every abnormal state to failure."""
    if timeout <= 0:
        print("security scanner timeout must be greater than zero", file=sys.stderr)
        return 2

    try:
        scanner = _resolve_scanner(relative_path)
    except ValueError as exc:
        print(f"security scanner configuration failure: {relative_path}: {exc}", file=sys.stderr)
        return 2

    display = scanner.relative_to(REPO_ROOT)
    print(f"\n== Security scanner: {display} ==", flush=True)
    try:
        completed = subprocess.run(
            [sys.executable, str(scanner)],
            cwd=REPO_ROOT,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        print(
            f"security scanner timed out after {timeout:g}s: {display}",
            file=sys.stderr,
        )
        return 124
    except OSError as exc:
        print(f"security scanner launch failure: {display}: {exc}", file=sys.stderr)
        return 126

    if completed.returncode == 0:
        return 0
    if completed.returncode < 0:
        print(
            f"security scanner terminated by signal {-completed.returncode}: {display}",
            file=sys.stderr,
        )
        return 1

    print(
        f"security scanner reported failure (exit {completed.returncode}): {display}",
        file=sys.stderr,
    )
    return 1


def run_suite(
    scanners: Iterable[str] = CANONICAL_SCANNERS,
    *,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> int:
    """Run scanners in order and stop at the first failure."""
    count = 0
    for scanner in scanners:
        count += 1
        result = run_scanner(scanner, timeout=timeout)
        if result != 0:
            return result
    if count == 0:
        print("security scanner suite is empty; refusing to pass", file=sys.stderr)
        return 2
    print(f"\nSecurity scanner suite passed for {count} scanners.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the canonical merge-blocking security scanner suite."
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="per-scanner timeout in seconds (default: %(default)s)",
    )
    args = parser.parse_args(argv)
    return run_suite(timeout=args.timeout)


if __name__ == "__main__":
    raise SystemExit(main())
