from skeleton.ai.runtime.deferred.retrieval_lifecycle import *
E=EmbeddingVersion("m","1",2,"norm")
def test_data_health_keeps_freshness_and_correctness_visible():
 h=data_health(DataSLO(.99,.99,FreshnessSLI(100,50,10)),1,1);assert h.availability_ok and h.correctness_ok and not h.freshness_ok and not h.healthy
def test_embedding_space_binds_model_version_dimension_preprocessing():
 a=EmbeddingRecord("a",E,(1,2));b=EmbeddingRecord("b",EmbeddingVersion("m","2",2,"norm"),(1,2));assert not comparable(a,b)
def test_vector_cutover_requires_shadow_and_all_quality_gates():
 active=VectorIndexVersion("i","1",E,False);shadow=VectorIndexVersion("i","2",E,True)
 assert promote_index(IndexMigration(active,shadow,IndexValidation(True,False,True)))==active
 assert promote_index(IndexMigration(active,shadow,IndexValidation(True,True,True))).version=="2"
def test_search_index_retirement_requires_rebuildability():
 x=SearchIndex("i",IndexWatermark("src-v1",10));assert retire_index(IndexLifecycle(x,True)).retired and not retire_index(IndexLifecycle(x,False)).retired
def test_freshness_uses_source_watermark_not_cache_age():
 r=FreshnessRequirement(5,StaleAction.QUALIFY);assert freshness(r,100,90)==FreshnessDecision(FreshnessState.STALE,StaleAction.QUALIFY)
 assert freshness(r,None,90).action is StaleAction.ABSTAIN
def test_source_trust_is_claim_domain_and_time_scoped():
 t=SourceTrust(SourceIdentity("s","o","l"),(TrustEvidence("e","claim","finance",10),));assert trust_for(t,"claim","finance",9) and not trust_for(t,"claim","medical",9) and not trust_for(t,"claim","finance",11)
def test_untrusted_content_remains_data_not_instruction():
 assert content_role(SourceTrust(SourceIdentity("s","o","l"),(),False),"c","d",0)=="data"
