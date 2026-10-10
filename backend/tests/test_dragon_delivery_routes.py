"""Real authenticated HTTP knowledge/design/native-delivery journey."""
import json
import sqlite3
from dataclasses import replace
from io import BytesIO
from zipfile import ZipFile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from routes import dragon_academy as route
from core.dragon_runtime_bridge import install_dragon_runtime
from skeleton.ai.game_builder.resource_governor import ResourceEnvelope
from skeleton.ai.webcrawler.dragon_resource_session import HardwareSample
from skeleton.kernel.global_resource_scheduler import GlobalResourceScheduler, GlobalResourcePolicy, ResourceVector, PlanePolicy
# Backend's legacy `tests` package shadows the repository tests package.
import importlib.util
from pathlib import Path
_fixture_spec = importlib.util.spec_from_file_location("dragon_delivery_fixtures", Path(__file__).resolve().parents[2] / "tests/test_dragon_delivery.py")
_fixture_module = importlib.util.module_from_spec(_fixture_spec)
_fixture_spec.loader.exec_module(_fixture_module)
setup_knowledge, setup_practice, design, NOW = (_fixture_module.setup_knowledge, _fixture_module.setup_practice, _fixture_module.design, _fixture_module.NOW)
from skeleton.ai.webcrawler.dragon_game_design import FIELDS


@pytest.fixture
def configured(tmp_path, monkeypatch):
    identity={"email":"alice@example.test","tenant_id":"tenant","role":"editor"}
    owner=route._principal(identity)
    knowledge=tmp_path/"knowledge.sqlite";practice=tmp_path/"practice.sqlite"
    library,delivery,review=setup_knowledge(knowledge,owner)
    db,parent,native=setup_practice(practice,owner);db.close()
    monkeypatch.setenv("SKL_DRAGON_KNOWLEDGE_DB_PATH",str(knowledge))
    monkeypatch.setenv("SKL_DRAGON_PRACTICE_DB_PATH",str(practice))
    monkeypatch.setattr(route.time,"time",lambda:NOW+2)
    app=FastAPI();app.include_router(route.router)
    app.dependency_overrides[route.get_current_user]=lambda:identity
    scheduler=GlobalResourceScheduler(GlobalResourcePolicy(ResourceVector(cpu_millis=4000,memory_mb=256,io_tokens=10),
        (PlanePolicy('interactive',2,ResourceVector(),1.),PlanePolicy('background',1,ResourceVector(),1.))))
    pool=install_dragon_runtime(app,scheduler,ResourceEnvelope(1000,100,2000000,10,1,1,10),
        hardware=lambda:HardwareSample(256*1024**2,4,.1,.9,True,False,NOW+2),clock=lambda:NOW+2)
    with TestClient(app) as client:
        yield client,pool,library,delivery,review,owner,identity
    library.close()


def payload():
    d=design()
    return {"design":{k:getattr(d,k) for k in FIELDS},"query":"movement"}


def submit_body(client):
    r=client.post('/api/dragon-academy/delivery/brief',json=payload())
    assert r.status_code==200,r.text
    brief=r.json();assert brief['ready_for_source_generation']
    return {**payload(),"approved":True,"plan_digest":brief['plan_digest'],
            "prepared_at":brief['prepared_at'],"request_id":"delivery_http_0123456789"}


def test_end_to_end_authenticated_brief_generation_archive_and_retry(configured):
    client,pool,library,delivery,review,owner,_=configured
    overview=client.get('/api/dragon-academy/delivery/overview')
    assert overview.status_code==200,overview.text
    assert overview.headers['cache-control']=='private, no-store'
    assert overview.json()['counts']['reviewed_sources']==2
    assert overview.json()['resource_runtime_ready']
    search=client.get('/api/dragon-academy/delivery/knowledge?query=movement').json()
    assert len(search['items'])==2 and all(c['approval']=='wiki_hoag_approved' for c in search['items'])
    assert all('exact_quote' not in c for c in search['items'])
    body=submit_body(client)
    created=client.post('/api/dragon-academy/delivery/generate',json=body)
    assert created.status_code==200,created.text
    result=created.json()
    assert result['delivery_state']=='source_generated'
    assert result['resource_execution']['done'] and result['compiled'] is False
    attempt=result['created_native']['attempt_id']
    charged=pool.executor(owner).governor.artifact_bytes
    assert charged>0
    repeat=client.post('/api/dragon-academy/delivery/generate',json=body)
    assert repeat.status_code==200,repeat.text
    assert repeat.json()['created_native']['attempt_id']==attempt
    assert pool.executor(owner).governor.artifact_bytes==charged
    zipped=client.get('/api/dragon-academy/native/'+attempt+'/archive')
    assert zipped.status_code==200
    with ZipFile(BytesIO(zipped.content)) as archive:
        assert b'SECTION' in archive.read('src/main.asm')
        assert json.loads(archive.read('dragon-knowledge-brief.json'))['plan_digest']==body['plan_digest']
        assert json.loads(archive.read('dragon-game-design.json'))['seed']==1
    assert len(client.get('/api/dragon-academy/status').json()['native_attempts'])==1


