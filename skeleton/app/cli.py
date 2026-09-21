"""CLI for the unified Skeleton application assembly."""

from __future__ import annotations

import argparse
import json
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

    check = sub.add_parser("check", help="validate the application assembly")
    check.add_argument(
        "--runtime",
        action="store_true",
        help="also require Docker and runtime environment values",
    )
    check.add_argument("--json", action="store_true", dest="as_json")

    up = sub.add_parser("up", help="build and start the assembled application")
    up.add_argument("--full", action="store_true", help="include optional full-profile services")
    up.add_argument("--no-build", action="store_true", help="do not rebuild images")

    sub.add_parser("down", help="stop the assembled application")
    sub.add_parser("ps", help="show assembled service state")

    logs = sub.add_parser("logs", help="show assembled service logs")
    logs.add_argument("service", nargs="?", default="")
    logs.add_argument("-f", "--follow", action="store_true")

    sub.add_parser("config", help="render and validate the Docker Compose configuration")
    return parser


def _print_status(as_json: bool) -> int:
    manifest = load_manifest()
    payload = manifest_payload(manifest)
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    print(f"{manifest.name} application assembly v{manifest.version}")
    print(f"compose: {manifest.compose_file}")
    for service in manifest.services:
        marker = "*" if service.canonical else "-"
        url = f" {service.public_url}" if service.public_url else ""
        profile = f" [{service.profile}]" if service.profile else ""
        print(f"{marker} {service.name:<10} {service.role:<18} {service.kind}{profile}{url}")
    return 0


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


def _run_compose(command: Sequence[str], root: Path) -> int:
    completed = subprocess.run(list(command), cwd=root, check=False)
    return int(completed.returncode)


def run_app_cli(argv: Sequence[str] | None = None) -> int:
    """Run the application assembly CLI and return a process-style exit code."""

    args = _parser().parse_args(list(argv or ()))
    command = args.command or "status"

    if command == "status":
        return _print_status(bool(getattr(args, "as_json", False)))
    if command == "check":
        return _print_checks(bool(args.runtime), bool(args.as_json))

    root = find_repo_root()
    manifest = load_manifest()

    if command == "up":
        checks = preflight(root, runtime=True, manifest=manifest)
        if not checks_ok(checks):
            for check in checks:
                if not check.ok and check.required:
                    print(f"[FAIL] {check.message}")
            print("application start aborted: runtime preflight failed")
            return 1
        return _run_compose(
            compose_command(
                "up",
                manifest=manifest,
                full=bool(args.full),
                build=not bool(args.no_build),
            ),
            root,
        )
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
