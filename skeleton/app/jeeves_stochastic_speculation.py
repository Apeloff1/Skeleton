"""Exact rejection-sampling speculative decoding with a native block verifier.

The target distribution, not the draft distribution, governs every emitted
token. Fixed seeds reproduce this algorithm, not the serial sampler's RNG
trajectory. CUDA explicitly requires a fused SDPA backend; no CPU fallback.
"""
from __future__ import annotations
from contextlib import nullcontext
import math
import random
import time

from skeleton.app.jeeves_speculative import _binding,MAX_BLOCK,MAX_CONTEXT,MAX_OUTPUT,MAX_LOGIT_CELLS
from skeleton.ai.model_runtime.flgb_model_runtime import TokenSequence,digest_json
from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.model_runtime.runtime_contracts import GenerationConfig,RuntimeContractError


def distribution(logits,config):
    """Match canonical temperature, top-k, min-p and nucleus order."""
    if not logits or any(math.isnan(x) or x==math.inf for x in logits) or not any(math.isfinite(x) for x in logits):
        raise RuntimeContractError("invalid sampling logits")
    if config.temperature<=1e-8 or config.top_k==1:
        i=max(range(len(logits)),key=logits.__getitem__)
        return [float(j==i) for j in range(len(logits))]
    peak=max(logits);t=max(1e-6,config.temperature)
    values=[math.exp((v-peak)/t) for v in logits]
    def normalize():
        total=sum(values)
        if not math.isfinite(total) or total<=0:
            raise RuntimeContractError("empty probability support")
        values[:]=[v/total for v in values]
    normalize()
    if 0<config.top_k<len(values):
        keep=set(sorted(range(len(values)),key=lambda i:-values[i])[:config.top_k])
        values[:]=[v if i in keep else 0.0 for i,v in enumerate(values)]
        normalize()
    if config.min_p>0:
        floor=config.min_p*max(values)
        values[:]=[v if v>=floor else 0.0 for v in values]
        normalize()
    if config.top_p<1:
        keep=set();mass=0.0
        for i in sorted(range(len(values)),key=lambda j:-values[j]):
            keep.add(i);mass+=values[i]
            if mass>=config.top_p:
                break
        values[:]=[v if i in keep else 0.0 for i,v in enumerate(values)]
        normalize()
    return values


def draw(probabilities,rng):
    total=sum(probabilities)
    if not math.isfinite(total) or total<=0 or any(v<0 or not math.isfinite(v) for v in probabilities):
        raise RuntimeContractError("invalid residual probability mass")
    threshold=rng.random()*total
    cumulative=0.0
    last=None
    for i,v in enumerate(probabilities):
        if v>0:
            last=i;cumulative+=v
            if threshold<cumulative:
                return i
    return last


def accept_or_correct(p,q,proposal,rng):
    if (len(p)!=len(q) or type(proposal) is not int or not 0<=proposal<len(q)
            or q[proposal]<=0):
        raise RuntimeContractError("invalid draft proposal probability")
    if rng.random()<min(1.0,p[proposal]/q[proposal]):
        return proposal,True
    residual=[max(0.0,a-b) for a,b in zip(p,q)]
    return draw(residual,rng),False


def block_logits(target,trial,start,*,require_gpu,workspace_bytes,poll):
    """One causal graph, all required target positions; no per-token forward."""
    if not 0<=start<len(trial):
        raise RuntimeContractError("invalid block position")
    n=len(trial);m=target.model
    charge=4*(4*m.n_heads*n*n+n*(12*m.dim+4*max(m.dim,m.d_ff)+m.V))
    if charge>workspace_bytes or n*m.V>MAX_LOGIT_CELLS:
        raise RuntimeContractError("block graph exceeds workspace ceiling")
    accel=target.model._accel
    if accel is None:
        if require_gpu:
            raise RuntimeContractError("CUDA fused execution requires resident accelerator")
        if target.device.actual!="cpu" or target.model.use_mod:
            raise RuntimeContractError("unsupported reference graph")
        hidden,_=target.model._forward(trial,retain_cache=False,interrupt=poll)
        return [target.model._unembed(row) for row in hidden[start:]],"reference_cpu"
    torch=accel.torch
    if require_gpu and (accel.device_name!="cuda" or not accel.resident):
        raise RuntimeContractError("CUDA fused execution cannot fall back")
    context=nullcontext()
    if require_gpu:
        from torch.nn.attention import sdpa_kernel,SDPBackend
        if not hasattr(torch.nn.functional,"scaled_dot_product_attention"):
            raise RuntimeContractError("native fused SDPA unavailable")
        context=sdpa_kernel([SDPBackend.FLASH_ATTENTION,SDPBackend.EFFICIENT_ATTENTION])
    with accel._inference_lock(poll),torch.inference_mode(),context:
        accel._assert_training_integrity()
        logits,_=accel._forward_ids(trial,all_positions=True,interrupt=poll)
        if tuple(logits.shape)!=(n,m.V) or not bool(torch.isfinite(logits).all().item()):
            raise RuntimeContractError("invalid accelerator block output")
        # One transfer for the verified block, not one per proposal.
        rows=logits[start:].detach().cpu().tolist()
    return rows,"cuda_fused_sdpa_required" if require_gpu else "torch_all_positions"


