"""Explicit physical-device speculative decoding diagnostic, no activation.

Compare pinned target and draft checkpoints with the same target sampling
policy. Measure wall time, acceptance and first-token empirical distributions.
The stochastic algorithm uses different RNG trajectories from serial sampling;
only deterministic greedy mode is expected to match serial tokens exactly.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import replace
from hashlib import sha256
import json
import math
from pathlib import Path
import statistics
import time

from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.model_runtime.runtime_contracts import DevicePolicy,GenerationConfig,RuntimeContractError
from skeleton.ai.model_runtime.flgb_model_runtime import digest_json
from skeleton.app.jeeves_stochastic_speculation import generate
from skeleton.retrieval.learned_embeddings import _read_pinned

MAX_CHECKPOINT=1024**3
MAX_CORPUS=65536


def corpus(path,pin):
    data=json.loads(_read_pinned(path,pin,MAX_CORPUS))
    if (type(data) is not list or not 1<=len(data)<=16 or len(set(data))!=len(data)
            or any(type(q) is not str or not q.strip() or len(q.encode())>1024 for q in data)):
        raise ValueError("one to sixteen bounded distinct private prompts required")
    return data


def _p95(xs):
    return sorted(xs)[max(0,math.ceil(len(xs)*.95)-1)]


def _stats(rows):
    elapsed=[r["elapsed_ms"] for r in rows]
    tokens=sum(r["tokens"] for r in rows)
    total=sum(elapsed)
    return {"cases":len(rows),"generated_tokens":tokens,"total_ms":round(total,3),
            "median_ms":round(statistics.median(elapsed),3),"p95_ms":round(_p95(elapsed),3),
            "aggregate_tokens_per_second":round(tokens*1000/total,4) if total else None}


def _tv(left,right):
    keys=set(left)|set(right);a=sum(left.values());b=sum(right.values())
    if not a or not b:
        raise ValueError("empty observed first-token distribution")
    return sum(abs(left[k]/a-right[k]/b) for k in keys)/2


def qualify(target,draft,prompts,*,config,block,seeds,require_gpu,workspace_bytes):
    if (type(seeds) is not int or not 8<=seeds<=128 or type(prompts) is not list
            or not 1<=len(prompts)<=16 or len(prompts)*seeds>512):
        raise ValueError("bounded explicit benchmark workload required")
    device=target.device.actual
    if require_gpu and device!="cuda":
        raise RuntimeContractError("physical CUDA evidence requires an admitted CUDA target")
    def sync():
        if device=="cuda":
            target.model._accel.torch.cuda.synchronize()
    pins=(target.model_digest,draft.model_digest,target.tokenizer.digest)
    baseline=[];speculative=[];cases=[]
    calls=accepted=proposed=0
    # Actual warm-up, excluded from timed samples.
    warm=replace(config,max_new_tokens=min(2,config.max_new_tokens),seed=-1)
    target.generate(prompts[0],warm)
    generate(target,draft,prompts[0],warm,block=block,require_gpu=require_gpu,workspace_bytes=workspace_bytes)
    started=time.monotonic()
    for index,prompt in enumerate(prompts):
        first_a,first_b=Counter(),Counter()
        parity=0
        for seed in range(seeds):
            if time.monotonic()-started>900:
                raise TimeoutError("benchmark cooperative deadline; no partial qualification")
            policy=replace(config,seed=seed)
            def poll():
                if time.monotonic()-started>900:
                    raise TimeoutError("benchmark deadline")
            def serial():
                sync();stamp=time.perf_counter()
                result=target.generate(prompt,policy,interrupt=poll)
                sync()
                return {"elapsed_ms":(time.perf_counter()-stamp)*1000,
                        "ids":list(result.generated_ids),"tokens":len(result.generated_ids),
                        "output_sha256":result.output_digest}
            def spec():
                sync();stamp=time.perf_counter()
                result=generate(target,draft,prompt,policy,block=block,
                    require_gpu=require_gpu,workspace_bytes=workspace_bytes,interrupt=poll)
                sync()
                return {"elapsed_ms":(time.perf_counter()-stamp)*1000,
                        "ids":result["generated_ids"],"tokens":len(result["generated_ids"]),
                        "output_sha256":digest_json(result["generated_ids"]),
                        "receipt_sha256":result["receipt_sha256"],
                        "target_passes":result["target_block_graph_calls"],
                        "accepted":result["accepted_draft_tokens"],"proposed":result["proposed_tokens"]}
            # Alternate execution order to reduce systematic warm-cache bias.
            if (index+seed)%2:
                b=spec();a=serial()
            else:
                a=serial();b=spec()
            if not a["ids"] or not b["ids"]:
                raise RuntimeContractError("empty benchmark generation")
            first_a[a["ids"][0]]+=1;first_b[b["ids"][0]]+=1
            parity+=a["ids"]==b["ids"]
            calls+=b["target_passes"];accepted+=b["accepted"];proposed+=b["proposed"]
            baseline.append({k:v for k,v in a.items() if k!="ids"})
            speculative.append({k:v for k,v in b.items() if k!="ids"})
        cases.append({"prompt_sha256":sha256(prompt.encode()).hexdigest(),
            "seed_count":seeds,"first_token_total_variation_empirical":round(_tv(first_a,first_b),6),
            "exact_sequence_matches":parity,"first_token_serial_counts":dict(sorted(first_a.items())),
            "first_token_speculative_counts":dict(sorted(first_b.items()))})
    target.assert_model_unchanged();draft.assert_model_unchanged()
    if pins!=(target.model_digest,draft.model_digest,target.tokenizer.digest):
        raise RuntimeContractError("benchmark model binding drift")
    base=_stats(baseline);spec_stats=_stats(speculative)
    result={"schema":"skeleton.jeeves.speculative-hardware-diagnostic.v1",
            "target_model_digest":pins[0],"draft_model_digest":pins[1],"tokenizer_digest":pins[2],
            "target_device_receipt":target.device.to_dict(),"draft_device_receipt":draft.device.to_dict(),
            "config":config.to_dict(),"block":block,"workspace_bytes":workspace_bytes,
            "seeds_per_prompt":seeds,"serial":base,"speculative":spec_stats,
            "observed_wall_speed_ratio":round(base["total_ms"]/spec_stats["total_ms"],5),
            "target_block_calls":calls,"proposed_tokens":proposed,"accepted_tokens":accepted,
            "observed_draft_acceptance":round(accepted/proposed,6) if proposed else None,
            "cases":cases,"serial_runs":baseline,"speculative_runs":speculative,
            "greedy_exact_token_parity":all(x["exact_sequence_matches"]==seeds for x in cases)
              if config.temperature<=1e-8 or config.top_k==1 else None,
            "distribution_equivalence_certified":False,"cross_hardware_speedup_certified":False,
            "production_quality_certified":False,"activation_authorized":False}
    result["receipt_sha256"]=digest_json(result)
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ("target","draft","corpus"):
        parser.add_argument("--"+name,type=Path,required=True)
        parser.add_argument("--"+name+"-sha256",required=True)
    parser.add_argument("--device",choices=("cpu","torch-cpu","cuda"),default="cpu")
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--block",type=int,default=4)
    parser.add_argument("--tokens",type=int,default=16)
    parser.add_argument("--seeds",type=int,default=8)
    parser.add_argument("--temperature",type=float,default=.8)
    parser.add_argument("--workspace-bytes",type=int,default=256*1024**2)
    parser.add_argument("--approve-local-qualification",action="store_true")
    args=parser.parse_args(argv)
    if not args.approve_local_qualification:
        parser.error("explicit local hardware qualification approval is required")
    target=NativeLLMRuntime.restore_json(_read_pinned(args.target,args.target_sha256,MAX_CHECKPOINT),
                          device_policy=DevicePolicy(requested=args.device,allow_fallback=False))
    draft=NativeLLMRuntime.restore_json(_read_pinned(args.draft,args.draft_sha256,MAX_CHECKPOINT),
                          device_policy=DevicePolicy(requested="cpu",allow_fallback=False))
    report=qualify(target,draft,corpus(args.corpus,args.corpus_sha256),
        config=GenerationConfig(max_new_tokens=args.tokens,temperature=args.temperature,use_cache=False),
        block=args.block,seeds=args.seeds,require_gpu=args.device=="cuda",workspace_bytes=args.workspace_bytes)
    report["corpus_file_sha256"]=args.corpus_sha256
    report["receipt_sha256"]=digest_json({k:v for k,v in report.items() if k!="receipt_sha256"})
    # Exclusive publication: never overwrite earlier hardware evidence.
    with args.output.open("x",encoding="utf-8") as handle:
        json.dump(report,handle,indent=2,sort_keys=True,allow_nan=False)
        handle.write("\n")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
