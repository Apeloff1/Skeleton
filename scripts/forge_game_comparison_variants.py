#!/usr/bin/env python3
"""Create three lawful, original console-editor project versions from a study."""

from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main(argv: list[str] | None = None) -> int:
    from scripts.compare_game_study import _atomic_write, _read_json_file
    from skeleton.jeeves.game_comparison_schema import ComparativeStudyError
    from skeleton.jeeves.game_comparison_variant_forge import forge_original_comparison_variants
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result",type=Path,required=True,help="Previously completed actual native comparative .result.json")
    parser.add_argument("--game",action="append",required=True,help="Explicit observed game id to use as cited inspiration, 2–30")
    parser.add_argument("--target",required=True,help="One supported canonical ConsoleProject hardware target")
    parser.add_argument("--project-prefix",default="comparative_original")
    parser.add_argument("--seed",type=int,default=100)
    parser.add_argument("--output-dir",type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        report=_read_json_file(args.result,24*1024*1024)
        if args.output_dir.is_symlink():
            raise ComparativeStudyError("Refusing symlinked original game project output directory")
        result=forge_original_comparison_variants(
            report,game_ids=args.game,target_id=args.target,
            project_prefix=args.project_prefix,author_seed=args.seed,
        )
        output=args.output_dir.resolve()
        output.mkdir(parents=True,exist_ok=True)
        for variant in result["authored_variants"]:
            prefix=variant["variant_id"]
            _atomic_write(
                output/(prefix+".editor.json"),
                json.dumps(variant["project_document"],sort_keys=True,indent=2,allow_nan=False).encode(),
            )
            _atomic_write(
                output/(prefix+".files.json"),
                json.dumps(variant["project_files"],sort_keys=True,indent=2,allow_nan=False).encode(),
            )
        summary={key:value for key,value in result.items() if key!="authored_variants"}
        summary["variants"]=[
            {
                "variant_id":v["variant_id"],"design_era":v["design_era"],
                "project_digest":v["original_project_sha256"],
                "editor_path":str(output/(v["variant_id"]+".editor.json")),
                "files_path":str(output/(v["variant_id"]+".files.json")),
                "compiled_rom":False,
            } for v in result["authored_variants"]
        ]
        _atomic_write(output/(args.project_prefix+".forge_receipt.json"),
                      json.dumps(summary,indent=2,sort_keys=True,allow_nan=False).encode())
        print(json.dumps({
            "status":"three_original_comparative_editor_projects_created",
            "source_game_count":result["source_game_count"],
            "dest_target_id":args.target,"original_project_count":len(summary["variants"]),
            "variants":summary["variants"],"roms_compiled":0,"model_weights_changed":False,
        },indent=2))
        return 0
    except (ValueError,OSError,RuntimeError) as exc:
        print(json.dumps({
            "status":"comparative_variant_forge_rejected","error_type":type(exc).__name__,
            "reason":str(exc)[:512]
        }),file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
