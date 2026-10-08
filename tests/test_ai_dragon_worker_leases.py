"""Worker lease and stale-worker regressions."""
import sqlite3,pytest
from skeleton.ai.webcrawler.dragon_analysis_runtime import DragonAnalysisRuntime
from skeleton.ai.webcrawler.dragon_analysis_chains import AnalysisLayer,LayerReceipt
from skeleton.ai.webcrawler.dragon_worker_leases import DragonWorkerLeases
from skeleton.ai.webcrawler.dragon_leased_runtime import commit_leased_receipt
from skeleton.ai.webcrawler.dragon_runtime_events import DragonRuntimeEventLedger
from skeleton.ai.webcrawler.dragon_receipt_attestation import DragonReceiptAttestations

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


def test_atomic_commit_rolls_back_receipt_attestation_and_release_on_event_failure():
 db=sqlite3.connect(":memory:")
 rt=DragonAnalysisRuntime(db);rt.create("u","r",now=1,authorized=True)
 leases=DragonWorkerLeases(db)
 lease=leases.acquire("u","r","source_integrity","worker-a","source-check","2026.10",
  now=1,ttl=10,authorized=True)
 events=DragonRuntimeEventLedger(db)
 events.append("u","r",event_type="sentinel",layer="source_integrity",outcome="accepted",
  evidence_fingerprint="b"*64,occurred_at=5,authorized=True)
 receipt=LayerReceipt(AnalysisLayer.SOURCE_INTEGRITY,(),"a"*64,1,True)
 with pytest.raises(ValueError,match="time regression"):
  commit_leased_receipt(rt,leases,lease,receipt,now=2,expected_revision=0,authorized=True)
 assert rt.checkpoint("u","r",authorized=True).revision==0
 with pytest.raises(KeyError):
  DragonReceiptAttestations(db).get("u","r","source_integrity",authorized=True)
 assert len(events.events("u","r",authorized=True))==1
 assert leases.require(lease,now=2.1,authorized=True)==lease


def test_atomic_commit_rejects_mixed_database_connections():
 runtime_db=sqlite3.connect(":memory:"); lease_db=sqlite3.connect(":memory:")
 rt=DragonAnalysisRuntime(runtime_db);rt.create("u","r",now=1,authorized=True)
 leases=DragonWorkerLeases(lease_db)
 lease=leases.acquire("u","r","source_integrity","worker-a","source-check","2026.10",
  now=1,ttl=10,authorized=True)
 receipt=LayerReceipt(AnalysisLayer.SOURCE_INTEGRITY,(),"a"*64,1,True)
 with pytest.raises(ValueError,match="shared runtime database connection"):
  commit_leased_receipt(rt,leases,lease,receipt,now=2,expected_revision=0,authorized=True)


def test_successful_atomic_commit_persists_all_evidence_before_release():
 db=sqlite3.connect(":memory:")
 rt=DragonAnalysisRuntime(db);rt.create("u","r",now=1,authorized=True)
 leases=DragonWorkerLeases(db)
 lease=leases.acquire("u","r","source_integrity","worker-a","source-check","2026.10",
  now=1,ttl=10,authorized=True)
 receipt=LayerReceipt(AnalysisLayer.SOURCE_INTEGRITY,(),"a"*64,1,True)
 out=commit_leased_receipt(rt,leases,lease,receipt,now=2,expected_revision=0,authorized=True)
 att=DragonReceiptAttestations(db).get("u","r","source_integrity",authorized=True)
 events=DragonRuntimeEventLedger(db).events("u","r",authorized=True)
 assert out.checkpoint.revision==1 and att.attestation_fingerprint==out.attestation.attestation_fingerprint
 assert len(events)==1 and events[0].evidence_fingerprint=="a"*64
 with pytest.raises(PermissionError,match="missing"):
  leases.require(lease,now=2.1,authorized=True)


def test_heartbeat_renews_same_lease_identity_without_generation_change():
 db=sqlite3.connect(":memory:"); leases=DragonWorkerLeases(db)
 lease=leases.acquire("u","r","source_integrity","w","impl","1",now=1,ttl=5,authorized=True)
 renewed=leases.renew(lease,now=3,ttl=10,authorized=True)
 assert renewed.token==lease.token
 assert renewed.generation==lease.generation
 assert renewed.expires_at==13
 with pytest.raises(PermissionError,match="stale"):
  leases.require(lease,now=4,authorized=True)
 assert leases.require(renewed,now=12,authorized=True)==renewed


def test_expired_or_replaced_worker_cannot_heartbeat():
 db=sqlite3.connect(":memory:"); leases=DragonWorkerLeases(db)
 old=leases.acquire("u","r","source_integrity","w1","impl","1",now=1,ttl=2,authorized=True)
 with pytest.raises(PermissionError,match="expired"):
  leases.renew(old,now=3,ttl=5,authorized=True)
 replacement=leases.acquire("u","r","source_integrity","w2","impl","2",now=3,ttl=5,authorized=True)
 with pytest.raises(PermissionError,match="stale"):
  leases.renew(old,now=3.5,ttl=5,authorized=True)
 assert leases.require(replacement,now=4,authorized=True)==replacement


def test_heartbeat_rejects_time_regression():
 db=sqlite3.connect(":memory:"); leases=DragonWorkerLeases(db)
 lease=leases.acquire("u","r","source_integrity","w","impl","1",now=5,ttl=10,authorized=True)
 with pytest.raises(ValueError,match="time regression"):
  leases.renew(lease,now=4,ttl=5,authorized=True)


def test_new_lease_tokens_are_unpredictable_across_identical_reacquisitions():
 db=sqlite3.connect(":memory:"); leases=DragonWorkerLeases(db)
 a=leases.acquire("u","r","source_integrity","w","impl","1",now=1,ttl=1,authorized=True)
 b=leases.acquire("u","r","source_integrity","w","impl","1",now=2,ttl=1,authorized=True)
 assert len(a.token)==64 and len(b.token)==64 and a.token!=b.token
