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
    sota        Show the #807 SOTA game-creation program map
    replay      Record and verify a deterministic mechanics replay
    session     Compose replay + AI + harbor + mass + era bind
    conductor   Run the 7-step GameForge conductor cards
    arena       Run the B100 structural sealed-replay arena
    spec        Compile a Game Spec card from a vision
    emit        Validate the emit-pack tree (no Godot binary)
    doctor      Run one doctor cycle on the weakest critique axis
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


def _cmd_capabilities(_rest: List[str]) -> int:
    from skeleton.application import capability_manifest

    print(json.dumps(capability_manifest(), indent=2, default=str))
    return 0


def _cmd_sota(rest: List[str]) -> int:
    from dataclasses import asdict

    from skeleton.application import get_lane, sota_program

    if rest:
        try:
            lane = get_lane(rest[0])
        except (KeyError, TypeError, ValueError) as exc:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
            return 2
        print(json.dumps(asdict(lane), indent=2, default=str))
        return 0
    print(json.dumps(sota_program(), indent=2, default=str))
    return 0


def _parse_seed(rest: List[str]) -> int | str:
    seed: int | str = 8847291
    i = 0
    while i < len(rest):
        if rest[i] == "--seed" and i + 1 < len(rest):
            raw = rest[i + 1]
            seed = int(raw) if raw.isdigit() else raw
            i += 2
        else:
            i += 1
    return seed


def _cmd_replay(rest: List[str]) -> int:
    from skeleton.game.replay import REPLAY_SCHEMA_VERSION, record, verify
    from skeleton.vault.tool_fence import inspect_tool

    seed = _parse_seed(rest)
    inputs = [
        {"t": 0, "verb": "attack"},
        {"t": 1, "verb": "defend"},
        {"t": 2, "verb": "grant_xp"},
        {"t": 3, "verb": "attack"},
        {"t": 4, "verb": "wait"},
    ]
    try:
        inspect_tool("replay.record", {"seed": seed})
        trace = record(seed=seed, inputs=inputs)
        check = verify(trace.to_dict())
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 2
    print(json.dumps({
        "ok": True,
        "schema_version": REPLAY_SCHEMA_VERSION,
        "digest": check["digest"],
        "frames": check["frames"],
        "seed": trace.seed,
    }, indent=2))
    return 0


def _cmd_session(rest: List[str]) -> int:
    from skeleton.game.session import run_session

    seed = _parse_seed(rest)
    inputs = [{"t": 0, "verb": "attack"}, {"t": 1, "verb": "wait"}]
    try:
        payload = run_session(seed=seed, inputs=inputs, forges=4)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 2
    print(json.dumps({
        "ok": True,
        "digest": payload["digest"],
        "replay_digest": payload["replay_digest"],
        "frames": payload["frames"],
        "era": payload["reference"]["era"],
        "stored_prose": payload["stored_prose"],
    }, indent=2))
    return 0


def _cmd_conductor(rest: List[str]) -> int:
    from skeleton.game.conductor import execute

    seed = _parse_seed(rest)
    try:
        payload = execute(seed=int(seed) if str(seed).isdigit() else 8847291)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 2
    print(json.dumps({
        "ok": True,
        "seed": payload["seed"],
        "steps": len(payload["steps"]),
        "weakest": payload["weakest"],
        "era": payload["reference"]["era"],
        "sota_ready": payload["sota_ready"],
        "stored_prose": payload["stored_prose"],
    }, indent=2))
    return 0


def _cmd_arena(rest: List[str]) -> int:
    from skeleton.game.arena import run_arena

    try:
        payload = run_arena()
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 2
    print(json.dumps({
        "ok": True,
        "n": payload["n"],
        "unique_digests": payload["unique_digests"],
        "extract_ok": payload["extract_ok"],
        "evidence": payload["evidence"],
        "sota_ready": payload["sota_ready"],
        "stored_prose": payload["stored_prose"],
    }, indent=2))
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
    if cmd == "sota": return _cmd_sota(rest)
    if cmd == "replay": return _cmd_replay(rest)
    if cmd == "session": return _cmd_session(rest)
    if cmd == "conductor": return _cmd_conductor(rest)
    if cmd == "arena": return _cmd_arena(rest)
    from skeleton.game.cli_sota import dispatch
    extra = dispatch(cmd, rest)
    if extra is not None:
        return extra
    if cmd == "command": return _cmd_shared_command(rest)
    if cmd == "status": return _cmd_shared_command(["status"])
    if cmd == "config": return _cmd_shared_command(["configuration"])
    if cmd in ("help", "-h", "--help"): print(__doc__); return 0
    print(f"Unknown command: {cmd}"); print(__doc__); return 1


if __name__ == "__main__":
    raise SystemExit(main())
