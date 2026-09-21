"""Host preloader for the unified Skeleton application.

The preloader is deliberately read-only.  It answers one question before any
installer mutation occurs: can this checkout support the assembled app?
"""

from __future__ import annotations

from dataclasses import dataclass
import platform
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Callable, Sequence

from skeleton.app.assembly import checks_ok, find_repo_root, preflight


Runner = Callable[..., subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class PreloadCheck:
    code: str
    ok: bool
    detail: str
    required: bool = True
    remediation: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "ok": self.ok,
            "detail": self.detail,
            "required": self.required,
            "remediation": self.remediation,
        }


@dataclass(frozen=True)
class PreloadReport:
    root: Path
    platform: str
    python: str
    checks: tuple[PreloadCheck, ...]

    @property
    def ready(self) -> bool:
        return all(check.ok or not check.required for check in self.checks)

    def to_dict(self) -> dict[str, object]:
        return {
            "ready": self.ready,
            "root": str(self.root),
            "platform": self.platform,
            "python": self.python,
            "checks": [check.to_dict() for check in self.checks],
        }


def _command_check(
    command: Sequence[str],
    *,
    code: str,
    label: str,
    remediation: str,
    runner: Runner,
    timeout: float = 5.0,
) -> PreloadCheck:
    try:
        completed = runner(
            list(command),
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return PreloadCheck(
            code=code,
            ok=False,
            detail=f"{label} unavailable: {type(exc).__name__}",
            remediation=remediation,
        )

    output = (completed.stdout or completed.stderr or "").strip().splitlines()
    suffix = f": {output[0][:160]}" if output else ""
    return PreloadCheck(
        code=code,
        ok=completed.returncode == 0,
        detail=(
            f"{label} available{suffix}"
            if completed.returncode == 0
            else f"{label} check failed with exit {completed.returncode}{suffix}"
        ),
        remediation=remediation if completed.returncode else "",
    )


def inspect_host(
    root: Path | None = None,
    *,
    runner: Runner = subprocess.run,
    min_free_bytes: int = 2 * 1024**3,
    recommended_free_bytes: int = 8 * 1024**3,
    require_python: bool = True,
    require_pip: bool = True,
) -> PreloadReport:
    """Return a deterministic, read-only host readiness report."""

    root = (root or find_repo_root()).resolve()
    checks: list[PreloadCheck] = []

    python_ok = sys.version_info >= (3, 11)
    checks.append(
        PreloadCheck(
            code="host:python",
            ok=python_ok,
            required=require_python,
            detail=f"Python {platform.python_version()} ({sys.executable})",
            remediation="Install Python 3.11 or newer." if require_python and not python_ok else "",
        )
    )

    structure = preflight(root, runtime=False)
    checks.append(
        PreloadCheck(
            code="host:assembly",
            ok=checks_ok(structure),
            detail=(
                "repository assembly structure is complete"
                if checks_ok(structure)
                else "repository assembly structure has missing required paths"
            ),
            remediation="Restore the required application assembly files.",
        )
    )

    if require_pip:
        checks.append(
            _command_check(
                [sys.executable, "-m", "pip", "--version"],
                code="host:pip",
                label="pip",
                remediation="Install pip for the active Python interpreter.",
                runner=runner,
            )
        )
    else:
        checks.append(
            PreloadCheck(
                code="host:pip",
                ok=True,
                required=False,
                detail="pip is not required by the bundled application runtime",
            )
        )

    docker = shutil.which("docker")
    checks.append(
        PreloadCheck(
            code="host:docker",
            ok=docker is not None,
            detail=f"Docker executable available at {docker}" if docker else "Docker executable not found",
            remediation="Install Docker Desktop or Docker Engine with the Compose plugin.",
        )
    )
    if docker:
        checks.append(
            _command_check(
                [docker, "compose", "version"],
                code="host:compose",
                label="Docker Compose",
                remediation="Install or enable the Docker Compose v2 plugin.",
                runner=runner,
            )
        )

    usage = shutil.disk_usage(root)
    checks.append(
        PreloadCheck(
            code="host:disk",
            ok=usage.free >= min_free_bytes,
            detail=f"{usage.free / 1024**3:.1f} GiB free on application filesystem",
            remediation=f"Free at least {min_free_bytes / 1024**3:.0f} GiB before installing.",
        )
    )
    checks.append(
        PreloadCheck(
            code="host:disk-recommended",
            ok=usage.free >= recommended_free_bytes,
            required=False,
            detail=(
                f"recommended Docker build headroom available ({usage.free / 1024**3:.1f} GiB)"
                if usage.free >= recommended_free_bytes
                else f"less than recommended {recommended_free_bytes / 1024**3:.0f} GiB Docker build headroom"
            ),
            remediation="Free additional disk space for faster, safer image builds.",
        )
    )

    env_exists = (root / ".env").is_file()
    checks.append(
        PreloadCheck(
            code="host:env",
            ok=env_exists,
            required=False,
            detail=".env already exists" if env_exists else ".env will be created during setup",
        )
    )

    return PreloadReport(
        root=root,
        platform=f"{platform.system()} {platform.machine()}",
        python=platform.python_version(),
        checks=tuple(checks),
    )
