"""Skeleton CLI entry point.

Usage:
    python -m skeleton <command> [options]

Commands:
    run         Start the skeleton runtime / GameForge vision run
    forge       Blueprint compilation and materialization
    test        Run test suites
    dev         Developer CLI (scaffold, wizard, health, visualize)
    eras        List GameForge era dialects
    generations List hardware generations
    plan        Jeeves BuildPlan for a vision / era
    cockpit     Apply one cockpit command
    walk        Prove spawn→extract on the emitted door graph
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
    command     Execute a shared command: command <name> ['{...json...}']
    status      Shared runtime status command
    config      Shared non-secret configuration command
    help        Show this help message
"""

from __future__ import annotations

import json
import sys
from typing import List, Optional


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
    if view == "shared_audit":
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


def _cmd_shared_command(rest: List[str]) -> int:
    from skeleton.api.server import get_state
    from skeleton.application import CONTRACT_VERSION, build_runtime_command_service

    if not rest:
        print(json.dumps({
            "contract_version": CONTRACT_VERSION,
            "command": "",
            "ok": False,
            "error": {"code": "invalid_command", "message": "command name is required"},
        }, indent=2))
        return 2

    command = rest[0].strip().lower()
    payload = {}
    if len(rest) > 1:
        raw_payload = " ".join(rest[1:]).strip()
        try:
            decoded = json.loads(raw_payload)
        except json.JSONDecodeError as exc:
            print(json.dumps({
                "contract_version": CONTRACT_VERSION,
                "command": command,
                "ok": False,
                "error": {"code": "invalid_argument", "message": f"invalid JSON payload: {exc.msg}"},
            }, indent=2))
            return 2
        if not isinstance(decoded, dict):
            print(json.dumps({
                "contract_version": CONTRACT_VERSION,
                "command": command,
                "ok": False,
                "error": {"code": "invalid_argument", "message": "command payload must be a JSON object"},
            }, indent=2))
            return 2
        payload = decoded

    state = get_state()
    if command in {"run", "tool", "memory", "admin"} and state.genesis is None:
        from skeleton.genesis import Genesis

        state.wire_from_genesis(Genesis(seed=42).boot())

    result = build_runtime_command_service(state).execute(command, payload)
    print(json.dumps(result.to_payload(), indent=2, default=str))
    return result.exit_code


def _cmd_eras(_rest: List[str]) -> int:
    from skeleton.forge.eras import list_eras, compile_era
    for era in list_eras():
        pack = compile_era(era)
        print(f"{era:22} dps={pack['primary_dps']:<7} speed={pack['player']['speed']}")
    return 0


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
    from skeleton.context.cockpit import Cockpit
    out = Cockpit().apply(" ".join(rest).strip())
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
    from skeleton.forge.eras import blend_eras, compile_era
    from skeleton.forge.walk import walk_from_pack
    from skeleton.jeeves.builder import BuilderBrain
    from skeleton.context.tensor import ContextTensor
    from skeleton.context.dodeca import Dodecahedron
    from skeleton.context.oracle import Magic8Ball
    era, blend, t, as_json = _parse_walk_args(rest)
    if blend:
        pack = blend_eras(blend[0], blend[1], t)
        tensor = ContextTensor.from_era(blend[0]).lerp(ContextTensor.from_era(blend[1]), t)
    else:
        pack = compile_era(era)
        tensor = ContextTensor.from_era(era)
    reading = Magic8Ball(Dodecahedron.from_tensor(tensor)).roll(tensor)
    plan = BuilderBrain().plan(pack, tensor=tensor, reading=reading)
    wr = walk_from_pack(pack, plan=plan.to_dict())
    payload = wr.to_dict()
    payload["plan"] = {"bias": plan.room_bias, "extract_late": plan.extract_late, "era": plan.era}
    if as_json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        print(f"extracted={wr.extracted} t={wr.t:.2f} hops={wr.hops} cores={wr.cores}/{wr.required_cores}")
    return 0 if wr.passed else 1


def _parse_run_args(rest: List[str]):
    vision_parts: List[str] = []
    era = None
    out = None
    overwrite = False
    as_json = False
    blend = None
    t = 0.5
    generation = None
    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--era" and i + 1 < len(rest):
            era = rest[i + 1]; i += 2
        elif a == "--out" and i + 1 < len(rest):
            out = rest[i + 1]; i += 2
        elif a == "--overwrite":
            overwrite = True; i += 1
        elif a == "--json":
            as_json = True; i += 1
        elif a == "--blend" and i + 2 < len(rest):
            blend = (rest[i + 1], rest[i + 2]); i += 3
        elif a == "--t" and i + 1 < len(rest):
            t = float(rest[i + 1]); i += 2
        elif a == "--generation" and i + 1 < len(rest):
            generation = rest[i + 1]; i += 2
        else:
            vision_parts.append(a); i += 1
    blend_arg = tuple(blend) + (t,) if blend else None
    return " ".join(vision_parts).strip(), era, out, overwrite, as_json, blend_arg, generation


def _cmd_gameforge_run(rest: List[str]) -> int:
    from skeleton.context.pipeline import GameForgeRun
    vision, era, out, overwrite, as_json, blend, generation = _parse_run_args(rest)
    if not vision and era is None and out is None and blend is None:
        from skeleton.genesis import Genesis
        genesis = Genesis(seed=42).boot()
        print("Skeleton runtime booted.")
        print(f"Handles: {list(genesis.handles.keys())}")
        return 0
    payload = GameForgeRun.live().execute(
        vision, era=era, answers={}, project_root=out, overwrite=overwrite, target="godot",
        blend=blend, generation=generation,
    )
    if as_json:
        slim = {k: payload[k] for k in ("succeeded", "era", "mass", "complete", "sim", "project", "forge") if k in payload}
        print(json.dumps(slim, indent=2, default=str))
    else:
        print(f"era={payload.get('era')} mass={payload.get('mass')} sim={(payload.get('sim') or {}).get('passed')} files={(payload.get('forge') or {}).get('file_count')}")
        if payload.get("project"):
            print("wrote", payload["project"]["root"])
    return 0 if payload.get("succeeded") else 1


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
        from skeleton.developer.cli import run_dev_cli
        result = run_dev_cli(rest)
        if isinstance(result, dict): print(json.dumps(result, indent=2, default=str))
        return 0 if (isinstance(result, dict) and "error" not in result) else 1
    if cmd == "eras": return _cmd_eras(rest)
    if cmd == "generations": return _cmd_generations(rest)
    if cmd == "plan": return _cmd_plan(rest)
    if cmd == "cockpit": return _cmd_cockpit(rest)
    if cmd == "walk": return _cmd_walk(rest)
    if cmd == "contracts": return _cmd_contracts(rest)
    if cmd == "capabilities": return _cmd_capabilities(rest)
    if cmd == "command": return _cmd_shared_command(rest)
    if cmd == "status": return _cmd_shared_command(["status"])
    if cmd == "config": return _cmd_shared_command(["configuration"])
    if cmd in ("help", "-h", "--help"): print(__doc__); return 0
    print(f"Unknown command: {cmd}"); print(__doc__); return 1


if __name__ == "__main__":
    raise SystemExit(main())
