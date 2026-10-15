#!/usr/bin/env python3
"""Emit truthful static coverage/gaps for Skeleton's complete console catalog."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))
from skeleton.jeeves.game_decompilation_capabilities import build_game_decompilation_target_matrix


def main(argv:list[str]|None=None)->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary",action="store_true")
    args=parser.parse_args(argv)
    result=build_game_decompilation_target_matrix()
    print(json.dumps(result["summary"] if args.summary else result,sort_keys=True,indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
