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
    help        Show this help message
"""

from __future__ import annotations

import json
import sys
from typing import List, Optional


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
    # Bare `run` with no vision boots genesis (operator path).
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


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print(__doc__)
        return 0

    cmd = args[0]
    rest = args[1:]

    if cmd == "run":
        return _cmd_gameforge_run(rest)

    if cmd == "forge":
        from skeleton.forge.universal import Forge
        forge = Forge()
        print("Forge ready.")
        if rest:
            bp = forge.new_blueprint(rest[0])
            print(f"Blueprint '{rest[0]}' created with {len(bp.components)} components.")
        return 0

    if cmd == "test":
        import unittest
        loader = unittest.TestLoader()
        suite = loader.discover("skeleton/testing", pattern="test_*.py")
        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)
        return 0 if result.wasSuccessful() else 1

    if cmd == "dev":
        from skeleton.developer.cli import run_dev_cli
        result = run_dev_cli(rest)
        if isinstance(result, dict):
            print(json.dumps(result, indent=2, default=str))
        return 0 if (isinstance(result, dict) and "error" not in result) else 1

    if cmd == "eras":
        return _cmd_eras(rest)
    if cmd == "generations":
        return _cmd_generations(rest)
    if cmd == "plan":
        return _cmd_plan(rest)
    if cmd == "cockpit":
        return _cmd_cockpit(rest)
    if cmd == "walk":
        return _cmd_walk(rest)

    if cmd in ("help", "-h", "--help"):
        print(__doc__)
        return 0

    print(f"Unknown command: {cmd}")
    print(__doc__)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
