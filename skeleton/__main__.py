"""Skeleton CLI entry point.

Usage:
    python -m skeleton <command> [options]

Commands:
    app         Unified application assembly (status/check/up/down/ps/logs/smoke)
    run         GameForge build (--answers JSON --playtest off|auto|require --repair-mode apply|suggest)
    forge       Blueprint compilation and materialization
    test        Run test suites
    dev         Developer CLI (scaffold, wizard, health, visualize)
    eras        List GameForge era dialects
    generations List hardware generations
    plan        Jeeves BuildPlan for a vision / era
    cockpit     Durable creator steering (BIND ERA, BIND ARCHETYPE, SNAPSHOT --out, RESTORE)
    walk        Prove spawn→extract on the emitted door graph
                (--mode thermal, --seed S, --all-eras, --steps, --json)
    doctor      Check forge prerequisites (eras, walk smoke, output dir, Godot)
    creator     Canonical typed creator command surface (create/edit/test/preview/export)
    contracts   Show the shared API/CLI feature-parity contract
    capabilities Show the stable machine-readable capability manifest
                Use `capabilities --lifecycle` for resolvable/loaded status
                Use `capabilities --plane-audit` for the F-15 plane audit
                Use `capabilities --boot-audit` for the genesis/BOOT_PHASES audit
                Use `capabilities --export-audit` for manifest export drift
                Use `capabilities --route-audit` for main-router API_ROUTES drift
                Use `capabilities --hmac-audit` for HMAC open-prefix vs API_ROUTES drift
                Use `capabilities --cli-audit` for developer CLI vs CLI_COMMANDS drift
                Use `capabilities --template-audit` for scaffold TEMPLATES drift
                Use `capabilities --sidecar-audit` for GameForge/command sidecar routes
                Use `capabilities --domain-audit` for gate-domain vs API_ROUTES mapping
                Use `capabilities --cortex-audit` for unmounted cortex register_routes
                Use `capabilities --mounted-audit` for create_app swarm/cockpit mounts
                Use `capabilities --main-cli-audit` for python -m skeleton help vs dispatch
                Use `capabilities --app-audit` for create_app inline GET / and /cortex/status
                Use `capabilities --charter-audit` for require_charter domain/action pairs
                Use `capabilities --contract-audit` for CommandSpec vs runtime register
                Use `capabilities --live-hmac-audit` for HMAC prefixes vs live handlers
                Use `capabilities --nested-audit` for nested include_router mounts
                Use `capabilities --env-audit` for SKELETON_OWN / HMAC env flags
                Use `capabilities --view-audit` for capability-view flag inventory
                Use `capabilities --idempotency-audit` for IdempotencyGuard handlers
                Use `capabilities --seal-audit` for live require_seal versus HMAC open
                Use `capabilities --admit-audit` for WriteAdmit mutating methods
                Use `capabilities --limit-audit` for SKELETON_GATE_* body/header limits
                Use `capabilities --shared-audit` for status/config shared-command mapping
                Use `capabilities --stack-audit` for install_gate middleware order
                Use `capabilities --allow-audit` for MATERIALISE_TARGETS / curve allow-lists
                Use `capabilities --version-audit` for advertised version identity
                Use `capabilities --authz-audit` for mutating vs auth_required
                Use `capabilities --dev-audit` for opt-in public-dev HMAC prefixes
                Use `capabilities --token-audit` for SKELETON_PUBLIC_DEV_SURFACES tokens
                Use `capabilities --mode-audit` for SessionMode core vs llm_core identity
                Use `capabilities --codename-audit` for advertised codename identity
                Use `capabilities --cver-audit` for command CONTRACT_VERSION identity
                Use `capabilities --ttl-audit` for HMAC/idempotency TTL identity
    invoke      Execute the versioned unified request envelope
    command     Execute a shared command: command <name> ['{...json...}']
    status      Shared runtime status command
    config      Shared non-secret configuration command
    help        Show this help message
"""

from __future__ import annotations

import json
import sys
from typing import Any, List, Optional


def _cmd_contracts(_rest: List[str]) -> int:
    from skeleton.application import parity_matrix

    print(json.dumps(parity_matrix(), indent=2, default=str))
    return 0


