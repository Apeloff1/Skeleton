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

    i = sub.add_parser("intake", help="12-beat answers → project")
    i.add_argument("pairs", nargs="*", help="id=option")
    i.add_argument("--out")
    i.add_argument("--overwrite", action="store_true")

    sub.add_parser("eras", help="list era dialects")
    c = sub.add_parser("check", help="static-check a files dict or a project dir")
    c.add_argument("path")

    args = p.parse_args(argv)

    if args.cmd == "eras":
        from skeleton.forge.eras import list_eras, compile_era
        for era in list_eras():
            pack = compile_era(era)
            print(f"{era:22} dps={pack['primary_dps']:<7} speed={pack['player']['speed']}")
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

    payload = GameForgeRun().execute(
        vision, era=era, answers=answers, project_root=out, overwrite=overwrite, target="godot",
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
