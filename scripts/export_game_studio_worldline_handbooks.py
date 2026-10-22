"""Materialize the 9,000 worldline game-production manuals from live source.

Usage:
  python scripts/export_game_studio_worldline_handbooks.py --out /tmp/forge-books --all
  python scripts/export_game_studio_worldline_handbooks.py --out /tmp/forge-books --offset 0 --limit 10

The exact 9,000-page library is lazily rendered, never stored in game context,
and a manifest with SHA-256 receipts is written to the output directory.
All paths derive from fixed owner enums; no caller-supplied file paths execute.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

from skeleton.forge.game_frontier_studio_worldline_handbooks import (
    HANDBOOK_PATHS,VOLUME_COUNT,handbook_receipt,identity,
)


def export(out: Path, *, offset: int=0, limit: int=32) -> dict:
    if (type(offset) is not int or type(limit) is not int
        or not 0<=offset<VOLUME_COUNT or not 1<=limit<=VOLUME_COUNT
        or offset+limit>VOLUME_COUNT):
        raise ValueError("handbook export requires bounded index range")
    out=out.resolve()
    receipts=[]
    for i in range(offset,offset+limit):
        d,t,r,l=identity(i)
        receipt=handbook_receipt(d,t,r,l)
        destination=(out/HANDBOOK_PATHS[i]).resolve()
        if not destination.is_relative_to(out):
            raise ValueError("export destination escapes authorized output folder")
        destination.parent.mkdir(parents=True,exist_ok=True)
        text=receipt.pop("markdown")
        destination.write_text(text,encoding="utf-8")
        digest=sha256(destination.read_bytes()).hexdigest()
        if digest!=receipt["content_sha256"]:
            raise ValueError("generated handbook SHA receipt mismatch")
        receipts.append(receipt)
    result={"schema":"skeleton.forge.handbook_export.v1",
            "volume_catalog":VOLUME_COUNT,
            "offset":offset,"exported":len(receipts),
            "receipts":receipts}
    manifest=out/f"worldline_handbooks_{offset}_{limit}.json"
    manifest.write_text(
        json.dumps(result,sort_keys=True,indent=2,ensure_ascii=False)+"\n",
        encoding="utf-8")
    return {"total":VOLUME_COUNT,"exported":len(receipts),
            "manifest":str(manifest),
            "first":receipts[0]["path"],
            "last":receipts[-1]["path"]}


def main() -> int:
    parser=argparse.ArgumentParser(description="Export source-verified Forge Studio game-production manuals")
    parser.add_argument("--out",required=True,type=Path)
    parser.add_argument("--offset",type=int,default=0)
    parser.add_argument("--limit",type=int,default=32)
    parser.add_argument("--all",action="store_true",help="Generate all 9,000 books and receipts")
    args=parser.parse_args()
    if args.all and (args.offset!=0 or args.limit!=32):
        parser.error("--all cannot be combined with offset or limit")
    try:
        result=export(args.out,offset=0 if args.all else args.offset,
                      limit=VOLUME_COUNT if args.all else args.limit)
    except (ValueError,OSError) as exc:
        print(f"Forge handbook export failed: {exc}",file=sys.stderr)
        return 2
    print(json.dumps(result,sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
