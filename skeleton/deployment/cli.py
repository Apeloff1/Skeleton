"""``python -m skeleton deploy`` — self-host deployment CLI.

Sub-commands::

    profiles                       list registered self-host profiles
    show      [profile options]    effective profile (secrets masked) + fingerprint
    validate  [profile options]    fail-closed config validation (exit 2 on errors)
    env       [profile options]    render the runtime .env (masked unless --out/--reveal)
    check     [profile options]    host preflight: startup/liveness/readiness checks
    probe     --url URL            HTTP live/ready probes against a running instance
    manifest  [--root R] [--out F] [--verify F]   packaging manifest build/verify
    units     --format systemd|compose            render supervisor definitions
    boot      [profile options]    one-command local boot (validate → preflight → serve)

Profile options (shared): ``--profile NAME``, ``--profile-file F.json``,
``--env-file F``, ``--data-dir D``, ``--host H``, ``--port P``,
``--set key=value`` (repeatable; ``store.<name>=path`` overrides one store),
``--no-environ`` (ignore ``SKL_*`` variables from the calling shell).

Exit codes: 0 ok, 1 check/boot failure, 2 invalid configuration or usage.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, TextIO

from .boot import BootOptions, Booter
from .envfile import EnvFileError, load_env_file, render_env
from .health import CheckKind, build_preflight_registry, build_runtime_probe_registry
from .manifest import ManifestError, build_manifest, load_manifest, verify_manifest, write_manifest
from .profile import ProfileError, SelfHostProfile, list_profiles, resolve_profile
from .units import render_compose_service, render_systemd_unit
from .validation import validate_profile

__all__ = ["build_parser", "run_deploy_cli"]

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_CONFIG = 2


class _ArgumentError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    """ArgumentParser that raises instead of calling ``sys.exit``."""

    def error(self, message: str) -> None:  # type: ignore[override]
        raise _ArgumentError(message)


def _add_profile_options(parser: argparse.ArgumentParser) -> None:
    group = parser.add_argument_group("profile")
    group.add_argument("--profile", default="local", help="named profile (default: local)")
    group.add_argument("--profile-file", help="JSON profile document (overrides --profile)")
    group.add_argument("--env-file", help="dotenv file overlaid on the profile")
    group.add_argument("--data-dir", help="durable state directory")
    group.add_argument("--in-memory", action="store_true", help="no data dir: every store in memory")
    group.add_argument("--host", help="bind host")
    group.add_argument("--port", type=int, help="bind port")
    group.add_argument("--set", dest="assignments", action="append", default=[], metavar="KEY=VALUE",
                       help="override any profile field (repeatable)")
    group.add_argument("--no-environ", action="store_true", help="ignore SKL_* variables from the environment")


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="python -m skeleton deploy", description="Skeleton self-host deployment tooling",
                     add_help=True)
    sub = parser.add_subparsers(dest="action", metavar="ACTION", parser_class=_Parser)

    sub.add_parser("profiles", help="list registered profiles")

    show = sub.add_parser("show", help="show the effective profile")
    _add_profile_options(show)

    validate = sub.add_parser("validate", help="validate the effective profile")
    _add_profile_options(validate)
    validate.add_argument("--no-fs", action="store_true", help="skip filesystem checks")
    validate.add_argument("--no-settings", action="store_true", help="skip runtime settings parity")
    validate.add_argument("--strict", action="store_true", help="treat warnings as errors")

    env = sub.add_parser("env", help="render the runtime environment")
    _add_profile_options(env)
    env.add_argument("--out", help="write a 0600 env file instead of printing")
    env.add_argument("--reveal", action="store_true", help="print secrets in clear text")
    env.add_argument("--json", action="store_true", help="print as JSON object")

    check = sub.add_parser("check", help="run host preflight checks")
    _add_profile_options(check)
    check.add_argument("--kind", choices=["all", "startup", "liveness", "readiness"], default="all")
    check.add_argument("--no-network", action="store_true", help="skip Mongo/Chroma reachability")
    check.add_argument("--no-port", action="store_true", help="skip bind-port availability")

    probe = sub.add_parser("probe", help="probe a running instance")
    probe.add_argument("--url", help="base URL (default: the profile's base URL)")
    probe.add_argument("--timeout", type=float, default=3.0)
    _add_profile_options(probe)

    manifest = sub.add_parser("manifest", help="build or verify the packaging manifest")
    manifest.add_argument("--root", default=".", help="repository/install root")
    manifest.add_argument("--out", help="write the full manifest JSON here")
    manifest.add_argument("--verify", metavar="MANIFEST", help="verify ROOT against an existing manifest")
    manifest.add_argument("--git-sha", default="", help="record the source commit")
    manifest.add_argument("--with-profile", action="store_true", help="embed the redacted profile")
    manifest.add_argument("--full", action="store_true", help="print every file entry (default: summary)")
    _add_profile_options(manifest)

    units = sub.add_parser("units", help="render systemd/compose definitions")
    units.add_argument("--format", choices=["systemd", "compose"], default="systemd")
    units.add_argument("--python", default="/usr/bin/python3", help="systemd: interpreter path")
    units.add_argument("--workdir", default="/opt/skeleton", help="systemd: WorkingDirectory")
    units.add_argument("--unit-env-file", default="/etc/skeleton/skeleton.env", help="systemd: EnvironmentFile")
    units.add_argument("--user", default="skeleton", help="systemd: service user")
    units.add_argument("--image", help="compose: use a prebuilt image instead of building")
    units.add_argument("--out", help="write to a file instead of printing")
    _add_profile_options(units)

    boot = sub.add_parser("boot", help="one-command local boot")
    _add_profile_options(boot)
    boot.add_argument("--dry-run", action="store_true", help="plan only; no side effects")
    boot.add_argument("--no-wait", action="store_true", help="do not wait for readiness")
    boot.add_argument("--detach", action="store_true", help="return once ready; log to --log")
    boot.add_argument("--log", default=".skeleton/server.log", help="log file when detached")
    boot.add_argument("--timeout", type=float, default=90.0, help="readiness timeout in seconds")
    boot.add_argument("--write-env", metavar="PATH", help="persist the effective env (0600)")
    boot.add_argument("--generate-token", action="store_true", help="mint an engine service token if missing")
    boot.add_argument("--skip-preflight", action="store_true")
    boot.add_argument("--no-settings", action="store_true", help="skip runtime settings parity check")
    boot.add_argument("--no-network", action="store_true", help="skip Mongo/Chroma reachability")
    boot.add_argument("--reload", action="store_true", help="uvicorn --reload (development)")
    return parser


def _resolve(args: argparse.Namespace, environ: Mapping[str, str]) -> SelfHostProfile:
    overlay: Optional[Dict[str, str]] = None
    if getattr(args, "env_file", None):
        overlay = load_env_file(args.env_file)
    overrides: Dict[str, Any] = {"host": args.host, "port": args.port}
    if args.in_memory:
        overrides["data_dir"] = ""
    elif args.data_dir is not None:
        overrides["data_dir"] = args.data_dir
    return resolve_profile(
        args.profile,
        profile_file=args.profile_file,
        env_overlay=overlay,
        environ=None if args.no_environ else environ,
        overrides={k: v for k, v in overrides.items() if v is not None},
        assignments=args.assignments,
    )


def _dump(payload: Any, out: TextIO) -> None:
    out.write(json.dumps(payload, indent=2, default=str) + "\n")


def _write_text(path: str, text: str) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def _cmd_profiles(_args: argparse.Namespace, _env: Mapping[str, str], out: TextIO, _err: TextIO) -> int:
    _dump({"kind": "deployment_profiles", "profiles": list_profiles()}, out)
    return EXIT_OK


def _cmd_show(args: argparse.Namespace, env: Mapping[str, str], out: TextIO, _err: TextIO) -> int:
    profile = _resolve(args, env)
    _dump({"kind": "deployment_profile", "fingerprint": profile.fingerprint(), "profile": profile.to_dict()}, out)
    return EXIT_OK


def _cmd_validate(args: argparse.Namespace, env: Mapping[str, str], out: TextIO, _err: TextIO) -> int:
    profile = _resolve(args, env)
    report = validate_profile(profile, check_filesystem=not args.no_fs, check_settings=not args.no_settings)
    payload = report.to_dict()
    payload["strict"] = bool(args.strict)
    _dump(payload, out)
    if not report.ok or (args.strict and report.warnings):
        return EXIT_CONFIG
    return EXIT_OK


def _cmd_env(args: argparse.Namespace, env: Mapping[str, str], out: TextIO, err: TextIO) -> int:
    from .envfile import write_env_file

    profile = _resolve(args, env)
    if args.out:
        header = (f"Skeleton self-host environment — profile {profile.name}\n"
                  f"fingerprint {profile.fingerprint()}\nContains secrets: keep 0600.")
        path = write_env_file(args.out, profile.to_env(include_secrets=True), header=header)
        _dump({"kind": "deployment_env_file", "path": str(path), "variables": len(profile.to_env())}, out)
        return EXIT_OK
    mapping = profile.to_env(include_secrets=args.reveal)
    if args.json:
        _dump(mapping, out)
    else:
        out.write(render_env(mapping, header=f"profile {profile.name} ({profile.fingerprint()[:12]})",
                             redact=not args.reveal))
    return EXIT_OK


def _cmd_check(args: argparse.Namespace, env: Mapping[str, str], out: TextIO, _err: TextIO) -> int:
    profile = _resolve(args, env).absolutized()
    registry = build_preflight_registry(profile, include_network=not args.no_network, include_port=not args.no_port)
    kinds = None if args.kind == "all" else [CheckKind(args.kind)]
    report = registry.run(kinds)
    payload = report.to_dict()
    payload["profile"] = profile.name
    _dump(payload, out)
    return report.exit_code()


def _cmd_probe(args: argparse.Namespace, env: Mapping[str, str], out: TextIO, _err: TextIO) -> int:
    url = args.url or _resolve(args, env).base_url
    if not url.startswith(("http://", "https://")):
        raise _ArgumentError("--url must be an http(s) URL")
    report = build_runtime_probe_registry(url, timeout_s=args.timeout).run()
    payload = report.to_dict()
    payload["url"] = url
    _dump(payload, out)
    return report.exit_code()


def _cmd_manifest(args: argparse.Namespace, env: Mapping[str, str], out: TextIO, _err: TextIO) -> int:
    if args.verify:
        manifest = load_manifest(args.verify)
        diff = verify_manifest(manifest, args.root)
        _dump(diff.to_dict(), out)
        return EXIT_OK if diff.ok else EXIT_FAIL
    profile = _resolve(args, env) if args.with_profile else None
    manifest = build_manifest(args.root, profile=profile, git_sha=args.git_sha)
    if args.out:
        write_manifest(manifest, args.out)
        payload = manifest.summary()
        payload["path"] = args.out
        _dump(payload, out)
    else:
        _dump(manifest.to_dict() if args.full else manifest.summary(), out)
    return EXIT_OK


def _cmd_units(args: argparse.Namespace, env: Mapping[str, str], out: TextIO, _err: TextIO) -> int:
    profile = _resolve(args, env)
    if args.format == "systemd":
        text = render_systemd_unit(profile, python=args.python, working_directory=args.workdir,
                                   env_file=args.unit_env_file or None, user=args.user)
    else:
        text = render_compose_service(profile, image=args.image)
    if args.out:
        _write_text(args.out, text)
        _dump({"kind": "deployment_units", "format": args.format, "path": args.out}, out)
    else:
        out.write(text)
    return EXIT_OK


BooterFactory = Callable[..., Booter]


def _cmd_boot(args: argparse.Namespace, env: Mapping[str, str], out: TextIO, err: TextIO,
              booter_factory: BooterFactory = Booter) -> int:
    profile = _resolve(args, env)
    options = BootOptions(
        dry_run=args.dry_run,
        wait_ready=not args.no_wait,
        foreground=not args.detach,
        ready_timeout_s=args.timeout,
        write_env=args.write_env,
        generate_token=args.generate_token,
        skip_preflight=args.skip_preflight,
        check_settings=not args.no_settings,
        network_checks=not args.no_network,
        reload=args.reload,
        log_path=args.log if args.detach else None,
    )

    def emit(line: str) -> None:
        err.write(line + "\n")
        err.flush()

    booter = booter_factory(profile, options, emit=emit, base_env=env)
    result = booter.run()
    _dump(result.to_dict(), out)
    return result.exit_code()


_HANDLERS = {
    "profiles": _cmd_profiles,
    "show": _cmd_show,
    "validate": _cmd_validate,
    "env": _cmd_env,
    "check": _cmd_check,
    "probe": _cmd_probe,
    "manifest": _cmd_manifest,
    "units": _cmd_units,
    "boot": _cmd_boot,
}


def run_deploy_cli(
    argv: Sequence[str],
    *,
    environ: Optional[Mapping[str, str]] = None,
    out: Optional[TextIO] = None,
    err: Optional[TextIO] = None,
    booter_factory: Optional[BooterFactory] = None,
) -> int:
    """Entry point used by ``python -m skeleton deploy``; returns an exit code."""

    out = out or sys.stdout
    err = err or sys.stderr
    env = dict(os.environ if environ is None else environ)
    args_list: List[str] = list(argv)
    if not args_list or args_list[0] in ("help", "-h", "--help"):
        out.write((__doc__ or "").strip() + "\n")
        return EXIT_OK
    parser = build_parser()
    try:
        args = parser.parse_args(args_list)
    except _ArgumentError as exc:
        err.write(f"deploy: {exc}\n")
        return EXIT_CONFIG
    except SystemExit as exc:  # --help on a sub-command
        return int(exc.code or 0)
    handler = _HANDLERS.get(args.action or "")
    if handler is None:
        err.write(f"deploy: unknown action {args.action!r}\n")
        return EXIT_CONFIG
    try:
        if handler is _cmd_boot and booter_factory is not None:
            return _cmd_boot(args, env, out, err, booter_factory=booter_factory)
        return handler(args, env, out, err)
    except (ProfileError, EnvFileError, ManifestError, _ArgumentError) as exc:
        _dump({"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}, out)
        return EXIT_CONFIG
