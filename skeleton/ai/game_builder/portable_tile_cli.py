"""Offline source-only native tile compiler for explicitly original artwork.

Usage:
  python -m skeleton.ai.game_builder.portable_tile_cli \
      --input authored_tiles.json --target nintendo_game_boy \
      --syntax rgbds --output original_tiles.asm --acknowledge-original

No network, commercial ROM import, rights self-approval, or native ROM build.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Sequence

from .portable_kernels import (
    compile_original_tile_bundle, emit_original_tile_source,
    verify_original_tile_roundtrip,
)

MAX_INPUT_BYTES = 256_000
SCHEMA = "skeleton.game_builder.original_indexed_tiles.v1"


class TileCLIError(ValueError):
    """Unsafe input, failed admission, or source export failure."""


def _load_source(path: Path) -> dict:
    """Read one immutable-in-place regular JSON source without symlink traversal."""
    try:
        prior=path.lstat()
        if not stat.S_ISREG(prior.st_mode) or not 1<=prior.st_size<=MAX_INPUT_BYTES:
            raise TileCLIError("source must be a bounded regular non-symlink file")
        flags=(os.O_RDONLY | getattr(os,"O_BINARY",0)
               | getattr(os,"O_NOFOLLOW",0) | getattr(os,"O_CLOEXEC",0)
               | getattr(os,"O_NONBLOCK",0))
        fd=os.open(path,flags)
        with os.fdopen(fd,"rb") as stream:
            opened=os.fstat(stream.fileno())
            if (not stat.S_ISREG(opened.st_mode)
                    or (prior.st_dev,prior.st_ino)!=(opened.st_dev,opened.st_ino)):
                raise TileCLIError("original source changed before opening")
            payload=stream.read(MAX_INPUT_BYTES+1)
            after=os.fstat(stream.fileno())
            current=path.lstat()
            identity=lambda row:(row.st_dev,row.st_ino,row.st_size,row.st_mtime_ns)
            if (not stat.S_ISREG(current.st_mode)
                    or identity(opened)!=identity(after)
                    or identity(opened)!=identity(current)
                    or len(payload)!=opened.st_size):
                raise TileCLIError("original source changed during admission")
    except (OSError, ValueError) as exc:
        if isinstance(exc,TileCLIError):
            raise
        raise TileCLIError("cannot read safe original tile source") from exc
    if len(payload)>MAX_INPUT_BYTES:
        raise TileCLIError("source exceeds 256 KB read budget")
    def pairs_unique(pairs):
        output={}
        for key,value in pairs:
            if key in output:
                raise TileCLIError("duplicate original tile source key")
            output[key]=value
        return output
    def reject_special(_:str):
        raise TileCLIError("non-finite JSON numbers cannot describe pixels")
    try:
        data=json.loads(payload.decode("utf-8","strict"),
                        object_pairs_hook=pairs_unique,parse_constant=reject_special)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise TileCLIError("malformed UTF-8 original tile JSON") from exc
    if not isinstance(data,dict) or set(data)!={"schema","project_id","tiles"}:
        raise TileCLIError("input must declare exact schema, project_id and tiles")
    if data["schema"]!=SCHEMA:
        raise TileCLIError("unknown original indexed-tile schema")
    project=data["project_id"]
    if (not isinstance(project,str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}",project)):
        raise TileCLIError("invalid bounded original project identifier")
    return data


def main(argv: Sequence[str] | None=None) -> int:
    parser=argparse.ArgumentParser(
        description="Compile acknowledged-original 8x8 pixel data to native source declarations"
    )
    parser.add_argument("--input",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--target",required=True)
    parser.add_argument("--syntax",choices=("c99","rgbds","ca65"),required=True)
    parser.add_argument("--symbol",default="ORIGINAL_TILES")
    parser.add_argument("--acknowledge-original",action="store_true")
    args=parser.parse_args(argv)
    try:
        if args.acknowledge_original is not True:
            raise TileCLIError("explicit original-source acknowledgement required")
        payload=_load_source(args.input.expanduser())
        bundle=compile_original_tile_bundle(
            args.target,payload["tiles"],acknowledged_original_source=True,
        )
        if not verify_original_tile_roundtrip(bundle,payload["tiles"]):
            raise TileCLIError("native tile bytes failed strict source roundtrip")
        output=emit_original_tile_source(bundle,syntax=args.syntax,symbol=args.symbol)
        # Exclusive creation prevents replacing a user file or following an
        # existing output symlink. This does not bless a writable parent dir.
        with args.output.expanduser().open("x",encoding="utf-8",newline="\n") as dest:
            dest.write(output)
        receipt={
            "schema":"skeleton.game_builder.portable_tile_compile.v1",
            "project_id":payload["project_id"],
            "target_id":bundle.target_id,
            "tile_codec":bundle.tile_codec,
            "tile_count":bundle.tile_count,
            "native_sha256":bundle.native_sha256,
            "source_sha256":hashlib.sha256(output.encode("utf-8")).hexdigest(),
            "source_bytes":len(output.encode("utf-8")),
            "original_source_acknowledged":True,
            "independent_rights_cleared":False,
            "native_binary_verified":False,
            "release_authorized":False,
        }
        print(json.dumps(receipt,sort_keys=True,separators=(",",":")))
        return 0
    except (TileCLIError, ValueError, PermissionError, OSError) as exc:
        print("portable tile compilation refused: "+str(exc),file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
