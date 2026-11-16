"""Paired, exact-output qualification for CPU-only native speculation.

This is an advisory evaluator for independent native trial receipts. It never
starts a model or modifies an installed manifest; operator activation remains
a separate action subject to canonical admission.
"""
from __future__ import annotations
from dataclasses import dataclass, replace
from hashlib import sha256
from itertools import product
import json
from statistics import median

from .llama_cpp import LlamaCppConfig
from .measured_tuning import TuningScope, corpus_identity


def _hash(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(",",":"),
                             allow_nan=False).encode("ascii")).hexdigest()


def _pin(value):
    if type(value) is not str or len(value)!=64 or any(x not in "0123456789abcdef" for x in value):
        raise ValueError("SHA256 pin required")


def _int(value,lo,hi):
    if type(value) is not int or not lo<=value<=hi:
        raise ValueError("invalid bounded measurement")


def profile_identity(scope:TuningScope,config:LlamaCppConfig):
    if type(scope) is not TuningScope or type(config) is not LlamaCppConfig:
        raise ValueError("typed scope/config required")
    # Pin complete configuration semantics including its privately hashed
    # environment. Artifact paths are operational details, not public data.
    return _hash({"scope":scope.identity,
                  "fields":{k:getattr(config,k) for k in config.__dataclass_fields__
                            if k not in ("executable","model_path","environment")},
                  "environment":_hash(dict(config.environment))})


@dataclass(frozen=True,slots=True)
class Pair:
    scope:TuningScope
    baseline:LlamaCppConfig
    candidate:LlamaCppConfig

    def __post_init__(self):
        if type(self.scope) is not TuningScope or type(self.baseline) is not LlamaCppConfig or type(self.candidate) is not LlamaCppConfig:
            raise ValueError("typed calibration pair required")
        a,b=self.baseline,self.candidate
        if a.speculation_runtime_sha256 is not None or b.speculation_runtime_sha256!=self.scope.runtime_sha256:
            raise ValueError("candidate runtime must match baseline scope")
        if a.gpu_layers!=0 or a.temperature!=0.0 or a.context_size is None:
            raise ValueError("explicit CPU-only greedy baseline required")
        if replace(b,speculation_runtime_sha256=None,speculation_ngram=0,
                   speculation_draft_tokens=0,speculation_min_hits=0,
                   speculation_reserve_bytes=0)!=a:
            raise ValueError("non-speculation execution policy drift")


@dataclass(frozen=True,slots=True)
class Trial:
    profile_sha256:str
    case_sha256:str
    repeat:int
    output_tokens_sha256:str
    finish_reason:str
    requested_input_tokens:int
    requested_output_tokens:int
    actual_output_tokens:int
    elapsed_us:int
    peak_host_bytes:int
    success:bool

    def __post_init__(self):
        for v in (self.profile_sha256,self.case_sha256,self.output_tokens_sha256):
            _pin(v)
        _int(self.repeat,0,15)
        _int(self.requested_input_tokens,1,1_048_576)
        _int(self.requested_output_tokens,1,8192)
        _int(self.actual_output_tokens,0,self.requested_output_tokens)
        _int(self.elapsed_us,1,86_400_000_000)
        _int(self.peak_host_bytes,1,1<<53)
        if type(self.success) is not bool or self.finish_reason not in (
            "completed","length","cancelled","error","deadline"):
            raise ValueError("invalid explicit outcome")
        if self.success and (self.finish_reason not in ("completed","length") or self.actual_output_tokens==0):
            raise ValueError("successful trial must produce target tokens")


@dataclass(frozen=True,slots=True)
class Verdict:
    eligible:bool
    reason:str
    paired_trials:int
    median_gain_bp:int
    evidence_sha256:str


def qualify(pair:Pair,observations,*,case_ids:tuple[str,...],
            host_limit:int,repetitions:int=3,min_gain_bp:int=500,
            max_tail_loss_bp:int=500):
    if type(pair) is not Pair:
        raise ValueError("typed speculative pair required")
    for v,lo,hi in ((host_limit,1,1<<53),(repetitions,3,16),
                   (min_gain_bp,1,10000),(max_tail_loss_bp,0,10000)):
        _int(v,lo,hi)
    if corpus_identity(case_ids)!=pair.scope.corpus_sha256:
        raise ValueError("different benchmark corpus")
    keys=set(product(case_ids,range(repetitions)))
    aid=profile_identity(pair.scope,pair.baseline)
    bid=profile_identity(pair.scope,pair.candidate)
    table={aid:{},bid:{}}
    for i,row in enumerate(observations):
        if i>=2*len(keys) or type(row) is not Trial or row.profile_sha256 not in table:
            raise ValueError("unexpected or oversized native trial stream")
        key=(row.case_sha256,row.repeat)
        group=table[row.profile_sha256]
        if key not in keys or key in group:
            raise ValueError("duplicate or unexpected paired trial")
        group[key]=row
    control,trial=table[aid],table[bid]
    gain=0
    count=0
    reason="incomplete_pairs"
    if set(control)==set(trial)==keys:
        count=len(keys)
        context=pair.baseline.context_size
        if any(not r.success or r.peak_host_bytes>host_limit
               or r.requested_input_tokens+r.requested_output_tokens>context
               for group in (control,trial) for r in group.values()):
            reason="native_failure_or_capacity_hold"
        elif any((trial[k].requested_input_tokens,trial[k].requested_output_tokens,
                  trial[k].actual_output_tokens,trial[k].output_tokens_sha256,trial[k].finish_reason)!=
                 (control[k].requested_input_tokens,control[k].requested_output_tokens,
                  control[k].actual_output_tokens,control[k].output_tokens_sha256,control[k].finish_reason)
                 for k in keys):
            reason="target_output_or_protocol_changed"
        elif any(trial[k].elapsed_us*10000>control[k].elapsed_us*(10000+max_tail_loss_bp) for k in keys):
            reason="tail_latency_regression"
        else:
            gain=int(median((control[k].elapsed_us-trial[k].elapsed_us)*10000//
                            control[k].elapsed_us for k in keys))
            reason="eligible_for_operator_review" if gain>=min_gain_bp else "no_measured_improvement"
    receipt=_hash({"scope":pair.scope.identity,"profiles":[aid,bid],
                   "policy":[host_limit,repetitions,min_gain_bp,max_tail_loss_bp],
                   "rows":[[p,k,r.output_tokens_sha256,r.finish_reason,r.requested_input_tokens,
                            r.requested_output_tokens,r.actual_output_tokens,r.elapsed_us,
                            r.peak_host_bytes,r.success] for p,g in sorted(table.items())
                            for k,r in sorted(g.items())],
                   "decision":[reason,count,gain]})
    return Verdict(reason=="eligible_for_operator_review",reason,count,gain,receipt)
