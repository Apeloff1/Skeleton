"""Transactional installer plane for the assembled Skeleton application."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from skeleton.app.assembly import (
    CHROMA_FULL_PROFILE_BLOCKED,
    checks_ok,
    compose_command,
    find_repo_root,
    load_manifest,
    preflight,
    public_service_urls,
    runtime_manifest,
)
from skeleton.app.preloader import PreloadReport, inspect_host
from skeleton.app.setup_runtime import SetupResult, ensure_runtime_environment, runtime_source_fingerprint

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
    env: dict[str, str] | None = None,
) -> InstallPhase:
    try:
        # Compose output can contain credentials and unbounded build logs.
        # Discard it instead of retaining it in GUI memory or installer receipts.
        completed = runner(
            list(command),
            cwd=root,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=timeout,
            **({"env": env} if env is not None else {}),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return InstallPhase(label, False, f"{label} failed: {type(exc).__name__}")

    detail = f"{label} completed" if completed.returncode == 0 else f"{label} exited {completed.returncode}"
    if completed.returncode and label == "python-install":
        detail += "; use an activated Python 3.11+ virtual environment and install requirements.txt; inspect package-index access"
    elif completed.returncode:
        detail += "; run app doctor and inspect the named service with app logs; credentials are omitted from this receipt"
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
    if result.warnings:
        # Setup warnings contain only bounded configuration-key diagnostics,
        # not secret material. Never silently report a fully configured AI
        # runtime when the optional provider key or signing seed is missing.
        detail += "; advisories: " + "; ".join(result.warnings)
    return InstallPhase("setup-runtime", True, detail)


def _runtime_source_stable(root: Path, admitted_digest: str) -> bool:
    """Check private .env custody without reading values into receipts.

    This is an epoch fence, not a filesystem transaction: arbitrary external
    writers may still race Docker. Any *observed* mutation denies qualification
    and prevents follow-up admission with stale startup inputs.
    """
    try:
        return runtime_source_fingerprint(root) == admitted_digest
    except (OSError, ValueError, UnicodeError):
        return False


def _runtime_source_rejection() -> InstallPhase:
    return InstallPhase(
        "runtime-source-epoch",
        False,
        "private runtime configuration changed or became unsafe during installation; "
        "services and readiness are not qualified; preserve .env and retry preflight",
    )


def install_application(
    root: Path | None = None,
    *,
    install_python: bool = True,
    start: bool = False,
    full: bool = False,
    production: bool = False,
    hot: bool = False,
    rotate_secrets: bool = False,
    admin_email: str | None = None,
    admin_password_file: Path | None = None,
    bundled_runtime: bool = False,
    runner: Runner = subprocess.run,
) -> InstallReceipt:
    """Run the bounded installer pipeline and return a redacted receipt."""

    root = (root or find_repo_root()).resolve()
    phases: list[InstallPhase] = []

    if full and start:
        return InstallReceipt(
            root=root,
            phases=(InstallPhase("chroma-persistence", False, CHROMA_FULL_PROFILE_BLOCKED),),
        )

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

    try:
        setup = ensure_runtime_environment(
            root,
            rotate_secrets=rotate_secrets,
            admin_email=admin_email,
            admin_password_file=admin_password_file,
        )
    except (OSError, ValueError) as exc:
        phases.append(
            InstallPhase(
                "setup-runtime",
                False,
                f"private runtime configuration could not be written: {type(exc).__name__}",
            )
        )
        return InstallReceipt(root=root, phases=tuple(phases))
    phases.append(_setup_phase(setup))
    for warning in setup.warnings:
        phases.append(InstallPhase("configuration-note", True, warning, required=False))

    if install_python:
        python_phase = _run(
            [sys.executable, "-m", "pip", "install", "-e", "."],
            root=root,
            runner=runner,
            label="python-install",
            timeout=1200.0,
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

    # Admit one process environment before runtime preflight; all later
    # manifest, Compose and readiness decisions consume the same snapshot.
    admitted_process_env = dict(os.environ)
    # Observe the .env source before preflight itself can read its contents.
    # Recheck afterward so configuration changes during validation cannot
    # certify startup using a different source or inode.
    admitted_digest: str | None = None
    if start:
        try:
            # A fresh installed runtime must have a bounded private source.
            # No bypass for a missing or replaced .env, including bundled EXEs.
            admitted_digest = runtime_source_fingerprint(root)
        except (OSError, ValueError, UnicodeError):
            phases.append(_runtime_source_rejection())
            return InstallReceipt(root=root, phases=tuple(phases))
    manifest = load_manifest()
    runtime_checks = preflight(
        root, runtime=True, manifest=manifest, environ=admitted_process_env,
    )
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
    if admitted_digest is not None and not _runtime_source_stable(root, admitted_digest):
        phases.append(_runtime_source_rejection())
        return InstallReceipt(root=root, phases=tuple(phases))
    # A concurrent operator change to os.environ after preflight cannot make
    # startup validate one port while a later probe uses another port.
    try:
        manifest = runtime_manifest(
            manifest, root=root, environ=admitted_process_env,
        )
    except (OSError, ValueError, UnicodeError):
        phases.append(
            InstallPhase(
                "runtime-manifest", False,
                "runtime port configuration invalid, unreadable or changed after preflight",
            )
        )
        return InstallReceipt(root=root, phases=tuple(phases))
    if admitted_digest is not None and not _runtime_source_stable(root, admitted_digest):
        phases.append(_runtime_source_rejection())
        return InstallReceipt(root=root, phases=tuple(phases))

    # Validate precisely the configuration used for startup. The production
    # frontend uses port 8080, unlike the default development Compose model.
    mode = "production" if production else "development"
    compose_env = {**admitted_process_env, **manifest.mode_env(mode), "COMPOSE_REMOVE_ORPHANS": "0"}
    compose_validate = _run(
        compose_command("config", manifest=manifest, full=full, hot=hot),
        root=root,
        runner=runner,
        label="compose-config",
        timeout=60.0,
        env=compose_env,
    )
    phases.append(compose_validate)
    if not compose_validate.ok or not start:
        return InstallReceipt(root=root, phases=tuple(phases))
    if admitted_digest is None or not _runtime_source_stable(root, admitted_digest):
        phases.append(_runtime_source_rejection())
        return InstallReceipt(root=root, phases=tuple(phases))

    try:
        host_urls = public_service_urls(
            root, manifest=manifest, environ=admitted_process_env,
        )
    except (OSError, ValueError, UnicodeError):
        phases.append(
            InstallPhase("public-endpoints", False, "public endpoint configuration unsafe or invalid")
        )
        return InstallReceipt(root=root, phases=tuple(phases))
    if not _runtime_source_stable(root, admitted_digest):
        phases.append(_runtime_source_rejection())
        return InstallReceipt(root=root, phases=tuple(phases))

    try:
        command = compose_command(
            "up",
            manifest=manifest,
            full=full,
            build=True,
            hot=hot,
        )
    except ValueError as exc:
        phases.append(InstallPhase("start", False, str(exc)))
        return InstallReceipt(root=root, phases=tuple(phases))
    try:
        completed = runner(
            list(command),
            cwd=root,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            env=compose_env,
            timeout=1800.0,
        )
        ok = completed.returncode == 0
        detail = "application services started" if ok else f"application start exited {completed.returncode}"
        if not ok:
            detail += "; inspect app doctor and app logs <service>; no credentials are included"
        phases.append(InstallPhase("start", ok, detail))
    except (OSError, subprocess.SubprocessError) as exc:
        phases.append(InstallPhase("start", False, f"application start failed: {type(exc).__name__}"))

    # Even an apparently successful Compose exit cannot attest a startup
    # whose private configuration changed during process execution.
    if admitted_digest is None or not _runtime_source_stable(root, admitted_digest):
        phases.append(_runtime_source_rejection())
        return InstallReceipt(root=root, phases=tuple(phases))

    full_start_ok = phases[-1].ok
    if not full_start_ok:
        # A failed protected-stack start must remain a required failure. When
        # the canonical frontend is independently startable, attempt only its
        # diagnostic surface; never remove backend/engine health fences or
        # promote setup liveness into full application readiness. The same
        # admitted private configuration epoch fences recovery and its probe.
        frontend = manifest.service("frontend")
        if not frontend.depends_on:
            if admitted_digest is None or not _runtime_source_stable(root, admitted_digest):
                phases.append(_runtime_source_rejection())
                return InstallReceipt(root=root, phases=tuple(phases))
            diagnostic_manifest = replace(
                manifest,
                default_services=("frontend",),
                full_services=("frontend",),
            )
            recovery = _run(
                compose_command("up", manifest=diagnostic_manifest, hot=hot),
                root=root,
                runner=runner,
                label="setup-ui-recovery",
                timeout=900.0,
                env=compose_env,
            )
            if admitted_digest is None or not _runtime_source_stable(root, admitted_digest):
                phases.append(_runtime_source_rejection())
                return InstallReceipt(root=root, phases=tuple(phases))
            phases.append(
                InstallPhase(
                    "setup-ui-recovery", recovery.ok,
                    recovery.detail + "; protected application start remains failed",
                    required=False,
                )
            )
            if recovery.ok:
                from skeleton.app.health import probe_local_setup

                probe = probe_local_setup(
                    replace(
                        frontend,
                        public_url=host_urls.get("frontend", frontend.public_url),
                        health_path="/setup",
                    ),
                    timeout=2.0,
                )
                if admitted_digest is None or not _runtime_source_stable(root, admitted_digest):
                    phases.append(_runtime_source_rejection())
                    return InstallReceipt(root=root, phases=tuple(phases))
                phases.append(
                    InstallPhase(
                        "setup-ui-availability", probe.ok,
                        (
                            "local setup route answered directly; backend and AI remain unavailable"
                            if probe.ok
                            else "setup route unavailable; inspect frontend logs"
                        ),
                        required=False,
                    )
                )
        else:
            phases.append(
                InstallPhase(
                    "setup-ui-recovery", False,
                    "frontend has protected startup dependencies; qualify #4682 before independent setup recovery",
                    required=False,
                )
            )

    if full_start_ok:
        from skeleton.app.health import probes_ok, wait_for_application

        results = wait_for_application(
            manifest=manifest,
            full=full,
            timeout=3.0,
            # Cold production startup is dependency ordered: Mongo must become
            # healthy before the engine starts, and the backend waits for both.
            # Their image health checks allow a 60-second start period, so the
            # old twelve-second budget routinely called a healthy first install
            # failed while containers were still inside their declared grace.
            attempts=60,
            delay=2.0,
            public_url_overrides=host_urls,
        )
        if admitted_digest is None or not _runtime_source_stable(root, admitted_digest):
            phases.append(_runtime_source_rejection())
            return InstallReceipt(root=root, phases=tuple(phases))
        healthy = probes_ok(results)
        failed = [result.service for result in results if not result.ok]
        phases.append(
            InstallPhase(
                "readiness",
                healthy,
                (
                    "application runtime is healthy"
                    if healthy
                    else "readiness probes failed: " + ", ".join(failed)
                ),
            )
        )
        if healthy:
            from skeleton.app.first_install import critical_backend_route_report

            # public_service_urls is intentionally a sparse *override* map.
            # On a clean install with default ports it has no "backend" key;
            # use the already resolved canonical manifest URL as the fallback.
            backend_url = host_urls["backend"] if "backend" in host_urls else manifest.service("backend").public_url
            route_status = critical_backend_route_report(backend_url, timeout=3.0)
            routes_ready = route_status["ready"] is True
            phases.append(
                InstallPhase(
                    "critical-api-routes",
                    routes_ready,
                    (
                        "required application API routers are registered"
                        if routes_ready
                        else "required API routes missing or unverified; inspect app doctor --live and /api/health/registry"
                    ),
                )
            )

    if admitted_digest is not None and not _runtime_source_stable(root, admitted_digest):
        phases.append(_runtime_source_rejection())

    return InstallReceipt(root=root, phases=tuple(phases))


def configure_setup_parsers(subparsers: argparse._SubParsersAction) -> None:
    """Attach preloader/setup/installer commands to the application CLI."""

    preload = subparsers.add_parser("preload", help="inspect host readiness without changing files")
    preload.add_argument("--json", action="store_true", dest="as_json")

    setup = subparsers.add_parser("setup", help="create or repair local runtime configuration")
    setup.add_argument("--rotate-secrets", action="store_true")
    setup.add_argument("--admin-email", help="explicit optional operator bootstrap email")
    setup.add_argument(
        "--admin-password-file",
        type=Path,
        help="private file containing the chosen bootstrap password; no password in argv",
    )
    setup.add_argument("--json", action="store_true", dest="as_json")

    install = subparsers.add_parser("install", help="run preloader, setup runtime and installer validation")
    install.add_argument(
        "--skip-python", action="store_true", help="skip editable Python package installation"
    )
    install.add_argument("--start", action="store_true", help="start the assembled app after installation")
    install.add_argument("--full", action="store_true", help="include optional full-profile services")
    install.add_argument(
        "--production", action="store_true", help="install/start using production image stages"
    )
    install.add_argument("--hot", action="store_true", help="start with the hot-reload Compose overlay")
    install.add_argument("--rotate-secrets", action="store_true")
    install.add_argument("--admin-email", help="explicit optional operator bootstrap email")
    install.add_argument(
        "--admin-password-file",
        type=Path,
        help="private file containing a strong operator bootstrap password",
    )
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
        try:
            result = ensure_runtime_environment(
                root,
                rotate_secrets=bool(args.rotate_secrets),
                admin_email=getattr(args, "admin_email", None),
                admin_password_file=getattr(args, "admin_password_file", None),
            )
        except (OSError, ValueError) as exc:
            # Policy errors contain fixed remediation text, never file content.
            message = (
                str(exc)
                if isinstance(exc, ValueError)
                else "private configuration or password file could not be read/written; check paths and permissions"
            )
            if args.as_json:
                print(json.dumps({"ok": False, "error": message}))
            else:
                print("setup blocked: " + message)
            return 1
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
            admin_email=getattr(args, "admin_email", None),
            admin_password_file=getattr(args, "admin_password_file", None),
        )
        return _print_install(receipt, as_json=bool(args.as_json))
    raise ValueError(f"unsupported setup command: {command}")
