#!/usr/bin/env python3
"""Train a local human-labeled numeric quality shadow model from game reports.

Never trains a production LLM or promotes learned parameters automatically.
All candidate source rights and review labels must have been checked upstream.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path

REPOSITORY_ROOT=Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0,str(REPOSITORY_ROOT))

from skeleton.jeeves.game_decompilation_learning import (
    CANDIDATE_SCHEMA, train_shadow_asset_quality_model,
)

MAX_INPUT_FILE = 8 * 1024 * 1024


def _read_report(path: Path) -> dict:
    fd=os.open(str(path),os.O_RDONLY|getattr(os,"O_NOFOLLOW",0))
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or not 1 <= info.st_size <= MAX_INPUT_FILE:
            raise ValueError("Shadow candidate report is not bounded regular file")
        with os.fdopen(os.dup(fd),"rb") as handle:
            raw=handle.read(MAX_INPUT_FILE+1)
        if len(raw)!=info.st_size:
            raise ValueError("Human-labeled source report changed while being read")
        obj=json.loads(raw)
        if not isinstance(obj,dict):
            raise ValueError("Human-labeled source report must be a JSON object")
        candidate=obj.get("local_shadow_training_candidate",obj)
        if not isinstance(candidate,dict) or candidate.get("schema_version")!=CANDIDATE_SCHEMA:
            raise ValueError("Expected scoped human-shadow review candidate")
        return candidate
    finally:
        os.close(fd)


def main(argv:list[str]|None=None)->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports",nargs="+",type=Path,help="8–128 independent human-scored JSON receipts")
    parser.add_argument("--output",type=Path,required=True,help="New local shadow checkpoint filename")
    parser.add_argument("--authorize-shadow-training",action="store_true",
                        help="Explicitly confirm label/source scope; no production promotion")
    parser.add_argument("--epochs",type=int,default=48)
    parser.add_argument("--learning-rate",type=float,default=.08)
    args=parser.parse_args(argv)
    if not args.authorize_shadow_training:
        parser.error("Explicit current shadow training approval is required")
    if not 8<=len(args.reports)<=128:
        parser.error("Shadow training requires 8–128 independently reviewed sources")
    if args.output.exists() or args.output.is_symlink():
        raise FileExistsError("Refusing to overwrite any existing model or checkpoint")
    if args.output.suffix!=".json" or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}",args.output.name):
        parser.error("Checkpoint requires a simple .json filename")
    rows=[_read_report(x) for x in args.reports]
    checkpoint=train_shadow_asset_quality_model(
        rows,authorize=lambda:args.authorize_shadow_training is True,
        epochs=args.epochs,learning_rate=args.learning_rate,
    )
    payload=json.dumps(checkpoint,sort_keys=True,indent=2,allow_nan=False).encode()
    fd=os.open(str(args.output),
        os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0),0o600)
    with os.fdopen(fd,"wb") as target:
        target.write(payload)
        target.flush()
        os.fsync(target.fileno())
    print(json.dumps({
        "checkpoint_sha256":checkpoint["checkpoint_sha256"],
        "file_sha256":hashlib.sha256(payload).hexdigest(),
        "trained_shadow_numeric_parameters":True,
        "train_sources":checkpoint["train_cases"],
        "held_out_sources":checkpoint["held_out_cases"],
        "heldout_mse_improved":checkpoint["passed_holdout_guard"],
        "production_ai_weights_changed":False,
        "checkpoint_path":str(args.output),
    },sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
