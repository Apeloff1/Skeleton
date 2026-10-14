from skeleton.ai.runtime.deferred.runtime_resources import *
def test_gpu_reservation_is_before_load_and_deterministic_best_fit():
 p=GPUMemoryPool("g",100,((0,40),(50,20)));a=reserve_gpu(p,"r",15)
 assert a.reservation.offset==50 and a.reservation.size==15
def test_gpu_fragmentation_can_reject_despite_total_free():
 assert reserve_gpu(GPUMemoryPool("g",100,((0,10),(20,10))),"r",15).reservation is None
def test_eviction_excludes_pinned_and_inflight_models():
 assert not evict_model(DrainState("m",True,0)).allowed
 assert not evict_model(DrainState("m",False,1)).allowed
 assert evict_model(DrainState("m",False,0)).reloadable
def test_kv_cache_requires_exact_context_boundary():
 k=KVCacheKey("m","c","p","s","tenant","private");e=KVCacheEntry(k,"d")
 assert kv_reusable(e,k) and not kv_reusable(e,KVCacheKey("m","c","p","s","other","private"))
def test_prefix_cache_binds_instruction_prompt_model_tokenizer_version_scope():
 k=PrefixCacheKey("i","p","m","tok","1","u");a=PrefixArtifact(k,"d",True)
 assert prefix_reuse(a,k).allowed
 assert not prefix_reuse(a,PrefixCacheKey("i","p","m","tok","2","u")).allowed
def test_speculation_accepts_only_target_verified_tokens():
 assert verify_draft((DraftToken(1),DraftToken(2)),(VerificationStep(1,True),VerificationStep(2,False)))==(1,)
def test_numa_falls_back_when_unknown_and_uses_measured_affinity():
 n=(NUMANode("0",(0,1),10),)
 assert not numa_place(n,NUMAAffinity("0",None)).topology_used
 assert numa_place(n,NUMAAffinity("0",1.2)).node_id=="0"
def test_collective_requires_measured_interconnect():
 assert not collective_path((GPUInterconnect("a","b",10,False),),("a","b")).admitted
 r=collective_path((GPUInterconnect("a","b",10,True),),("a","b"));assert r.admitted and r.path.bottleneck_bandwidth==10


def test_runtime_resource_invalid_inputs_fail_closed():
 import pytest
 with pytest.raises(ValueError): reserve_gpu(GPUMemoryPool("g",10,((0,10),)),"",1)
 with pytest.raises(ValueError): reserve_gpu(GPUMemoryPool("g",10,((9,2),)),"r",1)
 with pytest.raises(ValueError): evict_model(DrainState("m",False,-1))
 with pytest.raises(ValueError): verify_draft((DraftToken(1),),(VerificationStep(2,True),))
 with pytest.raises(ValueError): verify_draft((DraftToken(1),),())
 edges=(GPUInterconnect("a","b",10,True),GPUInterconnect("c","d",10,True))
 assert not collective_path(edges,("a","b","c","d")).admitted
