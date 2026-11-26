"""Machine-bound measured kernel selection; no automatic promotion or fallback."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import statistics
import time

from .flgb_model_runtime import digest_json
from .runtime_contracts import BatchGenerationRequest, GenerationConfig, RuntimeContractError

_KERNEL_FILES=("paged_attention.py","paged_cuda.py","native_llm_runtime.py")


def kernel_identity(runtime):
    a=getattr(runtime.model,"_accel",None)
    if a is None or not a.resident:
        raise RuntimeContractError("resident accelerator required for kernel qualification")
    torch=a.torch
    hardware={"device":a.device_name,"torch":str(torch.__version__),
              "torch_cuda":str(torch.version.cuda),"kv_dtype":a.kv_dtype_name}
    if a.device_name=="cuda":
        props=torch.cuda.get_device_properties(a.device)
        hardware.update(name=props.name, capability=[props.major,props.minor],
                total_memory=int(props.total_memory),multiprocessors=props.multi_processor_count,
                triton=importlib.metadata.version("triton"))
    elif a.device_name=="cpu":
        import platform
        hardware.update(machine=platform.machine(),processor=platform.processor(),threads=torch.get_num_threads())
    else:
        raise RuntimeContractError("custom paged profile only supports CUDA and explicit CPU reference")
    return {"model_sha256":runtime.model_digest,"tokenizer_sha256":runtime.tokenizer.digest,
            "architecture_sha256":runtime.architecture.digest,"device_sha256":runtime.device.digest,
            "hardware":hardware,
            "source":{n:hashlib.sha256(Path(__file__).with_name(n).read_bytes()).hexdigest() for n in _KERNEL_FILES}}


def _sync(a):
    if a.device_name=="cuda":
        a.torch.cuda.synchronize(a.device)


def _p95(values):
    values=sorted(values)
    return values[math.ceil(len(values)*.95)-1]


def measure(runtime, prompts, *, repeats=3, max_new_tokens=8,
            max_workspace_bytes, paged_kv_bytes, require_gpu=True, interrupt=None):
    """Paired single-request latency and batched throughput on the same exact model.

    Wall time includes runtime admission+checkpoint costs, not just kernels.
    Every timed trial must return identical token trajectories; no selective
    discarding of failed or slow samples. No synthetic benchmark claims.
    """
    if type(repeats) is not int or not 3<=repeats<=10:
        raise ValueError("kernel sweep requires 3–10 repeats")
    if not 2<=len(prompts)<=8 or any(not isinstance(p,str) or not p.strip() for p in prompts):
        raise ValueError("2–8 local prompts required")
    if type(max_new_tokens) is not int or not 1<=max_new_tokens<=128:
        raise ValueError("kernel qualification output bound exceeded")
    if type(require_gpu) is not bool:
        raise ValueError("explicit hardware mode required")
    identity=kernel_identity(runtime)
    a=runtime.model._accel
    if require_gpu and a.device_name!="cuda":
        raise RuntimeContractError("GPU paged qualification requires CUDA")
    cfg=GenerationConfig(max_new_tokens=max_new_tokens,temperature=0,use_cache=True)
    reqs=[BatchGenerationRequest(f"q-{i}",p,cfg) for i,p in enumerate(prompts)]
    runtime._admit_batch(reqs,interrupt=interrupt)
    rows=[]
    def invoke(group,paged):
        if interrupt is not None:
            interrupt()
        a.reset_decode_cache()
        _sync(a)
        if a.device_name=="cuda":
            a.torch.cuda.reset_peak_memory_stats(a.device)
        started=time.perf_counter()
        results=(runtime.generate_fused_batch(group,max_active_slots=len(group),
                  max_workspace_bytes=max_workspace_bytes,paged_kv_bytes=paged_kv_bytes,
                  require_gpu=require_gpu,interrupt=interrupt) if paged else
                  runtime.generate_batch(group,interrupt=interrupt))
        _sync(a)
        elapsed=time.perf_counter()-started
        if not math.isfinite(elapsed) or elapsed<=0:
            raise RuntimeContractError("invalid hardware timing")
        count=sum(r.result.usage.generated_tokens for r in results)
        if count<=0:
            raise RuntimeContractError("qualification generated no tokens")
        return {"seconds":elapsed,"tokens":count,"output_sha256":[r.result.output_digest for r in results],
                "peak_allocated_bytes":int(a.torch.cuda.max_memory_allocated(a.device)) if a.device_name=="cuda" else None}
    with a._inference_lock(interrupt):
        # Explicit unmeasured warmup compiles kernel and establishes successful graph.
        for group in (reqs[:1],reqs):
            invoke(group,False)
            invoke(group,True)
        for repeat in range(repeats):
            for mode,group in (("single",[reqs[repeat%len(reqs)]]),("batch",reqs)):
                measured={}
                for candidate in ((False,True) if repeat%2==0 else (True,False)):
                    measured["paged" if candidate else "serial"]=invoke(group,candidate)
                rows.append({"mode":mode,"repeat":repeat,**measured,
                             "exact":measured["serial"]["output_sha256"]==measured["paged"]["output_sha256"]})
        a.reset_decode_cache()
    if kernel_identity(runtime)!=identity:
        raise RuntimeContractError("hardware or source changed during qualification")
    result={"schema":"skeleton.native.kernel-measurement.v1","identity":identity,
            "max_workspace_bytes":max_workspace_bytes,"paged_kv_bytes":paged_kv_bytes,
            "max_new_tokens":max_new_tokens,"prompt_sha256":[hashlib.sha256(p.encode()).hexdigest() for p in prompts],
            "repeats":repeats,"rows":rows,"physical_gpu":a.device_name=="cuda",
            "measurement_scope":"operator_local_wall_time_and_cuda_torch_allocator_peak",
            "activation_authorized":False}
    result["measurement_sha256"]=digest_json(result)
    return result


@dataclass(frozen=True)
class MeasuredKernelProfile:
    measurement_sha256: str
    identity_sha256: str
    paged_kv_bytes: int
    max_workspace_bytes: int
    speedup_ppm: int
    max_output_tokens: int
    profile_kind: str="cuda_paged_decode"

    @property
    def digest(self):
        return digest_json(self.__dict__)

    def assert_matches(self,runtime):
        if (self.profile_kind!="cuda_paged_decode" or runtime.device.actual!="cuda"
            or digest_json(kernel_identity(runtime))!=self.identity_sha256):
            raise RuntimeContractError("measured GPU kernel profile no longer matches execution")

    @classmethod
    def admit(cls,runtime,report,expected_sha256,*,minimum_speedup_ppm=1050000):
        if type(minimum_speedup_ppm) is not int or not 1000000<=minimum_speedup_ppm<=10000000:
            raise ValueError("invalid required speedup")
        if not isinstance(report,dict) or report.get("measurement_sha256")!=expected_sha256 or digest_json({k:v for k,v in report.items() if k!="measurement_sha256"})!=expected_sha256:
            raise RuntimeContractError("measurement identity mismatch")
        if (report.get("schema")!="skeleton.native.kernel-measurement.v1" or report.get("physical_gpu") is not True
            or report.get("activation_authorized") is not False or report.get("identity")!=kernel_identity(runtime)
            or runtime.device.actual!="cuda"):
            raise RuntimeContractError("only matching real CUDA measurements may admit a kernel profile")
        repeats=report.get("repeats")
        rows=report.get("rows")
        if type(repeats) is not int or not 3<=repeats<=10 or not isinstance(rows,list) or len(rows)!=2*repeats:
            raise RuntimeContractError("incomplete paired kernel sweep")
        expected={(mode,i) for mode in ("single","batch") for i in range(repeats)}
        seen=set()
        for row in rows:
            key=(row.get("mode"),row.get("repeat"))
            if key not in expected or key in seen or row.get("exact") is not True:
                raise RuntimeContractError("missing, duplicate or nonequivalent kernel trial")
            seen.add(key)
            for field in ("serial","paged"):
                v=row[field]
                if (type(v["seconds"]) not in {int,float} or not math.isfinite(v["seconds"]) or v["seconds"]<=0
                    or type(v["tokens"]) is not int or v["tokens"]<=0
                    or type(v["peak_allocated_bytes"]) is not int or v["peak_allocated_bytes"]<=0):
                    raise RuntimeContractError("invalid physical kernel observation")
            if row["serial"]["tokens"]!=row["paged"]["tokens"] or row["serial"]["output_sha256"]!=row["paged"]["output_sha256"]:
                raise RuntimeContractError("kernel parity failure")
        single=[x for x in rows if x["mode"]=="single"]
        batch=[x for x in rows if x["mode"]=="batch"]
        single_speed=statistics.median(x["serial"]["seconds"]/x["paged"]["seconds"] for x in single)
        batch_speed=statistics.median(x["serial"]["seconds"]/x["paged"]["seconds"] for x in batch)
        # Application activates the paged kernel for individual requests.
        # Require both single and batch wins, and reject worse p95 latency.
        score=int(min(single_speed,batch_speed)*1000000)
        if score<minimum_speedup_ppm or any(_p95([x["paged"]["seconds"] for x in values])>_p95([x["serial"]["seconds"] for x in values]) for values in (single,batch)):
            raise RuntimeContractError("measured paged profile did not meet latency and throughput floors")
        budgets=[report[k] for k in ("paged_kv_bytes","max_workspace_bytes","max_new_tokens")]
        if any(type(x) is not int or not 1<=x<=1024**4 for x in budgets) or budgets[2]>128:
            raise RuntimeContractError("kernel measurement resource bounds invalid")
        return cls(expected_sha256,digest_json(report["identity"]),*budgets[:2],score,budgets[2])
