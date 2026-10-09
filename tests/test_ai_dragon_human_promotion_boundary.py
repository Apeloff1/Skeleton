"""Human-review and final-promotion boundary regressions."""
import sqlite3,pytest,json
from hashlib import sha256
from dataclasses import replace
from skeleton.ai.webcrawler.dragon_analysis_chains import AnalysisLayer,LayerReceipt
from skeleton.ai.webcrawler.dragon_analysis_execution import LayerDispatch
from skeleton.ai.webcrawler.dragon_adversarial_review_worker import AdversarialReviewOutput
from skeleton.ai.webcrawler.dragon_human_review import DragonHumanReviewLedger,ReviewerPrincipal
from skeleton.ai.webcrawler.dragon_knowledge_normalization_worker import NormalizedKnowledge
from skeleton.ai.webcrawler.dragon_memory_promotion_worker import execute_memory_promotion,execute_memory_promotion_from_ledger


def principal(reviewer_id):
    return ReviewerPrincipal(reviewer_id,"test-auth","subject:"+reviewer_id,9,"f"*64)

def verify_principal(value):
    return value.issuer=="test-auth" and value.credential_fingerprint=="f"*64


def setup():
    identity=["h","v1","supported",.95,"empirically_calibrated_probability","d"*64,"e"*64]
    kid=sha256(json.dumps(identity,separators=(",",":")).encode()).hexdigest()
    k=NormalizedKnowledge(kid,"h","v1","supported",.95,
      "empirically_calibrated_probability","d"*64,"e"*64,"resolved_support")
    ar=LayerReceipt(AnalysisLayer.ADVERSARIAL_REVIEW,("a"*64,),"b"*64,2,True,False)
    review=AdversarialReviewOutput(ar,(),(k.knowledge_id,))
    ledger=DragonHumanReviewLedger(sqlite3.connect(":memory:"))
    decision,hr=ledger.review("u",review,reviewer_id="human-1",approved=True,
      reviewed_at=10,rationale="evidence reviewed",authorized=True,records=(k,),
      reviewer_principal=principal("human-1"),principal_verifier=verify_principal)
    dispatch=LayerDispatch(AnalysisLayer.MEMORY_PROMOTION,(hr.output_fingerprint,),"promote","v1")
    return k,review,ledger,decision,hr,dispatch


def test_exact_approved_survivor_promotes():
    k,_,_,decision,hr,d=setup()
    out=execute_memory_promotion(d,(k,),human_receipt=hr,human_decision=decision,
      surviving_knowledge_ids=(k.knowledge_id,),authorized=True)
    assert out.receipt.passed and out.promoted[0].human_review_id==decision.review_id


def test_changed_survivor_set_invalidates_approval():
    k,_,_,decision,hr,d=setup()
    with pytest.raises(PermissionError,match="survivor set changed"):
        execute_memory_promotion(d,(k,),human_receipt=hr,human_decision=decision,
          surviving_knowledge_ids=(),authorized=True)


def test_failed_adversarial_review_cannot_be_approved():
    k,review,ledger,_,_,_=setup()
    failed=replace(review,receipt=replace(review.receipt,passed=False))
    with pytest.raises(PermissionError,match="cannot be approved"):
        ledger.review("u",failed,reviewer_id="human-1",approved=True,
          reviewed_at=11,rationale="no",authorized=True,records=(k,))


def test_rejected_human_review_cannot_promote():
    k,review,ledger,_,_,_=setup()
    decision,hr=ledger.review("u",review,reviewer_id="human-2",approved=False,
      reviewed_at=12,rationale="reject",authorized=True,records=(k,),
      reviewer_principal=principal("human-2"),principal_verifier=verify_principal)
    d=LayerDispatch(AnalysisLayer.MEMORY_PROMOTION,(hr.output_fingerprint,),"promote","v1")
    with pytest.raises(PermissionError,match="human approval"):
        execute_memory_promotion(d,(k,),human_receipt=hr,human_decision=decision,
          surviving_knowledge_ids=(k.knowledge_id,),authorized=True)


def test_same_id_content_substitution_after_approval_is_rejected():
    k,_,_,decision,hr,d=setup()
    forged=replace(k,probability=.7)
    with pytest.raises(ValueError,match="identity is not canonical"):
        execute_memory_promotion(d,(forged,),human_receipt=hr,human_decision=decision,
          surviving_knowledge_ids=(k.knowledge_id,),authorized=True)


