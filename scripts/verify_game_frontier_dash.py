#!/usr/bin/env python3
"""Independently compare real Godot wind-dash physics with unmodified control."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from skeleton.jeeves.game_frontier_native_dash_audit import (
    verify_native_wind_dash_playthrough,
)
from skeleton.jeeves.game_frontier_native_engine_dispatch import canonical_dispatch_json
from skeleton.jeeves.game_frontier_native_quest_session import NativeQuestSessionError


def _lines(path:Path,limit:int):
    if path.is_symlink() or not path.is_file() or path.stat().st_size>limit:
        raise NativeQuestSessionError("safe bounded Godot playback file required")
    data=path.read_text(encoding="utf-8")
    if not data.endswith("\n"):
        raise NativeQuestSessionError("incomplete Godot JSONL receipt")
    return [json.loads(line) for line in data.splitlines()]


def main(argv=None):
    args=argparse.ArgumentParser(description=__doc__)
    args.add_argument("--control-jsonl",required=True,type=Path)
    args.add_argument("--activated-jsonl",required=True,type=Path)
    args.add_argument("--ability-jsonl",required=True,type=Path)
    args.add_argument("--dispatch-json",required=True,type=Path)
    args.add_argument("--fps",required=True,type=int)
    args.add_argument("--max-bytes",default=1048576,type=int)
    opts=args.parse_args(argv)
    try:
        if not 2048<=opts.max_bytes<=16*1024*1024:
            raise NativeQuestSessionError("bounded dash verifier IO budget invalid")
        if opts.dispatch_json.is_symlink() or opts.dispatch_json.stat().st_size>opts.max_bytes:
            raise NativeQuestSessionError("unsafe dispatch source path")
        dispatch=json.loads(opts.dispatch_json.read_text(encoding="utf-8"))
        canonical_dispatch_json(dispatch)
        controls=_lines(opts.control_jsonl,opts.max_bytes)
        activated=_lines(opts.activated_jsonl,opts.max_bytes)
        actions=_lines(opts.ability_jsonl,opts.max_bytes)
        if len(actions)!=1:
            raise NativeQuestSessionError("exactly one unlocked dash activation required")
        report=verify_native_wind_dash_playthrough(
            controls,activated,actions[0],dispatch,fps=opts.fps)
        print(json.dumps(report,sort_keys=True,separators=(",",":"),allow_nan=False))
        return 0
    except (NativeQuestSessionError,ValueError,TypeError,KeyError,OSError,
            UnicodeError) as exc:
        print(f"real Godot wind dash rejected: {exc}",file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