def test_revoked_evidence_and_changed_design_cannot_generate(configured):
    client,pool,library,delivery,review,owner,_=configured
    body=submit_body(client)
    altered={**body,'design':{**body['design'],'seed':99}}
    assert client.post('/api/dragon-academy/delivery/generate',json=altered).status_code==409
    delivery.pyramid.revoke(owner,review['digest'],reason='changed_source',now=NOW+2,authorized=True,trusted_worker=True)
    assert client.post('/api/dragon-academy/delivery/generate',json=body).status_code==409
    assert client.get('/api/dragon-academy/status').json()['native_attempts']==[]
    assert pool.executor(owner).governor.artifact_bytes==0


def test_resource_deferral_then_recovery_has_no_duplicate_or_fake_output(configured):
    client,pool,library,delivery,review,owner,_=configured
    body=submit_body(client)
    executor=pool.executor(owner);sample=executor.hardware()
    executor.hardware=lambda:replace(sample,thermal_limited=True)
    deferred=client.post('/api/dragon-academy/delivery/generate',json=body)
    assert deferred.status_code==200,deferred.text
    assert deferred.json()['delivery_state']=='deferred' and deferred.json()['created_native'] is None
    assert client.get('/api/dragon-academy/status').json()['native_attempts']==[]
    executor.hardware=lambda:sample
    generated=client.post('/api/dragon-academy/delivery/generate',json=body)
    assert generated.status_code==200,generated.text
    assert generated.json()['delivery_state']=='source_generated'


def test_owner_isolation_and_explicit_consent(configured):
    client,pool,library,delivery,review,owner,identity=configured
    body=submit_body(client)
    assert client.post('/api/dragon-academy/delivery/generate',json={**body,'approved':False}).status_code==403
    assert client.post('/api/dragon-academy/delivery/generate',json={**body,'approved':'true'}).status_code==422
    assert client.post('/api/dragon-academy/delivery/brief',json={**payload(),'owner':owner}).status_code==422
    identity['email']='bob@example.test'
    assert client.get('/api/dragon-academy/delivery/knowledge?query=movement').json()['items']==[]
    assert client.post('/api/dragon-academy/delivery/generate',json=body).status_code==409


def test_no_runtime_or_missing_knowledge_does_not_fabricate_success(configured,monkeypatch):
    client,pool,library,delivery,review,owner,_=configured
    body=submit_body(client)
    client.app.state.dragon_execution_pool=None
    assert client.post('/api/dragon-academy/delivery/generate',json=body).status_code==503
    monkeypatch.delenv('SKL_DRAGON_KNOWLEDGE_DB_PATH')
    assert client.get('/api/dragon-academy/delivery/overview').status_code==503


def test_project_synthesis_recovery_after_projection_failure(configured,monkeypatch):
    from skeleton.ai.game_builder.dragon_delivery import DragonDelivery
    client,pool,library,delivery,review,owner,_=configured
    body=submit_body(client)
    original=DragonDelivery.record_project_learning
    def unavailable(*args,**kwargs):
        raise sqlite3.OperationalError('projection unavailable')
    monkeypatch.setattr(DragonDelivery,'record_project_learning',unavailable)
    generated=client.post('/api/dragon-academy/delivery/generate',json=body)
    assert generated.status_code==200,generated.text
    result=generated.json();assert result['learning_recovery_required']
    attempt=result['created_native']['attempt_id']
    charged=pool.executor(owner).governor.artifact_bytes
    monkeypatch.setattr(DragonDelivery,'record_project_learning',original)
    repaired=client.post('/api/dragon-academy/delivery/'+attempt+'/learning',json={})
    assert repaired.status_code==200,repaired.text
    assert repaired.json()['new_source_generated'] is False
    topic=repaired.json()['project_learning']['topic_id']
    findings=client.get('/api/dragon-academy/delivery/almanacs/'+topic+'/learning')
    assert findings.status_code==200,findings.text
    rows=findings.json()['findings'];assert len(rows)==1
    assert rows[0]['kind']=='source_synthesis'
    assert rows[0]['current_source_lineage'] and not rows[0]['empirical_truth_established']
    assert rows[0]['memory_promotion_authorized'] is False
    duplicate=client.post('/api/dragon-academy/delivery/'+attempt+'/learning',json={})
    assert duplicate.json()==repaired.json()
    assert pool.executor(owner).governor.artifact_bytes==charged
    assert len(client.get('/api/dragon-academy/status').json()['native_attempts'])==1


def test_delivery_does_not_consume_unrelated_practice_lesson(configured):
    client,pool,library,delivery,review,owner,_=configured
    body=submit_body(client)
    with route._lab() as (lab,_):
        lab.db.execute('UPDATE dragon_practice_lessons SET mechanics_json=? WHERE owner=?',('["combat"]',owner))
        lab.db.commit()
    result=client.post('/api/dragon-academy/delivery/generate',json=body)
    assert result.status_code==403,result.text
    assert client.get('/api/dragon-academy/status').json()['native_attempts']==[]
