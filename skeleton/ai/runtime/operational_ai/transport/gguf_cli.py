"""Linux offline GGUF CLI: verify, capacity-check and generate real model tokens.

Usage:
 python -m skeleton.ai.runtime.operational_ai.transport.gguf_cli verify --root /secure/models
 python -m skeleton.ai.runtime.operational_ai.transport.gguf_cli chat --root /secure/models --message 'Hello'
"""
from __future__ import annotations
import argparse,json,sys
from ..model.gguf.service import load_approved_manifest,activate_model
from ..model.gguf.memory import assess_memory
from ..model.gguf.manifest import GGUFManifestError


def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(description='Offline, verified local GGUF runtime')
    p.add_argument('action',choices=['verify','chat','smoke'])
    p.add_argument('--root',required=True)
    p.add_argument('--manifest',default='model.manifest.json')
    p.add_argument('--message',default='Hello')
    p.add_argument('--max-tokens',type=int,default=64)
    p.add_argument('--context',type=int,default=2048)
    p.add_argument('--threads',type=int,default=4)
    p.add_argument('--gpu-layers',type=int,default=0)
    args=p.parse_args(argv)
    try:
        manifest=load_approved_manifest(args.root,args.manifest)
        capacity=assess_memory(manifest)
        if not capacity.accepted:raise GGUFManifestError('not enough available memory')
        if args.action=='verify':
            from ..model.gguf.assembly import assemble_model
            from ..model.gguf.header import inspect_header
            with assemble_model(args.root,manifest) as assembly:
                header=inspect_header(assembly.fd)
                print(json.dumps({'status':'verified-shards-not-inference-qualified',
                    'model_sha256':assembly.sha256,'version':header.version,
                    'tensors':header.tensors,'bytes':assembly.bytes},sort_keys=True))
            return 0
        with activate_model(args.root,manifest,n_ctx=args.context,n_threads=args.threads,
                            n_gpu_layers=args.gpu_layers) as backend:
            if args.action=='smoke':
                from ..model.gguf.selftest import live_smoke
                print(json.dumps(live_smoke(backend),sort_keys=True))
            else:
                if not 1<=args.max_tokens<=4096:raise GGUFManifestError('output token budget invalid')
                result=backend.generate([{'role':'user','content':args.message}],
                    max_output_tokens=args.max_tokens,seed=7,temperature=0.8)
                print(json.dumps({'text':result.text,'model_sha256':result.model_digest,
                     'prompt_tokens':result.prompt_tokens,'generated_tokens':result.generated_tokens,
                     'output_sha256':result.output_digest,'finish_reason':result.finish_reason},
                    sort_keys=True))
        return 0
    except (GGUFManifestError,OSError) as exc:
        print(f'OFFLINE MODEL NOT READY: {exc}',file=sys.stderr)
        return 2

if __name__=='__main__':raise SystemExit(main())
