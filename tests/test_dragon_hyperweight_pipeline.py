"""100-matrix, sandbox, visual, RSS and weekly Dragon regression gates."""
from dataclasses import replace
from datetime import datetime,timezone
from hashlib import sha256
import sqlite3

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from skeleton.ai.game_builder.contracts import canonical_digest,canonical_json
from skeleton.ai.webcrawler.dragon_hundred_matrix_scrutiny import (
    MATRIX_IDS,SignedMatrixFinding,scrutinize_one_hundred)
from skeleton.ai.webcrawler.dragon_weight_tier_sandbox import (
    HoldoutTrial,SealedTierEvaluation,SignedOverlayApproval,
    JeevesWeightOverlay,qualify_tier)
from skeleton.ai.webcrawler.dragon_video_inspiration import digest_video_inspiration
from skeleton.ai.webcrawler.dragon_rss_update_queue import (
    SignedRssSnapshot,DragonRssUpdateQueue)
from skeleton.ai.webcrawler.dragon_weekly_research_export import export_weekly,render_weekly_backlog
from skeleton.ai.webcrawler.dragon_nest_worker_admission import (
    HatchlingWorkerTicket,DragonNestWorkerAdmission)
from skeleton.ai.webcrawler.dragon_frame_custody import CapturedFrame,FrameBatch
from skeleton.ai.webcrawler.dragon_visual_features import VisualFeatureBatch
from skeleton.ai.webcrawler.dragon_temporal_segmentation import FeatureFrame
from skeleton.ai.webcrawler.video_digest import VideoKnowledgeChunk,VideoObservation

def keypair():
    key=Ed25519PrivateKey.generate()
    return key,key.public_key().public_bytes_raw()

def sign(key,obj):
    return key.sign(canonical_json(obj).encode()).hex()

def matrix_bundle():
    key,pub=keypair()
    records=[]
    for matrix_id in MATRIX_IDS:
        f=SignedMatrixFinding(
            matrix_id=matrix_id,owner="studio",knowledge_digest="a"*64,
            evidence_digest="b"*64,
            independent_group_digests=("1"*64,"2"*64),
            reviewer="independent-wiki",key_id="review-key-1",
            issued_at=100,expires_at=1000,verdict="pass",signature_hex="")
        records.append(replace(f,signature_hex=sign(key,f.body())))
    return key,pub,tuple(records)

def test_hundred_matrix_catalog_complete_signed_and_nonpromoting():
    _,pub,records=matrix_bundle()
    assert len(MATRIX_IDS)==100 and len(set(MATRIX_IDS))==100
    report=scrutinize_one_hundred(
        "studio","a"*64,records,public_key=pub,
        trusted_reviewer="independent-wiki",key_id="review-key-1",now=150)
    assert report["shadow_review_proposal_eligible"] is True
    assert report["passed_matrix_count"]==100
    assert len(report["axis_pass_counts"])==10
    assert all(v==10 for v in report["axis_pass_counts"].values())
    assert not report["normal_weight_promotion_authorized"]
    assert not report["hyperweight_promotion_authorized"]
    assert not report["neural_training_authorized"]
    assert len(report["report_digest"])==64

def test_hundred_matrix_missing_conflicted_expired_or_bad_signature_stays_closed():
    key,pub,records=matrix_bundle()
    kwargs=dict(public_key=pub,trusted_reviewer="independent-wiki",
                key_id="review-key-1",now=150)
    part=scrutinize_one_hundred("studio","a"*64,records[:-1],**kwargs)
    assert part["passed_matrix_count"]==99
    assert len(part["missing_matrix_ids"])==1
    assert not part["shadow_review_proposal_eligible"]
    failed=replace(records[0],verdict="conflict",signature_hex="")
    failed=replace(failed,signature_hex=sign(key,failed.body()))
    no=scrutinize_one_hundred("studio","a"*64,(failed,)+records[1:],**kwargs)
    assert not no["shadow_review_proposal_eligible"]
    assert failed.matrix_id in no["failed_matrix_ids"]
    with pytest.raises(ValueError,match="duplicate"):
        scrutinize_one_hundred("studio","a"*64,records+(records[0],),**kwargs)
    with pytest.raises(PermissionError,match="signature"):
        scrutinize_one_hundred(
            "studio","a"*64,(replace(records[0],evidence_digest="f"*64),)+records[1:],**kwargs)
    with pytest.raises(PermissionError,match="identity"):
        scrutinize_one_hundred(
            "other","a"*64,records,**kwargs)
    expired=scrutinize_one_hundred(
        "studio","a"*64,records,**{**kwargs,"now":1000})
    assert not expired["shadow_review_proposal_eligible"]

