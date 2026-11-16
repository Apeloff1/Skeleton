"""Independent operator holdout, matched native GGUF quality/throughput campaign.

Separate supplied holdout, exact answer scoring, identical engine/hardware and
slot policy; no downloads, hosted fallback, or automatic promotion. Report
retains only digests and counts, not private question/answer/model output.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
import math
import platform
import statistics
import time
from pathlib import Path

from .deployment import LocalModelDeployment
from .llama_cpp import LlamaCppModel
from .resident_gguf_batch import ResidentGGUFBatch, ResidentBatchPolicy


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()


def text_sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


@dataclass(frozen=True)
class Competitor:
    label: str
    manifest: Path
    manifest_sha256: str

    def __post_init__(self):
        import re
        if not isinstance(self.label,str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,40}",self.label):
            raise ValueError("invalid competitor identity")
        if not isinstance(self.manifest,Path) or not isinstance(self.manifest_sha256,str) or not re.fullmatch(r"[0-9a-f]{64}",self.manifest_sha256):
            raise ValueError("exact local manifest pin required")


def read_holdout(path: Path,expected_sha256: str):
    if path.is_symlink() or not path.is_file():
        raise ValueError("explicit local holdout required")
    with path.open("rb") as handle:
        raw=handle.read(4*1024**2+1)
    if len(raw)>4*1024**2 or hashlib.sha256(raw).hexdigest()!=expected_sha256:
        raise ValueError("holdout byte identity mismatch")
    payload=json.loads(raw)
    if not isinstance(payload,list) or not 4<=len(payload)<=256:
        raise ValueError("4–256 independent holdout cases required")
    names=set()
    prompts=set()
    for row in payload:
        if not isinstance(row,dict) or set(row)!={"id","category","prompt","exact"}:
            raise ValueError("invalid holdout record")
        if any(not isinstance(row[k],str) or not row[k].strip() for k in row):
            raise ValueError("invalid holdout text")
        if (len(row["id"])>128 or len(row["category"])>64 or len(row["prompt"].encode())>65536
            or len(row["exact"].encode())>8192 or row["id"] in names or text_sha(row["prompt"]) in prompts):
            raise ValueError("duplicate or oversized holdout")
        names.add(row["id"])
        prompts.add(text_sha(row["prompt"]))
    return payload


def compare(profiles,holdout,*,holdout_sha256,server,server_sha256,policy,
            runtime_libraries=(), repeats=3,max_new_tokens=128,total_seconds=3600):
    if not 2<=len(profiles)<=4 or len({x.label for x in profiles})!=len(profiles):
        raise ValueError("2–4 distinct local competitors required")
    if type(repeats) is not int or not 2<=repeats<=5 or type(total_seconds) is not int or not 1<=total_seconds<=14400:
        raise ValueError("campaign repeat/deadline outside bounds")
    if not isinstance(policy,ResidentBatchPolicy) or policy.slot_spill_bytes or len(holdout)%policy.slots:
        raise ValueError("matched campaign requires whole no-spill batches")
    if type(max_new_tokens) is not int or not 1<=max_new_tokens<=min(8192,policy.context_per_slot-1):
        raise ValueError("invalid matched output budget")
    if len(profiles)*len(holdout)*repeats>4096:
        raise ValueError("campaign trial ceiling exceeded")
    admitted={}
    for entry in profiles:
        selected=LocalModelDeployment.load(entry.manifest,expected_sha256=entry.manifest_sha256)
        model=LlamaCppModel(selected.llama_cpp_config(rehash_artifacts_each_run=True))
        if model.model_digest!=selected.execution_model_sha256:
            raise ValueError("competitor model identity changed")
        admitted[entry.label]=(selected,model)
    if len({x[1].model_digest for x in admitted.values()})!=len(profiles):
        raise ValueError("competitors must use distinct weight identities")
    start=time.monotonic()
    results=[]
    for repeat in range(repeats):
        # Rotate profile order to limit thermal/time-order bias.
        offset=repeat%len(profiles)
        ordered=list(profiles[offset:])+list(profiles[:offset])
        for entry in ordered:
            selected,model=admitted[entry.label]
            if time.monotonic()-start>=total_seconds:
                raise TimeoutError("competitive campaign incomplete; no partial winner")
            with ResidentGGUFBatch(model,server,server_sha256,policy,runtime_libraries=runtime_libraries) as session:
                # Warmup outside timing using explicit fixed non-holdout text.
                session.generate(["Output a short readiness response."]*policy.slots,max_new_tokens=1)
                for offset in range(0,len(holdout),policy.slots):
                    if time.monotonic()-start>=total_seconds:
                        raise TimeoutError("competitive campaign incomplete; no partial winner")
                    group=holdout[offset:offset+policy.slots]
                    began=time.perf_counter()
                    output=session.generate([row["prompt"] for row in group],max_new_tokens=max_new_tokens)
                    elapsed=time.perf_counter()-began
                    if not math.isfinite(elapsed) or elapsed<=0 or output["model_sha256"]!=model.model_digest or len(output["results"])!=len(group):
                        raise RuntimeError("invalid matched native evidence")
                    rows=[]
                    for case,result in zip(group,output["results"]):
                        rows.append({"case_sha256":digest({"id":case["id"],"category":case["category"]}),
                            "category_sha256":text_sha(case["category"]),"exact":result["text"]==case["exact"],
                            "response_sha256":text_sha(result["text"]),
                            "input_tokens":result["input_tokens"],"output_tokens":len(result["token_ids"])})
                    results.append({"label":entry.label,"repeat":repeat,"offset":offset,"seconds":elapsed,
                                    "offloaded_layers_reported":output["offloaded_layers_reported"],"cases":rows})
    summaries={}
    for entry in profiles:
        batches=[x for x in results if x["label"]==entry.label]
        cases=[row for b in batches for row in b["cases"]]
        durations=sorted(b["seconds"] for b in batches)
        tokens=sum(row["output_tokens"] for row in cases)
        summaries[entry.label]={"exact":sum(c["exact"] for c in cases),"attempts":len(cases),
            "total_native_output_tokens":tokens,"end_to_end_output_tokens_per_second":tokens/sum(durations),
            "median_batch_seconds":statistics.median(durations),"p95_batch_seconds":durations[math.ceil(len(durations)*.95)-1]}
    report={"schema":"skeleton.gguf.independent-holdout-comparison.v1","status":"operator_measured_not_certified",
        "holdout_file_sha256":holdout_sha256,"holdout_content_sha256":digest(holdout),
        "engine_sha256":server_sha256,"hardware_host":{"system":platform.system(),"machine":platform.machine()},
        "repeats":repeats,"slots":policy.slots,"context_per_slot":policy.context_per_slot,
        "gpu_layers_requested":policy.gpu_layers,"flash_attention":policy.flash_attention,
        "batch_tokens":policy.batch_tokens,"microbatch_tokens":policy.microbatch_tokens,
        "competitors":[{"label":label,"model_sha256":model.model_digest,"manifest_sha256":dep.manifest_digest,
                        "model_bytes":model.total_model_bytes} for label,(dep,model) in admitted.items()],
        "summaries":summaries,"rows":results,"activation_authorized":False,
        "limits":["exact output scoring only","operator-supplied holdout provenance not independently verified",
                  "native startup offload log required, no independent GPU profiler evidence",
                  "wall time includes per-batch custody and tokenization; warmup excluded"]}
    report["report_sha256"]=digest(report)
    return report
