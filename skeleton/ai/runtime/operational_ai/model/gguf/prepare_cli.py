"""Operator-controlled, source-bound sharding entry point (no Git binary writes)."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from dataclasses import asdict
from .prepare import prepare_gguf
from .manifest import GGUFManifestError


def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(description='Create real private, small GGUF shards for ordered AI bundle')
    p.add_argument('--input',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--model-id',required=True)
    p.add_argument('--license',required=True)
    p.add_argument('--source',required=True)
    p.add_argument('--rights-approved',action='store_true',required=True)
    p.add_argument('--context',type=int,default=8192)
    p.add_argument('--memory-bytes',type=int,default=4_000_000_000)
    p.add_argument('--gpu-layers',type=int,default=0)
    args=p.parse_args(argv)
    try:
        result=prepare_gguf(args.input,args.output_dir,model_id=args.model_id,
            license=args.license,source=args.source,rights_approved=args.rights_approved,
            context_ceiling=args.context,memory_bytes=args.memory_bytes,
            gpu_layers_ceiling=args.gpu_layers)
        print(json.dumps(asdict(result),sort_keys=True))
        return 0
    except (GGUFManifestError,OSError,ValueError) as exc:
        print(json.dumps({'status':'blocked','reason':str(exc)}),file=sys.stderr)
        return 2

if __name__=='__main__':raise SystemExit(main())