def _cmd_capabilities(rest: List[str]) -> int:
    from skeleton.application import (
        capability_lifecycle_snapshot,
        capability_manifest,
        export_audit_snapshot,
        genesis_boot_audit_snapshot,
        plane_audit_snapshot,
        api_route_audit_snapshot,
        hmac_open_audit_snapshot,
        developer_cli_audit_snapshot,
        template_audit_snapshot,
        sidecar_route_audit_snapshot,
        gate_domain_audit_snapshot,
        cortex_route_audit_snapshot,
        mounted_route_audit_snapshot,
        main_cli_audit_snapshot,
        app_route_audit_snapshot,
        charter_audit_snapshot,
        contract_audit_snapshot,
        live_hmac_audit_snapshot,
        nested_router_audit_snapshot,
        env_flag_audit_snapshot,
        capability_view_audit_snapshot,
        idempotency_audit_snapshot,
        seal_audit_snapshot,
        admit_write_audit_snapshot,
        gate_limit_audit_snapshot,
        cli_shared_audit_snapshot,
        gate_stack_audit_snapshot,
        allow_list_audit_snapshot,
        version_audit_snapshot,
        authz_audit_snapshot,
        open_dev_audit_snapshot,
        dev_token_audit_snapshot,
        session_mode_audit_snapshot,
        codename_audit_snapshot,
        contract_version_audit_snapshot,
        ttl_audit_snapshot,
    )

    flags = {item.strip().lower() for item in rest if item.strip()}
    aliases = {
        "lifecycle": {"--lifecycle", "lifecycle"},
        "plane_audit": {"--plane-audit", "plane-audit", "--plane_audit", "plane_audit"},
        "boot_audit": {"--boot-audit", "boot-audit", "--boot_audit", "boot_audit"},
        "export_audit": {"--export-audit", "export-audit", "--export_audit", "export_audit"},
        "route_audit": {"--route-audit", "route-audit", "--route_audit", "route_audit"},
        "hmac_audit": {"--hmac-audit", "hmac-audit", "--hmac_audit", "hmac_audit"},
        "cli_audit": {"--cli-audit", "cli-audit", "--cli_audit", "cli_audit"},
        "template_audit": {"--template-audit", "template-audit", "--template_audit", "template_audit"},
        "sidecar_audit": {"--sidecar-audit", "sidecar-audit", "--sidecar_audit", "sidecar_audit"},
        "domain_audit": {"--domain-audit", "domain-audit", "--domain_audit", "domain_audit"},
        "cortex_audit": {"--cortex-audit", "cortex-audit", "--cortex_audit", "cortex_audit"},
        "mounted_audit": {"--mounted-audit", "mounted-audit", "--mounted_audit", "mounted_audit"},
        "main_cli_audit": {"--main-cli-audit", "main-cli-audit", "--main_cli_audit", "main_cli_audit"},
        "app_audit": {"--app-audit", "app-audit", "--app_audit", "app_audit"},
        "charter_audit": {"--charter-audit", "charter-audit", "--charter_audit", "charter_audit"},
        "contract_audit": {"--contract-audit", "contract-audit", "--contract_audit", "contract_audit"},
        "live_hmac_audit": {"--live-hmac-audit", "live-hmac-audit", "--live_hmac_audit", "live_hmac_audit"},
        "nested_audit": {"--nested-audit", "nested-audit", "--nested_audit", "nested_audit"},
        "env_audit": {"--env-audit", "env-audit", "--env_audit", "env_audit"},
        "view_audit": {"--view-audit", "view-audit", "--view_audit", "view_audit"},
        "idempotency_audit": {"--idempotency-audit", "idempotency-audit", "--idempotency_audit", "idempotency_audit"},
        "seal_audit": {"--seal-audit", "seal-audit", "--seal_audit", "seal_audit"},
        "admit_audit": {"--admit-audit", "admit-audit", "--admit_audit", "admit_audit"},
        "limit_audit": {"--limit-audit", "limit-audit", "--limit_audit", "limit_audit"},
        "shared_audit": {"--shared-audit", "shared-audit", "--shared_audit", "shared_audit"},
        "stack_audit": {"--stack-audit", "stack-audit", "--stack_audit", "stack_audit"},
        "allow_audit": {"--allow-audit", "allow-audit", "--allow_audit", "allow_audit"},
        "version_audit": {"--version-audit", "version-audit", "--version_audit", "version_audit"},
        "authz_audit": {"--authz-audit", "authz-audit", "--authz_audit", "authz_audit"},
        "dev_audit": {"--dev-audit", "dev-audit", "--dev_audit", "dev_audit"},
        "token_audit": {"--token-audit", "token-audit", "--token_audit", "token_audit"},
        "mode_audit": {"--mode-audit", "mode-audit", "--mode_audit", "mode_audit"},
        "codename_audit": {"--codename-audit", "codename-audit", "--codename_audit", "codename_audit"},
        "cver_audit": {"--cver-audit", "cver-audit", "--cver_audit", "cver_audit"},
        "ttl_audit": {"--ttl-audit", "ttl-audit", "--ttl_audit", "ttl_audit"},
    }
    allowed = set().union(*aliases.values())
    unknown = flags - allowed
    if unknown:
        print(f"Unknown capabilities option: {sorted(unknown)[0]}")
        return 2
    selected = [name for name, names in aliases.items() if flags & names]
    if len(selected) > 1:
        print(f"{' and '.join(selected)} are mutually exclusive")
        return 2
    view = selected[0] if selected else ""
    if view == "ttl_audit":
        payload = ttl_audit_snapshot()
    elif view == "cver_audit":
        payload = contract_version_audit_snapshot()
    elif view == "codename_audit":
        payload = codename_audit_snapshot()
    elif view == "mode_audit":
        payload = session_mode_audit_snapshot()
    elif view == "token_audit":
        payload = dev_token_audit_snapshot()
    elif view == "dev_audit":
        payload = open_dev_audit_snapshot()
    elif view == "authz_audit":
        payload = authz_audit_snapshot()
    elif view == "version_audit":
        payload = version_audit_snapshot()
    elif view == "allow_audit":
        payload = allow_list_audit_snapshot()
    elif view == "stack_audit":
        payload = gate_stack_audit_snapshot()
    elif view == "shared_audit":
        payload = cli_shared_audit_snapshot()
    elif view == "limit_audit":
        payload = gate_limit_audit_snapshot()
    elif view == "admit_audit":
        payload = admit_write_audit_snapshot()
    elif view == "seal_audit":
        payload = seal_audit_snapshot()
    elif view == "idempotency_audit":
        payload = idempotency_audit_snapshot()
    elif view == "view_audit":
        payload = capability_view_audit_snapshot()
    elif view == "env_audit":
        payload = env_flag_audit_snapshot()
    elif view == "nested_audit":
        payload = nested_router_audit_snapshot()
    elif view == "live_hmac_audit":
        payload = live_hmac_audit_snapshot()
    elif view == "contract_audit":
        payload = contract_audit_snapshot()
    elif view == "charter_audit":
        payload = charter_audit_snapshot()
    elif view == "app_audit":
        payload = app_route_audit_snapshot()
    elif view == "main_cli_audit":
        payload = main_cli_audit_snapshot()
    elif view == "mounted_audit":
        payload = mounted_route_audit_snapshot()
    elif view == "cortex_audit":
        payload = cortex_route_audit_snapshot()
    elif view == "domain_audit":
        payload = gate_domain_audit_snapshot()
    elif view == "sidecar_audit":
        payload = sidecar_route_audit_snapshot()
    elif view == "template_audit":
        payload = template_audit_snapshot()
    elif view == "cli_audit":
        payload = developer_cli_audit_snapshot()
    elif view == "hmac_audit":
        payload = hmac_open_audit_snapshot()
    elif view == "route_audit":
        payload = api_route_audit_snapshot()
    elif view == "export_audit":
        payload = export_audit_snapshot()
    elif view == "boot_audit":
        payload = genesis_boot_audit_snapshot()
    elif view == "plane_audit":
        payload = plane_audit_snapshot()
    elif view == "lifecycle":
        payload = capability_lifecycle_snapshot()
    else:
        payload = capability_manifest()
    print(json.dumps(payload, indent=2, default=str))
    return 0


