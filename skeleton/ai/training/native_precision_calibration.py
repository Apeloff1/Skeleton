"""Actual groupwise precision sensitivity experiments for the native CPU graph.

Use a deterministic packed symmetric integer codec, then evaluate its
DEQUANTIZED weight values on the real reference transformer. This is a
calibration-only experiment: no GGUF format claim, packed-tensor execution,
automatic deployment, physical memory measurement or promotion permission.
Compare interactions in a combined candidate after isolated trials.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import math
import struct
import time
from typing import Callable

from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime

from .contamination_scan import MaterializedExample, scan_materialized_overlap
from .flgb_training_runtime import DatasetRevision, DatasetRights, digest_json, require_digest
from .native_retention_evaluation import RetentionCase, RetentionPolicy, corpus_digest, evaluate_retention

_BITS=(4,6,8)
_MAX_VALUES=4_000_000


def _int(value,lo,hi,name):
    if type(value) is not int or not lo<=value<=hi:
        raise ValueError("invalid precision "+name)


@dataclass(frozen=True,slots=True)
class PackedBlock:
    bits:int
    count:int
    scale_f32:bytes
    payload:bytes

    def __post_init__(self):
        if type(self.bits) is not int or self.bits not in _BITS:
            raise ValueError("unsupported native calibration code width")
        _int(self.count,1,256,"block length")
        if type(self.scale_f32) is not bytes or len(self.scale_f32)!=4:
            raise ValueError("invalid FP32 block scale")
        scale=struct.unpack(">f",self.scale_f32)[0]
        if not math.isfinite(scale) or scale<=0:
            raise ValueError("invalid finite block scale")
        valid_bits=self.count*self.bits
        if type(self.payload) is not bytes or len(self.payload)!=(valid_bits+7)//8:
            raise ValueError("invalid packed block byte count")
        if valid_bits%8 and self.payload[-1]>>(valid_bits%8):
            raise ValueError("noncanonical high padding bits")
        mask=(1<<self.bits)-1
        accum=available=offset=0
        for _ in range(self.count):
            while available<self.bits:
                accum|=self.payload[offset]<<available
                available+=8;offset+=1
            if (accum&mask)==mask:
                raise ValueError("reserved symmetric integer code")
            accum>>=self.bits;available-=self.bits

    @property
    def bytes_used(self):
        return len(self.scale_f32)+len(self.payload)

    @property
    def digest(self):
        return sha256(struct.pack(">BH",self.bits,self.count)+self.scale_f32+self.payload).hexdigest()

    def decode(self):
        scale=struct.unpack(">f",self.scale_f32)[0]
        qmax=(1<<(self.bits-1))-1
        mask=(1<<self.bits)-1
        accum=available=offset=0
        values=[]
        for _ in range(self.count):
            while available<self.bits:
                accum|=self.payload[offset]<<available
                available+=8;offset+=1
            values.append(((accum&mask)-qmax)*scale)
            accum>>=self.bits;available-=self.bits
        return values


def pack_block(values,bits:int)->PackedBlock:
    if type(bits) is not int or bits not in _BITS:
        raise ValueError("unsupported native calibration code width")
    if not isinstance(values,(list,tuple)) or not 1<=len(values)<=256:
        raise ValueError("bounded block required")
    if any(type(x) not in (int,float) or not math.isfinite(x) for x in values):
        raise ValueError("nonfinite native weight block")
    qmax=(1<<(bits-1))-1
    peak=max(abs(x) for x in values)
    try:
        scale_f32=struct.pack(">f",peak/qmax if peak else 1.0)
    except (OverflowError,struct.error) as exc:
        raise ValueError("weight block cannot represent an FP32 scale") from exc
    scale=struct.unpack(">f",scale_f32)[0]
    if not math.isfinite(scale) or scale<=0:
        raise ValueError("nonzero native block scale underflow or overflow")
    accum=available=0
    output=bytearray()
    for x in values:
        code=max(-qmax,min(qmax,round(x/scale)))+qmax
        accum|=code<<available
        available+=bits
        while available>=8:
            output.append(accum&255)
            accum>>=8;available-=8
    if available:
        output.append(accum)
    return PackedBlock(bits,len(values),scale_f32,bytes(output))


@dataclass(frozen=True,slots=True)
class PrecisionPolicy:
    group_size:int=32
    bit_widths:tuple[int,...]=(4,6,8)
    max_profiles:int=12
    max_values:int=1_000_000
    max_total_values:int=4_000_000
    max_model_bytes:int=64*1024**2
    max_total_evaluation_steps:int=16384

    def __post_init__(self):
        _int(self.group_size,4,256,"group size")
        _int(self.max_profiles,2,32,"profile count")
        _int(self.max_values,1,_MAX_VALUES,"group value count")
        _int(self.max_total_values,1,16_000_000,"total weight work")
        _int(self.max_model_bytes,1024,256*1024**2,"logical model bytes")
        _int(self.max_total_evaluation_steps,1,65536,"evaluation work")
        if (type(self.bit_widths) is not tuple or not self.bit_widths
                or any(type(x) is not int or x not in _BITS for x in self.bit_widths)
                or tuple(sorted(set(self.bit_widths)))!=self.bit_widths):
            raise ValueError("explicit unique ascending candidate bit widths required")

    @property
    def digest(self):
        return digest_json({"algorithm":"native-symmetric-packed-calibration-v1",
                            **{k:getattr(self,k) for k in self.__dataclass_fields__}})


@dataclass(frozen=True,slots=True)
class PrecisionTrial:
    group:str
    bits:int
    values:int
    codec_bytes:int
    packed_digest:str
    candidate_digest:str
    evaluation_digest:str|None
    holds:tuple[str,...]

    @property
    def supported(self):
        return self.evaluation_digest is not None and not self.holds


@dataclass(frozen=True,slots=True)
class PrecisionReport:
    base_model_digest:str
    calibration_dataset_digest:str
    final_holdout_inventory_digest:str
    policy_digest:str
    evaluation_policy_digest:str
    trials:tuple[PrecisionTrial,...]
    proposed_bits:tuple[tuple[str,int],...]
    combined_model_digest:str|None
    combined_evaluation_digest:str|None
    combined_codec_bytes:int
    combined_values:int
    holds:tuple[str,...]
    evidence_digest:str

    @property
    def promotion_authorized(self):
        return False


def _groups(model):
    """Explicit disjoint matrix groups; no bias/norm or tied-weight edits."""
    groups={"output":((model,"Wout"),),"embedding":((model,"E"),)}
    if model.position_mode!="rope":
        groups["position"]=((model,"P"),)
    for i,layer in enumerate(model.layers):
        groups[f"layer-{i}-attention"]=tuple((layer,x) for x in ("Wq","Wk","Wv","Wo"))
        if model.d_ff:
            groups[f"layer-{i}-ffn"]=tuple((layer,x) for x in ("W1","Wu","W2"))
    return groups


def _count(refs):
    return sum(len(row) for obj,name in refs for row in getattr(obj,name))


def _quantize(model,group,bits,group_size,poll):
    refs=_groups(model)[group]
    hashes=sha256()
    size=count=0
    modified=False
    for obj,name in refs:
        matrix=getattr(obj,name)
        output=[]
        for row in matrix:
            poll()
            decoded=[]
            for start in range(0,len(row),group_size):
                block=pack_block(row[start:start+group_size],bits)
                values=block.decode()
                hashes.update(bytes.fromhex(block.digest))
                count+=block.count
                size+=block.bytes_used
                modified=modified or any(x!=y for x,y in zip(row[start:start+group_size],values))
                decoded.extend(values)
            output.append(decoded)
        setattr(obj,name,output)
    return count,size,hashes.hexdigest(),modified


def calibrate_native_precision(
    baseline:NativeLLMRuntime, groups:tuple[str,...], cases:tuple[RetentionCase,...], *,
    expected_base_digest:str, dataset:DatasetRevision, rights:DatasetRights,
    training_examples:tuple[MaterializedExample,...],
    training_item_sha256:frozenset[str], expected_training_inventory_sha256:str,
    final_holdout_sha256:frozenset[str], expected_final_holdout_sha256:str,
    policy:PrecisionPolicy, retention_policy:RetentionPolicy, deadline:float,
    interrupt:Callable[[],None]|None=None,
)->tuple[PrecisionReport,NativeLLMRuntime|None]:
    """Run isolated and combined real sensitivity trials on calibration only.

    Final holdout contributes hashes for exclusion, never text or scores.
    It remains independently evaluated after calibration. This function
    accepts the caller's authenticated inventories; completeness and semantic
    leakage are external assurance requirements. Candidate result contains
    ordinary floating-point weights, not a deployable packed kernel.
    """
    if type(baseline) is not NativeLLMRuntime or type(policy) is not PrecisionPolicy or type(retention_policy) is not RetentionPolicy:
        raise ValueError("canonical native runtime and typed policies required")
    if type(dataset) is not DatasetRevision or type(rights) is not DatasetRights:
        raise ValueError("explicit calibration dataset revision and rights required")
    if not rights.permits("calibration") or not rights.permits("evaluation"):
        raise ValueError("explicit calibration and evaluation rights required")
    if baseline.model_digest!=expected_base_digest:
        raise ValueError("precision baseline identity mismatch")
    if (type(final_holdout_sha256) is not frozenset or not 1<=len(final_holdout_sha256)<=100000
            or type(training_item_sha256) is not frozenset):
        raise ValueError("explicit separate final holdout inventory required")
    for item in final_holdout_sha256:
        require_digest(item,"reserved final holdout")
    final_digest=digest_json(sorted(final_holdout_sha256))
    if final_digest!=expected_final_holdout_sha256:
        raise ValueError("final holdout inventory changed")
    if (dataset.dataset_id!=rights.dataset_id or dataset.rights_digest!=rights.digest
            or dataset.content_digest!=corpus_digest(cases)):
        raise ValueError("calibration dataset revision or rights identity mismatch")
    if not 1<=len(training_item_sha256)<=4096:
        raise ValueError("bounded complete materialized training inventory required")
    for item in training_item_sha256:
        require_digest(item,"training item")
    if digest_json(sorted(training_item_sha256))!=expected_training_inventory_sha256:
        raise ValueError("training inventory identity mismatch")
    if final_holdout_sha256.intersection(c.content_sha256 for c in cases) or final_holdout_sha256.intersection(training_item_sha256):
        raise ValueError("calibration or training contaminates reserved final holdout")
    if isinstance(deadline,bool) or not isinstance(deadline,(float,int)) or not math.isfinite(deadline):
        raise ValueError("finite monotonic calibration deadline required")
    def poll():
        if interrupt is not None:
            interrupt()
        if time.monotonic()>=deadline:
            raise TimeoutError("native precision calibration deadline exceeded")
    poll()
    overlap=scan_materialized_overlap(training_examples,
            tuple(MaterializedExample(c.content_sha256,c.text) for c in cases),interrupt=poll)
    if overlap.training_inventory_sha256!=expected_training_inventory_sha256 or overlap.review_required:
        raise ValueError("calibration training inventory or contamination hold")
    baseline.assert_model_unchanged()
    baseline.tokenizer.assert_unchanged()
    model=baseline.model
    if (baseline.device.actual!="cpu" or baseline.device.resident or model._accel is not None
            or model.use_mod or model.tied or model.E is model.Wout):
        raise ValueError("calibration requires untied reference CPU model")
    if baseline.model_bytes>policy.max_model_bytes:
        raise ValueError("calibration model exceeds logical memory ceiling")
    available=_groups(model)
    if (type(groups) is not tuple or not groups or len(groups)>policy.max_profiles
            or any(type(g) is not str or g not in available for g in groups)
            or len(set(groups))!=len(groups)):
        raise ValueError("bounded explicit disjoint calibration groups required")
    groups=tuple(sorted(groups))
    trial_limit=len(groups)*len(policy.bit_widths)+1
    if trial_limit>policy.max_profiles:
        raise ValueError("precision profile count exceeded")
    counts={g:_count(available[g]) for g in groups}
    if (any(not 0<v<=policy.max_values for v in counts.values())
            or sum(counts.values())*(len(policy.bit_widths)+1)>policy.max_total_values):
        raise ValueError("precision weight work exceeded")
    steps=0
    for case in cases:
        poll()
        ids=baseline.encode(case.text).token_ids
        if not 2<=len(ids)<=min(retention_policy.max_case_tokens,baseline.limits.max_context):
            raise ValueError("calibration input exceeds non-sliding token admission")
        steps+=len(ids)-1
    if steps>retention_policy.max_steps or steps*trial_limit>policy.max_total_evaluation_steps:
        raise ValueError("precision evaluation work exceeded")
    cp=baseline.checkpoint()
    trials=[]
    selected={}
    def evaluate(candidate):
        return evaluate_retention(baseline,candidate,cases,dataset=dataset,rights=rights,
            expected_baseline_sha256=expected_base_digest,
            expected_candidate_sha256=candidate.model_digest,
            training_item_sha256=training_item_sha256,training_examples=training_examples,
            expected_training_inventory_sha256=expected_training_inventory_sha256,
            policy=retention_policy,deadline=deadline,interrupt=poll)
    for group in groups:
        admitted=[]
        for bits in policy.bit_widths:
            poll()
            candidate=NativeLLMRuntime.restore(cp)
            n,size,packed,changed=_quantize(candidate.model,group,bits,policy.group_size,poll)
            if n!=counts[group]:
                raise ValueError("precision group accounting drift")
            if changed:
                candidate.refresh_model_identity()
                evaluation=evaluate(candidate)
                row=PrecisionTrial(group,bits,n,size,packed,candidate.model_digest,
                                   evaluation.evidence_sha256,evaluation.holds)
            else:
                # No weight change cannot be used to claim measured quality.
                row=PrecisionTrial(group,bits,n,size,packed,expected_base_digest,None,("unchanged_profile",))
            trials.append(row)
            if row.supported:
                admitted.append(row)
            del candidate
        if admitted:
            selected[group]=min(admitted,key=lambda r:(r.codec_bytes,r.bits,r.packed_digest))
    combined=None
    combined_id=combined_eval=None
    combined_size=combined_values=0
    holds=[]
    if selected:
        candidate=NativeLLMRuntime.restore(cp)
        for group,row in sorted(selected.items()):
            poll()
            n,size,packed,changed=_quantize(candidate.model,group,row.bits,policy.group_size,poll)
            if not changed or (n,size,packed)!=(row.values,row.codec_bytes,row.packed_digest):
                raise ValueError("combined precision bytes differ from isolated trial")
            combined_size+=size
            combined_values+=n
        candidate.refresh_model_identity()
        evaluation=evaluate(candidate)
        combined_id=candidate.model_digest
        combined_eval=evaluation.evidence_sha256
        if evaluation.holds:
            holds.extend("combined:"+x for x in evaluation.holds)
        else:
            combined=candidate
    else:
        holds.append("no_qualified_changed_group")
    poll()
    baseline.assert_model_unchanged()
    if baseline.model_digest!=expected_base_digest:
        raise ValueError("precision baseline drift")
    proposed=tuple((g,row.bits) for g,row in sorted(selected.items()))
    record={
        "base":expected_base_digest,"dataset":dataset.digest,"rights":rights.digest,
        "final_holdout":final_digest,"policy":policy.digest,
        "evaluation_policy":retention_policy.identity,
        "training_inventory":expected_training_inventory_sha256,
        "contamination_evidence":overlap.evidence_sha256,
        "trials":[{k:getattr(row,k) for k in row.__dataclass_fields__} for row in trials],
        "proposed_bits":proposed,"combined_model":combined_id,
        "combined_evaluation":combined_eval,"codec_bytes":combined_size,
        "combined_values":combined_values,"holds":sorted(holds),
    }
    report=PrecisionReport(expected_base_digest,dataset.digest,final_digest,policy.digest,
        retention_policy.identity,tuple(trials),proposed,combined_id,combined_eval,
        combined_size,combined_values,tuple(sorted(holds)),digest_json(record))
    return report,combined


__all__=["PackedBlock","pack_block","PrecisionPolicy","PrecisionTrial","PrecisionReport","calibrate_native_precision"]
