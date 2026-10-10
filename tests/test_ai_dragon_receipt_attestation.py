"""Execution attestation regressions."""
import sqlite3
from skeleton.ai.webcrawler.dragon_analysis_runtime import DragonAnalysisRuntime
from skeleton.ai.webcrawler.dragon_analysis_chains import AnalysisLayer,LayerReceipt
from skeleton.ai.webcrawler.dragon_worker_leases import DragonWorkerLeases
from skeleton.ai.webcrawler.dragon_leased_runtime import commit_leased_receipt
from skeleton.ai.webcrawler.dragon_attestation_replay import verify_receipt_attestation

def build():
 db=sqlite3.connect(":memory:");rt=DragonAnalysisRuntime(db);rt.create("u","r",now=1,authorized=True)
 leases=DragonWorkerLeases(db);lease=leases.acquire("u","r","source_integrity","w","impl","v1",now=1,ttl=10,authorized=True)
 receipt=LayerReceipt(AnalysisLayer.SOURCE_INTEGRITY,(),"a"*64,1,True)
 out=commit_leased_receipt(rt,leases,lease,receipt,now=2,expected_revision=0,authorized=True)
 return db,out

def test_commit_persists_worker_attestation():
 db,out=build();a=out.attestation
 assert a.worker_id=="w" and a.implementation=="impl" and a.version=="v1"
 assert a.committed_revision==1 and len(a.attestation_fingerprint)==64

def test_replay_verifies_exact_accepted_receipt():
 db,_=build();v=verify_receipt_attestation(db,"u","r","source_integrity",authorized=True)
 assert v.valid and v.reason=="verified"

def test_receipt_mutation_breaks_replay():
 db,_=build();db.execute("UPDATE dragon_analysis_run_receipts SET output_fingerprint=? WHERE owner='u' AND run_id='r'",("b"*64,));db.commit()
 v=verify_receipt_attestation(db,"u","r","source_integrity",authorized=True)
 assert not v.valid and "mismatch" in v.reason

def test_attestation_mutation_breaks_replay():
 db,_=build();db.execute("UPDATE dragon_receipt_attestations SET version='evil' WHERE owner='u' AND run_id='r'");db.commit()
 v=verify_receipt_attestation(db,"u","r","source_integrity",authorized=True)
 assert not v.valid and "attestation fingerprint" in v.reason


def test_earlier_attestation_replays_after_later_valid_receipt():
 db,out=build()
 rt=DragonAnalysisRuntime(db);leases=DragonWorkerLeases(db)
 lease=leases.acquire("u","r","temporal_segmentation","w2","temporal","v2",
  now=3,ttl=10,authorized=True)
 temporal=LayerReceipt(AnalysisLayer.TEMPORAL_SEGMENTATION,("a"*64,),"b"*64,1,True)
 commit_leased_receipt(rt,leases,lease,temporal,now=4,expected_revision=1,authorized=True)
 v=verify_receipt_attestation(db,"u","r","source_integrity",authorized=True)
 assert v.valid and v.reason=="verified"


def test_non_output_receipt_mutation_breaks_historical_chain_replay():
 db,_=build()
 db.execute("""UPDATE dragon_analysis_run_receipts SET independent_sources=7
  WHERE owner='u' AND run_id='r' AND layer='source_integrity'""")
 db.commit()
 v=verify_receipt_attestation(db,"u","r","source_integrity",authorized=True)
 assert not v.valid and "historical chain fingerprint mismatch" in v.reason


def test_replay_binds_attestation_to_persisted_worker_lease_history():
 db,out=build();a=out.attestation
 row=db.execute("""SELECT worker_id,implementation,version,token_digest,leased_at,expires_at,released_at
  FROM dragon_worker_lease_history WHERE owner='u' AND run_id='r' AND layer='source_integrity'
  AND generation=?""",(a.lease_generation,)).fetchone()
 assert row[:4]==(a.worker_id,a.implementation,a.version,a.lease_token_digest)
 assert row[4]<=row[6]<row[5]

def test_historical_worker_identity_mutation_breaks_replay():
 db,_=build()
 db.execute("""UPDATE dragon_worker_lease_history SET worker_id='other'
  WHERE owner='u' AND run_id='r' AND layer='source_integrity'""");db.commit()
 v=verify_receipt_attestation(db,"u","r","source_integrity",authorized=True)
 assert not v.valid and "lease identity mismatch" in v.reason

def test_historical_lease_validity_mutation_breaks_replay():
 db,_=build()
 db.execute("""UPDATE dragon_worker_lease_history SET expires_at=released_at
  WHERE owner='u' AND run_id='r' AND layer='source_integrity'""");db.commit()
 v=verify_receipt_attestation(db,"u","r","source_integrity",authorized=True)
 assert not v.valid and "lease validity mismatch" in v.reason

def test_worker_receipt_audit_time_must_match_lease_release():
 db,_=build()
 db.execute("""UPDATE dragon_runtime_events SET occurred_at=occurred_at+0.5
  WHERE owner='u' AND run_id='r' AND event_type='worker_receipt'""");db.commit()
 v=verify_receipt_attestation(db,"u","r","source_integrity",authorized=True)
 assert not v.valid and "release/audit time mismatch" in v.reason