def _boot_runtime_if_needed(state: Any, command: str) -> None:
    if command in {"run", "tool", "memory", "admin", "retrieve", "plan", "evidence"} and state.genesis is None:
        from skeleton.genesis import Genesis

        state.wire_from_genesis(Genesis(seed=42).boot())


def _print_contract_error(*, command: str, code: str, message: str, exit_code: int, correlation_id: str = "") -> int:
    from skeleton.application import CONTRACT_VERSION, SCHEMA_VERSION, SUPPORTED_MODE

    payload = {
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "command": command,
        "ok": False,
        "mode": SUPPORTED_MODE,
        "correlation_id": correlation_id,
        "error": {"code": code, "message": message},
    }
    print(json.dumps(payload, indent=2))
    return exit_code


def _cmd_invoke(rest: List[str]) -> int:
    from skeleton.api.server import get_state
    from skeleton.application import CommandError, invoke_unified, normalize_request

    if not rest:
        return _print_contract_error(
            command="",
            code="invalid_argument",
            message="invoke envelope JSON is required",
            exit_code=2,
        )
    raw_payload = " ".join(rest).strip()
    try:
        decoded = json.loads(raw_payload)
    except json.JSONDecodeError:
        return _print_contract_error(
            command="",
            code="invalid_argument",
            message="invalid JSON payload",
            exit_code=2,
        )
    if not isinstance(decoded, dict):
        return _print_contract_error(
            command="",
            code="invalid_argument",
            message="invoke envelope must be a JSON object",
            exit_code=2,
        )

    try:
        request = normalize_request(decoded)
    except CommandError:
        result = invoke_unified(None, decoded)
        print(json.dumps(result.to_payload(), indent=2, default=str))
        return result.exit_code

    state = get_state()
    _boot_runtime_if_needed(state, request.command)
    result = invoke_unified(state, decoded)
    print(json.dumps(result.to_payload(), indent=2, default=str))
    return result.exit_code


