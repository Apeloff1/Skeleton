"""Independent operator holdout, matched native GGUF quality/throughput campaign.

Separate supplied holdout, exact answer scoring, identical engine/hardware and
slot policy; no downloads, hosted fallback, or automatic promotion. Report
retains only digests and counts, not private question/answer/model output.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
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
        "runtime_profile_sha256":digest(asdict(policy)),"runtime_profile":asdict(policy),
        "competitors":[{"label":label,"model_sha256":model.model_digest,"manifest_sha256":dep.manifest_digest,
                        "model_bytes":model.total_model_bytes} for label,(dep,model) in admitted.items()],
        "summaries":summaries,"rows":results,"activation_authorized":False,
        "limits":["exact output scoring only","operator-supplied holdout provenance not independently verified",
                  "native startup offload log required, no independent GPU profiler evidence",
                  "wall time includes per-batch custody and tokenization; warmup excluded"]}
    report["report_sha256"]=digest(report)
    return report


def _runtime_summary(rows, labels, base_label, minimum_speedup, maximum_tail_ratio):
    """Paired quality/throughput evidence; all repeat/case coordinates must match."""
    if (type(minimum_speedup) not in (float,int) or not math.isfinite(minimum_speedup)
            or not 1 <= minimum_speedup <= 10 or type(maximum_tail_ratio) not in (float,int)
            or not math.isfinite(maximum_tail_ratio) or not 1 <= maximum_tail_ratio <= 2):
        raise ValueError("invalid runtime promotion diagnostic thresholds")
    summaries = {}
    coordinates = {}
    for label in labels:
        batches = [row for row in rows if row["label"] == label]
        if not batches:
            raise ValueError("runtime profile missing complete evidence")
        timings = sorted(row["seconds"] for row in batches)
        if any(not math.isfinite(t) or t <= 0 for t in timings):
            raise ValueError("invalid runtime measurement")
        observed = {}
        for batch in batches:
            for case in batch["cases"]:
                key = (batch["repeat"], case["case_sha256"])
                if key in observed:
                    raise ValueError("duplicate runtime evidence coordinate")
                observed[key] = (case["response_sha256"], case["exact"], case["output_tokens"])
        if not observed:
            raise ValueError("empty runtime profile")
        coordinates[label] = observed
        tokens = sum(c[2] for c in observed.values())
        summaries[label] = {
            "attempts": len(observed), "exact": sum(c[1] for c in observed.values()),
            "output_tokens": tokens, "seconds": sum(timings),
            "output_tokens_per_second": tokens / sum(timings),
            "median_batch_seconds": statistics.median(timings),
            "p95_batch_seconds": timings[math.ceil(.95 * len(timings)) - 1],
        }
    baseline = summaries[base_label]
    reference = coordinates[base_label]
    for label, summary in summaries.items():
        current = coordinates[label]
        if current.keys() != reference.keys():
            raise ValueError("unpaired runtime evidence")
        parity = sum(current[key] == reference[key] for key in reference)
        speed = (summary["output_tokens_per_second"] / baseline["output_tokens_per_second"]
                 if baseline["output_tokens_per_second"] else 0.0)
        tail = summary["p95_batch_seconds"] / baseline["p95_batch_seconds"]
        summary.update({
            "exact_response_parity": parity == len(reference),
            "paired_equal": parity, "paired_total": len(reference),
            "throughput_ratio": speed, "p95_latency_ratio": tail,
            "eligible_for_operator_review": (label != base_label and baseline["output_tokens"] > 0
                and parity == len(reference) and speed >= minimum_speedup and tail <= maximum_tail_ratio),
        })
    return summaries


def compare_runtime_profiles(competitor, holdout_path, *, holdout_sha256, server,
                             server_sha256, policies, baseline, runtime_libraries=(),
                             repeats=3, max_new_tokens=128, total_seconds=3600,
                             minimum_speedup=1.05, maximum_tail_ratio=1.05):
    """Run same-weights cross-over trials against explicitly supplied native policies.

    Unlike the distinct-model holdout, only typed scheduling/placement knobs may
    vary. Quantized weights, input/output budgets, cache policy and engine pins
    remain identical. This does not authorize activation.
    """
    import re
    if not isinstance(competitor, Competitor):
        raise TypeError("one pinned competitor required")
    if (not isinstance(policies, dict) or not 2 <= len(policies) <= 8
            or baseline not in policies or any(not isinstance(k,str)
                or not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", k)
                or not isinstance(v,ResidentBatchPolicy) for k,v in policies.items())):
        raise ValueError("2–8 uniquely named typed runtime policies required")
    if len({digest(asdict(p)) for p in policies.values()}) != len(policies):
        raise ValueError("runtime variants must have distinct configuration identities")
    base = policies[baseline]
    # Only performance policy fields may differ, not admission/session limits.
    fixed = ("slots","context_per_slot","gpu_layers","max_memory_bytes",
             "timeout_seconds","max_session_seconds","max_batches","slot_spill_bytes")
    if base.slot_spill_bytes or any(any(getattr(p,k)!=getattr(base,k) for k in fixed)
                                   for p in policies.values()):
        raise ValueError("runtime comparison requires matching no-spill admission envelopes")
    if (type(repeats) is not int or not 2<=repeats<=5 or type(total_seconds) is not int
            or not 1<=total_seconds<=14400 or type(max_new_tokens) is not int
            or not 1<=max_new_tokens<=min(8192,base.context_per_slot-1)):
        raise ValueError("invalid runtime trial bounds")
    if (type(minimum_speedup) not in (float,int) or not math.isfinite(minimum_speedup)
            or not 1<=minimum_speedup<=10 or type(maximum_tail_ratio) not in (float,int)
            or not math.isfinite(maximum_tail_ratio) or not 1<=maximum_tail_ratio<=2):
        raise ValueError("invalid runtime diagnostic thresholds")
    holdout = read_holdout(holdout_path,holdout_sha256)
    if (len(holdout)%base.slots or 1+len(holdout)//base.slots>base.max_batches
            or len(holdout)*len(policies)*repeats>4096):
        raise ValueError("runtime trial batch or aggregate budget exceeded")
    selected = LocalModelDeployment.load(competitor.manifest,expected_sha256=competitor.manifest_sha256)
    model = LlamaCppModel(selected.llama_cpp_config(rehash_artifacts_each_run=True))
    if model.model_digest != selected.execution_model_sha256:
        raise ValueError("runtime trial model identity changed")
    labels = list(policies)
    began = time.monotonic()
    rows = []
    def check_time():
        if time.monotonic()-began>=total_seconds:
            raise TimeoutError("runtime campaign deadline exceeded; incomplete evidence withheld")
    for repeat in range(repeats):
        # Rotate each repeat; even two variants exchange the first position.
        shift = repeat % len(labels)
        ordered = labels[shift:]+labels[:shift]
        for label in ordered:
            check_time()
            policy = policies[label]
            with ResidentGGUFBatch(model,server,server_sha256,policy,
                                   runtime_libraries=runtime_libraries) as session:
                check_time()
                session.generate(["Output a short readiness response."]*base.slots,max_new_tokens=1)
                for offset in range(0,len(holdout),base.slots):
                    check_time()
                    group = holdout[offset:offset+base.slots]
                    start = time.perf_counter()
                    reply = session.generate([case["prompt"] for case in group],max_new_tokens=max_new_tokens)
                    elapsed = time.perf_counter()-start
                    check_time()
                    if (reply["model_sha256"]!=model.model_digest or reply["server_sha256"]!=server_sha256
                            or reply["native_tuning_args"]!=list(policy.tuning_args())
                            or len(reply["results"])!=len(group)):
                        raise RuntimeError("runtime profile evidence identity mismatch")
                    cases=[]
                    for case,result in zip(group,reply["results"]):
                        cases.append({
                            "case_sha256":digest({"id":case["id"],"category":case["category"]}),
                            "response_sha256":digest({"text":result["text"],"ids":result["token_ids"],
                                                      "stop":result["stop_type"]}),
                            "exact":result["text"]==case["exact"],
                            "output_tokens":len(result["token_ids"]),
                        })
                    rows.append({"label":label,"repeat":repeat,"offset":offset,"seconds":elapsed,
                                 "offloaded_layers_reported":reply["offloaded_layers_reported"],
                                 "cases":cases})
            check_time()
    summaries = _runtime_summary(rows,labels,baseline,minimum_speedup,maximum_tail_ratio)
    report = {
        "schema":"skeleton.gguf.matched-runtime-tuning.v1",
        "status":"operator_measured_not_hardware_certified",
        "holdout_file_sha256":holdout_sha256,"holdout_content_sha256":digest(holdout),
        "manifest_sha256":selected.manifest_digest,"model_sha256":model.model_digest,
        "engine_sha256":server_sha256,"runtime_libraries":list(runtime_libraries),
        "runtime_profile_sha256":{k:digest(asdict(v)) for k,v in policies.items()},
        "runtime_profiles":{k:asdict(v) for k,v in policies.items()},
        "baseline":baseline,"repeats":repeats,"max_new_tokens":max_new_tokens,
        "minimum_speedup":minimum_speedup,"maximum_tail_ratio":maximum_tail_ratio,
        "summaries":summaries,"rows":rows,"activation_authorized":False,
        "limits":["wall-clock end-to-end evidence including tokenization and source custody",
                  "warmup and model startup excluded from batch timing",
                  "GPU placement is native-reported, not physically attested",
                  "campaign deadline rejects late results; not an OS-wide hard time cap"],
    }
    report["report_sha256"]=digest(report)
    return report
