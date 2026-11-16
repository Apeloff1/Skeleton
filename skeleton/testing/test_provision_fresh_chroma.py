"""Fresh Chroma deployment boundary: no recreation, migration or ambiguous resume."""
from __future__ import annotations

import importlib
import json
from pathlib import Path
import sys

import pytest

SCRIPTS=Path(__file__).resolve().parents[2]/"scripts"
sys.path.insert(0,str(SCRIPTS))
p=importlib.import_module("provision_fresh_chroma")
HEAD="a"*40
IMAGE_ID="sha256:"+"b"*64
PROJECT={"project":"skeleton","engine_id":"c"*64,"network":"skeleton_tutolage","network_id":"d"*64}
CID="e"*64
VOLUME="skeleton_chroma_durable_data"


def fixture(**updates):
    body={"schema":p.FIXTURE_SCHEMA,"source_head":HEAD,"image":p.IMAGE,"image_id":IMAGE_ID,
          "version":"1.2.3","scope":"disposable_named_volume_only","checks":dict.fromkeys(p.CHECKS,True),
          "fixture_cleanup_verified":True,"synthetic_vector_state_sha256":"1"*64,
          "legacy_migration_qualified":False,"production_full_profile_qualified":False,
          "release_qualified":False}
    body.update(updates)
    row={**body,"receipt_sha256":p.digest(body)}
    raw=p.canonical(row)
    return raw,p.sha(raw)


@pytest.mark.parametrize("updates",[
    {"source_head":"f"*40},{"scope":"production"},{"checks":{}},
    {"fixture_cleanup_verified":False},{"release_qualified":True},
    {"legacy_migration_qualified":True},{"production_full_profile_qualified":True},
    {"image":"chromadb/chroma:latest"},{"image_id":"sha256:bad"},
    {"version":"bad"},{"synthetic_vector_state_sha256":None},
])
def test_fixture_denies_invalid_scope_or_evidence(updates):
    raw,pin=fixture(**updates)
    with pytest.raises(p.ProvisionDenied):
        p.fixture_receipt(raw,pin,HEAD)


def test_receipt_pin_required():
    raw,pin=fixture()
    assert p.fixture_receipt(raw,pin,HEAD)["image_id"]==IMAGE_ID
    with pytest.raises(p.ProvisionDenied):
        p.fixture_receipt(raw,"0"*64,HEAD)


@pytest.mark.parametrize("legacy",["chroma_data","unrelated_chroma_data"])
def test_any_historical_volume_blocks_new_install(monkeypatch,legacy):
    monkeypatch.setattr(p,"_volumes",lambda *filters: [] if filters else [legacy])
    with pytest.raises(p.ProvisionDenied):
        p._legacy_absent()


def test_existing_canonical_container_blocks_fresh(monkeypatch):
    monkeypatch.setattr(p,"_legacy_absent",lambda:None)
    monkeypatch.setattr(p,"_container_ids",lambda *args:[CID])
    with pytest.raises(p.ProvisionDenied):
        p._fresh_absent("skeleton",VOLUME)


def test_existing_durable_volume_blocks_fresh(monkeypatch):
    monkeypatch.setattr(p,"_legacy_absent",lambda:None)
    monkeypatch.setattr(p,"_container_ids",lambda *args:[])
    monkeypatch.setattr(p,"_volumes",lambda *args:[VOLUME])
    with pytest.raises(p.ProvisionDenied):
        p._fresh_absent("skeleton",VOLUME)


def created():
    return {"schema":p.SCHEMA,"source_head":HEAD,"fixture_sha256":"2"*64,
            "project":dict(PROJECT),"volume":VOLUME,"token":"3"*32,"image_id":IMAGE_ID,
            "version":"1.2.3","port":8000,"state":"created_not_qualified","intent_sha256":"4"*64,
            "volume_sha256":"5"*64,"container_id":CID}


def encode_receipt(body):
    raw=p.canonical(p._receipt(body))+b"\n"
    return raw,p.sha(raw)


@pytest.mark.parametrize("updates",[
    {"volume":"another_chroma_durable_data"},{"port":True},{"port":80},{"port":65536},
    {"token":"invalid"},{"container_id":"short"},{"state":"qualified"},
    {"project":{**PROJECT,"network":"foreign"}},{"image_id":"sha256:wrong"},
])
def test_created_receipt_denies_substitution(updates):
    raw,pin=encode_receipt({**created(),**updates})
    with pytest.raises(p.ProvisionDenied):
        p.created_receipt(raw,pin)


