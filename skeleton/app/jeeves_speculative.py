"""Local greedy draft/target block verification with native causal logits.

Only a compatible, explicitly supplied CPU draft is admitted. The target is
the authoritative model. No stochastic acceptance approximations, hidden
remote generator, rolling-window approximation or silent fallback. This
reference path evaluates all proposed target positions in one causal pass;
physical speedup must be measured independently.
"""
from __future__ import annotations

from hashlib import sha256
import math
import time

from skeleton.ai.model_runtime.flgb_model_runtime import TokenSequence, digest_json
from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.model_runtime.runtime_contracts import GenerationConfig, RuntimeContractError

MAX_BLOCK=8
MAX_OUTPUT=128
MAX_CONTEXT=2048
MAX_LOGIT_CELLS=2_000_000


def _admit(runtime,sequence,config):
    if not isinstance(runtime,NativeLLMRuntime):
        raise RuntimeContractError("native runtime required")
    runtime._admit_sequence(sequence,config)
    if (runtime.device.actual!="cpu" or runtime.model.resident or
            getattr(runtime.model,"_accel",None) is not None or runtime.model.use_mod):
        raise RuntimeContractError("reference speculative path requires plain CPU transformer")
    if len(sequence.token_ids)+config.max_new_tokens>min(runtime.limits.max_context,MAX_CONTEXT):
        raise RuntimeContractError("speculative path cannot shift context window")
    if config.temperature!=0 or config.stop_strings:
        raise RuntimeContractError("only greedy token-stop speculative decoding admitted")


def _binding(rt):
    rt.assert_model_unchanged()
    rt.tokenizer.assert_unchanged()
    rt._assert_execution_device()
    return (rt.model_digest,rt.tokenizer.digest,rt.architecture.digest,rt.device.digest,
            rt.limits,rt.device_policy)


def _choose(rt,logits,history,count,config):
    if len(logits)!=rt.tokenizer.vocab_size or not all(math.isfinite(x) for x in logits):
        raise RuntimeContractError("invalid speculative graph logits")
    adjusted=rt._sampling_logits(logits,history,count,config)
    return max(range(len(adjusted)),key=adjusted.__getitem__)


def generate_speculative(target,draft,prompt,config,*,block=4,interrupt=None):
    if (not isinstance(config,GenerationConfig) or
            not 1<=config.max_new_tokens<=MAX_OUTPUT or type(block) is not int or not 1<=block<=MAX_BLOCK):
        raise RuntimeContractError("invalid speculative generation budget")
    if not isinstance(target,NativeLLMRuntime) or not isinstance(draft,NativeLLMRuntime):
        raise RuntimeContractError("two native runtimes required")
    if not isinstance(prompt,str) or not prompt.strip() or len(prompt.encode())>8192:
        raise RuntimeContractError("bounded prompt required")
    sequence=target.encode(prompt)
    draft_sequence=draft.encode(prompt)
    _admit(target,sequence,config)
    _admit(draft,draft_sequence,config)
    target_pin,draft_pin=_binding(target),_binding(draft)
    if (target_pin[0]==draft_pin[0] or target_pin[1]!=draft_pin[1] or
            sequence.token_ids!=draft_sequence.token_ids):
        raise RuntimeContractError("distinct draft with identical tokenizer required")
    if (block+1)*target.tokenizer.vocab_size>MAX_LOGIT_CELLS:
        raise RuntimeContractError("target verification logits exceed budget")
    tokens=list(sequence.token_ids)
    output=[]
    rounds=[]
    draft_calls=target_passes=accepted=proposed=0
    stop="length"
    started=time.monotonic()
    def poll():
        if interrupt is not None:
            interrupt()
        if time.monotonic()-started>45:
            raise TimeoutError("speculative cooperative deadline exceeded")
    while len(output)<config.max_new_tokens:
        poll()
        remaining=config.max_new_tokens-len(output)
        count=min(block,remaining)
        proposals=[]
        for _ in range(count):
            history=tokens+proposals
            seq=TokenSequence(draft.tokenizer.digest,tuple(history),digest_json(history))
            logits=draft.infer_sequence(seq,use_cache=False,interrupt=poll).logits
            draft_calls+=1
            token=_choose(draft,logits,history,len(output)+len(proposals),config)
            proposals.append(token)
            if token in config.stop_token_ids:
                break
        # All target positions are computed by a single actual causal model
        # forward, not one target forward per candidate token. A rejected
        # suffix remains ephemeral and cannot become committed output.
        trial=tokens+proposals
        hidden,_=target.model._forward(trial,retain_cache=False,interrupt=poll)
        target_passes+=1
        start=len(tokens)-1
        if len(hidden)!=len(trial):
            raise RuntimeContractError("invalid target block geometry")
        local_accepted=0
        correction=None
        for index,token in enumerate(proposals):
            logits=target.model._unembed(hidden[start+index])
            expected=_choose(target,logits,tokens,len(output),config)
            actual=token if token==expected else expected
            if token==expected:
                local_accepted+=1
            else:
                correction=expected
            tokens.append(actual)
            output.append(actual)
            if actual in config.stop_token_ids:
                stop="stop_token"
                break
            if correction is not None:
                break
        proposed+=len(proposals)
        accepted+=local_accepted
        rounds.append({"proposed_ids":proposals,"accepted":local_accepted,"correction_id":correction})
        if stop!="length":
            break
        if correction is None and len(output)<config.max_new_tokens:
            # Bonus token from the target's final proposed position.
            bonus=_choose(target,target.model._unembed(hidden[-1]),tokens,len(output),config)
            tokens.append(bonus);output.append(bonus)
            rounds[-1]["bonus_id"]=bonus
            if bonus in config.stop_token_ids:
                stop="stop_token";break
    poll()
    if _binding(target)!=target_pin or _binding(draft)!=draft_pin:
        raise RuntimeContractError("speculative runtime binding changed")
    visible=output[:-1] if stop=="stop_token" and not config.include_stop_tokens else output
    report={"schema":"skeleton.jeeves.native-speculative.v1","target_model_digest":target.model_digest,
            "draft_model_digest":draft.model_digest,"tokenizer_digest":target.tokenizer.digest,
            "prompt_sequence_sha256":sequence.digest,"config_sha256":digest_json(config.to_dict()),
            "generated_ids":output,"text":target.decode_ids(visible),"finish_reason":stop,
            "draft_graph_calls":draft_calls,"target_block_graph_calls":target_passes,
            "proposed_tokens":proposed,"accepted_draft_tokens":accepted,"rounds":rounds,
            "elapsed_ms":round((time.monotonic()-started)*1000,3),
            "target_authoritative":True,"stochastic_sampling_supported":False,
            "speedup_certified":False,"transcript_committed":False}
    report["receipt_sha256"]=digest_json(report)
    return report
