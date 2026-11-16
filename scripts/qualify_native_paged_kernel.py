"""Measure native CUDA paged attention and serial inference against pinned local checkpoint."""
from __future__ import annotations
import argparse,json,hashlib
from pathlib import Path
from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.model_runtime.runtime_contracts import DevicePolicy
from skeleton.ai.model_runtime.kernel_qualification import measure


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--checkpoint",type=Path,required=True)
    p.add_argument("--sha256",required=True)
    p.add_argument("--prompt-file",type=Path,action="append",required=True)
    p.add_argument("--workspace-bytes",type=int,required=True)
    p.add_argument("--kv-bytes",type=int,required=True)
    p.add_argument("--repeats",type=int,default=3)
    p.add_argument("--max-new-tokens",type=int,default=8)
    p.add_argument("--cpu-reference",action="store_true")
    a=p.parse_args(argv)
    with a.checkpoint.open("rb") as f:
        raw=f.read(256*1024**2+1)
    if len(raw)>256*1024**2 or hashlib.sha256(raw).hexdigest()!=a.sha256:
        p.error("checkpoint digest/size mismatch")
    prompts=[]
    for path in a.prompt_file:
        with path.open("rb") as f:
            text=f.read(65537)
        if not 1<=len(text)<=65536:
            p.error("prompt size outside bounds")
        prompts.append(text.decode())
    rt=NativeLLMRuntime.restore_json(raw,device_policy=DevicePolicy(
        requested="torch-cpu" if a.cpu_reference else "cuda",allow_fallback=False))
    print(json.dumps(measure(rt,prompts,repeats=a.repeats,max_new_tokens=a.max_new_tokens,
        max_workspace_bytes=a.workspace_bytes,paged_kv_bytes=a.kv_bytes,
        require_gpu=not a.cpu_reference),allow_nan=False,sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
