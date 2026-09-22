"""CLI for the unified Skeleton application assembly."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import Sequence

from skeleton.app.assembly import (
    checks_ok,
    compose_command,
    find_repo_root,
    load_manifest,
    manifest_payload,
    preflight,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton app",
        description="Validate and operate the repository as one assembled application.",
    )
    sub = parser.add_subparsers(dest="command")

    status = sub.add_parser("status", help="show the canonical application topology")
    status.add_argument("--json", action="store_true", dest="as_json")
    status.add_argument("--live", action="store_true", help="also probe public runtime health")
    status.add_argument("--full", action="store_true", help="include optional full-profile health")
    status.add_argument("--timeout", type=float, default=3.0, help="per-service live probe timeout")

    check = sub.add_parser("check", help="validate the application assembly")
    check.add_argument(
        "--runtime",
        action="store_true",
        help="also require Docker and runtime environment values",
    )
    check.add_argument("--json", action="store_true", dest="as_json")

    plan = sub.add_parser("plan", help="show dependency-aware application startup order")
    plan.add_argument("--full", action="store_true", help="include optional full-profile services")
    plan.add_argument("--json", action="store_true", dest="as_json")

    up = sub.add_parser("up", help="build and start the assembled application")
    up.add_argument("--full", action="store_true", help="include optional full-profile services")
    up.add_argument("--no-build", action="store_true", help="do not rebuild images")
    up.add_argument(
        "--production",
        action="store_true",
        help="use production backend and frontend image stages",
    )
    up.add_argument(
        "--hot",
        action="store_true",
        help="bind repository source into dev containers for hot reload",
    )
    up.add_argument(
        "--no-verify",
        action="store_true",
        help="return after Compose starts without probing public application surfaces",
    )
    up.add_argument("--verify-attempts", type=int, default=12)
    up.add_argument("--verify-delay", type=float, default=1.0)

    sub.add_parser("down", help="stop the assembled application")
    sub.add_parser("ps", help="show assembled service state")

    smoke = sub.add_parser("smoke", help="probe assembled public service health")
    smoke.add_argument("--full", action="store_true", help="probe the full profile")
    smoke.add_argument("--timeout", type=float, default=3.0)
    smoke.add_argument("--attempts", type=int, default=1)
    smoke.add_argument("--delay", type=float, default=1.0)
    smoke.add_argument("--json", action="store_true", dest="as_json")

    logs = sub.add_parser("logs", help="show assembled service logs")
    logs.add_argument("service", nargs="?", default="")
    logs.add_argument("-f", "--follow", action="store_true")

    sub.add_parser("config", help="render and validate the Docker Compose configuration")

    from skeleton.app.installer import configure_setup_parsers

    configure_setup_parsers(sub)
    return parser


def _print_status(
    as_json: bool,
    *,
    live: bool = False,
    full: bool = False,
    timeout: float = 3.0,
) -> int:
    manifest = load_manifest()
    payload = manifest_payload(manifest)
    live_results = ()
    live_ok: bool | None = None

    if live:
        if timeout <= 0:
            print("status timeout must be greater than zero")
            return 2
        from skeleton.app.health import probe_application, probes_ok

        live_results = probe_application(manifest=manifest, full=full, timeout=timeout)
        live_ok = probes_ok(live_results)
        payload["runtime_health"] = {
            "ok": live_ok,
            "full": full,
            "results": [result.to_dict() for result in live_results],
        }

    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if live_ok is not False else 1

    print(f"{manifest.name} application assembly v{manifest.version}")
    print(f"compose: {manifest.compose_file}")
    for service in manifest.services:
        marker = "*" if service.canonical else "-"
        url = f" {service.public_url}" if service.public_url else ""
        profile = f" [{service.profile}]" if service.profile else ""
        print(f"{marker} {service.name:<10} {service.role:<18} {service.kind}{profile}{url}")

    if live:
        print("")
        for result in live_results:
            status = result.status if result.status is not None else "-"
            print(
                f"[{'PASS' if result.ok else 'FAIL'}] "
                f"{result.service:<10} status={status} {result.url} {result.detail}"
            )
        print("runtime: healthy" if live_ok else "runtime: unhealthy")

    return 0 if live_ok is not False else 1


def _print_checks(runtime: bool, as_json: bool) -> int:
    root = find_repo_root()
    checks = preflight(root, runtime=runtime)
    ok = checks_ok(checks)
    if as_json:
        print(
            json.dumps(
                {
                    "ok": ok,
                    "root": str(root),
                    "runtime": runtime,
                    "checks": [check.to_dict() for check in checks],
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(f"assembly root: {root}")
        for check in checks:
            print(f"[{'PASS' if check.ok else 'FAIL'}] {check.message}")
        print("assembly: ready" if ok else "assembly: blocked")
    return 0 if ok else 1


def _run_compose(
    command: Sequence[str],
    root: Path,
    *,
    env_overrides: dict[str, str] | None = None,
) -> int:
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)
    completed = subprocess.run(list(command), cwd=root, check=False, env=env)
    return int(completed.returncode)


def run_app_cli(argv: Sequence[str] | None = None) -> int:
    """Run the application assembly CLI and return a process-style exit code."""

    args = _parser().parse_args(list(argv or ()))
    command = args.command or "status"

    if command == "status":
        return _print_status(
            bool(getattr(args, "as_json", False)),
            live=bool(getattr(args, "live", False)),
            full=bool(getattr(args, "full", False)),
            timeout=float(getattr(args, "timeout", 3.0)),
        )
    if command == "check":
        return _print_checks(bool(args.runtime), bool(args.as_json))
    if command == "plan":
        from skeleton.app.plan import build_plan

        plan = build_plan(full=bool(args.full))
        if bool(args.as_json):
            print(json.dumps(plan.to_dict(), indent=2, sort_keys=True))
        else:
            print(f"assembly profile: {plan.profile}")
            print("requested: " + ", ".join(plan.requested))
            for index, layer in enumerate(plan.layers):
                print(f"layer {index}: " + ", ".join(layer))
            print("startup order: " + " -> ".join(plan.services))
        return 0

    if command in {"preload", "setup", "install"}:
        from skeleton.app.installer import run_setup_command

        return run_setup_command(command, args)


    root = find_repo_root()
    manifest = load_manifest()

    if command == "up":
        if bool(args.production) and bool(args.hot):
            print("--production and --hot are mutually exclusive")
            return 2
        checks = preflight(root, runtime=True, manifest=manifest)
        if not checks_ok(checks):
            for check in checks:
                if not check.ok and check.required:
                    print(f"[FAIL] {check.message}")
            print("application start aborted: runtime preflight failed")
            return 1
        mode = "production" if bool(args.production) else "development"
        exit_code = _run_compose(
            compose_command(
                "up",
                manifest=manifest,
                full=bool(args.full),
                build=not bool(args.no_build),
                hot=bool(args.hot),
            ),
            root,
            env_overrides=manifest.mode_env(mode),
        )
        if exit_code or bool(args.no_verify):
            return exit_code

        from skeleton.app.health import probes_ok, wait_for_application

        try:
            results = wait_for_application(
                manifest=manifest,
                full=bool(args.full),
                timeout=3.0,
                attempts=int(args.verify_attempts),
                delay=float(args.verify_delay),
            )
        except ValueError as exc:
            print(f"invalid startup verification budget: {exc}")
            return 2

        for result in results:
            status = result.status if result.status is not None else "-"
            print(
                f"[{'PASS' if result.ok else 'FAIL'}] "
                f"{result.service:<10} status={status} {result.url} {result.detail}"
            )
        if probes_ok(results):
            print("application start: ready")
            return 0
        print("application start: services launched but readiness verification failed")
        return 1
    if command == "smoke":
        from skeleton.app.health import probes_ok, wait_for_application

        timeout = float(args.timeout)
        attempts = int(args.attempts)
        delay = float(args.delay)
        if timeout <= 0:
            print("smoke timeout must be greater than zero")
            return 2
        try:
            results = wait_for_application(
                manifest=manifest,
                full=bool(args.full),
                timeout=timeout,
                attempts=attempts,
                delay=delay,
            )
        except ValueError as exc:
            print(f"invalid smoke budget: {exc}")
            return 2
        ok = probes_ok(results)
        if bool(args.as_json):
            print(
                json.dumps(
                    {
                        "ok": ok,
                        "full": bool(args.full),
                        "results": [result.to_dict() for result in results],
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            for result in results:
                status = result.status if result.status is not None else "-"
                print(
                    f"[{'PASS' if result.ok else 'FAIL'}] "
                    f"{result.service:<10} status={status} {result.url} {result.detail}"
                )
            print("application smoke: healthy" if ok else "application smoke: unhealthy")
        return 0 if ok else 1
    if command == "down":
        return _run_compose(compose_command("down", manifest=manifest), root)
    if command == "ps":
        return _run_compose(compose_command("ps", manifest=manifest), root)
    if command == "logs":
        return _run_compose(
            compose_command(
                "logs",
                manifest=manifest,
                follow=bool(args.follow),
                service=str(args.service or ""),
            ),
            root,
        )
    if command == "config":
        return _run_compose(compose_command("config", manifest=manifest), root)

    raise AssertionError(f"unhandled app command: {command}")
