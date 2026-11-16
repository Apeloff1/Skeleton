"""Run real native resident GGUF competitive holdout campaign."""
from __future__ import annotations
import argparse,json
from pathlib import Path
from skeleton.ai.runtime.inference.competitive_holdout import Competitor, read_holdout, compare
from skeleton.ai.runtime.inference.resident_gguf_batch import ResidentBatchPolicy


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--profile",action="append",required=True,metavar="LABEL=MANIFEST=SHA256")
    p.add_argument("--holdout",type=Path,required=True)
    p.add_argument("--holdout-sha256",required=True)
    p.add_argument("--server",type=Path,required=True)
    p.add_argument("--server-sha256",required=True)
    p.add_argument("--server-library",action="append",default=[])
    p.add_argument("--slots",type=int,default=2)
    p.add_argument("--context-per-slot",type=int,required=True)
    p.add_argument("--gpu-layers",type=int,required=True)
    p.add_argument("--memory-bytes",type=int,required=True)
    p.add_argument("--repeats",type=int,default=3)
    p.add_argument("--max-new-tokens",type=int,default=128)
    a=p.parse_args(argv)
    profiles=[]
    for row in a.profile:
        label,path,pin=row.split("=",2)
        profiles.append(Competitor(label,Path(path),pin))
    data=read_holdout(a.holdout,a.holdout_sha256)
    policy=ResidentBatchPolicy(a.slots,a.context_per_slot,a.gpu_layers,a.memory_bytes)
    report=compare(profiles,data,holdout_sha256=a.holdout_sha256,server=a.server,server_sha256=a.server_sha256,
        policy=policy,runtime_libraries=tuple(tuple(x.split("=",1)) for x in a.server_library),
        repeats=a.repeats,max_new_tokens=a.max_new_tokens)
    print(json.dumps(report,sort_keys=True,allow_nan=False))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
