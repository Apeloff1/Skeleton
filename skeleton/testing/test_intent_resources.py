from skeleton.ai.runtime.deferred.intent_resources import *
def test_approval_reuse_is_scope_version_and_use_bounded():
 s=ApprovalScope("x","v1","later",frozenset({"read"}));p=ApprovalReusePolicy(2)
 assert reusable(s,"x","v1",1,p) and not reusable(s,"x","v2",1,p) and not reusable(s,"x","v1",2,p)
def test_trust_presentation_preserves_uncertainty_degraded_and_evidence():
 p=present_trust(TrustSignal(.8,.3,True,("eval",)));assert p.degraded and p.uncertainty==.3 and p.evidence_count==1
def test_authoritative_instruction_is_separate_from_inference_and_supersedes():
 a=IntentRevision("r1",UserIntent("i","do A","maybe B",()),None);b=IntentRevision("r2",UserIntent("i","do C",None,()),"r1")
 assert latest_intent((a,b)).intent.authoritative_instruction=="do C"
def test_project_memory_is_tenant_project_and_trust_isolated():
 m=ProjectMemory("t","p","verified",(ProjectMemoryRevision("r",ProjectFact("f","v","src","verified"),None),))
 assert read_project_memory(m,"t","p","verified") and not read_project_memory(m,"other","p","verified")
def test_workspace_permissions_propagate_from_current_membership():
 w=Workspace("w",(WorkspaceMember("u",frozenset({"read"}),False),),(WorkspaceResource("r"),))
 assert not member_authorized(w,"u","read")
def test_resource_names_reject_traversal_and_require_scope():
 for n in ("../x","a/b"," a"):
  try:ResourceName("t","p",n,"v");assert False
  except ValueError:pass
def test_resolution_requires_authority_and_is_explicit_about_aliases():
 ref=ResourceRef(ResourceName("t","p","x","v1"));q=ResourceQuery(ResourceNamespace("t","p"),"x",None)
 h,r=resolve(q,(ref,),authorized=False);assert h is None and not r.authorized
 h,r=resolve(q,(ref,),authorized=True);assert h and r.alias_used and r.resolved_version=="v1"
def test_ambiguous_latest_resolution_fails_closed():
 refs=(ResourceRef(ResourceName("t","p","x","v1")),ResourceRef(ResourceName("t","p","x","v2")))
 h,r=resolve(ResourceQuery(ResourceNamespace("t","p"),"x",None),refs,authorized=True);assert h is None
def test_artifact_graph_is_version_specific_and_detects_cycles():
 a=ArtifactNode("a","1");b=ArtifactNode("b","1")
 assert artifact_cycle(ArtifactGraph((a,b),(ArtifactDependency(a,b,DependencyKind.BUILD),ArtifactDependency(b,a,DependencyKind.RUNTIME))))

def test_depth_invariants_fail_closed():
 import pytest
 scope=ApprovalScope("s","v","later",frozenset({"read"}));assert not reusable(scope,"s","v",0,ApprovalReusePolicy(0))
 with pytest.raises(ValueError):present_trust(TrustSignal(1.1,0.1,False,("e",)))
 intent=UserIntent("i","do",None,());rev=IntentRevision("r",intent,None)
 with pytest.raises(ValueError):latest_intent((rev,rev))
 a=ArtifactNode("a","1");b=ArtifactNode("b","1")
 with pytest.raises(ValueError):artifact_cycle(ArtifactGraph((a,),(ArtifactDependency(a,b,DependencyKind.RUNTIME),)))