def setup(monkeypatch):
    calls=[]
    running=[False]
    monkeypatch.setattr(p,"_head",lambda h: calls.append(("head",h)))
    monkeypatch.setattr(p,"_project",lambda:dict(PROJECT))
    monkeypatch.setattr(p,"_legacy_absent",lambda:None)
    monkeypatch.setattr(p,"_fresh_absent",lambda project,volume:None)
    monkeypatch.setattr(p,"_image_id",lambda:IMAGE_ID)
    monkeypatch.setattr(p,"_volume",lambda *args:"5"*64)
    monkeypatch.setattr(p,"_container",lambda *args,**kw:(CID,running[0]))
    monkeypatch.setattr(p,"_await_ready",lambda port:"1.2.3")
    def docker(*args,**kw):
        calls.append(args)
        assert args==("start",CID)
        running[0]=True
        return b""
    monkeypatch.setattr(p,"docker",docker)
    return calls,running


def test_fresh_commits_intent_and_created_receipt_before_start(monkeypatch,tmp_path):
    tmp_path.chmod(0o700)
    calls,running=setup(monkeypatch)
    journal=tmp_path/"attempt.json"
    def compose(project,volume,token,port):
        assert json.loads(journal.read_bytes())["state"]=="creation_intent"
        assert project==PROJECT and volume==VOLUME and port==8000
        calls.append(("create",))
    monkeypatch.setattr(p,"_compose",compose)
    raw,pin=fixture()
    result=p.fresh(HEAD,raw,pin,8000,journal)
    assert result["heartbeat_verified"] is True
    assert result["release_qualified"] is False
    assert result["production_full_profile_qualified"] is False
    assert result["application_vector_integration_qualified"] is False
    assert running[0] and calls.index(("create",))<calls.index(("start",CID))
    created_path=tmp_path/"attempt.created.json"
    receipt=p.created_receipt(created_path.read_bytes(),result["created_receipt_sha256"])
    assert receipt["container_id"]==CID
    assert receipt["intent_sha256"]==p.sha(journal.read_bytes())


def test_uncertain_creation_preserves_intent_and_never_repeats(monkeypatch,tmp_path):
    tmp_path.chmod(0o700)
    calls,_=setup(monkeypatch)
    journal=tmp_path/"attempt.json"
    def failed(*args):
        calls.append(("create",))
        raise p.ProvisionDenied("uncertain creation")
    monkeypatch.setattr(p,"_compose",failed)
    raw,pin=fixture()
    for _ in range(2):
        with pytest.raises(p.ProvisionDenied):
            p.fresh(HEAD,raw,pin,8000,journal)
    assert calls.count(("create",))==1
    assert journal.exists() and not (tmp_path/"attempt.created.json").exists()
    assert ("start",CID) not in calls


def test_existing_restart_does_not_recreate(monkeypatch):
    calls,running=setup(monkeypatch)
    result=p._observe_existing(created(),HEAD,start=True)
    assert running[0] and result["heartbeat_verified"]
    assert [c for c in calls if c[0]!="head"]==[("start",CID)]


@pytest.mark.parametrize("drift",["container","volume","network","image"])
def test_restart_identity_change_never_starts(monkeypatch,drift):
    calls,_=setup(monkeypatch)
    if drift=="container":
        monkeypatch.setattr(p,"_container",lambda *args,**kw:("f"*64,False))
    elif drift=="volume":
        monkeypatch.setattr(p,"_volume",lambda *args:"f"*64)
    elif drift=="network":
        monkeypatch.setattr(p,"_project",lambda:{**PROJECT,"network_id":"f"*64})
    else:
        monkeypatch.setattr(p,"_image_id",lambda:"sha256:"+"f"*64)
    with pytest.raises(p.ProvisionDenied):
        p._observe_existing(created(),HEAD,start=True)
    assert ("start",CID) not in calls


def test_read_only_inspection_does_not_start(monkeypatch):
    calls,_=setup(monkeypatch)
    result=p._observe_existing(created(),HEAD,start=False)
    assert result["running"] is False and result["heartbeat_verified"] is False
    assert ("start",CID) not in calls


def test_compose_invocation_has_no_recreate_or_down(monkeypatch):
    calls=[]
    monkeypatch.setattr(p,"docker",lambda *args,**kw:calls.append((args,kw)) or b"")
    p._compose(PROJECT,VOLUME,"3"*32,8000)
    assert calls[0][0][-2:]==("config","--quiet")
    assert calls[1][0][-3:]==("create","--no-recreate","chroma")
    assert all("--env-file" in args and "/dev/null" in args for args,_ in calls)
    assert all("down" not in args and "--remove-orphans" not in args for args,_ in calls)