def generate(target,draft,prompt,config,*,block=4,require_gpu=False,workspace_bytes=256*1024**2,interrupt=None):
    if (not isinstance(target,NativeLLMRuntime) or not isinstance(draft,NativeLLMRuntime)
            or not isinstance(config,GenerationConfig) or not 1<=config.max_new_tokens<=MAX_OUTPUT
            or type(block) is not int or not 1<=block<=MAX_BLOCK or type(require_gpu) is not bool
            or type(workspace_bytes) is not int or not 1<=workspace_bytes<=2*1024**3
            or not isinstance(prompt,str) or not prompt.strip() or len(prompt.encode())>8192
            or config.stop_strings or config.use_cache):
        raise RuntimeContractError("invalid bounded speculative policy")
    seq=target.encode(prompt);dseq=draft.encode(prompt)
    target._admit_sequence(seq,config);draft._admit_sequence(dseq,config)
    pins=(_binding(target),_binding(draft))
    if pins[0][0]==pins[1][0] or pins[0][1]!=pins[1][1] or seq.token_ids!=dseq.token_ids:
        raise RuntimeContractError("distinct same-tokenizer draft required")
    if target.model.use_mod or draft.model.use_mod or draft.device.actual!="cpu":
        raise RuntimeContractError("plain native target and CPU draft required")
    if len(seq.token_ids)+config.max_new_tokens>min(MAX_CONTEXT,target.limits.max_context,draft.limits.max_context):
        raise RuntimeContractError("window shifts not admitted")
    if (block+1)*target.tokenizer.vocab_size>MAX_LOGIT_CELLS:
        raise RuntimeContractError("proposal distribution storage limit")
    if require_gpu and (target.model._accel is None or target.model._accel.device_name!="cuda"):
        raise RuntimeContractError("CUDA target required")
    rng=random.Random(int(config.seed)&0xffffffff)
    history=list(seq.token_ids);output=[];rounds=[];finish="length"
    begun=time.monotonic();draft_calls=target_calls=accepted=proposed=0
    modes=set()
    def poll():
        if interrupt is not None:
            interrupt()
        if time.monotonic()-begun>45:
            raise TimeoutError("speculative decoding deadline")
    while len(output)<config.max_new_tokens:
        poll()
        proposals=[];draft_probs=[]
        for _ in range(min(block,config.max_new_tokens-len(output))):
            prefix=history+proposals
            sequence=TokenSequence(draft.tokenizer.digest,tuple(prefix),digest_json(prefix))
            logits=draft.infer_sequence(sequence,use_cache=False,interrupt=poll).logits
            q=distribution(draft._sampling_logits(logits,prefix,len(output)+len(proposals),config),config)
            token=draw(q,rng);proposals.append(token);draft_probs.append(q);draft_calls+=1
            if token in config.stop_token_ids:
                break
        rows,mode=block_logits(target,history+proposals,len(history)-1,
            require_gpu=require_gpu,workspace_bytes=workspace_bytes,poll=poll)
        modes.add(mode);target_calls+=1;proposed+=len(proposals)
        if len(rows)!=len(proposals)+1:
            raise RuntimeContractError("incomplete target verification positions")
        count=0;correction=None
        for i,token in enumerate(proposals):
            p=distribution(target._sampling_logits(rows[i],history,len(output),config),config)
            actual,ok=accept_or_correct(p,draft_probs[i],token,rng)
            history.append(actual);output.append(actual)
            if ok:
                count+=1
            else:
                correction=actual
            if actual in config.stop_token_ids:
                finish="stop_token";break
            if not ok:
                break
        accepted+=count
        row={"proposals":proposals,"accepted":count,"correction_id":correction}
        rounds.append(row)
        if finish!="length":
            break
        if correction is None and len(output)<config.max_new_tokens:
            p=distribution(target._sampling_logits(rows[-1],history,len(output),config),config)
            bonus=draw(p,rng);history.append(bonus);output.append(bonus);row["bonus_id"]=bonus
            if bonus in config.stop_token_ids:
                finish="stop_token";break
    poll()
    if (_binding(target),_binding(draft))!=pins:
        raise RuntimeContractError("model binding changed")
    visible=output[:-1] if finish=="stop_token" and not config.include_stop_tokens else output
    result={"schema":"skeleton.jeeves.stochastic-speculative.v1","target_model_digest":target.model_digest,
            "draft_model_digest":draft.model_digest,"tokenizer_digest":target.tokenizer.digest,
            "prompt_sequence_sha256":seq.digest,"config_sha256":digest_json(config.to_dict()),
            "generated_ids":output,"text":target.decode_ids(visible),"finish_reason":finish,
            "target_block_graph_calls":target_calls,"draft_graph_calls":draft_calls,
            "accepted_draft_tokens":accepted,"proposed_tokens":proposed,"rounds":rounds,
            "target_graph_modes":sorted(modes),"elapsed_ms":round((time.monotonic()-begun)*1000,3),
            "algorithm":"draft_acceptance_ratio_positive_residual","target_authoritative":True,
            "serial_rng_parity_claimed":False,"distribution_equivalence_measured":False,
            "speedup_certified":False,"transcript_committed":False}
    result["receipt_sha256"]=digest_json(result)
    return result