def _cmd_shared_command(rest: List[str]) -> int:
    from skeleton.api.server import get_state
    from skeleton.application import build_runtime_command_service

    if not rest:
        return _print_contract_error(
            command="",
            code="invalid_command",
            message="command name is required",
            exit_code=2,
        )

    command = rest[0].strip().lower()
    payload = {}
    if len(rest) > 1:
        raw_payload = " ".join(rest[1:]).strip()
        try:
            decoded = json.loads(raw_payload)
        except json.JSONDecodeError:
            return _print_contract_error(
                command=command,
                code="invalid_argument",
                message="invalid JSON payload",
                exit_code=2,
            )
        if not isinstance(decoded, dict):
            return _print_contract_error(
                command=command,
                code="invalid_argument",
                message="command payload must be a JSON object",
                exit_code=2,
            )
        payload = decoded

    state = get_state()
    _boot_runtime_if_needed(state, command)

    result = build_runtime_command_service(state).execute(command, payload)
    print(json.dumps(result.to_payload(), indent=2, default=str))
    return result.exit_code


def _cmd_eras(rest: List[str]) -> int:
    from skeleton.forge.walk_cli import run_eras
    return run_eras(rest)


def _cmd_generations(_rest: List[str]) -> int:
    from skeleton.forge.hardware import catalog
    for g in catalog():
        print(f"{g['key']:10} {g['label']:16} {g['viewport'][0]}x{g['viewport'][1]}  {g['tagline']}")
    return 0


def _cmd_plan(rest: List[str]) -> int:
    from skeleton.cortex.live import live_jeeves, persist
    vision = " ".join(rest).strip()
    out = live_jeeves().plan_build(vision=vision)
    persist()
    print(json.dumps(out, indent=2, default=str))
    return 0


