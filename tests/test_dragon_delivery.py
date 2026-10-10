"""Whole delivery journey: reviewed sources -> Hoag -> native project lineage."""
from dataclasses import replace
from pathlib import Path
import sqlite3
import json
import pytest

from skeleton.ai.game_builder.reviewed_knowledge import ReviewedKnowledgeStore, ReviewedDocument, ReviewedNote
from skeleton.ai.game_builder.dragon_almanacs import DragonAlmanacs
from skeleton.ai.game_builder.dragon_delivery import DragonDelivery, design_controls
from skeleton.ai.game_builder.dragon_wisdom_pyramid import DragonWisdomPyramid
from skeleton.ai.game_builder.dragon_wisdom_authority import DragonWisdomAuthority
from skeleton.ai.webcrawler.dragon_game_design import parse_design, starter_design
from skeleton.ai.webcrawler.dragon_native_practice import DragonNativePracticeLab
from skeleton.ai.webcrawler.dragon_practice_lab import DragonPracticeLab, ApprovedLesson
from skeleton.ai.webcrawler.dragon_game_mechanics import Mechanic
from skeleton.ai.webcrawler.dragon_knowledge_promotion import PromotionDecision

NOW = 1791648000


def setup_knowledge(path, owner="alice", now=NOW):
    library = ReviewedKnowledgeStore(path)
    text = "Movement and collision behavior must be measured."
    for name in ("a", "b"):
        document = ReviewedDocument(owner=owner, source_id="source-"+name,
            source_url="https://example.org/"+name, title="Original movement study "+name,
            text=text, observed_at="2026-10-10T00:00:00Z", license_id="design_reference_license",
            allowed_scopes=("design_reference",), reviewer_id="reviewer-"+name, approved=True,
            notes=(ReviewedNote(note_id="note-"+name, mechanic="movement",
                statement="Movement should be tested against measured collision boundaries.",
                start=0, end=8, stance="supports", confidence_ppm=950000,
                dependence_group="publisher-"+name, tags=("movement",)),))
        library.import_document(document, expected_parent_digest=None, authorized=True)
    pyramid = DragonWisdomPyramid(library)
    authority = DragonWisdomAuthority(pyramid, wiki_signing_key=b"w"*32,
                                     approval_signing_key=b"a"*32, issuer="identity-service")
    brief = library.build_brief(owner,"movement",authorized=True,min_independent_groups=2)
    grant = authority.issue_grant(owner,"wiki-person","independent-lab","wiki_reviewer",
        brief.to_payload()["brief_digest"],now=now,expires_at=now+300,identity_verified=True,authorized=True)
    review = authority.review(owner,brief,mechanic="movement",disposition="accepted",
        review_evidence_digest="a"*64,grant=grant,now=now,expires_at=now+3600,
        authorized=True,trusted_worker=True)
    approval = authority.issue_grant(owner,"approver-person","other-lab","memory_approver",
        review["digest"],now=now,expires_at=now+300,identity_verified=True,authorized=True)
    authority.approve(owner,review["digest"],grant=approval,now=now+1,authorized=True,trusted_worker=True)
    return library, DragonDelivery(DragonAlmanacs(library)), review


def design(target="game_boy", seed=1):
    value=starter_design(title="Original Movement Quest",target=target,genre="arcade_score_attack",seed=seed)
    if target not in ("pc_linux","pc_windows","pc_macos","steam_deck"):
        value.update(stages=1,candidates=1,palette="dmg_green")
    return parse_design(value)


def setup_practice(path, owner="alice"):
    db=sqlite3.connect(path)
    parent=DragonPracticeLab(db)
    proof=PromotionDecision("movement-proof",True,.99,"calibrated",None,(),"a"*64)
    parent.offer(ApprovedLesson(owner,"Original movement lesson",proof,"b"*64,
        (Mechanic.MOVEMENT,Mechanic.EXPLORATION),True),now=NOW,authorized=True)
    return db,parent,DragonNativePracticeLab(db,parent)


def test_complete_design_to_native_delivery_survives_restart(tmp_path):
    library,delivery,review=setup_knowledge(tmp_path/"knowledge.sqlite")
    db,parent,native=setup_practice(tmp_path/"practice.sqlite")
    plan=delivery.brief("alice",design(),"movement",now=NOW+2,authorized=True)
    assert plan["ready_for_source_generation"] and len(plan["citations"])==2
    assert plan["independent_groups"]==2
    assert plan["compiler_adapter_available"]
    assert all(c["review_digest"]==review["digest"] for c in plan["citations"])
    attempt=native.generate("alice",target_id="game_boy",style="arcade_score_attack",now=NOW+3,
        authorized=True,consent=True,design=design(),source_context=plan,request_id="request_0123456789")
    raw=native.project("alice",attempt.attempt_id,authorized=True)
    assert "SECTION" in raw["files"]["src/main.asm"]
    assert json.loads(raw["files"]["dragon-game-design.json"])["title"]=="Original Movement Quest"
    assert json.loads(raw["files"]["dragon-knowledge-brief.json"])["plan_digest"]==plan["plan_digest"]
    assert parent.progress("alice",authorized=True).xp==30
    zipped,digest=native.archive("alice",attempt.attempt_id,authorized=True)
    db.close()
    db=sqlite3.connect(tmp_path/"practice.sqlite")
    parent=DragonPracticeLab(db);native=DragonNativePracticeLab(db,parent)
    again=native.generate("alice",target_id="game_boy",style="arcade_score_attack",now=NOW+4,
        authorized=True,consent=True,design=design(),source_context=plan,request_id="request_0123456789")
    assert again==attempt
    assert native.archive("alice",attempt.attempt_id,authorized=True)==(zipped,digest)
    assert len(native.list("alice",authorized=True))==1
    with pytest.raises(LookupError):native.project("bob",attempt.attempt_id,authorized=True)
    library.close();db.close()


