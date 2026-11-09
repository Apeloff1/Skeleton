"""Export indexed phase manuscripts without materializing 90,000 in RAM.

Examples:
  python -m scripts.export_game_studio_phase_handbooks --out build/phase-books --offset 0 --limit 25
  python -m scripts.export_game_studio_phase_handbooks --out build/phase-books --all

Writes SHA-256 receipt manifest in capped chunks. All destination path
components are exact trusted enum identities, never arbitrary user filenames.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

from skeleton.forge.game_frontier_studio_phase_handbooks import (
    BOOK_COUNT,PHASE_BOOK_PATHS,identity,receipt,
)


def export(out:Path,*,offset:int=0,limit:int=32)->dict:
    if (type(offset) is not int or type(limit) is not int
        or not 0<=offset<BOOK_COUNT or not 1<=limit<=BOOK_COUNT
        or offset+limit>BOOK_COUNT):
        raise ValueError("phase-book export range outside ninety-thousand library")
    root=out.resolve()
    count=0
    manifests=[]
    for begin in range(offset,offset+limit,100):
        end=min(offset+limit,begin+100)
        index=[]
        for number in range(begin,end):
            meta=receipt(*identity(number))
            markdown=meta.pop("markdown")
            path=(root/PHASE_BOOK_PATHS[number]).resolve()
            if not path.is_relative_to(root):
                raise ValueError("phase handbook path escapes requested export root")
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(markdown,encoding="utf8")
            if sha256(path.read_bytes()).hexdigest()!=meta["content_sha256"]:
                raise ValueError("written phase handbook does not match SHA receipt")
            index.append(meta)
            count+=1
        manifest=root/f"phase_books_{begin}_{end}.json"
        manifest.write_text(json.dumps({
            "schema":"skeleton.forge.phase_handbook_manifest.v1",
            "catalog":BOOK_COUNT,"range":[begin,end],
            "receipts":index,
        },sort_keys=True,indent=2,ensure_ascii=False)+"\n",encoding="utf8")
        manifests.append(str(manifest))
    return {"total_catalog":BOOK_COUNT,"exported":count,
            "manifest_count":len(manifests),
            "first_manifest":manifests[0],"last_manifest":manifests[-1]}


def main()->int:
    parser=argparse.ArgumentParser(description="Export generated source-verified game phase manuals")
    parser.add_argument("--out",required=True,type=Path)
    parser.add_argument("--offset",default=0,type=int)
    parser.add_argument("--limit",default=32,type=int)
    parser.add_argument("--all",action="store_true")
    args=parser.parse_args()
    if args.all and (args.offset!=0 or args.limit!=32):
        parser.error("--all cannot be combined with --offset or --limit")
    try:
        result=export(args.out,offset=0 if args.all else args.offset,
                      limit=BOOK_COUNT if args.all else args.limit)
    except (ValueError,OSError) as exc:
        print(f"Phase handbook export failed: {exc}",file=sys.stderr)
        return 2
    print(json.dumps(result,sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
