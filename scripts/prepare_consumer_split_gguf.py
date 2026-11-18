"""Create a native multi-shard GGUF manifest from explicit ordered local pins."""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from skeleton.ai.runtime.inference.deployment import create_local_model_deployment
from skeleton.ai.runtime.inference.gguf_bundle import admit_native_bundle, split_identity


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--first",type=Path,required=True)
    parser.add_argument("--sha256",action="append",required=True)
    parser.add_argument("--runtime",type=Path,required=True)
    parser.add_argument("--manifest",type=Path,required=True)
    parser.add_argument("--model-id",required=True)
    parser.add_argument("--context",type=int,required=True)
    parser.add_argument("--gpu-layers",type=int,default=0)
    parser.add_argument("--threads",type=int)
    parser.add_argument("--max-bytes",type=int,required=True)
    args=parser.parse_args(argv)
    pins=tuple(args.sha256)
    audit=admit_native_bundle(args.first,pins,max_bytes=args.max_bytes)
    deployment=create_local_model_deployment(args.manifest,executable_path=args.runtime,
        model_path=args.first,model_id=args.model_id,context_size=args.context,
        gpu_layers=args.gpu_layers,threads=args.threads,model_shard_sha256=pins)
    if deployment.execution_model_sha256 != split_identity(pins):
        raise RuntimeError("prepared bundle identity differs")
    print(json.dumps({"status":"split_manifest_created_not_qualified",
        "model_sha256":deployment.execution_model_sha256,
        "manifest_sha256":deployment.manifest_digest,"model_bytes":audit["total_bytes"],
        "shards":len(pins),"activation_authorized":False},sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