def make_eval(key,candidate,*,tier="shadow_to_weight",prior=None):
    trials=tuple(HoldoutTrial(
        case_id="case-"+str(i),task_family=("platform","npc","physics")[i%3],
        source_group=("publisher-1","publisher-2","publisher-3")[i%3],
        expected_digest="d"*64,
        baseline_correct=i<7,candidate_correct=i<9,
        baseline_latency_ms=50,candidate_latency_ms=45,
        baseline_peak_kib=100,candidate_peak_kib=95)
        for i in range(12))
    e=SealedTierEvaluation(
        owner="studio",candidate_digest=candidate,prior_digest=prior or "0"*64,
        matrix_report_digest="a"*64,tier=tier,
        suite_digest=canonical_digest([vars(t) for t in trials]),
        trials=trials,holdout_excluded_from_training=True,
        evaluator="independent-mirror",key_id="eval-1",
        issued_at=100,expires_at=900,signature_hex="")
    return replace(e,signature_hex=sign(key,e.body()))

def test_two_signed_sandboxes_and_jeeves_fast_index_with_rollback():
    eval_key,eval_pub=keypair()
    op_key,op_pub=keypair()
    entries=(("f"*64,("gameboy","sprite")),("e"*64,("physics","editor")))
    digest=canonical_digest([[identity,list(words)] for identity,words in entries])
    signed=make_eval(eval_key,digest)
    verdict=qualify_tier(
        signed,evaluator_public_key=eval_pub,evaluator="independent-mirror",
        key_id="eval-1",now=150)
    assert verdict["promotion_review_eligible"]
    assert verdict["newly_correct"]==2 and verdict["regressions"]==0
    assert not verdict["neural_training_authorized"]
    approval=SignedOverlayApproval(
        owner="studio",tier="shadow_to_weight",candidate_digest=digest,
        verdict_digest=verdict["verdict_digest"],operator="operator",
        key_id="operator-1",expires_at=800,signature_hex="")
    approval=replace(approval,signature_hex=sign(op_key,approval.body()))
    router=JeevesWeightOverlay("studio")
    args=dict(entries=entries,verdict=verdict,approval=approval,evaluation=signed,
        evaluator_public_key=eval_pub,evaluator="independent-mirror",
        evaluator_key_id="eval-1",operator_public_key=op_pub,
        operator="operator",key_id="operator-1",now=150)
    with pytest.raises(PermissionError,match="signature"):
        router.activate(expected_generation=0,**{
            **args,"evaluation":replace(signed,holdout_excluded_from_training=False)})
    status=router.activate(expected_generation=0,**args)
    assert status["generation"]==1 and status["rollback_available"]
    assert not status["neural_weights_changed"]
    assert router.route("gameboy sprite")["bookmarked_retrieval_ids"]==["f"*64]
    with pytest.raises(PermissionError,match="stale"):
        router.activate(expected_generation=0,**args)
    assert router.rollback(expected_generation=1,authorized=True)==2
    assert router.route("gameboy")["bookmarked_retrieval_ids"]==[]
    with pytest.raises(PermissionError,match="rollback"):
        router.rollback(expected_generation=2,authorized=False)

def test_sandbox_requires_real_holdout_improvement_and_no_regressions():
    key,pub=keypair()
    sig=make_eval(key,"e"*64)
    trials=list(sig.trials)
    trials[0]=replace(trials[0],candidate_correct=False)
    modified=replace(sig,trials=tuple(trials),
        suite_digest=canonical_digest([vars(t) for t in trials]),signature_hex="")
    signed=replace(modified,signature_hex=sign(key,modified.body()))
    report=qualify_tier(
        signed,evaluator_public_key=pub,evaluator="independent-mirror",
        key_id="eval-1",now=150)
    assert not report["promotion_review_eligible"]
    assert report["regressions"]==1
    with pytest.raises(PermissionError):
        qualify_tier(replace(sig,holdout_excluded_from_training=False),
            evaluator_public_key=pub,evaluator="independent-mirror",
            key_id="eval-1",now=150)

