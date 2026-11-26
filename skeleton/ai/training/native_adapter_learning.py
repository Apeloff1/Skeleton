"""Bounded native output-projection adaptation on the existing Cortex LoRA.

A frozen, untied CPU candidate backbone supplies actual hidden activations.
Only low-rank factors receive gradients until explicit candidate folding.
No attached serving adapter, external teacher, GPU fallback, or automatic
promotion. The shadow lease owner decides whether candidate work may proceed.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Callable

from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.cortex.attn import cosine_lr, matvec, matvec_T, softmax
from skeleton.cortex.lora import LoRA

from .flgb_training_runtime import digest_json

_MAX_FACTORS = 2_000_000
_MAX_STEPS = 65536


def _integer(value, low, high, name):
    if type(value) is not int or not low <= value <= high:
        raise ValueError("invalid adapter " + name)


@dataclass(frozen=True, slots=True)
class NativeAdapterPolicy:
    initial_rank: int = 2
    maximum_rank: int = 8
    rank_step: int = 2
    factor_budget: int = 131072
    maximum_steps: int = 8192
    maximum_prefix_tokens: int = 1024
    maximum_attention_work: int = 32_000_000
    maximum_factor_work: int = 200_000_000
    maximum_projection_parameters: int = 4_000_000
    learning_rate_ppm: int = 20000
    retention_weight_ppm: int = 200000
    gradient_clip_ppm: int = 1000000
    delta_radius_ppm: int = 50000
    fisher_strength_ppm: int = 1000000
    plateau_window: int = 16
    plateau_min_gain_ppm: int = 10000
    seed: int = 41
    project_conflicts: bool = True

    def __post_init__(self):
        for name, lo, hi in (
            ("initial_rank",1,128),("maximum_rank",1,128),("rank_step",1,128),
            ("factor_budget",2,_MAX_FACTORS),("maximum_steps",1,_MAX_STEPS),
            ("maximum_prefix_tokens",2,8192),("maximum_attention_work",1,2_000_000_000),
            ("maximum_factor_work",1,2_000_000_000),("maximum_projection_parameters",1,16_000_000),
            ("learning_rate_ppm",1,100000),("retention_weight_ppm",0,500000),
            ("gradient_clip_ppm",1,5000000),("delta_radius_ppm",1,500000),("fisher_strength_ppm",0,8_000_000),
            ("plateau_window",4,256),("plateau_min_gain_ppm",0,1000000),
            ("seed",0,2**32-1),
        ):
            _integer(getattr(self,name),lo,hi,name)
        if self.initial_rank>self.maximum_rank:
            raise ValueError("initial adapter rank exceeds maximum")
        if type(self.project_conflicts) is not bool:
            raise ValueError("explicit gradient conflict policy required")

    @property
    def digest(self):
        return digest_json({"algorithm":"native-output-lora-projected-trust-v1",
                            **{k:getattr(self,k) for k in self.__dataclass_fields__}})


@dataclass(frozen=True, slots=True)
class AdapterLearningReport:
    base_model_digest: str
    policy_digest: str
    source_inventory_digest: str
    initial_rank: int
    final_rank: int
    optimizer_steps: int
    conflict_projections: int
    radius_projections: int
    expansions: int
    trainable_parameters: int
    delta_norm_ppm: int
    sensitivity_norm_ppm: int
    sensitivity_projections: int
    sensitivity_digest: str
    mean_hard_loss_micronats: int
    factor_digest: str
    merged_projection_digest: str
    receipt_digest: str


def _norm(values):
    # Scaled Euclidean norm avoids overflow from naive sum-of-squares.
    result = 0.0
    for x in values:
        if not math.isfinite(x):
            raise ValueError("nonfinite adapter parameter or gradient")
        result = math.hypot(result,x)
    return result


def _flat(matrix):
    return (x for row in matrix for x in row)


def _dot(a,b):
    return math.fsum(x*y for x,y in zip(a,b))


def _probabilities(logits):
    if not logits or any(not math.isfinite(x) for x in logits):
        raise ValueError("nonfinite adapter logits")
    result=softmax(list(logits))
    if any(not math.isfinite(x) or x<0.0 for x in result):
        raise ValueError("nonfinite adapter probabilities")
    return result


def _factor_gradient(adapter, hidden, dlog):
    """Exact factor gradients at the same pre-update A and B."""
    ax=matvec(adapter.A,list(hidden))
    dz=matvec_T(adapter.B,list(dlog))
    scale=adapter.scale
    ga=[scale*dz[k]*hidden[j] for k in range(adapter.rank)
                              for j in range(adapter.in_dim)]
    gb=[scale*dlog[i]*ax[k] for i in range(adapter.out_dim)
                               for k in range(adapter.rank)]
    return ga+gb


def _gradient_mix(hard, retention, *, weight, clip, project):
    if len(hard)!=len(retention):
        raise ValueError("adapter gradient shape mismatch")
    _norm(hard); reserve_norm=_norm(retention)
    did_project=False
    if project and weight>0 and reserve_norm>1e-15:
        # Retention-priority projection: when the hard update conflicts
        # with preserving the frozen teacher, remove its opposing component.
        # This is local first-order geometry, not a guarantee of no forgetting.
        direction=[x/reserve_norm for x in retention]
        opposing=_dot(hard,direction)
        if opposing<0:
            hard=[x-opposing*y for x,y in zip(hard,direction)]
            did_project=True
    mixed=[(1.0-weight)*x+weight*y for x,y in zip(hard,retention)]
    magnitude=_norm(mixed)
    if magnitude>clip:
        mixed=[x*(clip/magnitude) for x in mixed]
    return mixed,did_project


def _delta_norm(adapter, row_weights=None, column_weights=None):
    """Frobenius norm of scale*B*A without materializing a dense delta.

    ||BA||_F^2 = trace((B^T B)(A A^T)). Gram storage is O(rank^2).
    Reject overflow rather than silently claim a valid trust region.
    """
    r=adapter.rank
    terms=[]
    for i in range(r):
        for j in range(r):
            aa=(_dot(adapter.A[i],adapter.A[j]) if column_weights is None else
                math.fsum(x*y*w for x,y,w in zip(adapter.A[i],adapter.A[j],column_weights)))
            bb=(math.fsum(row[i]*row[j] for row in adapter.B) if row_weights is None else
                math.fsum(row[i]*row[j]*w for row,w in zip(adapter.B,row_weights)))
            terms.append(aa*bb)
    squared=math.fsum(terms)
    if not math.isfinite(squared):
        raise ValueError("nonfinite low-rank delta energy")
    # A tiny negative can arise from cancellation between Gram terms.
    scale=max(1.0,math.fsum(abs(v) for v in terms))
    if squared < -1e-12*scale:
        raise ValueError("invalid low-rank Gram energy")
    return abs(adapter.scale)*math.sqrt(max(0.0,squared))


def _project_radius(adapter,radius,row_weights=None,column_weights=None):
    norm=_delta_norm(adapter,row_weights,column_weights)
    if norm<=radius:
        return False
    factor=radius/norm*(1.0-1e-12)
    adapter.B=[[x*factor for x in row] for row in adapter.B]
    if _delta_norm(adapter,row_weights,column_weights)>radius*(1.0+1e-9):
        raise ValueError("adapter trust radius projection failed")
    return True


class _OnlineSensitivity:
    """Factorized diagonal Fisher-inspired protection on admitted prefixes.

    For a categorical output distribution the output-logit Fisher diagonal
    is p*(1-p); the input factor uses squared frozen hidden activations.
    Average those factors separately (diagonal Kronecker approximation).
    Normalize each to its observed maximum and add a unit floor. This
    creates a stricter ellipsoid for sensitive output parameters. It is not
    a full Fisher matrix or an EWC measurement of independent old tasks.
    """

    def __init__(self,vocab,width,strength):
        self.row=[0.0]*vocab
        self.column=[0.0]*width
        self.strength=strength
        self.count=0

    def observe(self,probabilities,hidden):
        if (len(probabilities)!=len(self.row) or len(hidden)!=len(self.column)
                or any(not math.isfinite(x) for x in hidden)
                or any(not math.isfinite(p) or not 0<=p<=1 for p in probabilities)):
            raise ValueError("invalid frozen sensitivity observation")
        self.count+=1
        n=self.count
        for i,p in enumerate(probabilities):
            self.row[i]+=(p*(1-p)-self.row[i])/n
        for j,x in enumerate(hidden):
            square=x*x
            if not math.isfinite(square):
                raise ValueError("unrepresentable hidden sensitivity")
            self.column[j]+=(square-self.column[j])/n

    def weights(self):
        def normalized(values):
            peak=max(values,default=0.0)
            return ([1.0+self.strength*(x/peak) for x in values]
                    if peak>0 and self.strength else [1.0]*len(values))
        return normalized(self.row),normalized(self.column)

    @property
    def digest(self):
        return digest_json({"observations":self.count,"row":self.row,
                            "column":self.column,"strength":self.strength})


def _update(adapter,gradient,lr):
    expected=adapter.rank*(adapter.in_dim+adapter.out_dim)
    if len(gradient)!=expected:
        raise ValueError("adapter gradient count mismatch")
    cursor=0
    # Compute complete new factors first. Reject nonfinite before commit.
    a=[]
    b=[]
    for matrix,target in ((adapter.A,a),(adapter.B,b)):
        for row in matrix:
            updated=[]
            for x in row:
                updated.append(x-lr*gradient[cursor])
                cursor+=1
            target.append(updated)
    _norm(_flat(a));_norm(_flat(b))
    adapter.A,adapter.B=a,b
    adapter.steps+=1


def _validate_frozen_runtime(runtime):
    model=runtime.model
    if (runtime.device.actual!="cpu" or runtime.device.resident
            or model._accel is not None or model.resident or model.device!="cpu"
            or model.use_mod or model.tied or model.E is model.Wout
            or getattr(model,"lora",None) is not None
            or getattr(model,"hyper_lora",None) is not None):
        raise ValueError("adapter learning requires untied, unadapted reference CPU candidate")
    runtime.assert_model_unchanged()
    runtime.tokenizer.assert_unchanged()


def fit_native_output_adapter(
    candidate:NativeLLMRuntime, texts:tuple[str,...], *, policy:NativeAdapterPolicy,
    expected_base_digest:str, interrupt:Callable[[],None],
    heartbeat:Callable[[],object]|None=None,
)->AdapterLearningReport:
    """Train actual low-rank output deltas and fold into a private candidate.

    The caller must own a freshly cloned candidate; no production runtime
    may be passed. All source text must already be admitted by the existing
    shadow intake. Counters and weights are not committed until the full
    factor training and trust-region validation complete. On cancellation
    after the final commit the caller still must discard the candidate.
    """
    if type(candidate) is not NativeLLMRuntime or type(policy) is not NativeAdapterPolicy:
        raise ValueError("typed native candidate and adapter policy required")
    if candidate.model_digest!=expected_base_digest or not callable(interrupt):
        raise ValueError("candidate identity or interruption authority mismatch")
    interrupt()
    _validate_frozen_runtime(candidate)
    model=candidate.model
    if type(texts) is not tuple or not 1<=len(texts)<=100000:
        raise ValueError("bounded admitted corpus required")
    width=model.dim
    vocab=model.V
    if (policy.maximum_rank>min(width,vocab)
            or policy.maximum_rank*(width+vocab)>policy.factor_budget):
        raise ValueError("adapter rank exceeds admitted dimensions or factor budget")
    if vocab*width>policy.maximum_projection_parameters:
        raise ValueError("dense candidate folding exceeds projection allocation budget")
    window_ceiling=min(candidate.limits.max_context,model.ctx)
    if window_ceiling>policy.maximum_prefix_tokens:
        # Do not quietly shorten training context to satisfy a resource limit.
        raise ValueError("adapter prefix budget does not cover native context")
    sequences=[]
    steps=0
    attention_work=0
    total_bytes=0
    for raw in texts:
        interrupt()
        if type(raw) is not str or not raw.strip() or len(raw)>16384:
            raise ValueError("invalid admitted adapter source")
        total_bytes+=len(raw.encode("utf-8"))
        if total_bytes>4*1024**2:
            raise ValueError("adapter source bytes exceeded")
        seq=candidate.encode(raw)
        ids=seq.token_ids
        if ids!=tuple(model._ids(raw)):
            raise ValueError("adapter tokenizer differs from native training path")
        steps+=max(0,len(ids)-1)
        if steps>policy.maximum_steps:
            raise ValueError("adapter optimizer budget exceeded")
        for i in range(1,len(ids)):
            attention_work+=min(i,window_ceiling)**2*model.n_layers*model.n_heads
            if attention_work>policy.maximum_attention_work:
                raise ValueError("adapter attention work budget exceeded")
        sequences.append(seq)
    if not steps:
        raise ValueError("adapter corpus has no supervised targets")
    # Conservative factor arithmetic work units including multiple r^2 Gram
    # contractions and final dense folding. This is not a time estimate.
    factor_work=(steps*policy.maximum_rank**2*(width+vocab)*8
                 + vocab*width*policy.maximum_rank)
    if factor_work>policy.maximum_factor_work:
        raise ValueError("adapter factor arithmetic budget exceeded")
    source_digest=digest_json([seq.digest for seq in sequences])
    # Initial alpha=rank, setting scale=1. Existing expand_rank keeps the
    # effective function by rescaling B when alpha/r changes.
    adapter=LoRA(vocab,width,rank=policy.initial_rank,alpha=float(policy.initial_rank),
                 seed=policy.seed,name="Wout")
    base_norm=_norm(_flat(model.Wout))
    if base_norm<=0:
        raise ValueError("cannot derive relative trust radius from zero output matrix")
    radius=base_norm*policy.delta_radius_ppm/1_000_000
    hard_losses=[]
    loss_sum=0.0
    sensitivity=_OnlineSensitivity(vocab,width,policy.fisher_strength_ppm/1_000_000)
    n=conflicts=radius_hits=expansions=sensitivity_hits=0
    for seq in sequences:
        for i in range(1,len(seq.token_ids)):
            interrupt()
            if heartbeat is not None and n and n%32==0:
                heartbeat()
            ids=seq.token_ids[max(0,i-window_ceiling):i]
            target=seq.token_ids[i]
            hidden,_=model._forward(ids,retain_cache=False,interrupt=interrupt)
            y=hidden[-1]
            baseline=model._unembed(y)
            p0=_probabilities(baseline)
            sensitivity.observe(p0,y)
            p=_probabilities(adapter.apply(baseline,y))
            loss=-math.log(max(p[target],1e-12))
            hard=[value-float(j==target) for j,value in enumerate(p)]
            retention=[v-q for v,q in zip(p,p0)]
            gh=_factor_gradient(adapter,y,hard)
            gr=_factor_gradient(adapter,y,retention)
            dx,conflict=_gradient_mix(gh,gr,weight=policy.retention_weight_ppm/1_000_000,
                         clip=policy.gradient_clip_ppm/1_000_000,
                         project=policy.project_conflicts)
            eta=cosine_lr(n,steps,base=policy.learning_rate_ppm/1_000_000)
            _update(adapter,dx,eta)
            conflicts+=int(conflict)
            radius_hits+=int(_project_radius(adapter,radius))
            if sensitivity.strength:
                rows,columns=sensitivity.weights()
                sensitivity_hits+=int(_project_radius(adapter,radius,rows,columns))
            n+=1
            loss_sum+=loss
            hard_losses.append(loss)
            interval=policy.plateau_window
            if len(hard_losses)>interval*2:
                hard_losses.pop(0)
            if (len(hard_losses)==2*interval and n%(2*interval)==0
                    and adapter.rank<policy.maximum_rank):
                earlier=math.fsum(hard_losses[:interval])/interval
                later=math.fsum(hard_losses[interval:])/interval
                if (earlier-later)*1_000_000 < max(earlier,1e-12)*policy.plateau_min_gain_ppm:
                    before=adapter.delta(y)
                    adapter.expand_rank(min(policy.maximum_rank,adapter.rank+policy.rank_step),
                                        seed=policy.seed+n)
                    after=adapter.delta(y)
                    if any(not math.isclose(a,b,rel_tol=1e-11,abs_tol=1e-13)
                           for a,b in zip(before,after)):
                        raise ValueError("adapter expansion failed function preservation")
                    radius_hits+=int(_project_radius(adapter,radius))
                    if sensitivity.strength:
                        sensitivity_hits+=int(_project_radius(adapter,radius,rows,columns))
                    expansions+=1
            interrupt()
    if n!=steps:
        raise ValueError("adapter optimizer steps differ from admission")
    interrupt()
    _validate_frozen_runtime(candidate)
    if candidate.model_digest!=expected_base_digest:
        raise ValueError("frozen candidate identity changed during adaptation")
    factor_digest=digest_json(adapter.snapshot())
    delta_norm=_delta_norm(adapter)
    sensitivity_rows,sensitivity_cols=sensitivity.weights()
    sensitivity_norm=_delta_norm(adapter,sensitivity_rows,sensitivity_cols)
    if sensitivity_norm>radius*(1+1e-9):
        raise ValueError("retention sensitivity radius exceeded")
    if delta_norm<=0 or delta_norm>radius*(1+1e-9):
        raise ValueError("empty or out-of-trust-region adaptation")
    # Build merged output off to the side, verifying finite values and actual
    # dense delta. No other candidate array is touched.
    merged=[]
    actual_delta=0.0
    actual_weighted_delta=0.0
    changed=False
    for i,row in enumerate(model.Wout):
        interrupt()
        updated=[]
        for j,old in enumerate(row):
            value=old+adapter.scale*math.fsum(adapter.B[i][k]*adapter.A[k][j]
                                              for k in range(adapter.rank))
            if not math.isfinite(value):
                raise ValueError("nonfinite folded output projection")
            actual_delta=math.hypot(actual_delta,value-old)
            actual_weighted_delta=math.hypot(actual_weighted_delta,
                (value-old)*math.sqrt(sensitivity_rows[i]*sensitivity_cols[j]))
            changed=changed or value!=old
            updated.append(value)
        merged.append(updated)
    if (not changed or actual_delta>radius*(1+1e-8)
            or actual_weighted_delta>radius*(1+1e-8)):
        raise ValueError("folded output is unchanged or exceeds trust radius")
    evidence={
        "base":expected_base_digest,"policy":policy.digest,"source":source_digest,
        "initial_rank":policy.initial_rank,"final_rank":adapter.rank,"steps":n,
        "conflicts":conflicts,"radius_projections":radius_hits,"expansions":expansions,
        "trainable_parameters":adapter.rank*(width+vocab),
        "delta_norm_ppm":round(actual_delta/base_norm*1_000_000),
        "sensitivity_norm_ppm":round(actual_weighted_delta/base_norm*1_000_000),
        "sensitivity_projections":sensitivity_hits,
        "sensitivity_digest":sensitivity.digest,
        "mean_hard_loss_micronats":round(loss_sum/n*1_000_000),
        "factors":factor_digest,"merged_projection":digest_json(merged),
    }
    receipt=digest_json(evidence)
    interrupt()
    # Final candidate-only commit. Runtime must be freshly re-admitted by
    # its shadow owner; the old runtime digest is intentionally stale.
    model.Wout=merged
    model.steps+=n
    model.fitted+=len(texts)
    return AdapterLearningReport(expected_base_digest,policy.digest,source_digest,
        policy.initial_rank,adapter.rank,n,conflicts,radius_hits,expansions,
        evidence["trainable_parameters"],evidence["delta_norm_ppm"],
        evidence["sensitivity_norm_ppm"],sensitivity_hits,sensitivity.digest,
        evidence["mean_hard_loss_micronats"],factor_digest,evidence["merged_projection"],receipt)


__all__=["NativeAdapterPolicy","AdapterLearningReport","fit_native_output_adapter"]