def test_brief_rebuild_checks_expiry_revocation_and_target_support(tmp_path):
    library,delivery,review=setup_knowledge(tmp_path/"knowledge.sqlite")
    plan=delivery.brief("alice",design(),"movement",now=NOW+2,authorized=True)
    assert delivery.brief("alice",design(),"movement",now=NOW+20,prepared_at=NOW+2,authorized=True)==plan
    with pytest.raises(ValueError):delivery.brief("alice",design(),"movement",now=NOW+302,prepared_at=NOW+2,authorized=True)
    blocked=delivery.brief("alice",design("xbox_series"),"movement",now=NOW+3,authorized=True)
    assert not blocked["ready_for_source_generation"] and "target_style_emitter_missing" in blocked["blockers"]
    delivery.pyramid.revoke("alice",review["digest"],reason="changed_source",now=NOW+4,authorized=True,trusted_worker=True)
    fresh=delivery.brief("alice",design(),"movement",now=NOW+5,prepared_at=NOW+2,authorized=True)
    assert not fresh["ready_for_source_generation"] and fresh["plan_digest"]!=plan["plan_digest"]
    library.close()


def test_unapproved_sources_never_become_generation_evidence(tmp_path):
    library,delivery,_=setup_knowledge(tmp_path/"knowledge.sqlite")
    result=delivery.search("bob","movement",now=NOW+2,authorized=True)
    assert result["items"]==[]
    assert not delivery.brief("bob",design(),"movement",now=NOW+2,authorized=True)["ready_for_source_generation"]
    assert delivery.search("alice","movement",now=NOW+3601,authorized=True)["items"][0]["approval"]=="source_reviewed_only"
    before=library.db.total_changes
    view=delivery.overview("alice",now=NOW+2,authorized=True)
    assert view["counts"]["reviewed_sources"]==2
    assert view["counts"]["approved_mechanics"]==1
    assert view["counts"]["current_memory_cards"]==0
    assert view["overall_completion_percent"] is None
    assert library.db.total_changes==before
    library.close()


def test_design_parameters_change_real_generated_game(tmp_path):
    library,delivery,_=setup_knowledge(tmp_path/"knowledge.sqlite")
    db,_,native=setup_practice(tmp_path/"practice.sqlite")
    results=[]
    for seed in (1,98765):
        d=design(seed=seed);plan=delivery.brief("alice",d,"movement",now=NOW+2,authorized=True)
        a=native.generate("alice",target_id=d.target,style=d.genre,now=NOW+3,authorized=True,consent=True,
                         design=d,source_context=plan,request_id="request_seed_"+str(seed).zfill(8))
        results.append(native.project("alice",a.attempt_id,authorized=True)["files"]["src/main.asm"])
    assert results[0]!=results[1]
    assert "hero" not in design_controls("game_boy","arcade_score_attack")["effective"]
    assert "hero" in design_controls("pc_linux","arcade_score_attack")["effective"]
    assert "hero" not in design_controls("pc_linux","turn_based_rpg")["effective"]
    library.close();db.close()


def test_delivery_refuses_forged_digest_wrong_owner_and_changed_retry(tmp_path):
    library,delivery,_=setup_knowledge(tmp_path/"knowledge.sqlite")
    db,_,native=setup_practice(tmp_path/"practice.sqlite")
    d=design();plan=delivery.brief("alice",d,"movement",now=NOW+2,authorized=True)
    with pytest.raises(ValueError):delivery.brief("alice",replace(d,digest="f"*64),"movement",now=NOW+2,authorized=True)
    native.generate("alice",target_id=d.target,style=d.genre,now=NOW+3,authorized=True,consent=True,
        design=d,source_context=plan,request_id="request_same_012345")
    second=delivery.brief("alice",design(seed=2),"movement",now=NOW+2,authorized=True)
    with pytest.raises(ValueError,match="retry"):
        native.generate("alice",target_id=d.target,style=d.genre,now=NOW+4,authorized=True,consent=True,
            design=design(seed=2),source_context=second,request_id="request_same_012345")
    with pytest.raises(ValueError,match="owner-bound"):
        native.generate("bob",target_id=d.target,style=d.genre,now=NOW+4,authorized=True,consent=True,
            design=d,source_context=plan,request_id="request_same_012345")
    assert len(native.list("alice",authorized=True))==1
    library.close();db.close()


def test_offline_cli_uses_same_reviewed_brief_without_provider(tmp_path):
    import subprocess,sys
    library,_,_=setup_knowledge(tmp_path/'knowledge.sqlite');library.close()
    d=design()
    from skeleton.ai.webcrawler.dragon_game_design import FIELDS
    spec=tmp_path/'design.json';spec.write_text(json.dumps({k:getattr(d,k) for k in FIELDS}))
    result=subprocess.run([sys.executable,'-m','skeleton.ai.game_builder.dragon_almanac_cli',
        'delivery-brief','--database',str(tmp_path/'knowledge.sqlite'),'--owner','alice',
        '--trusted-local-operator','--now',str(NOW+2),'--query','movement','--design',str(spec)],
        capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stderr
    brief=json.loads(result.stdout)
    assert brief['ready_for_source_generation'] and len(brief['citations'])==2
    assert not brief['training_authorized'] and not brief['release_authorized']
