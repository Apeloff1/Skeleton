import pytest
from skeleton.ai.runtime.deferred.policy_refresh import *
D="a"*64
def test_routing_fallback_cannot_cross_privacy_or_capability_boundary():
 p=RoutingPolicy("p","r1",(RouteConstraint("llm","eu",1.0,.9),),("bad","good"))
 cs=(ProviderCandidate("bad","llm","us",.1,1),ProviderCandidate("good","llm","eu",.5,.95))
 assert route(p,cs).provider_id=="good"
def test_routing_fails_closed_without_compatible_candidate():
 p=RoutingPolicy("p","r1",(RouteConstraint("llm","eu",1,.9),),("x",))
 assert not route(p,(ProviderCandidate("x","llm","us",.1,1),)).allowed
def test_routing_identity_changes_with_policy_revision():
 a=RoutingPolicy("p","r1",(RouteConstraint("llm","eu",1,.9),),()); b=RoutingPolicy("p","r2",a.constraints,())
 assert a.identity!=b.identity
def test_untrusted_memory_cannot_be_promoted_authoritative_without_evidence():
 with pytest.raises(ValueError,match="requires evidence"): MemoryPromotion("m",MemoryTrust.INFERRED,MemoryTrust.AUTHORITATIVE,None)
 assert MemoryPromotion("m",MemoryTrust.INFERRED,MemoryTrust.AUTHORITATIVE,D).evidence_digest==D
def test_retrieval_filters_tenant_before_ranking():
 p=RetrievalPolicy("p",RetrievalFilter("t1",("internal",),None,None),RankingPolicy(100,False))
 docs=(RetrievalDocument("evil","t2","internal","t",1,999),RetrievalDocument("ok","t1","internal","t",1,1))
 assert [d.document_id for d in retrieve(p,docs)]==["ok"]
def test_retrieval_stale_degradation_is_explicit():
 strict=RetrievalPolicy("p",RetrievalFilter("t",("c",),None,None),RankingPolicy(10,False))
 stale=(RetrievalDocument("d","t","c","t",99,1),)
 assert retrieve(strict,stale)==()
 permissive=RetrievalPolicy("p",strict.filter,RankingPolicy(10,True))
 assert retrieve(permissive,stale)==stale
def test_refresh_projection_does_not_switch_before_commit():
 r=RefreshCoordinator(KnowledgeRefresh("r","epoch1","epoch2","src1"))
 assert r.receipt().projection_epoch=="epoch1"
 assert r.checkpoint(10).projection_epoch=="epoch1"
 assert r.commit().projection_epoch=="epoch2"
def test_refresh_cursor_is_monotonic_and_resumable():
 r=RefreshCoordinator(KnowledgeRefresh("r","e1","e2","src"))
 r.checkpoint(10)
 with pytest.raises(ValueError,match="backwards"): r.checkpoint(9)
 assert r.cursor.offset==10
def test_refresh_preserves_history_epoch_after_commit():
 r=RefreshCoordinator(KnowledgeRefresh("r","history","new","src")); r.checkpoint(1); receipt=r.commit()
 assert receipt.history_epoch=="history" and receipt.projection_epoch=="new"
