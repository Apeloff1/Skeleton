"""Run real native resident GGUF competitive holdout campaign."""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
from skeleton.ai.runtime.inference.competitive_holdout import Competitor, read_holdout, compare, compare_runtime_profiles
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
    p.add_argument("--runtime-variants",type=Path,help="Pinned JSON mapping labels to typed policy overrides")
    p.add_argument("--runtime-variants-sha256")
    p.add_argument("--baseline")
    p.add_argument("--minimum-speedup",type=float,default=1.05)
    p.add_argument("--maximum-tail-ratio",type=float,default=1.05)
    p.add_argument("--repeats",type=int,default=3)
    p.add_argument("--max-new-tokens",type=int,default=128)
    a=p.parse_args(argv)
    profiles=[]
    for row in a.profile:
        label,path,pin=row.split("=",2)
        profiles.append(Competitor(label,Path(path),pin))
    policy=ResidentBatchPolicy(a.slots,a.context_per_slot,a.gpu_layers,a.memory_bytes)
    if a.runtime_variants is not None:
        from dataclasses import replace
        if len(profiles)!=1 or not a.baseline or not a.runtime_variants_sha256:
            p.error("runtime comparison requires one model, baseline and exact variants digest")
        if a.runtime_variants.is_symlink() or not a.runtime_variants.is_file():
            p.error("regular local runtime variants file required")
        with a.runtime_variants.open("rb") as stream:
            raw=stream.read(65537)
        if len(raw)>65536 or hashlib.sha256(raw).hexdigest()!=a.runtime_variants_sha256:
            p.error("runtime variants identity mismatch")
        def unique(pairs):
            result={}
            for name,value in pairs:
                if name in result:
                    raise ValueError("duplicate runtime variant JSON field")
                result[name]=value
            return result
        variants=json.loads(raw,object_pairs_hook=unique)
        fields={"prefill_threads","numa","split_mode","tensor_split","main_gpu",
                "cpu_moe_layers","moe_cache_mib","cpu_ffn_layers","batch_tokens",
                "microbatch_tokens","flash_attention"}
        if not isinstance(variants,dict) or not 2<=len(variants)<=8:
            p.error("2–8 runtime variants required")
        policies={}
        for label,config in variants.items():
            if not isinstance(config,dict) or set(config)-fields:
                p.error("runtime variant contains unapproved fields")
            if "tensor_split" in config:
                if not isinstance(config["tensor_split"],list):
                    p.error("tensor split must be a JSON list")
                config["tensor_split"]=tuple(config["tensor_split"])
            policies[label]=replace(policy,**config)
        report=compare_runtime_profiles(profiles[0],a.holdout,holdout_sha256=a.holdout_sha256,
            server=a.server,server_sha256=a.server_sha256,policies=policies,baseline=a.baseline,
            runtime_libraries=tuple(tuple(x.split("=",1)) for x in a.server_library),
            repeats=a.repeats,max_new_tokens=a.max_new_tokens,minimum_speedup=a.minimum_speedup,
            maximum_tail_ratio=a.maximum_tail_ratio)
        from skeleton.ai.runtime.inference.competitive_holdout import digest
        report.pop("report_sha256")
        report["variants_file_sha256"]=a.runtime_variants_sha256
        report["report_sha256"]=digest(report)
        print(json.dumps(report,sort_keys=True,allow_nan=False))
        return 0
    if a.baseline or a.runtime_variants_sha256:
        p.error("runtime comparison options require a variants file")
    data=read_holdout(a.holdout,a.holdout_sha256)
    report=compare(profiles,data,holdout_sha256=a.holdout_sha256,server=a.server,server_sha256=a.server_sha256,
        policy=policy,runtime_libraries=tuple(tuple(x.split("=",1)) for x in a.server_library),
        repeats=a.repeats,max_new_tokens=a.max_new_tokens)
    print(json.dumps(report,sort_keys=True,allow_nan=False))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
