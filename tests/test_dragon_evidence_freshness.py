"""Dragon end-to-end freshness fences: signed research, vault and canary.

These test fixtures use independent private keys only in-process. Production
must provision signer secrets separately from the Dragon/Jeeves process.
"""
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock, patch
import sqlite3

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from skeleton.ai.game_builder.contracts import canonical_json
from skeleton.ai.webcrawler.dragon_evidence_freshness_ledger import (
    SignedKnowledgeFreshness, DragonKnowledgeFreshnessLedger)
from skeleton.ai.webcrawler.dragon_jeeves_freshness_guard import JeevesFreshnessGuard
from skeleton.ai.webcrawler.dragon_weight_deployment_vault import DragonDurableWeightVault
from skeleton.ai.webcrawler.dragon_weight_canary import DragonWeightCanary

OWNER="studio"
KEY=b"operator-owned-freshness-HMAC-secret-32-bytes"
KNOW="a"*64
SOURCES="b"*64
INDEX="c"*64
CONTROL="d"*64


def signer():
    private=Ed25519PrivateKey.generate()
    return private,private.public_key().public_bytes_raw()


def signed(private, *, knowledge=KNOW, sources=SOURCES, index=INDEX,
           status="fresh", reason="independent_review", reviewed=100,
           expires=500, owner=OWNER):
    item=SignedKnowledgeFreshness(
        owner,knowledge,sources,index,status,reason,
        "independent-wiki-reviewer","review-key-1",reviewed,expires,"")
    return replace(item,signature_hex=private.sign(
        canonical_json(item.body()).encode()).hex())


def ledger(db,public,owner=OWNER):
    return DragonKnowledgeFreshnessLedger(
        db,owner=owner,signing_key=KEY,reviewer_public_key=public,
        reviewer="independent-wiki-reviewer",key_id="review-key-1")


def test_freshness_requires_external_signature_and_exact_source_index():
    private,pub=signer()
    with sqlite3.connect(":memory:") as db:
        l=ledger(db,pub)
        assert l.state(KNOW,now=150,index_digest=INDEX,
                       source_set_digest=SOURCES)["state"]=="unreviewed"
        receipt=signed(private)
        assert l.record(receipt,now=150,expected_revision=0,authorized=True)[
            "freshness_status"]=="fresh"
        state=l.require_current(KNOW,now=150,index_digest=INDEX,
                                source_set_digest=SOURCES)
        assert state["serve_permitted"] and state["revision"]==1
        assert state["head_mac"]!="0"*64
        assert not state["weights_modified"]
        for index,sources in ((CONTROL,SOURCES),(INDEX,"e"*64)):
            with pytest.raises(PermissionError,match="wrong_source_or_index"):
                l.require_current(KNOW,now=150,index_digest=index,
                                  source_set_digest=sources)
        with pytest.raises(PermissionError,match="expired_or_future"):
            l.require_current(KNOW,now=500,index_digest=INDEX,
                              source_set_digest=SOURCES)
        with pytest.raises(PermissionError,match="stale knowledge"):
            l.record(receipt,now=150,expected_revision=0,authorized=True)
        with pytest.raises(PermissionError,match="operator-side"):
            l.record(receipt,now=150,expected_revision=1,authorized=False)


def test_freshness_change_requires_new_source_set_and_revocation_is_terminal():
    key,pub=signer()
    with sqlite3.connect(":memory:") as db:
        l=ledger(db,pub)
        l.record(signed(key),now=150,expected_revision=0,authorized=True)
        stale=signed(key,status="stale",reason="source_changed",reviewed=151)
        l.record(stale,now=151,expected_revision=1,authorized=True)
        with pytest.raises(PermissionError,match="stale"):
            l.require_current(KNOW,now=151,index_digest=INDEX,
                              source_set_digest=SOURCES)
        unchanged=signed(key,reviewed=152)
        with pytest.raises(PermissionError,match="unchanged stale"):
            l.record(unchanged,now=152,expected_revision=2,authorized=True)
        fresh=signed(key,reviewed=153,sources="e"*64)
        l.record(fresh,now=153,expected_revision=2,authorized=True)
        assert l.require_current(KNOW,now=153,index_digest=INDEX,
                                 source_set_digest="e"*64)["revision"]==3
        revoked=signed(key,reviewed=154,sources="e"*64,
                       status="revoked",reason="rights_revoked")
        l.record(revoked,now=154,expected_revision=3,authorized=True)
        with pytest.raises(PermissionError,match="revoked"):
            l.require_current(KNOW,now=155,index_digest=INDEX,
                              source_set_digest="e"*64)
        with pytest.raises(PermissionError,match="revoked knowledge"):
            l.record(signed(key,reviewed=156,sources="f"*64),
                     now=156,expected_revision=4,authorized=True)


def test_freshness_denies_forgery_cross_owner_and_invalid_policy():
    private,pub=signer()
    stranger,other_pub=signer()
    with sqlite3.connect(":memory:") as db:
        l=ledger(db,pub)
        with pytest.raises(PermissionError,match="signature"):
            l.record(signed(stranger),now=150,expected_revision=0,authorized=True)
        with pytest.raises(PermissionError,match="policy"):
            l.record(signed(private,owner="other"),now=150,
                     expected_revision=0,authorized=True)
        with pytest.raises(PermissionError,match="policy"):
            l.record(signed(private,status="fresh",reason="source_changed"),
                     now=150,expected_revision=0,authorized=True)
        with pytest.raises(PermissionError,match="future"):
            l.record(signed(private,reviewed=200),now=150,
                     expected_revision=0,authorized=True)
        assert l.state(KNOW,now=150,index_digest=INDEX,
                       source_set_digest=SOURCES)["revision"]==0


