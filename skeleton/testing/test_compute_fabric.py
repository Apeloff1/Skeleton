from skeleton.ai.runtime.deferred.compute_fabric import *
def test_tier_move_preserves_digest_metadata_and_critical_redundancy():
 p=TieringPolicy(2,(StorageTier.HOT,StorageTier.COLD))
 assert tier_move_valid(TierMove("a",StorageTier.HOT,StorageTier.COLD,"d","d",True,2),p)
 assert not tier_move_valid(TierMove("a",StorageTier.HOT,StorageTier.COLD,"d","x",True,2),p)
 assert not tier_move_valid(TierMove("a",StorageTier.HOT,StorageTier.COLD,"d","d",True,1),p)
def test_locality_never_overrides_security_or_authority():
 s=DataLocation("a","z1",10);c=LocalityConstraint(frozenset({"z2"}),False,True)
 assert not plan_transfer(s,"z2",c,1).admitted
def test_build_outputs_bind_job_worker_environment_and_attestation():
 j=BuildFarmJob("j","src","in");w=BuildWorker("w","env",True);a=build_artifact(j,w,"out","log")
 assert (a.job_id,a.worker_id,a.environment_id,a.attested)==("j","w","env",True)
 try:build_artifact(j,BuildWorker("w","env",False),"out","log");assert False
 except ValueError:pass
def test_eval_aggregation_is_deterministic_and_identity_bound():
 xs=(EvaluationFarmResult("j","b","e","s","acc",.8),EvaluationFarmResult("j","a","e","s","acc",.9))
 assert aggregate_results(xs)==aggregate_results(tuple(reversed(xs)))
 assert aggregate_results(xs)[0].worker_id=="a"
def test_research_queue_cannot_preempt_production_outside_policy():
 q=ResearchQueue((ResearchComputeJob("normal",ResearchPriority.NORMAL,1,"p"),),True)
 assert not allocate_research(q).admitted
 q=ResearchQueue((ResearchComputeJob("urgent",ResearchPriority.URGENT,1,"p"),),True)
 assert allocate_research(q).job_id=="urgent"
def test_research_queue_enforces_quota_and_stable_priority_order():
 q=ResearchQueue((ResearchComputeJob("b",ResearchPriority.NORMAL,1,"p"),ResearchComputeJob("a",ResearchPriority.NORMAL,1,"p")),False)
 assert allocate_research(q).job_id=="a"
 assert not allocate_research(ResearchQueue((ResearchComputeJob("x",ResearchPriority.URGENT,0,"p"),),False)).admitted
