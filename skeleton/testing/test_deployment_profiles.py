import pytest
from skeleton.ai.runtime.deferred.deployment_profiles import AirGapProfile,Connectivity,DeferredOperation,DeferredSyncLedger,EdgeNode,EdgeProfile,EnterpriseProfile,EnterpriseTopology,OfflineProfile,SyncState,TransferBundle,admit_transfer
D="a"*64
def test_offline_profile_cannot_claim_remote_capabilities():
 with pytest.raises(ValueError,match="remote capabilities"): OfflineProfile("offline",Connectivity.OFFLINE,("local:model",),("remote:web",),"data@1","t")
def test_offline_profile_exposes_freshness_revision():
 p=OfflineProfile("offline",Connectivity.OFFLINE,("local:model",),(),"data@1","t"); assert p.data_revision=="data@1" and p.freshness_observed_at
def test_deferred_sync_is_idempotent():
 l=DeferredSyncLedger(); op=DeferredOperation("op1",D,"idem1","authority:receipt"); assert l.reconcile(op,remote_revision="r2")==l.reconcile(op,remote_revision="r3")
def test_deferred_sync_rejects_collision():
 l=DeferredSyncLedger(); l.reconcile(DeferredOperation("op1",D,"same","auth"),remote_revision="r1")
 with pytest.raises(ValueError,match="collision"): l.reconcile(DeferredOperation("op2",D,"same","auth"),remote_revision="r2")
def test_conflict_is_explicit(): assert DeferredSyncLedger().reconcile(DeferredOperation("op",D,"id","auth"),remote_revision="r",conflict=True).state is SyncState.CONFLICT
def test_air_gap_disables_egress():
 with pytest.raises(ValueError,match="disable"): AirGapProfile("secure",False,True,("release",))
def test_air_gap_import_requires_trusted_signer():
 p=AirGapProfile("secure",False,False,("release",)); assert admit_transfer(p,TransferBundle("b",D,D,"release",D)); assert not admit_transfer(p,TransferBundle("b2",D,D,"unknown",D))
def test_air_gap_requires_signer():
 with pytest.raises(ValueError,match="trusted"): AirGapProfile("secure",False,False,())
def test_edge_profile_memory_bound():
 with pytest.raises(ValueError,match="cannot exceed"): EdgeProfile("tiny",2,1024,4096,2048,"strict",Connectivity.INTERMITTENT)
def test_edge_node_binds_state():
 n=EdgeNode("node",EdgeProfile("edge",4,8192,16384,4096,"strict",Connectivity.INTERMITTENT),"runtime@abc",D); assert n.persisted_state_digest==D
def test_enterprise_authority_separation():
 with pytest.raises(ValueError,match="separate"): EnterpriseProfile("org",EnterpriseTopology.HA,("alice",),("alice",),"policy@1")
def test_enterprise_identity_policy_bound():
 p=EnterpriseProfile("org",EnterpriseTopology.HA,("admin",),("model-approver",),"policy@1"); q=EnterpriseProfile("org",EnterpriseTopology.HA,("admin",),("model-approver",),"policy@2"); assert p.identity!=q.identity