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
