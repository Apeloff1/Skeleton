"""python -m skeleton — run, intake, eras, check."""
from __future__ import annotations

import argparse
import json
import sys


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m skeleton")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="vision → Godot project")
    r.add_argument("vision", nargs="?", default="")
    r.add_argument("--era")
    r.add_argument("--out", dest="out")
    r.add_argument("--overwrite", action="store_true")
    r.add_argument("--json", action="store_true")
    r.add_argument("--blend", nargs=2, metavar=("ERA_A", "ERA_B"))
    r.add_argument("--t", dest="t", type=float, default=0.5)
    r.add_argument("--generation")

    i = sub.add_parser("intake", help="12-beat answers → project")
    i.add_argument("pairs", nargs="*", help="id=option")
    i.add_argument("--out")
    i.add_argument("--overwrite", action="store_true")

    sub.add_parser("eras", help="list era dialects")
    sub.add_parser("generations", help="list hardware generations")
    c = sub.add_parser("check", help="static-check a files dict or a project dir")
    c.add_argument("path")

    pl = sub.add_parser("plan", help="Jeeves BuildPlan for a vision / era")
    pl.add_argument("vision", nargs="?", default="")
    pl.add_argument("--era")
    pl.add_argument("--blend", nargs=2, metavar=("ERA_A", "ERA_B"))
    pl.add_argument("--t", dest="t", type=float, default=0.5)

    ck = sub.add_parser("cockpit", help="apply one cockpit command")
    ck.add_argument("command")

    th = sub.add_parser("think", help="Jeeves neocortex think (the model in training)")
    th.add_argument("stimulus", nargs="?", default="")
    th.add_argument("--bind", nargs=2, metavar=("SLOT", "BACKEND"))
    th.add_argument("--acquire")
    th.add_argument("--surpass")
    th.add_argument("--recall", action="store_true")

    trn = sub.add_parser("train", help="run GameForge curriculum epochs on the own-system")
    trn.add_argument("--epochs", type=int, default=1)

    wk = sub.add_parser("walk", help="prove spawn→extract on the emitted door graph")
    wk.add_argument("--era", default="extraction_now")
    wk.add_argument("--blend", nargs=2, metavar=("ERA_A", "ERA_B"))
    wk.add_argument("--t", dest="t", type=float, default=0.5)
    wk.add_argument("--json", action="store_true")

    args = p.parse_args(argv)

    if args.cmd == "eras":
        from skeleton.forge.eras import list_eras, compile_era
        for era in list_eras():
            pack = compile_era(era)
            print(f"{era:22} dps={pack['primary_dps']:<7} speed={pack['player']['speed']}")
        return 0

    if args.cmd == "generations":
        from skeleton.forge.hardware import catalog
        for g in catalog():
            print(f"{g['key']:10} {g['label']:16} {g['viewport'][0]}x{g['viewport'][1]}  {g['tagline']}")
        return 0

    if args.cmd == "check":
        from pathlib import Path
        from skeleton.forge.gdscript_check import check_files
        root = Path(args.path)
        files = {str(f.relative_to(root)): f.read_text() for f in root.rglob("*") if f.is_file() and f.suffix in {".gd", ".tscn", ".godot", ".cfg", ".json"}}
        problems = check_files(files)
        if problems:
            print("FAIL")
            for x in problems:
                print(" -", x)
            return 2
        print(f"OK {len(files)} files")
        return 0

    if args.cmd == "cockpit":
        from skeleton.context.cockpit import Cockpit
        cpit = Cockpit()
        out = cpit.apply(args.command)
        print(json.dumps(out, indent=2, default=str))
        return 0

    if args.cmd == "train":
        from skeleton.cortex import JeevesCortex
        out = JeevesCortex().train(epochs=args.epochs)
        print(json.dumps(out, indent=2, default=str))
        return 0 if out.get("held_rate", 0) >= 0.5 else 1

    if args.cmd == "walk":
        from skeleton.forge.eras import blend_eras, compile_era
        from skeleton.forge.walk import walk_from_pack
        from skeleton.jeeves.builder import BuilderBrain
        from skeleton.context.tensor import ContextTensor
        from skeleton.context.dodeca import Dodecahedron
        from skeleton.context.oracle import Magic8Ball
        if args.blend:
            pack = blend_eras(args.blend[0], args.blend[1], args.t)
            tensor = ContextTensor.from_era(args.blend[0]).lerp(
                ContextTensor.from_era(args.blend[1]), args.t
            )
        else:
            pack = compile_era(args.era)
            tensor = ContextTensor.from_era(args.era)
        reading = Magic8Ball(Dodecahedron.from_tensor(tensor)).roll(tensor)
        plan = BuilderBrain().plan(pack, tensor=tensor, reading=reading)
        wr_i = walk_from_pack(pack, plan=plan.to_dict(), mode="ideal")
        wr = walk_from_pack(pack, plan=plan.to_dict(), mode="thermal")
        payload = wr.to_dict()
        payload["ideal"] = {"t": round(wr_i.t, 4), "extracted": wr_i.extracted}
        payload["plan"] = {"bias": plan.room_bias, "extract_late": plan.extract_late, "era": plan.era}
        if args.json:
            print(json.dumps(payload, indent=2, default=str))
        else:
            print(
                f"extracted={wr.extracted} thermal={wr.t:.2f}s ideal={wr_i.t:.2f}s "
                f"hops={wr.hops} heat_peak={wr.heat_peak:.1f} cores={wr.cores}/{wr.required_cores}"
            )
        return 0 if wr.passed and wr.t + 0.2 >= wr_i.t else 1

    if args.cmd == "think":
        from skeleton.cortex import JeevesCortex
        neo = JeevesCortex()
        if args.bind:
            slot, how = args.bind
            if how == "echo":
                neo.bind_echo(slot)
            else:
                neo.bind_local(slot)
        trace = neo.think(args.stimulus)
        if args.acquire:
            neo.acquire(args.acquire)
        if args.surpass:
            neo.surpass(args.surpass)
            if args.stimulus:
                trace = neo.think(args.stimulus)
        payload = trace.to_dict()
        if args.recall:
            payload["recall"] = neo.recall(args.stimulus)
        print(json.dumps(payload, indent=2, default=str))
        return 0

    if args.cmd == "plan":
        from skeleton.context.tensor import ContextTensor, detect_era
        from skeleton.forge.eras import blend_eras, compile_era
        from skeleton.jeeves.builder import BuilderBrain
        from skeleton.context.dodeca import Dodecahedron
        from skeleton.context.oracle import Magic8Ball
        if args.blend:
            pack = blend_eras(args.blend[0], args.blend[1], args.t)
            tensor = ContextTensor.from_era(args.blend[0]).lerp(
                ContextTensor.from_era(args.blend[1]), args.t
            )
            object.__setattr__(tensor, "era", pack["era"])
        elif args.era:
            pack = compile_era(args.era)
            tensor = ContextTensor.from_era(args.era)
        else:
            era, _ = detect_era(args.vision or "")
            pack = compile_era(era)
            tensor = ContextTensor.from_era(era)
        reading = Magic8Ball(Dodecahedron.from_tensor(tensor)).roll(tensor)
        plan = BuilderBrain().plan(pack, tensor=tensor, reading=reading)
        print(json.dumps(plan.to_dict(), indent=2))
        return 0

    from skeleton.context.pipeline import GameForgeRun

    answers = None
    vision = ""
    era = None
    out = None
    overwrite = False
    if args.cmd == "run":
        vision = args.vision
        era = args.era
        out = args.out
        overwrite = args.overwrite
        as_json = args.json
        blend = tuple(args.blend) + (args.t,) if args.blend else None
        generation = args.generation
    else:
        answers = {}
        for pair in args.pairs:
            if "=" not in pair:
                print("answers must be id=option", file=sys.stderr)
                return 2
            k, v = pair.split("=", 1)
            answers[k] = v
        out = args.out
        overwrite = args.overwrite
        as_json = False
        blend = None
        generation = None

    payload = GameForgeRun().execute(
        vision, era=era, answers=answers, project_root=out, overwrite=overwrite, target="godot",
        blend=blend, generation=generation,
    )
    if args.cmd == "run" and as_json:
        slim = {k: payload[k] for k in ("succeeded", "era", "mass", "complete", "sim", "project", "forge") if k in payload}
        print(json.dumps(slim, indent=2, default=str))
        return 0 if payload["succeeded"] else 1
    print(f"era={payload.get('era')} mass={payload.get('mass')} sim={payload.get('sim', {}).get('passed')} files={payload.get('forge', {}).get('file_count')}")
    if payload.get("project"):
        print("wrote", payload["project"]["root"])
    return 0 if payload.get("succeeded") else 1


if __name__ == "__main__":
    raise SystemExit(main())
