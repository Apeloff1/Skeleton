"""Render bounded batches of actual chronicle manuals and source SHA manifests."""
from __future__ import annotations
import argparse
from hashlib import sha256
import json
from pathlib import Path
from skeleton.forge.game_frontier_studio_chronicle_handbooks import (
    BOOK_COUNT,CHRONICLE_BOOK_PATHS,identity,receipt,
)
def export(destination:Path,*,offset:int=0,limit:int=32)->dict:
    if (type(offset) is not int or type(limit) is not int
        or not 0<=offset<BOOK_COUNT or not 1<=limit<=100
        or offset+limit>BOOK_COUNT):
        raise ValueError("chronicle export needs 1-100 valid manuscript IDs")
    root=destination.resolve()
    receipts=[]
    rankings=[]
    for i in range(offset,offset+limit):
        item=receipt(*identity(i))
        body=item.pop("markdown")
        path=(root/CHRONICLE_BOOK_PATHS[i]).resolve()
        if not path.is_relative_to(root):
            raise ValueError("book path escapes root")
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(body,encoding="utf8")
        if sha256(path.read_bytes()).hexdigest()!=item["content_sha256"]:
            raise ValueError("written manuscript failed SHA integrity")
        receipts.append(item)
        rankings.append({key:item[key] for key in
                         ("path","volume","quality_score","words","bytes","content_sha256")})
    ranking={
        "quality":sorted(rankings,key=lambda x:(-x["quality_score"],-x["words"],x["path"])),
        "length":sorted(rankings,key=lambda x:(-x["words"],-x["quality_score"],x["path"])),
    }
    manifest=root/f"chronicle_manifest_{offset}_{offset+limit}.json"
    manifest.write_text(json.dumps({
        "schema":"skeleton.forge.chronicle_export_manifest.v1",
        "scope":"actual_exported_batch_only","catalog":BOOK_COUNT,
        "range":[offset,offset+limit],"receipts":receipts,"ranking":ranking,
    },sort_keys=True,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    return {"catalog":BOOK_COUNT,"exported":len(receipts),
            "manifest":str(manifest),"scope":"actual_exported_batch_only"}
def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--offset",type=int,default=0)
    p.add_argument("--limit",type=int,default=32)
    a=p.parse_args()
    print(json.dumps(export(a.out,offset=a.offset,limit=a.limit),sort_keys=True))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
