"""Export real campaign Markdown with SHA receipts and two honest rankings.

Each batch renders only its requested source-grounded manuscripts, writes
bounded manifest shards and ranks *only the materialized batch* by measured
documentation-completeness and word length. No million-file memory load.

Run:
  python -m scripts.export_game_studio_campaign_handbooks --out build/books --offset 0 --limit 25
  python -m scripts.export_game_studio_campaign_handbooks --out build/books --offset 25 --limit 25
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

from skeleton.forge.game_frontier_studio_campaign_handbooks import (
    BOOK_COUNT, CAMPAIGN_BOOK_PATHS, identity, receipt,
)


def export(destination:Path,*,offset:int=0,limit:int=32)->dict:
    if (type(offset) is not int or type(limit) is not int or
        not 0<=offset<BOOK_COUNT or not 1<=limit<=1000 or
        offset+limit>BOOK_COUNT):
        raise ValueError("campaign export requires 1–1000 books in the valid catalog")
    root=destination.resolve()
    ranking=[]
    manifest_paths=[]
    for start in range(offset,offset+limit,100):
        end=min(offset+limit,start+100)
        receipts=[]
        for i in range(start,end):
            entry=receipt(*identity(i))
            doc=entry.pop("markdown")
            path=(root/CAMPAIGN_BOOK_PATHS[i]).resolve()
            if not path.is_relative_to(root):
                raise ValueError("manual path escapes authorized export folder")
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(doc,encoding="utf8")
            if sha256(path.read_bytes()).hexdigest()!=entry["content_sha256"]:
                raise ValueError("on-disk manual differs from SHA receipt")
            receipts.append(entry)
            ranking.append({
                "path":entry["path"],"volume":entry["volume"],
                "quality_score":entry["quality_score"],
                "words":entry["words"],"characters":entry["characters"],
                "content_sha256":entry["content_sha256"],
            })
        manifest=root/f"campaign_books_{start}_{end}.json"
        manifest.write_text(json.dumps({
            "schema":"skeleton.forge.campaign_handbook_manifest.v1",
            "catalog":BOOK_COUNT,"range":[start,end],"receipts":receipts,
        },indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf8")
        manifest_paths.append(str(manifest))
    variants={
        "quality":sorted(ranking,key=lambda x:(-x["quality_score"],-x["words"],x["path"])),
        "length":sorted(ranking,key=lambda x:(-x["words"],-x["quality_score"],x["path"])),
    }
    rankfile=root/f"campaign_ranking_{offset}_{offset+limit}.json"
    rankfile.write_text(json.dumps({
        "schema":"skeleton.forge.campaign_handbook_batch_ranking.v1",
        "scope":"only_this_rendered_export_batch","catalog":BOOK_COUNT,
        "evaluated":len(ranking),"ranking":variants,
    },indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf8")
    return {"total_catalog":BOOK_COUNT,"exported":len(ranking),
            "manifest_count":len(manifest_paths),
            "ranking_file":str(rankfile),"scope":"rendered_export_batch_only",
            "first":ranking[0]["path"],"last":ranking[-1]["path"]}


def main()->int:
    p=argparse.ArgumentParser(description="Export real game production manuals ranked by measured quality and length")
    p.add_argument("--out",required=True,type=Path)
    p.add_argument("--offset",type=int,default=0)
    p.add_argument("--limit",type=int,default=32)
    args=p.parse_args()
    try:
        result=export(args.out,offset=args.offset,limit=args.limit)
    except (OSError,ValueError) as exc:
        print(f"Campaign handbook export failed: {exc}",file=sys.stderr)
        return 2
    print(json.dumps(result,sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
