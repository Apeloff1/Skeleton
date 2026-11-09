"""Canonical Dragon article captures: digest-chained text revisions and review packets."""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json

import pytest

from skeleton.ai.game_builder.contracts import canonical_digest, canonical_json
from skeleton.ai.game_builder.dragon_almanacs import DragonAlmanacs
from skeleton.ai.game_builder.dragon_almanac_sequence import SequentialAlmanacWorker
from skeleton.ai.game_builder.dragon_technical_source_atlas import CATALOG
from skeleton.ai.game_builder.dragon_technical_source_captures import DragonSourceCaptures
from skeleton.ai.game_builder.reviewed_knowledge import ReviewedKnowledgeStore
from skeleton.ai.webcrawler.core import FetchResponse, extract_document

OWNER="studio-capture"
T0=1791800000


@pytest.fixture
def setup(tmp_path):
    with ReviewedKnowledgeStore(tmp_path/"capture.sqlite") as library:
        a=DragonAlmanacs(library)
        source=next(item for item in CATALOG if item["slug"]=="pandocs")
        url=source["url"]
        sid="source-"+sha256(url.encode()).hexdigest()
        body={"source_id":sid,"url":url,"host":source["url"].split("/")[2],
              "kind":"web_candidate","discoveries":[],
              "availability":"not_checked","rights":"not_assessed",
              "independence":"not_assessed","training_authorized":False,
              "provisional_discovery":True}
        library.db.execute(
            "INSERT INTO dragon_almanac_sources VALUES(?,?,?,?)",
            (OWNER,sid,canonical_json(body),canonical_digest(body))
        )
        worker=SequentialAlmanacWorker(a)
        worker.seed(OWNER,authorized=True)
        captures=DragonSourceCaptures(a)
        yield library,a,worker,captures,sid,url


def policy_worker(setup,*,policy_expires=T0+120):
    _,_,worker,_,sid,url=setup
    claim=worker.claim(OWNER,now=T0,authorized=True,trusted_worker=True,ttl=120)
    assert claim.source_id==sid and claim.stage=="policy" and claim.url==url
    output="a"*64
    evidence={"url":claim.url,"input_digest":claim.input_digest,
              "output_digest":output,"robots_permitted":True,
              "terms_permitted":True,"reference_use_permitted":True,
              "ssrf_checked":True,"expires_at":policy_expires}
    worker.finish(claim,now=T0+1,output_digest=output,evidence=evidence,
                  authorized=True,trusted_worker=True)


def doc(url,at=T0+2,text=None):
    text=text or ("Gameboy hardware uses explicit memory and sprite registers. "
                  "Precise frame timing and memory layout matter for a homebrew game. "
                  "The original documentation identifies register addresses.")
    result=extract_document(FetchResponse(
        url,200,{"content-type":"text/plain"},text.encode(),float(at)
    ),url)
    assert result is not None
    return result


def record(setup,*,text=None,at=T0+2,key="capture-1",authorized=True,stored=True):
    _,_,_,captures,sid,url=setup
    return captures.record(OWNER,sid,doc(url,at,text),capture_id=key,
        observed_at=at,authorized=authorized,trusted_worker=True,
        reference_storage_permitted=stored)


def test_no_capture_before_separate_current_source_policy(setup):
    _,_,_,captures,sid,url=setup
    with pytest.raises(PermissionError,match="policy"):
        record(setup)
    assert captures.history(OWNER,sid,authorized=True)==()
    policy_worker(setup)
    first=record(setup)
    assert first["change"]=="new"
    assert first["sequence"]==1
    assert first["independent_review_required"]
    assert not first["knowledge_approved"] and not first["training_authorized"]
    assert first["evidence_candidates"]>0
    assert first["improvements"][0].startswith("(")


def test_capture_quotes_are_verbatim_and_review_not_weight_promotion(setup):
    policy_worker(setup)
    created=record(setup)
    _,_,_,captures,sid,_=setup
    brief=captures.review_packet(OWNER,sid,authorized=True,include_text=True)
    assert brief["capture_digest"]==created["capture_digest"]
    assert brief["source_review_needed"]
    assert brief["rights_recheck_required"]
    assert not brief["reviewed_knowledge_inserted"]
    assert not brief["training_authorized"]
    assert brief["candidate_quotes"]
    for quote in brief["candidate_quotes"]:
        assert brief["raw_captured_text"][quote["start"]:quote["end"]]==quote["exact_quote"]
        assert quote["review_required"]
        assert quote["end"]-quote["start"]<=240
    assert captures.review_packet(OWNER,sid,authorized=True)["raw_captured_text"] is None


def test_changed_and_unchanged_versions_with_immutable_chain(setup):
    policy_worker(setup)
    one=record(setup)
    same=record(setup,key="capture-2",at=T0+3)
    assert same["change"]=="unchanged"
    assert same["evidence_candidates"]==0
    assert same["sequence"]==2
    changed=record(setup,key="capture-3",at=T0+4,text=(
        "Gameboy hardware has a newly revised frame scheduler description. "
        "There are distinct register timings and animation techniques."
    ))
    assert changed["change"]=="changed"
    assert changed["sequence"]==3
    assert changed["capture_digest"]!=one["capture_digest"]
    _,_,_,captures,sid,_=setup
    history=captures.history(OWNER,sid,authorized=True)
    assert [x["change"] for x in history]==["new","unchanged","changed"]
    assert captures.review_packet(OWNER,sid,authorized=True)["source_review_needed"]
    assert captures.review_packet(OWNER,sid,authorized=True)["previous_capture_digest"]==same["capture_digest"]


