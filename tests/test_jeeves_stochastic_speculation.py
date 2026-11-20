"""Distribution and actual native block-graph qualification."""
from collections import Counter
import random

import pytest

from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.model_runtime.runtime_contracts import DevicePolicy,GenerationConfig,RuntimeContractError
from skeleton.cortex.transformer import TinyTransformer
from skeleton.cortex.attn import sample_logits
from skeleton.app.jeeves_stochastic_speculation import distribution,draw,accept_or_correct,generate,block_logits


def runtime(seed=41,device="cpu"):
    return NativeLLMRuntime(TinyTransformer(
        vocab=("system:","user:","assistant:","hello","world","answer","local","offline","jeeves","."," "),
        dim=16,ctx=128,seed=seed,n_heads=2,n_layers=2,d_ff=32),
        device_policy=DevicePolicy(requested=device,allow_fallback=False))


@pytest.mark.parametrize("top_k,top_p,min_p",[(0,1,0),(3,.8,0),(0,.7,.1),(1,1,0)])
def test_distribution_matches_canonical_draw(top_k,top_p,min_p):
    cfg=GenerationConfig(temperature=.7,top_k=top_k,top_p=top_p,min_p=min_p)
    logits=[-.8,1.25,.6,float("-inf"),-.4,1.3]
    p=distribution(logits,cfg)
    assert sum(p)==pytest.approx(1) and p[3]==0
    for seed in range(100):
        assert draw(p,random.Random(seed))==sample_logits(logits,random.Random(seed),
            temperature=cfg.temperature,top_k=top_k,top_p=top_p,min_p=min_p)


def test_acceptance_residual_measures_target_not_draft_distribution():
    p=[.07,.18,.75];q=[.65,.3,.05]
    rng=random.Random(923)
    counts=Counter()
    rejection=0
    for _ in range(24000):
        token,accepted=accept_or_correct(p,q,draw(q,rng),rng)
        counts[token]+=1;rejection+=not accepted
    assert rejection>10000
    for i,prob in enumerate(p):
        assert counts[i]/24000==pytest.approx(prob,abs=.015)


@pytest.mark.parametrize("block",[1,4,8])
def test_actual_native_greedy_block_equivalence(block):
    target,draft=runtime(),runtime(17)
    cfg=GenerationConfig(max_new_tokens=8,temperature=0,use_cache=False)
    direct=target.generate("hello world",cfg)
    result=generate(target,draft,"hello world",cfg,block=block)
    assert result["generated_ids"]==list(direct.generated_ids)
    assert result["target_graph_modes"]==["reference_cpu"]
    assert result["target_block_graph_calls"]<=8
    assert result["target_authoritative"] and not result["speedup_certified"]


def test_native_stochastic_seed_and_stop_contract():
    target,draft=runtime(),runtime(17)
    cfg=GenerationConfig(max_new_tokens=8,temperature=.8,top_k=5,top_p=.9,
        min_p=.02,seed=33,use_cache=False,repetition_penalty=1.1)
    one=generate(target,draft,"hello world",cfg)
    two=generate(target,draft,"hello world",cfg)
    assert one["generated_ids"]==two["generated_ids"]
    assert len(one["generated_ids"])==8
    assert not one["serial_rng_parity_claimed"]
    assert one["accepted_draft_tokens"]<=one["proposed_tokens"]
    with pytest.raises(RuntimeContractError):
        generate(target,draft,"hello",cfg,require_gpu=True)
    with pytest.raises(RuntimeContractError):
        generate(target,target,"hello",cfg)


def test_actual_torch_cpu_all_positions_matches_independent_prefixes():
    pytest.importorskip("torch")
    target,draft=runtime(device="torch-cpu"),runtime(17)
    ids=list(target.encode("hello world .").token_ids)
    rows,mode=block_logits(target,ids,0,require_gpu=False,workspace_bytes=1024**2,poll=lambda:None)
    assert mode=="torch_all_positions"
    for i,row in enumerate(rows):
        expected=target.model._accel.logits(ids[:i+1])
        assert row==pytest.approx(expected,rel=1e-5,abs=1e-5)
    result=generate(target,draft,"hello world",GenerationConfig(max_new_tokens=4,
        temperature=.7,seed=8,use_cache=False))
    assert result["target_graph_modes"]==["torch_all_positions"]


def test_physical_cuda_fused_path_when_explicit_device_exists():
    torch=pytest.importorskip("torch")
    if not torch.cuda.is_available():
        pytest.skip("physical CUDA device not available; no fused GPU qualification")
    target,draft=runtime(device="cuda"),runtime(17)
    cfg=GenerationConfig(max_new_tokens=4,temperature=.8,seed=4,use_cache=False)
    result=generate(target,draft,"hello world",cfg,require_gpu=True,workspace_bytes=64*1024**2)
    assert result["target_graph_modes"]==["cuda_fused_sdpa_required"]
    assert len(result["generated_ids"])==4



def test_paired_hardware_diagnostic_uses_real_generation_and_no_promotion():
    from scripts.qualify_jeeves_speculation import qualify
    target,draft=runtime(),runtime(17)
    report=qualify(target,draft,["hello world"],config=GenerationConfig(
        max_new_tokens=2,temperature=0,use_cache=False),
        block=2,seeds=8,require_gpu=False,workspace_bytes=1024**2)
    assert report["serial"]["cases"]==report["speculative"]["cases"]==8
    assert report["greedy_exact_token_parity"] is True
    assert report["cases"][0]["first_token_total_variation_empirical"]==0
    assert report["target_device_receipt"]["actual"]=="cpu"
    assert report["observed_wall_speed_ratio"]>0
    assert report["activation_authorized"] is False
    assert report["production_quality_certified"] is False