def _cmd_cockpit(rest: List[str]) -> int:
    """Execute an operator command against durable, bounded creator steering."""
    from pathlib import Path
    from skeleton.context.cockpit import Cockpit, CockpitError
    from skeleton.context.operator_state import (
        capture_steering, read_steering, restore_cockpit, write_steering,
    )

    try:
        saved = read_steering()
        cockpit = restore_cockpit(saved) if saved else Cockpit()
        if rest and rest[0].upper() == "RESTORE":
            if len(rest) != 2:
                raise ValueError("usage: cockpit RESTORE <snapshot.json>")
            incoming = read_steering(Path(rest[1]))
            if incoming is None:
                raise ValueError("cockpit snapshot does not exist")
            write_steering(incoming)
            out = {"ok": True, "verb": "RESTORE",
                   "result": restore_cockpit(incoming).snapshot()}
        elif rest and rest[0].upper() == "SNAPSHOT" and len(rest) == 3 and rest[1] == "--out":
            location = write_steering(
                capture_steering(cockpit, era_bound=bool(saved and saved["era_bound"])),
                Path(rest[2]),
            )
            out = {"ok": True, "verb": "SNAPSHOT", "path": str(location),
                   "result": cockpit.snapshot()}
        elif rest and rest[0].upper() == "SNAPSHOT" and len(rest) != 1:
            raise ValueError("usage: cockpit SNAPSHOT [--out snapshot.json]")
        else:
            out = cockpit.apply(" ".join(rest).strip())
            verb = out["verb"]
            if verb in {"BIND", "SET", "LERP", "BLEND", "DETECT"}:
                era_bound = bool(saved and saved["era_bound"])
                if verb in {"DETECT", "LERP"} or (
                    verb == "BIND" and len(rest) > 1 and rest[1].upper() == "ERA"
                ):
                    era_bound = True
                elif verb == "BLEND":
                    era_bound = False
                write_steering(capture_steering(cockpit, era_bound=era_bound))
    except (OSError, ValueError, CockpitError) as exc:
        print(f"cockpit error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(out, indent=2, default=str))
    return 0

def _parse_walk_args(rest: List[str]):
    era = "extraction_now"
    blend = None
    t = 0.5
    as_json = False
    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--era" and i + 1 < len(rest):
            era = rest[i + 1]; i += 2
        elif a == "--blend" and i + 2 < len(rest):
            blend = (rest[i + 1], rest[i + 2]); i += 3
        elif a == "--t" and i + 1 < len(rest):
            t = float(rest[i + 1]); i += 2
        elif a == "--json":
            as_json = True; i += 1
        else:
            i += 1
    return era, blend, t, as_json


def _cmd_walk(rest: List[str]) -> int:
    from skeleton.forge.walk_cli import run_walk
    return run_walk(rest)


def _cmd_doctor(rest: List[str]) -> int:
    from skeleton.forge.walk_cli import run_doctor
    return run_doctor(rest)


def _parse_run_args(rest: List[str]):
    """Parse the creator loop without swallowing misspelled or missing flags."""
    import argparse

    parser = argparse.ArgumentParser(prog="python -m skeleton run")
    parser.add_argument("vision", nargs="*", help="game concept in natural language")
    parser.add_argument("--era", help="override a cockpit-bound era for this run")
    parser.add_argument("--archetype", help="override a cockpit-bound archetype")
    parser.add_argument("--out", help="output directory for the Godot project")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--blend", nargs=2, metavar=("ERA_A", "ERA_B"))
    parser.add_argument("--t", type=float, default=0.5)
    parser.add_argument("--generation")
    parser.add_argument("--answers", help="UTF-8 JSON file with questionnaire answers")
    parser.add_argument("--playtest", choices=("off", "auto", "require"), default="off")
    parser.add_argument("--repair-mode", choices=("apply", "suggest"), default="apply")
    args = parser.parse_intermixed_args(rest)
    if not 0 <= args.t <= 1:
        parser.error("--t must be between 0 and 1")
    return args


def _load_run_answers(path: Optional[str]) -> dict:
    """Fail closed on bad questionnaire input rather than starting an empty run."""
    from pathlib import Path
    if path is None:
        return {}
    with Path(path).expanduser().open("rb") as stream:
        data = stream.read(1024 * 1024 + 1)
    if len(data) > 1024 * 1024:
        raise ValueError("--answers JSON exceeds 1 MiB")
    try:
        answers = json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"--answers must be valid UTF-8 JSON: {exc}") from exc
    if not isinstance(answers, dict) or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in answers.items()
    ):
        raise ValueError("--answers must be a JSON object mapping strings to strings")
    return answers