def test_recomputed_id_still_cannot_change_approved_record():
    k,_,_,decision,hr,d=setup()
    identity=[k.hypothesis_id,k.ontology_version,k.verdict,.96,k.probability_semantics,k.calibration_artifact_fingerprint,k.evidence_fingerprint]
    changed=replace(k,knowledge_id=sha256(json.dumps(identity,separators=(",",":")).encode()).hexdigest(),probability=.96)
    with pytest.raises(PermissionError,match="survivor set changed"):
        execute_memory_promotion(d,(changed,),human_receipt=hr,human_decision=decision,
          surviving_knowledge_ids=(changed.knowledge_id,),authorized=True)


def test_current_manifest_bound_review_round_trips_from_ledger():
 k,_,ledger,decision,_,_=setup()
 loaded=ledger.get("u",decision.review_id,authorized=True)
 assert loaded==decision and loaded.survivor_manifest

def test_legacy_review_schema_migrates_but_legacy_approval_stays_untrusted():
 db=sqlite3.connect(":memory:")
 db.execute("""CREATE TABLE dragon_human_reviews(
  owner TEXT NOT NULL,review_id TEXT NOT NULL,reviewer_id TEXT NOT NULL,
  adversarial_fingerprint TEXT NOT NULL,survivor_digest TEXT NOT NULL,
  approved INTEGER NOT NULL,reviewed_at REAL NOT NULL,rationale TEXT NOT NULL,
  PRIMARY KEY(owner,review_id))""")
 db.execute("INSERT INTO dragon_human_reviews VALUES(?,?,?,?,?,?,?,?)",
  ("u","r","human","a"*64,"b"*64,1,1.0,"legacy approval"))
 db.commit()
 ledger=DragonHumanReviewLedger(db)
 columns={row[1] for row in db.execute("PRAGMA table_info(dragon_human_reviews)")}
 assert "survivor_manifest" in columns
 with pytest.raises(PermissionError,match="legacy human review"):
  ledger.get("u","r",authorized=True)


def test_review_requires_verified_reviewer_principal():
 k,review,ledger,_,_,_=setup()
 with pytest.raises(PermissionError,match="verified reviewer principal"):
  ledger.review("u",review,reviewer_id="human-3",approved=True,reviewed_at=13,
   rationale="approve",authorized=True,records=(k,))

def test_reviewer_principal_must_match_declared_reviewer():
 k,review,ledger,_,_,_=setup()
 with pytest.raises(PermissionError,match="identity mismatch"):
  ledger.review("u",review,reviewer_id="human-3",approved=True,reviewed_at=13,
   rationale="approve",authorized=True,records=(k,),
   reviewer_principal=principal("human-other"),principal_verifier=verify_principal)

def test_host_reviewer_verifier_can_reject_principal():
 k,review,ledger,_,_,_=setup()
 with pytest.raises(PermissionError,match="verification failed"):
  ledger.review("u",review,reviewer_id="human-3",approved=True,reviewed_at=13,
   rationale="approve",authorized=True,records=(k,),
   reviewer_principal=principal("human-3"),principal_verifier=lambda _:False)

def test_promotion_rejects_decision_without_verified_principal_fingerprint():
 k,_,_,decision,hr,d=setup()
 forged=replace(decision,reviewer_principal_fingerprint="")
 with pytest.raises(PermissionError,match="verified reviewer principal"):
  execute_memory_promotion(d,(k,),human_receipt=hr,human_decision=forged,
   surviving_knowledge_ids=(k.knowledge_id,),authorized=True)


def test_durable_promotion_reloads_exact_review_from_ledger():
 k,_,ledger,decision,hr,d=setup()
 out=execute_memory_promotion_from_ledger(d,(k,),human_receipt=hr,
  review_ledger=ledger,owner="u",surviving_knowledge_ids=(k.knowledge_id,),authorized=True)
 assert out.promoted[0].human_review_id==decision.review_id

def test_durable_promotion_rejects_unpersisted_approval_receipt():
 k,_,ledger,decision,hr,d=setup()
 forged=replace(hr,output_fingerprint="9"*64)
 forged_dispatch=replace(d,input_fingerprints=(forged.output_fingerprint,))
 with pytest.raises(KeyError,match="human review not found"):
  execute_memory_promotion_from_ledger(forged_dispatch,(k,),human_receipt=forged,
   review_ledger=ledger,owner="u",surviving_knowledge_ids=(k.knowledge_id,),authorized=True)
