"""Fail-closed one-command local development bootstrap for VOL-195."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from typing import Callable, Sequence


REQUIRED_PYTHON = "3.11.16"
PROJECT_FILE = "pyproject.toml"
LOCK_FILE = "uv.lock"


class BootstrapError(RuntimeError):
    """Local bootstrap cannot proceed reproducibly."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True, slots=True)
class BootstrapPlan:
    root: str
    python_version: str
    project_digest: str
    lock_digest: str
    commands: tuple[tuple[str, ...], ...]

    @property
    def digest(self) -> str:
        payload = {
            "root": self.root,
            "python_version": self.python_version,
            "project_digest": self.project_digest,
            "lock_digest": self.lock_digest,
            "commands": [list(command) for command in self.commands],
        }
        return hashlib.sha256(
            json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()

    def as_dict(self) -> dict[str, object]:
        return {
            "root": self.root,
            "python_version": self.python_version,
            "project_digest": self.project_digest,
            "lock_digest": self.lock_digest,
            "commands": [list(command) for command in self.commands],
            "digest": self.digest,
        }


def build_plan(
    root: str | Path = ".",
    *,
    python_version: str = REQUIRED_PYTHON,
) -> BootstrapPlan:
    project_root = Path(root).resolve()
    project = project_root / PROJECT_FILE
    lock = project_root / LOCK_FILE
    if not project.is_file():
        raise BootstrapError(f"missing {PROJECT_FILE}: {project}")
    if not lock.is_file():
        raise BootstrapError(
            "missing uv.lock; reproducible bootstrap refuses to resolve an "
            "unlocked dependency graph"
        )
    if not isinstance(python_version, str) or not python_version.strip():
        raise BootstrapError("python_version must be non-empty text")
    version = python_version.strip()
    if version != python_version:
        raise BootstrapError("python_version must be canonical text")

    commands = (
        ("uv", "python", "install", version),
        ("uv", "sync", "--locked", "--python", version, "--extra", "dev"),
    )
    return BootstrapPlan(
        root=str(project_root),
        python_version=version,
        project_digest=_sha256(project),
        lock_digest=_sha256(lock),
        commands=commands,
    )


def execute_plan(
    plan: BootstrapPlan,
    *,
    runner: Callable[..., object] = subprocess.run,
) -> None:
    if not isinstance(plan, BootstrapPlan):
        raise BootstrapError("plan must be BootstrapPlan")
    if shutil.which("uv") is None:
        raise BootstrapError(
            "uv is required; install the pyproject.toml-pinned uv version first"
        )
    root = Path(plan.root)
    for command in plan.commands:
        runner(command, cwd=root, check=True)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reproducibly bootstrap the Skeleton local development environment."
    )
    parser.add_argument("--root", default=".")
    parser.add_argument("--python", default=REQUIRED_PYTHON, dest="python_version")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        plan = build_plan(args.root, python_version=args.python_version)
        if args.json or args.dry_run:
            print(json.dumps(plan.as_dict(), indent=2, sort_keys=True))
        if not args.dry_run:
            execute_plan(plan)
    except (BootstrapError, subprocess.CalledProcessError) as exc:
        parser.exit(2, f"bootstrap failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
