"""Transactional installer plane for the assembled Skeleton application."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import sys
from typing import Callable, Sequence

from skeleton.app.assembly import (
    checks_ok,
    compose_command,
    find_repo_root,
    load_manifest,
    preflight,
)
from skeleton.app.preloader import PreloadReport, inspect_host
from skeleton.app.setup_runtime import SetupResult, ensure_runtime_environment


Runner = Callable[..., subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class InstallPhase:
    name: str
    ok: bool
    detail: str
    required: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "ok": self.ok,
            "detail": self.detail,
            "required": self.required,
        }


@dataclass(frozen=True)
class InstallReceipt:
    root: Path
    phases: tuple[InstallPhase, ...]

    @property
    def ok(self) -> bool:
        return all(phase.ok or not phase.required for phase in self.phases)

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "root": str(self.root),
            "phases": [phase.to_dict() for phase in self.phases],
        }


def _run(
    command: Sequence[str],
    *,
    root: Path,
    runner: Runner,
    label: str,
    timeout: float | None = None,
) -> InstallPhase:
    try:
        completed = runner(
            list(command),
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return InstallPhase(label, False, f"{label} failed: {type(exc).__name__}")

    stdout = (completed.stdout or "").strip().splitlines()
    stderr = (completed.stderr or "").strip().splitlines()
    tail = stdout[-1] if stdout else (stderr[-1] if stderr else "")
    detail = f"{label} completed" if completed.returncode == 0 else f"{label} exited {completed.returncode}"
    if tail:
        detail += f": {tail[:240]}"
    return InstallPhase(label, completed.returncode == 0, detail)


def _preload_phase(report: PreloadReport) -> InstallPhase:
    blockers = [check.code for check in report.checks if check.required and not check.ok]
    if blockers:
        return InstallPhase(
            "preload",
            False,
            "host preloader blocked installation: " + ", ".join(blockers),
        )
    return InstallPhase("preload", True, "host preloader passed")


def _setup_phase(result: SetupResult) -> InstallPhase:
    if result.created:
        detail = f"runtime environment created at {result.env_path}"
    elif result.changed:
        detail = f"runtime environment repaired at {result.env_path}"
    else:
        detail = f"runtime environment already configured at {result.env_path}"
    if result.configured_keys:
        detail += "; configured " + ", ".join(result.configured_keys)
    return InstallPhase("setup-runtime", True, detail)


def install_application(
    root: Path | None = None,
    *,
    install_python: bool = True,
    start: bool = False,
    full: bool = False,
    production: bool = False,
    hot: bool = False,
    rotate_secrets: bool = False,
    bundled_runtime: bool = False,
    runner: Runner = subprocess.run,
) -> InstallReceipt:
    """Run the bounded installer pipeline and return a redacted receipt."""

    root = (root or find_repo_root()).resolve()
    phases: list[InstallPhase] = []

    if production and hot:
        return InstallReceipt(
            root=root,
            phases=(InstallPhase("arguments", False, "--production and --hot are mutually exclusive"),),
        )

    preload = inspect_host(
        root,
        runner=runner,
        require_python=not bundled_runtime,
        require_pip=not bundled_runtime,
    )
    phases.append(_preload_phase(preload))
    if not phases[-1].ok:
        return InstallReceipt(root=root, phases=tuple(phases))

    setup = ensure_runtime_environment(root, rotate_secrets=rotate_secrets)
    phases.append(_setup_phase(setup))

    if install_python:
        python_phase = _run(
            [sys.executable, "-m", "pip", "install", "-e", "."],
            root=root,
            runner=runner,
            label="python-install",
        )
        phases.append(python_phase)
        if not python_phase.ok:
            return InstallReceipt(root=root, phases=tuple(phases))
    else:
        phases.append(
            InstallPhase(
                "python-install",
                True,
                (
                    "Python package installation provided by bundled runtime"
                    if bundled_runtime
                    else "Python package installation skipped by operator"
                ),
                required=False,
            )
        )

    manifest = load_manifest()
    runtime_checks = preflight(root, runtime=True, manifest=manifest)
    runtime_ok = checks_ok(runtime_checks)
    failed_codes = [check.code for check in runtime_checks if check.required and not check.ok]
    phases.append(
        InstallPhase(
            "runtime-preflight",
            runtime_ok,
            (
                "runtime prerequisites passed"
                if runtime_ok
                else "runtime prerequisites failed: " + ", ".join(failed_codes)
            ),
        )
    )
    if not runtime_ok:
        return InstallReceipt(root=root, phases=tuple(phases))

    compose_validate = _run(
        compose_command("config", manifest=manifest),
        root=root,
        runner=runner,
        label="compose-config",
        timeout=60.0,
    )
    phases.append(compose_validate)
    if not compose_validate.ok or not start:
        return InstallReceipt(root=root, phases=tuple(phases))

    mode = "production" if production else "development"
    command = compose_command(
        "up",
        manifest=manifest,
        full=full,
        build=True,
        hot=hot,
    )
    try:
        completed = runner(
            list(command),
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            env={**__import__("os").environ, **manifest.mode_env(mode)},
        )
        ok = completed.returncode == 0
        tail_lines = ((completed.stdout or "") + "\n" + (completed.stderr or "")).strip().splitlines()
        detail = "application services started" if ok else f"application start exited {completed.returncode}"
        if tail_lines:
            detail += f": {tail_lines[-1][:240]}"
        phases.append(InstallPhase("start", ok, detail))
    except (OSError, subprocess.SubprocessError) as exc:
        phases.append(InstallPhase("start", False, f"application start failed: {type(exc).__name__}"))

    if phases[-1].ok:
        from skeleton.app.health import probes_ok, wait_for_application

        results = wait_for_application(
            manifest=manifest,
            full=full,
            timeout=3.0,
            attempts=12,
            delay=1.0,
        )
        healthy = probes_ok(results)
        failed = [result.service for result in results if not result.ok]
        phases.append(
            InstallPhase(
                "readiness",
                healthy,
                "application runtime is healthy"
                if healthy
                else "readiness probes failed: " + ", ".join(failed),
            )
        )

    return InstallReceipt(root=root, phases=tuple(phases))


def configure_setup_parsers(subparsers: argparse._SubParsersAction) -> None:
    """Attach preloader/setup/installer commands to the application CLI."""

    preload = subparsers.add_parser("preload", help="inspect host readiness without changing files")
    preload.add_argument("--json", action="store_true", dest="as_json")

    setup = subparsers.add_parser("setup", help="create or repair local runtime configuration")
    setup.add_argument("--rotate-secrets", action="store_true")
    setup.add_argument("--json", action="store_true", dest="as_json")

    install = subparsers.add_parser("install", help="run preloader, setup runtime and installer validation")
    install.add_argument("--skip-python", action="store_true", help="skip editable Python package installation")
    install.add_argument("--start", action="store_true", help="start the assembled app after installation")
    install.add_argument("--full", action="store_true", help="include optional full-profile services")
    install.add_argument("--production", action="store_true", help="install/start using production image stages")
    install.add_argument("--hot", action="store_true", help="start with the hot-reload Compose overlay")
    install.add_argument("--rotate-secrets", action="store_true")
    install.add_argument("--json", action="store_true", dest="as_json")


def _print_preload(report: PreloadReport, *, as_json: bool) -> int:
    if as_json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        print(f"preloader root: {report.root}")
        print(f"host: {report.platform}; Python {report.python}")
        for check in report.checks:
            required = "" if check.required else " (advisory)"
            print(f"[{'PASS' if check.ok else 'FAIL'}] {check.code}{required}: {check.detail}")
            if not check.ok and check.remediation:
                print(f"       fix: {check.remediation}")
        print("preloader: ready" if report.ready else "preloader: blocked")
    return 0 if report.ready else 1


def _print_setup(result: SetupResult, *, as_json: bool) -> int:
    if as_json:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    else:
        state = "created" if result.created else ("updated" if result.changed else "unchanged")
        print(f"setup runtime: {state} {result.env_path}")
        if result.configured_keys:
            print("configured: " + ", ".join(result.configured_keys))
        if result.preserved_keys:
            print("preserved: " + ", ".join(result.preserved_keys))
        for warning in result.warnings:
            print(f"[WARN] {warning}")
    return 0


def _print_install(receipt: InstallReceipt, *, as_json: bool) -> int:
    if as_json:
        print(json.dumps(receipt.to_dict(), indent=2, sort_keys=True))
    else:
        for phase in receipt.phases:
            required = "" if phase.required else " (optional)"
            print(f"[{'PASS' if phase.ok else 'FAIL'}] {phase.name}{required}: {phase.detail}")
        print("installer: complete" if receipt.ok else "installer: blocked")
    return 0 if receipt.ok else 1


def run_setup_command(command: str, args: argparse.Namespace, root: Path | None = None) -> int:
    root = (root or find_repo_root()).resolve()
    if command == "preload":
        return _print_preload(inspect_host(root), as_json=bool(args.as_json))
    if command == "setup":
        result = ensure_runtime_environment(root, rotate_secrets=bool(args.rotate_secrets))
        return _print_setup(result, as_json=bool(args.as_json))
    if command == "install":
        receipt = install_application(
            root,
            install_python=not bool(args.skip_python),
            start=bool(args.start),
            full=bool(args.full),
            production=bool(args.production),
            hot=bool(args.hot),
            rotate_secrets=bool(args.rotate_secrets),
        )
        return _print_install(receipt, as_json=bool(args.as_json))
    raise ValueError(f"unsupported setup command: {command}")