def visual_packet():
    source_url="https://video.example/watch/demo"
    frame=CapturedFrame("frame-1","studio","job","b"*64,
        "consent","scope",150,"c"*64,3000,"local-frame-1")
    frames=FrameBatch((frame,),"a"*64)
    features=VisualFeatureBatch(
        (FeatureFrame(150,(0.4,0.6),"frame-1"),),"d"*64,"a"*64)
    chunks=(VideoKnowledgeChunk("chunk-1",100,400,
        "Sprite editor and tilemap tool demo.",("transcript",),
        ("line-1",),source_url),)
    observations=(VideoObservation(100,400,"frame_description",
        "Sprite editor visible in tool panel.",0.9,"frame-1"),)
    return source_url,frames,features,chunks,observations

def test_video_inspiration_creates_timecoded_frame_bookmarks_not_weights():
    source_url,frames,features,chunks,obs=visual_packet()
    packet=digest_video_inspiration(
        "source-"+"1"*64,source_url,chunks,features,obs,frames,
        consent_verified=True,authorized=True)
    assert packet["bookmarked_clips"]==1
    assert packet["notes"][0]["frame_digest"]=="c"*64
    assert "editor" in packet["tool_editor_leads"]
    assert packet["independent_visual_fact_review_required"]
    assert not packet["normal_weight_promotion_authorized"]
    assert not packet["hyperweight_promotion_authorized"]
    with pytest.raises(PermissionError):
        digest_video_inspiration(
            "source-"+"1"*64,source_url,chunks,features,obs,frames,
            consent_verified=False,authorized=True)
    with pytest.raises(ValueError,match="frame"):
        digest_video_inspiration(
            "source-"+"1"*64,source_url,chunks,features,
            (replace(obs[0],source_id="forged"),),frames,
            consent_verified=True,authorized=True)

def rss_xml():
    return b'<rss version="2.0"><channel><item><title>New game physics guide</title><link>https://updates.example/game-physics</link><guid>update-1</guid><pubDate>Mon, 12 Oct 2026 08:00:00 GMT</pubDate></item></channel></rss>'

def rss_snapshot(key,xml):
    obj=SignedRssSnapshot("studio","source-"+"1"*64,
        "https://updates.example/feed.xml",sha256(xml).hexdigest(),
        100,180,"rss-independent","rss-1","f"*64,"")
    return replace(obj,signature_hex=sign(key,obj.body()))

def test_rss_idle_only_signed_queue_deduplicates_and_weekly_exports(tmp_path):
    key,pub=keypair()
    xml=rss_xml()
    ticket=HatchlingWorkerTicket(
        "studio","updates","source-"+"1"*64,
        "https://updates.example/feed.xml",
        "hatchling:updates-1","d"*64,
        "2026-10-12T00:00:00Z","2026-10-12T00:00:30Z")
    admission=object.__new__(DragonNestWorkerAdmission)
    checks=[]
    admission.authorize_chunk=lambda *args,**kw:(checks.append(kw) or True)
    with sqlite3.connect(":memory:") as db:
        queue=DragonRssUpdateQueue(db)
        kwargs=dict(reviewer_public_key=pub,trusted_issuer="rss-independent",
            key_id="rss-1",now=150,admission_kwargs={},authorized=True)
        first=queue.ingest(ticket,admission,xml,rss_snapshot(key,xml),**kwargs)
        assert first["new_unverified_leads"]==1
        assert len(checks)==2
        second=queue.ingest(ticket,admission,xml,rss_snapshot(key,xml),**kwargs)
        assert second["idempotent"] and second["new_unverified_leads"]==0
        report=queue.pending("studio",authorized=True)
        assert report["count"]==1
        assert queue.pending("different-tenant",authorized=True)["entries"]==[]
        assert not report["training_authorized"]
        md,index=render_weekly_backlog(
            "studio",datetime(2026,10,12,tzinfo=timezone.utc),
            visual=(),rss=(report,),matrix_reports=())
        assert "New game physics guide" in md
        assert index["item_count"]==1
        dest=export_weekly(
            tmp_path.resolve(),"studio",
            datetime(2026,10,12,tzinfo=timezone.utc),
            visual=(),rss=(report,),matrix_reports=())
        assert (tmp_path/"2026-W42"/"dragon-upgrade-backlog.md").is_file()
        assert (tmp_path/"2026-W42"/"dragon-bookmarks.json").is_file()
        assert dest["items"]==1 and not dest["model_weights_changed"]
        with pytest.raises(PermissionError):
            queue.ingest(ticket,admission,xml,replace(
                rss_snapshot(key,xml),rights_receipt_digest="a"*64),**kwargs)
        db.execute("UPDATE dragon_rss_updates_v1 SET payload='{}'")
        with pytest.raises(ValueError,match="tamper"):
            queue.pending("studio",authorized=True)