def test_freshness_full_replay_detects_payload_corruption_and_truncation():
    private,pub=signer()
    with sqlite3.connect(":memory:") as db:
        first=ledger(db,pub)
        first.record(signed(private),now=150,expected_revision=0,authorized=True)
        restarted=ledger(db,pub)
        assert restarted.require_current(KNOW,now=150,index_digest=INDEX,
                                        source_set_digest=SOURCES)["revision"]==1
        db.execute(
            "UPDATE dragon_knowledge_freshness_v1 SET payload='{}' "
            "WHERE owner=? AND knowledge_digest=?",(OWNER,KNOW))
        with pytest.raises(ValueError,match="corruption"):
            restarted.state(KNOW,now=150,index_digest=INDEX,
                            source_set_digest=SOURCES)
    with sqlite3.connect(":memory:") as db:
        l=ledger(db,pub)
        l.record(signed(private),now=150,expected_revision=0,authorized=True)
        db.execute(
            "DELETE FROM dragon_knowledge_freshness_v1 WHERE owner=?",
            (OWNER,))
        with pytest.raises(ValueError,match="truncated"):
            l.state(KNOW,now=150,index_digest=INDEX,
                    source_set_digest=SOURCES)


def mocked_vault(db):
    vault=DragonDurableWeightVault(
        db,owner=OWNER,signing_key=b"operator-owned-routing-secret-32bytes-minimum")
    state={"owner":OWNER,"generation":2,"head_digest":"f"*64,
           "index_digest":INDEX,"history_verified":True,
           "neural_weights_changed":False}
    return vault,state


def test_guarded_jeeves_route_serves_only_fresh_signed_index():
    private,pub=signer()
    with sqlite3.connect(":memory:") as db:
        l=ledger(db,pub)
        vault,state=mocked_vault(db)
        l.record(signed(private),now=150,expected_revision=0,authorized=True)
        route_result={"index_digest":INDEX,
                      "bookmarked_retrieval_ids":["e"*64],
                      "read_only":True,"neural_weights_changed":False}
        guard=JeevesFreshnessGuard(vault,l)
        with patch.object(vault,"audit",return_value=state),patch.object(
            vault,"route",return_value=route_result) as route:
            answer=guard.route("gameboy physics",now=150,
                               bindings={INDEX:(KNOW,SOURCES)})
            assert answer["route_mode"]=="approved_active"
            assert answer["bookmarked_retrieval_ids"]==["e"*64]
            assert answer["freshness_revision"]==1
            assert not answer["automated_learning_authorized"]
            route.assert_called_once()
            with pytest.raises(PermissionError,match="not current"):
                guard.route("gameboy",now=500,bindings={INDEX:(KNOW,SOURCES)})
            route.assert_called_once()
            with pytest.raises(PermissionError,match="binding"):
                guard.route("gameboy",now=150,bindings={CONTROL:(KNOW,SOURCES)})


def test_guarded_jeeves_canary_falls_back_only_to_fresh_control():
    private,pub=signer()
    with sqlite3.connect(":memory:") as db:
        l=ledger(db,pub)
        l.record(signed(private,knowledge="a"*64,index=INDEX,status="stale",
                        reason="source_changed"),now=150,
                 expected_revision=0,authorized=True)
        l.record(signed(private,knowledge="b"*64,index=CONTROL,sources="f"*64),
                 now=150,expected_revision=0,authorized=True)
        vault,state=mocked_vault(db)
        plan=SimpleNamespace(owner=OWNER,candidate_digest=INDEX,
                             control_digest=CONTROL)
        canary=object.__new__(DragonWeightCanary)
        canary.vault=vault
        canary.plan=plan
        canary.audit=Mock(return_value={"owner":OWNER,
                                       "candidate_exposure_permitted":True})
        canary.select=Mock(side_effect=AssertionError(
            "invalid candidate may not receive traffic"))
        guard=JeevesFreshnessGuard(vault,l,canary)
        routed={"selected_index_digest":CONTROL,
                "bookmarked_retrieval_ids":["e"*64],
                "read_only":True,"neural_weights_changed":False}
        bindings={INDEX:(KNOW,SOURCES), CONTROL:("b"*64,"f"*64)}
        with patch.object(vault,"audit",return_value=state),patch.object(
            vault,"route_version",return_value=routed) as safe_control:
            got=guard.route("physics",now=150,bindings=bindings,
                            cohort_digest="9"*64)
            assert got["selected_index_digest"]==CONTROL
            assert got["route_mode"]=="fallback_stale_candidate"
            safe_control.assert_called_once()
        db.execute("UPDATE dragon_knowledge_freshness_v1 SET event_mac=? "
                   "WHERE owner=? AND knowledge_digest=?",("0"*64,OWNER,"b"*64))
        with patch.object(vault,"audit",return_value=state):
            with pytest.raises(ValueError,match="corruption"):
                guard.route("physics",now=150,bindings=bindings,
                            cohort_digest="9"*64)


def test_guard_refuses_midroute_generation_change():
    private,pub=signer()
    with sqlite3.connect(":memory:") as db:
        l=ledger(db,pub)
        l.record(signed(private),now=150,expected_revision=0,authorized=True)
        vault,state=mocked_vault(db)
        newer={**state,"generation":3}
        guard=JeevesFreshnessGuard(vault,l)
        with patch.object(vault,"audit",side_effect=[state,newer]),patch.object(
            vault,"route",return_value={"index_digest":INDEX,
                "bookmarked_retrieval_ids":[],"read_only":True,
                "neural_weights_changed":False}):
            with pytest.raises(PermissionError,match="concurrent"):
                guard.route("physics",now=150,bindings={INDEX:(KNOW,SOURCES)})