def _cmd_gameforge_run(rest: List[str]) -> int:
    from skeleton.context.pipeline import GameForgeRun
    from skeleton.context.operator_state import read_steering, restore_cockpit
    try:
        args = _parse_run_args(rest)
        answers = _load_run_answers(args.answers)
        saved = read_steering()
    except SystemExit as exc:
        return int(exc.code)
    except (OSError, ValueError) as exc:
        print(f"run arguments error: {exc}", file=sys.stderr)
        return 2
    if not rest:
        from skeleton.genesis import Genesis
        genesis = Genesis(seed=42).boot()
        print("Skeleton runtime booted.")
        print(f"Handles: {list(genesis.handles.keys())}")
        return 0
    cockpit = restore_cockpit(saved) if saved else None
    era = args.era or (
        saved["tensor"]["era"] if saved and saved["era_bound"] else None
    )
    blend = (*args.blend, args.t) if args.blend else None
    payload = GameForgeRun.live(cockpit=cockpit).execute(
        " ".join(args.vision).strip(),
        era=era,
        archetype=args.archetype,
        answers=answers,
        project_root=args.out,
        overwrite=args.overwrite,
        target="godot",
        blend=blend,
        generation=args.generation,
        playtest=args.playtest,
        repair_mode=args.repair_mode,
    )
    failed = [stage for stage in (payload.get("run") or {}).get("stages", [])
              if stage.get("status") == "FAILED"]
    playtest = payload.get("playtest") or {}
    status = playtest.get("status", "off" if args.playtest == "off" else "not-reached")
    if args.json:
        slim = {k: payload[k] for k in (
            "succeeded", "era", "mass", "complete", "sim", "project", "forge", "playtest"
        ) if k in payload}
        slim["failed_stages"] = failed
        print(json.dumps(slim, indent=2, default=str))
    else:
        print(f"era={payload.get('era')} mass={payload.get('mass')} "
              f"sim={(payload.get('sim') or {}).get('passed')} "
              f"files={(payload.get('forge') or {}).get('file_count')} playtest={status}")
        if payload.get("project"):
            print("wrote", payload["project"]["root"])
        for stage in failed:
            print(f"FAILED stage={stage.get('name')}: "
                  f"{stage.get('error') or stage.get('gate_failure')}", file=sys.stderr)
    return 0 if payload.get("succeeded") else 1


def _cmd_creator(rest: List[str]) -> int:
    """Compile one CLI creator request into the canonical B014 envelope."""
    from skeleton.forge.creator.command_surface import (
        CreatorCommandError,
        creator_cli_payload,
    )

    try:
        payload = creator_cli_payload(rest)
    except CreatorCommandError as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": exc.code,
                    "message": str(exc),
                    "context": dict(getattr(exc, "context", {})),
                },
                sort_keys=True,
            )
        )
        return 2
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _cmd_test(_rest: List[str]) -> int:
    """Run the configured pytest suite, with unittest discovery as a fallback."""
    try:
        import pytest
    except ImportError:
        import unittest
        suite = unittest.TestLoader().discover("skeleton/testing", pattern="test_*.py")
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        return 0 if result.wasSuccessful() else 1
    return int(pytest.main(["skeleton/testing", "-ra"]))


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print(__doc__)
        return 0

    cmd = args[0]
    rest = args[1:]
    if cmd == "app":
        from skeleton.app.cli import run_app_cli
        return run_app_cli(rest)
    if cmd == "run": return _cmd_gameforge_run(rest)
    if cmd == "forge":
        from skeleton.forge.universal import Forge
        forge = Forge(); print("Forge ready.")
        if rest:
            bp = forge.new_blueprint(rest[0])
            print(f"Blueprint '{rest[0]}' created with {len(bp.components)} components.")
        return 0
    if cmd == "test": return _cmd_test(rest)
    if cmd == "dev":
        from skeleton.developer.cli import dev_exit_code, run_dev_cli
        result = run_dev_cli(rest)
        if isinstance(result, dict): print(json.dumps(result, indent=2, default=str))
        return dev_exit_code(result)
    if cmd == "eras": return _cmd_eras(rest)
    if cmd == "generations": return _cmd_generations(rest)
    if cmd == "plan": return _cmd_plan(rest)
    if cmd == "cockpit": return _cmd_cockpit(rest)
    if cmd == "walk": return _cmd_walk(rest)
    if cmd == "doctor": return _cmd_doctor(rest)
    if cmd == "creator": return _cmd_creator(rest)
    if cmd == "contracts": return _cmd_contracts(rest)
    if cmd == "capabilities": return _cmd_capabilities(rest)
    if cmd == "invoke": return _cmd_invoke(rest)
    if cmd == "command": return _cmd_shared_command(rest)
    if cmd == "status": return _cmd_shared_command(["status"])
    if cmd == "config": return _cmd_shared_command(["configuration"])
    if cmd in ("help", "-h", "--help"): print(__doc__); return 0
    print(f"Unknown command: {cmd}"); print(__doc__); return 1


if __name__ == "__main__":
    raise SystemExit(main())
