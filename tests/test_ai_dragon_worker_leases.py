"""Worker lease and stale-worker regressions."""
import sqlite3,pytest
from skeleton.ai.webcrawler.dragon_analysis_runtime import DragonAnalysisRuntime
from skeleton.ai.webcrawler.dragon_analysis_chains import AnalysisLayer,LayerReceipt
from skeleton.ai.webcrawler.dragon_worker_leases import DragonWorkerLeases
from skeleton.ai.webcrawler.dragon_leased_runtime import commit_leased_receipt

def test_active_lease_excludes_second_worker():
 db=sqlite3.connect(":memory:");l=DragonWorkerLeases(db)
 l.acquire("u","r","source_integrity","w1","impl","1",now=1,ttl=10,authorized=True)
 with pytest.raises(RuntimeError,match="already leased"):
  l.acquire("u","r","source_integrity","w2","impl","1",now=2,ttl=10,authorized=True)

def test_expired_lease_is_recovered_with_new_generation():
 db=sqlite3.connect(":memory:");l=DragonWorkerLeases(db)
 a=l.acquire("u","r","source_integrity","w1","impl","1",now=1,ttl=2,authorized=True)
 b=l.acquire("u","r","source_integrity","w2","impl","2",now=3,ttl=2,authorized=True)
 assert b.generation==a.generation+1 and b.token!=a.token
 with pytest.raises(PermissionError,match="stale"):
  l.require(a,now=3.5,authorized=True)

def test_expired_worker_cannot_commit_receipt():
 db=sqlite3.connect(":memory:");rt=DragonAnalysisRuntime(db);rt.create("u","r",now=1,authorized=True)
 l=DragonWorkerLeases(db);lease=l.acquire("u","r","source_integrity","w","impl","1",now=1,ttl=2,authorized=True)
 receipt=LayerReceipt(AnalysisLayer.SOURCE_INTEGRITY,(),"a"*64,1,True)
 with pytest.raises(PermissionError,match="expired"):
  commit_leased_receipt(rt,l,lease,receipt,now=3,expected_revision=0,authorized=True)
 assert rt.checkpoint("u","r",authorized=True).revision==0

def test_valid_worker_commit_releases_lease_and_records_identity():
 db=sqlite3.connect(":memory:");rt=DragonAnalysisRuntime(db);rt.create("u","r",now=1,authorized=True)
 l=DragonWorkerLeases(db);lease=l.acquire("u","r","source_integrity","worker-a","source-check","2026.10",now=1,ttl=10,authorized=True)
 receipt=LayerReceipt(AnalysisLayer.SOURCE_INTEGRITY,(),"a"*64,1,True)
 out=commit_leased_receipt(rt,l,lease,receipt,now=2,expected_revision=0,authorized=True)
 assert out.checkpoint.revision==1 and out.worker_id=="worker-a" and out.version=="2026.10"
 with pytest.raises(PermissionError,match="missing"):l.require(lease,now=2.1,authorized=True)