def test_unchanged_latest_version_does_not_reissue_knowledge(setup):
    policy_worker(setup)
    record(setup)
    record(setup,key="capture-2",at=T0+3)
    _,_,_,captures,sid,_=setup
    brief=captures.review_packet(OWNER,sid,authorized=True)
    assert brief["change"]=="unchanged"
    assert brief["candidate_quotes"]==[]
    assert not brief["source_review_needed"]
    assert brief["reviewed_knowledge_inserted"] is False


def test_idempotency_retry_and_conflicting_capture_id(setup):
    policy_worker(setup)
    first=record(setup)
    second=record(setup)
    assert second["replayed"] is True
    assert first["capture_digest"]==second["capture_digest"]
    with pytest.raises(ValueError,match="conflicting"):
        record(setup,key="capture-1",at=T0+3)
    _,_,_,captures,sid,_=setup
    assert len(captures.history(OWNER,sid,authorized=True))==1


def test_stale_policy_expiration_and_denied_storage_or_owner(setup):
    policy_worker(setup,policy_expires=T0+5)
    with pytest.raises(PermissionError):
        record(setup,at=T0+6)
    with pytest.raises(PermissionError,match="retention"):
        record(setup,stored=False)
    with pytest.raises(PermissionError,match="owner"):
        record(setup,authorized=False)


def test_tampered_capture_history_or_head_fails_closed(setup):
    policy_worker(setup)
    record(setup)
    library,_,_,captures,sid,_=setup
    library.db.execute(
        "UPDATE dragon_technical_captures_v1 SET body='{}' "
        "WHERE owner=? AND source=?",(OWNER,sid))
    with pytest.raises(ValueError,match="integrity"):
        captures.history(OWNER,sid,authorized=True)
    library.db.execute("DELETE FROM dragon_technical_captures_v1 "
                       "WHERE owner=? AND source=?",(OWNER,sid))
    with pytest.raises(ValueError,match="head"):
        captures.history(OWNER,sid,authorized=True)


def test_registry_tenant_isolation_and_forged_crawler_document(setup):
    policy_worker(setup)
    _,_,_,captures,sid,url=setup
    with pytest.raises(ValueError,match="unregistered"):
        captures.history("different-tenant",sid,authorized=True)
    with pytest.raises(ValueError,match="unregistered"):
        captures.record("different-tenant",sid,doc(url),capture_id="other",
                        observed_at=T0+2,authorized=True,
                        trusted_worker=True,reference_storage_permitted=True)
    corrupted=replace(doc(url),text="altered but hash was not recomputed")
    with pytest.raises(ValueError,match="hash"):
        captures.record(OWNER,sid,corrupted,capture_id="forged",
                        observed_at=T0+2,authorized=True,trusted_worker=True,
                        reference_storage_permitted=True)


def test_noncanonical_fetch_source_url_and_oversize_refused(setup):
    policy_worker(setup)
    _,_,_,captures,sid,url=setup
    modified=replace(doc(url),fetched_url="https://other.example.org/path")
    with pytest.raises(ValueError,match="non-redirected"):
        captures.record(OWNER,sid,modified,capture_id="redirect",
                        observed_at=T0+2,authorized=True,trusted_worker=True,
                        reference_storage_permitted=True)
    with pytest.raises(ValueError,match="bounded nonempty"):
        record(setup,text="x"*241000)


def test_capture_event_is_source_specific_not_released_to_canonical_knowledge(setup):
    policy_worker(setup)
    record(setup)
    library,_,_,captures,sid,_=setup
    assert library._rows(OWNER)==[]
    assert captures.history(OWNER,sid,authorized=True)[0]["training_authorized"] is False



def test_staged_capture_advances_existing_fetch_and_extract_receipts(setup):
    policy_worker(setup)
    library,_,worker,captures,sid,url=setup
    document=doc(url,T0+2)
    saved=captures.record(
        OWNER,sid,document,capture_id="real-fetch",
        observed_at=T0+2,response_body_bytes=len(document.text.encode()),
        authorized=True,trusted_worker=True,reference_storage_permitted=True)
    claim=worker.claim(OWNER,now=T0+4,authorized=True,trusted_worker=True)
    assert claim.stage=="fetch"
    first=captures.complete_fetch_stage(
        claim,capture_digest=saved["capture_digest"],now=T0+5,
        authorized=True,trusted_worker=True)
    assert first["next_stage"]=="extract"
    claim=worker.claim(OWNER,now=T0+6,authorized=True,trusted_worker=True)
    assert claim.stage=="extract"
    second=captures.complete_extract_stage(
        claim,capture_digest=saved["capture_digest"],now=T0+7,
        authorized=True,trusted_worker=True)
    assert second["next_stage"]=="analyze"
    assert second["candidate_quotes"]>0
    state=library.db.execute(
        "SELECT stage,state FROM dragon_almanac_jobs "
        "WHERE owner=? AND source=?",(OWNER,sid)).fetchone()
    assert state==(3,"pending")
    assert library._rows(OWNER)==[]


def test_undocumented_response_bytes_cannot_forge_fetch_receipt(setup):
    policy_worker(setup)
    _,_,worker,captures,_,_=setup
    event=record(setup)
    claim=worker.claim(OWNER,now=T0+4,authorized=True,trusted_worker=True)
    with pytest.raises(ValueError,match="HTTP response"):
        captures.complete_fetch_stage(
            claim,capture_digest=event["capture_digest"],now=T0+5,
            authorized=True,trusted_worker=True)
    with pytest.raises(ValueError,match="non-stale"):
        captures.complete_fetch_stage(
            claim,capture_digest="b"*64,now=T0+5,
            authorized=True,trusted_worker=True)
