"""Quantized KV candidate qualification, not a native allocation authority.

Search existing llama.cpp K/V precision settings independently. Logical
GGML block estimates guide experiments but never reduce configured physical
memory reserves or authorize a live model change. Only paired measurements
can identify a candidate worth separate operator admission.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
from itertools import islice, product
import json
from statistics import median

from .llama_cpp import GgufServingMetadata, LlamaCppConfig
from .measured_tuning import TuningScope, corpus_identity

_FORMATS = {"f16": (1, 2), "q8_0": (32, 34), "q4_0": (32, 18)}
# Restrict the logical estimator to regular dense transformer geometries.
# MLA, recurrent, hybrid, sliding-window and heterogeneous tensors need
# backend-specific layout evidence rather than this formula.
_DENSE_ARCHITECTURES = frozenset(("llama", "qwen2", "qwen3"))


def _int(n, lo, hi):
    if type(n) is not int or not lo <= n <= hi:
        raise ValueError("invalid bounded precision quantity")


def _pin(s):
    if type(s) is not str or len(s) != 64 or any(c not in "0123456789abcdef" for c in s):
        raise ValueError("expected SHA256")


def _digest(obj):
    return sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"),
                             allow_nan=False).encode("ascii")).hexdigest()


def logical_kv_bytes(metadata: GgufServingMetadata, *, context: int,
                     key_type: str, value_type: str) -> int:
    """Block-rounded logical tensor estimate; not an allocator or fit proof."""
    if type(metadata) is not GgufServingMetadata or metadata.architecture not in _DENSE_ARCHITECTURES:
        raise ValueError("unsupported regular attention geometry")
    _int(context, 128, 1_048_576)
    _int(metadata.context_length, context, 1_048_576)
    layers = metadata.block_count
    heads = metadata.head_count
    kv_heads = metadata.head_count_kv
    # Require explicit K/V dimensions and KV heads. Do not infer MLA or GQA
    # from embedding size, or silently substitute MHA for unknown metadata.
    key = metadata.key_length
    value = metadata.value_length
    for n in (layers, heads, kv_heads, key, value):
        _int(n, 1, 65536)
    if kv_heads > heads or heads % kv_heads:
        raise ValueError("incompatible attention geometry")

    def row(dim, fmt):
        if fmt not in _FORMATS:
            raise ValueError("unsupported KV type")
        block, width = _FORMATS[fmt]
        return ((dim + block - 1) // block) * width
    estimate = context * layers * kv_heads * (row(key, key_type) + row(value, value_type))
    _int(estimate, 1, 1 << 53)
    return estimate


@dataclass(frozen=True, slots=True)
class PrecisionProfile:
    scope: TuningScope
    configuration: LlamaCppConfig
    logical_bytes: int
    geometry_sha256: str

    def __post_init__(self):
        if type(self.scope) is not TuningScope or type(self.configuration) is not LlamaCppConfig:
            raise ValueError("typed scope/configuration required")
        if (self.configuration.kv_cache_type_k not in _FORMATS
                or self.configuration.kv_cache_type_v not in _FORMATS):
            raise ValueError("explicit K/V precision required")
        _pin(self.geometry_sha256)
        _int(self.logical_bytes, 1, 1 << 53)

    @property
    def identity(self):
        c = self.configuration
        return _digest({
            "scope": self.scope.identity, "geometry": self.geometry_sha256,
            "logical_bytes": self.logical_bytes,
            "config": {k: getattr(c,k) for k in (
                "context_size","threads","batch_size","gpu_layers","model_id",
                "kv_cache_location","kv_cache_type_k","kv_cache_type_v",
                "kv_bytes_per_token","runtime_scratch_bytes","timeout_seconds",
                "speculation_runtime_sha256","speculation_ngram","speculation_draft_tokens",
                "speculation_min_hits","speculation_reserve_bytes",
                "max_output_bytes","max_stderr_bytes","temperature",
                "output_framing","reject_model_symlink","rehash_artifacts_each_run",
                "runtime_libraries")},
            "args": _digest(c.extra_args),
            "env": _digest(dict(c.environment)),
        })


def profiles(config: LlamaCppConfig, metadata: GgufServingMetadata, *,
             scope: TuningScope,
             supported_pairs: tuple[tuple[str,str], ...]) -> tuple[PrecisionProfile,...]:
    """Caller supplies pairs independently supported by the pinned backend."""
    if type(config) is not LlamaCppConfig or type(scope) is not TuningScope:
        raise ValueError("typed local deployment scope required")
    if type(supported_pairs) is not tuple or not 1 <= len(supported_pairs) <= 9:
        raise ValueError("bounded explicit backend precision capabilities required")
    if any(type(p) is not tuple or len(p)!=2 or any(type(x) is not str or x not in _FORMATS for x in p)
           for p in supported_pairs):
        raise ValueError("invalid backend precision pair")
    if len(set(supported_pairs)) != len(supported_pairs):
        raise ValueError("duplicate precision pair")
    baseline = (config.kv_cache_type_k,config.kv_cache_type_v)
    if baseline not in supported_pairs or config.context_size is None:
        raise ValueError("explicit baseline precision and context required")
    geometry = _digest(metadata.as_dict())
    choices = (baseline,)+tuple(sorted(set(supported_pairs)-{baseline}))
    return tuple(PrecisionProfile(scope,replace(config,kv_cache_type_k=k,kv_cache_type_v=v),
                 logical_kv_bytes(metadata,context=config.context_size,key_type=k,value_type=v),
                 geometry) for k,v in choices)


@dataclass(frozen=True, slots=True)
class Trial:
    profile_sha256: str
    case_sha256: str
    repeat: int
    input_tokens: int
    output_tokens: int
    elapsed_us: int
    peak_host_bytes: int
    peak_device_bytes: int
    quality_bp: int
    success: bool
    output_sha256: str

    def __post_init__(self):
        for s in (self.profile_sha256,self.case_sha256,self.output_sha256):
            _pin(s)
        _int(self.repeat,0,15)
        _int(self.input_tokens,1,1_048_576)
        _int(self.output_tokens,0,8192)
        _int(self.elapsed_us,1,86_400_000_000)
        _int(self.peak_host_bytes,1,1<<53)
        _int(self.peak_device_bytes,0,1<<53)
        _int(self.quality_bp,0,10000)
        if type(self.success) is not bool or (self.success and not self.output_tokens):
            raise ValueError("explicit valid native trial outcome required")


@dataclass(frozen=True, slots=True)
class Verdict:
    baseline_sha256: str
    recommended_sha256: str | None
    retained: tuple[str,...]
    rejected: tuple[tuple[str,str],...]
    receipt_sha256: str


def qualify(candidates: tuple[PrecisionProfile,...], rows, *,
            case_ids: tuple[str,...], critical_cases: frozenset[str],
            repetitions: int=3, minimum_quality_bp: int=9500,
            max_quality_loss_bp: int=0, max_latency_loss_bp: int=500,
            min_memory_gain_bp: int=500, host_limit: int,
            device_limit: int=0) -> Verdict:
    """Paired native trials, strict per-case gates and a measured Pareto set.

    Device memory must be independently measured for GPU experiments. A
    zero device limit is only meaningful for confirmed CPU-only workloads.
    Never infer physical savings from logical geometry or accept a missing
    sample. Critical cases additionally require an exact output digest.
    """
    for x,lo,hi in ((repetitions,3,16),(minimum_quality_bp,0,10000),
                   (max_quality_loss_bp,0,1000),(max_latency_loss_bp,0,10000),
                   (min_memory_gain_bp,1,10000),(host_limit,1,1<<53),
                   (device_limit,0,1<<53)):
        _int(x,lo,hi)
    if type(candidates) is not tuple or not 1 <= len(candidates) <= 9 or any(type(p) is not PrecisionProfile for p in candidates):
        raise ValueError("typed bounded candidates required")
    base=candidates[0]
    if corpus_identity(case_ids)!=base.scope.corpus_sha256:
        raise ValueError("corpus mismatch")
    if type(critical_cases) is not frozenset or not critical_cases or not critical_cases.issubset(case_ids):
        raise ValueError("explicit critical corpus subset required")
    mapping={p.identity:p for p in candidates}
    if len(mapping)!=len(candidates):
        raise ValueError("duplicate precision candidate")
    for p in candidates:
        if (p.scope!=base.scope or p.geometry_sha256!=base.geometry_sha256
            or replace(p.configuration,kv_cache_type_k=base.configuration.kv_cache_type_k,
                       kv_cache_type_v=base.configuration.kv_cache_type_v)!=base.configuration):
            raise ValueError("candidate changed non-precision identity")
    if base.configuration.gpu_layers != 0 and device_limit==0:
        raise ValueError("GPU or unknown placement needs independent device bound")
    keys=set(product(case_ids,range(repetitions)))
    table={k:{} for k in mapping}
    for n,row in enumerate(rows):
        if n>=len(keys)*len(mapping) or type(row) is not Trial or row.profile_sha256 not in mapping:
            raise ValueError("unexpected trial")
        key=(row.case_sha256,row.repeat)
        bucket=table[row.profile_sha256]
        if key not in keys or key in bucket:
            raise ValueError("duplicate or out-of-corpus trial")
        bucket[key]=row
    rejected={}
    metrics={}
    context=base.configuration.context_size
    def complete(identity):
        group=table[identity]
        return (set(group)==keys and all(r.success and r.quality_bp>=minimum_quality_bp
                and r.peak_host_bytes<=host_limit and r.peak_device_bytes<=device_limit
                and r.input_tokens+r.output_tokens<=context for r in group.values()))

    chosen=None
    kept=()
    if not complete(base.identity):
        rejected={p.identity:"baseline_unqualified" for p in candidates}
    else:
        control=table[base.identity]
        def summarize(group):
            return (max(r.peak_host_bytes for r in group.values()),
                    max(r.peak_device_bytes for r in group.values()),
                    int(median(r.elapsed_us for r in group.values())),
                    min(r.quality_bp for r in group.values()))
        metrics[base.identity]=summarize(control)
        for p in candidates[1:]:
            identity=p.identity
            group=table[identity]
            if not complete(identity):
                rejected[identity]="incomplete_or_resource_quality_hold"
                continue
            if any((group[k].input_tokens,group[k].output_tokens)!=(control[k].input_tokens,control[k].output_tokens)
                   or group[k].quality_bp+max_quality_loss_bp<control[k].quality_bp
                   or group[k].elapsed_us*10000>control[k].elapsed_us*(10000+max_latency_loss_bp)
                   or (k[0] in critical_cases and group[k].output_sha256!=control[k].output_sha256)
                   for k in keys):
                rejected[identity]="paired_regression"
                continue
            values=summarize(group)
            old=metrics[base.identity]
            # Host and device are separate physical budgets, not additive UMA.
            if (values[0]>old[0] or values[1]>old[1] or not
                    ((old[0]-values[0])*10000>=old[0]*min_memory_gain_bp
                    or (old[1]>0 and (old[1]-values[1])*10000>=old[1]*min_memory_gain_bp))):
                rejected[identity]="no_measured_memory_advantage"
                continue
            metrics[identity]=values
        def dominates(a,b):
            a=(*a[:3],-a[3]); b=(*b[:3],-b[3])
            return all(x<=y for x,y in zip(a,b)) and any(x<y for x,y in zip(a,b))
        kept=tuple(sorted(k for k,v in metrics.items()
                         if not any(dominates(w,v) for j,w in metrics.items() if j!=k)))
        alternatives=[k for k in kept if k!=base.identity]
        chosen=min(alternatives,key=lambda k:(metrics[k][0],metrics[k][1],
                   metrics[k][2],-metrics[k][3],k)) if alternatives else base.identity
    receipt=_digest({"scope":base.scope.identity,"baseline":base.identity,
                     "profiles":sorted(mapping),"policy":[repetitions,minimum_quality_bp,
                     max_quality_loss_bp,max_latency_loss_bp,min_memory_gain_bp,host_limit,device_limit],
                     "critical":sorted(critical_cases),"rows":[[p,k,r.input_tokens,r.output_tokens,
                     r.elapsed_us,r.peak_host_bytes,r.peak_device_bytes,r.quality_bp,r.success,r.output_sha256]
                     for p,g in sorted(table.items()) for k,r in sorted(g.items())],
                     "selected":chosen,"kept":kept,"rejected":sorted(rejected.items())})
    return Verdict(base.identity,chosen,kept,tuple(sorted(rejected.items())),receipt)
