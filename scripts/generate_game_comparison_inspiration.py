#!/usr/bin/env python3
"""Generate original SVG art, playable WAV, editable cutscenes and gameplay drafts."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def main(argv: list[str]|None=None)->int:
    from scripts.compare_game_study import _atomic_write,_read_json_file
    from skeleton.jeeves.game_comparison_inspiration import (
        build_original_inspiration_pack,GENRES,
    )
    from skeleton.jeeves.game_comparison_inspiration_viewer import render_inspiration_gallery
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result",type=Path,required=True,help="Real native comparative study evidence JSON")
    parser.add_argument("--game",action="append",required=True,help="Select 2–30 actually observed source game IDs")
    parser.add_argument("--genre",required=True,choices=GENRES)
    parser.add_argument("--brief",required=True,help="Your own original 4–240-character design concept")
    parser.add_argument("--seed",type=int,default=17)
    parser.add_argument("--output-dir",type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        if args.output_dir.is_symlink():
            raise ValueError("Generated content destination must not be symlinked")
        report=_read_json_file(args.result,24*1024*1024)
        files,receipt=build_original_inspiration_pack(
            report,game_ids=args.game,genre=args.genre,creative_brief=args.brief,
            author_seed=args.seed,
        )
        dest=args.output_dir.resolve()
        dest.mkdir(parents=True,exist_ok=True)
        for name,data in files.items():
            path=dest/name
            path.parent.mkdir(parents=True,exist_ok=True)
            if path.is_symlink() or path.parent.is_symlink():
                raise ValueError("Generated original media path must not be symlinked")
            _atomic_write(path,data)
        _atomic_write(dest/"original_inspiration_gallery.html",
                      render_inspiration_gallery(receipt).encode())
        _atomic_write(
            dest/"original_inspiration_receipt.json",
            json.dumps(receipt,sort_keys=True,indent=2,allow_nan=False).encode(),
        )
        print(json.dumps({
            "status":"original_comparative_inspiration_pack_written",
            "source_study_id":receipt["study_id"],
            "generated_artifacts":receipt["generated_file_count"],
            "creative_stages":["earlier","middle","after"],
            "categories":receipt["generated_categories"],
            "manifest":str(dest/"original_inspiration_receipt.json"),
            "gallery":str(dest/"original_inspiration_gallery.html"),
            "actual_video_rendered":False,
            "original_gameplay_compiled":False,
            "model_weights_changed":False,
        },indent=2))
        return 0
    except (ValueError,OSError,RuntimeError) as exc:
        print(json.dumps({
            "status":"original_inspiration_rejected",
            "error_type":type(exc).__name__,"reason":str(exc)[:512],
        }),file=sys.stderr)
        return 2

if __name__=="__main__":
    raise SystemExit(main())
