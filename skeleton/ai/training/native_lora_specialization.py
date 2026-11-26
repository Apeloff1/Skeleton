"""Actual offline low-rank gradient training on frozen native transformer weights.

The caller supplies governed dataset rights and separate evaluation rows.
Never mutates the active base, publishes production weights or fetches data.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile

from .flgb_training_runtime import (
    AdapterTrainingRun, CandidateWeights, DatasetRevision, DatasetRights,
    TrainingContractError, digest_json,
)

_TARGET=re.compile(r"layers\.([0-9]+)\.(Wq|Wk|Wv|Wo|W1|Wu|W2)")


@dataclass(frozen=True)
class SpecializationPolicy:
    rank: int=4
    alpha: float=8.0
    learning_rate: float=0.01
    steps: int=32
    seed: int=0
    max_tokens: int=65536
    max_adapter_parameters: int=2_000_000
    max_gradient_norm: float=1.0

    def __post_init__(self):
        for v,lo,hi in ((self.rank,1,128),(self.steps,1,4096),(self.seed,0,2**32-1),
                        (self.max_tokens,2,2_000_000),(self.max_adapter_parameters,2,20_000_000)):
            if type(v) is not int or not lo<=v<=hi:
                raise TrainingContractError("invalid specialization limit")
        for v,lo,hi in ((self.alpha,0.001,1024),(self.learning_rate,0.000001,1),(self.max_gradient_norm,0.00001,100)):
            if type(v) not in {int,float} or not math.isfinite(v) or not lo<=v<=hi:
                raise TrainingContractError("invalid specialization numeric policy")

    @property
    def digest(self):
        return digest_json(asdict(self))


def dataset_digest(train, heldout):
    if not isinstance(train,(list,tuple)) or not isinstance(heldout,(list,tuple)):
        raise TrainingContractError("explicit training and held-out row lists required")
    if not 1<=len(train)<=4096 or not 1<=len(heldout)<=4096:
        raise TrainingContractError("dataset row count outside bounds")
    if any(not isinstance(x,str) or not x.strip() or len(x.encode())>65536 for x in (*train,*heldout)):
        raise TrainingContractError("training row outside bounds")
    if sum(len(x.encode()) for x in (*train,*heldout))>32*1024**2:
        raise TrainingContractError("dataset byte ceiling exceeded")
    return digest_json({"train":list(train),"heldout":list(heldout)})


def _targets(accel, names, policy):
    lm=accel.lm
    selected={}
    for name in names:
        if name=="Wout":
            if lm.tied:
                raise TrainingContractError("tied output specialization requires explicit untied candidate")
            matrix=accel._Wout
        else:
            m=_TARGET.fullmatch(name)
            if not m or int(m.group(1))>=len(accel._layers):
                raise TrainingContractError("unknown native adapter target")
            matrix=accel._layers[int(m.group(1))].get(m.group(2))
        if matrix is None or matrix.ndim!=2 or policy.rank>min(matrix.shape):
            raise TrainingContractError("adapter rank exceeds target geometry")
        selected[name]=matrix.detach()
    if sum(policy.rank*sum(p.shape) for p in selected.values())>policy.max_adapter_parameters:
        raise TrainingContractError("adapter parameter budget exceeded")
    return selected


def train_specialization(runtime, run: AdapterTrainingRun, rights: DatasetRights,
                         revision: DatasetRevision, train, heldout, *,
                         scope: str, policy: SpecializationPolicy, interrupt=None):
    if not isinstance(run,AdapterTrainingRun) or not isinstance(rights,DatasetRights) or not isinstance(revision,DatasetRevision) or not isinstance(policy,SpecializationPolicy):
        raise TypeError("governed adapter run, dataset rights/revision and policy required")
    if (not rights.permits(scope) or revision.dataset_id!=rights.dataset_id
        or revision.rights_digest!=rights.digest or revision.digest!=run.dataset_revision_digest
        or dataset_digest(train,heldout)!=revision.content_digest
        or run.config_digest!=policy.digest or runtime.model_digest!=run.base_model_digest):
        raise TrainingContractError("specialization authority or content binding mismatch")
    runtime.assert_model_unchanged()
    runtime.tokenizer.assert_unchanged()
    tok=runtime.tokenizer
    rows=[tok.encode_ids(x) for x in train]
    eval_rows=[tok.encode_ids(x) for x in heldout]
    if any(not 2<=len(x)<=runtime.limits.max_context for x in rows+eval_rows):
        raise TrainingContractError("training row native token context exceeds bounds")
    if set(rows)&set(eval_rows) or len(set(rows))!=len(rows) or len(set(eval_rows))!=len(eval_rows):
        raise TrainingContractError("training/heldout token contamination or duplicate")
    planned=sum(len(rows[i%len(rows)])-1 for i in range(policy.steps))+2*sum(len(x)-1 for x in eval_rows)
    if planned>policy.max_tokens:
        raise TrainingContractError("specialization token compute budget exceeded")
    a=getattr(runtime.model,"_accel",None)
    if a is None or not a.resident:
        raise TrainingContractError("specialization requires explicitly resident Torch weights")
    torch=a.torch
    lm=a.lm
    with a._inference_lock(interrupt):
        a._assert_training_integrity()
        binding=a._kv_binding()
        selected=_targets(a,run.target_modules,policy)
        rng=torch.Generator(device="cpu").manual_seed(policy.seed)
        params={}
        for name,matrix in selected.items():
            out_dim,in_dim=matrix.shape
            low_a=(torch.randn((policy.rank,in_dim),generator=rng)* (1/math.sqrt(in_dim))).to(a.device)
            low_b=torch.zeros((out_dim,policy.rank),device=a.device)
            params[name]=(torch.nn.Parameter(low_a),torch.nn.Parameter(low_b))
        learned=[p for pair in params.values() for p in pair]
        optimizer=torch.optim.AdamW(learned,lr=policy.learning_rate,weight_decay=0.0)
        scale=policy.alpha/policy.rank
        functional=torch.nn.functional

        def project(x,matrix,name):
            output=x@matrix.detach().T
            if name in params:
                low_a,low_b=params[name]
                output=output+((x@low_a.T)@low_b.T)*scale
            return output

        def norm(x,blob,prefix):
            g=blob[prefix+"_g"].detach()
            if lm.norm=="rms":
                return x*torch.rsqrt(x.square().mean(-1,keepdim=True)+1e-5)*g
            return functional.layer_norm(x,(lm.dim,),g,blob[prefix+"_b"].detach(),eps=1e-5)

        def loss(ids, use_adapter=True):
            if interrupt is not None:
                interrupt()
            xids=torch.tensor(ids[:-1],dtype=torch.long,device=a.device)
            targets=torch.tensor(ids[1:],dtype=torch.long,device=a.device)
            x=a._E.detach()[xids]
            if lm.position_mode!="rope":
                x=x+a._P.detach()[:len(xids)]
            def p(x,w,name):
                return project(x,w,name) if use_adapter else x@w.detach().T
            for i,blob in enumerate(a._layers):
                if interrupt is not None:
                    interrupt()
                n=norm(x,blob,"ln1")
                prefix=f"layers.{i}."
                q=a._rope(p(n,blob["Wq"],prefix+"Wq"))
                k=a._rope(p(n,blob["Wk"],prefix+"Wk"))
                v=p(n,blob["Wv"],prefix+"Wv")
                y=a._attention(q,k,v,heads=lm.n_heads,head_dim=lm.dim//lm.n_heads,interrupt=interrupt)
                x=x+p(y,blob["Wo"],prefix+"Wo")
                if blob.get("W1") is not None:
                    n=norm(x,blob,"ln2")
                    gate=p(n,blob["W1"],prefix+"W1")+blob["b1"].detach()
                    z=(functional.silu(gate)*(p(n,blob["Wu"],prefix+"Wu")+blob["bu"].detach())
                       if blob.get("Wu") is not None else a._gelu(gate))
                    x=x+p(z,blob["W2"],prefix+"W2")+blob["b2"].detach()
            logits=p(x,a._Wout,"Wout")+a._bout.detach()
            return functional.cross_entropy(logits,targets)

        def evaluate(use_adapter):
            total=count=0
            with torch.no_grad():
                for ids in eval_rows:
                    value=float(loss(ids,use_adapter).item())
                    if not math.isfinite(value):
                        raise TrainingContractError("nonfinite heldout loss")
                    total+=value*(len(ids)-1)
                    count+=len(ids)-1
            return total/count

        before=evaluate(False)
        losses=[]
        for step in range(policy.steps):
            optimizer.zero_grad(set_to_none=True)
            value=loss(rows[step%len(rows)])
            if not bool(torch.isfinite(value).item()):
                raise TrainingContractError("nonfinite adapter training loss")
            value.backward()
            grad=torch.nn.utils.clip_grad_norm_(learned,policy.max_gradient_norm,error_if_nonfinite=True)
            optimizer.step()
            losses.append(float(value.detach().item()))
        after=evaluate(True)
        if a._kv_binding()!=binding:
            raise TrainingContractError("active base changed during adapter training")
        runtime.assert_model_unchanged()
        tok.assert_unchanged()
        weights={name:{"A":x.detach().cpu().tolist(),"B":y.detach().cpu().tolist()}
                 for name,(x,y) in sorted(params.items())}
    if any(not math.isfinite(v) for row in weights.values() for m in row.values() for r in m for v in r):
        raise TrainingContractError("nonfinite candidate adapter weights")
    candidate={"schema":"skeleton.native.lora-candidate.v1","base_model_digest":runtime.model_digest,
               "tokenizer_digest":tok.digest,"dataset_revision_digest":revision.digest,
               "rights_digest":rights.digest,"run":asdict(run),"policy":asdict(policy),
               "targets":weights,"training_steps":policy.steps,"reserved_compute_tokens":planned,
               "heldout_base_nll":before,"heldout_candidate_nll":after,
               "mean_training_nll":sum(losses)/len(losses),"activation_authorized":False}
    candidate["candidate_sha256"]=digest_json(candidate)
    return candidate


def materialize_candidate(runtime, candidate, *, expected_sha256: str):
    """Merge exact low-rank deltas into a separate checkpoint-derived runtime."""
    from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
    from skeleton.ai.model_runtime.runtime_contracts import DevicePolicy
    from skeleton.cortex.lora import LoRA
    if not isinstance(candidate,dict) or candidate.get("schema")!="skeleton.native.lora-candidate.v1":
        raise TrainingContractError("candidate adapter schema mismatch")
    if candidate.get("candidate_sha256")!=expected_sha256 or digest_json({k:v for k,v in candidate.items() if k!="candidate_sha256"})!=expected_sha256:
        raise TrainingContractError("candidate adapter identity mismatch")
    if candidate.get("activation_authorized") is not False or candidate.get("base_model_digest")!=runtime.model_digest or candidate.get("tokenizer_digest")!=runtime.tokenizer.digest:
        raise TrainingContractError("adapter base or tokenizer mismatch")
    policy=SpecializationPolicy(**candidate["policy"])
    run=AdapterTrainingRun(**candidate["run"])
    if run.base_model_digest!=runtime.model_digest or run.config_digest!=policy.digest or set(candidate["targets"])!=set(run.target_modules):
        raise TrainingContractError("candidate target or policy binding mismatch")
    clone=NativeLLMRuntime.restore(runtime.checkpoint(),device_policy=DevicePolicy(requested="cpu",allow_fallback=False))
    lm=clone.model
    count=0
    for name,weights in candidate["targets"].items():
        if name=="Wout" and not lm.tied:
            matrix=lm.Wout
        else:
            match=_TARGET.fullmatch(name)
            if not match or int(match.group(1))>=len(lm.layers):
                raise TrainingContractError("invalid merge target")
            matrix=getattr(lm.layers[int(match.group(1))],match.group(2),None)
        if not matrix or not matrix[0]:
            raise TrainingContractError("missing merge target")
        a,b=weights["A"],weights["B"]
        out_dim,in_dim=len(matrix),len(matrix[0])
        if len(a)!=policy.rank or len(b)!=out_dim or any(len(r)!=in_dim for r in a) or any(len(r)!=policy.rank for r in b):
            raise TrainingContractError("candidate low-rank tensor geometry mismatch")
        count+=policy.rank*(out_dim+in_dim)
        if count>policy.max_adapter_parameters or any(type(v) not in {int,float} or not math.isfinite(v) for r in a+b for v in r):
            raise TrainingContractError("adapter candidate numeric or allocation limit")
        adapter=LoRA(out_dim,in_dim,rank=policy.rank,alpha=policy.alpha)
        adapter.A=[list(r) for r in a]
        adapter.B=[list(r) for r in b]
        adapter.merge_into(matrix)
        if any(not math.isfinite(v) for row in matrix for v in row):
            raise TrainingContractError("merged candidate contains nonfinite values")
    clone.refresh_model_identity()
    runtime.assert_model_unchanged()
    identity=CandidateWeights(run.run_id,clone.model_digest,expected_sha256,runtime.model_digest)
    return clone,identity


def publish_candidate(candidate, output: Path):
    """Create-only candidate bytes; no implicit deployment or registry activation."""
    if not isinstance(output,Path) or output.exists() or output.is_symlink():
        raise FileExistsError("new adapter candidate path required")
    raw=json.dumps(candidate,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
    if len(raw)>256*1024**2:
        raise TrainingContractError("candidate serialization exceeds byte cap")
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(dir=output.parent,prefix=".lora-candidate-",delete=False) as handle:
            temporary=Path(handle.name)
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary,output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return hashlib.sha256(raw).hexdigest()
