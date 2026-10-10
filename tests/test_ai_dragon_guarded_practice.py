"""Resource admission reaches real canonical practice artifact generation."""
import sqlite3
from dataclasses import replace
from hashlib import sha256
import pytest
from skeleton.ai.webcrawler.dragon_chunk_executor import DragonChunkExecutor
from skeleton.ai.webcrawler.dragon_resource_session import DragonResourceSession, HardwareSample
from skeleton.ai.game_builder.resource_governor import ResourceGovernor, ResourceEnvelope
from skeleton.kernel.global_resource_scheduler import GlobalResourceScheduler, GlobalResourcePolicy, ResourceVector, PlanePolicy
from skeleton.ai.webcrawler.dragon_practice_lab import DragonPracticeLab, ApprovedLesson
from skeleton.ai.webcrawler.dragon_practice_cycles import DragonPracticeCycles
from skeleton.ai.webcrawler.dragon_game_mechanics import Mechanic
from skeleton.ai.webcrawler.dragon_knowledge_promotion import PromotionDecision


def setup(global_enabled=True, native=False):
    db=sqlite3.connect(':memory:')
    lab=DragonPracticeLab(db)
    promotion=PromotionDecision('physics',True,.99,'calibrated',None,(),sha256(b'physics').hexdigest())
    lab.offer(ApprovedLesson('alice','Physics',promotion,'b'*64,(Mechanic.MOVEMENT,Mechanic.PLATFORMING),True),authorized=True,now=10)
    cycles=DragonPracticeCycles(db,lab)
    cycles.enable('alice',authorized=True,human_approved=True,now=10,expires_at=3010,
        max_ticks=2,demos_per_tick=2,generation_mode='native' if native else 'html')
    scheduler=GlobalResourceScheduler(GlobalResourcePolicy(ResourceVector(cpu_millis=4000,memory_mb=256,io_tokens=10),
        (PlanePolicy('background',1,ResourceVector(),1.),PlanePolicy('interactive',2,ResourceVector(),1.))))
    governor=ResourceGovernor(ResourceEnvelope(100,10,1000000,3,1,1,10))
    sample=HardwareSample(256*1024**2,4,.1,.9,True,False,10)
    executor=DragonChunkExecutor(DragonResourceSession(global_resources=scheduler if global_enabled else None,tenant='alice'),
        governor,lambda:sample,clock=lambda:10)
    return db,lab,cycles,scheduler,governor,executor,sample


@pytest.mark.parametrize('native',[False,True])
def test_admitted_tick_creates_real_artifacts(native):
    db,lab,cycles,scheduler,governor,executor,sample=setup(native=native)
    attempts,run=cycles.pulse_guarded('alice',authorized=True,executor=executor)
    assert run.done and len(attempts)==2
    assert cycles.status('alice',authorized=True).remaining_ticks==1
    assert governor.artifact_bytes==2*lab.policy.max_artifact_bytes
    assert scheduler.usage('background').empty
    if not native:
        assert '<html' in lab.artifact('alice',attempts[0].attempt_id,authorized=True).lower()
    else:
        assert db.execute('SELECT COUNT(*) FROM dragon_native_game_attempts').fetchone()[0]==2


@pytest.mark.parametrize('reason',['missing_global','foreground','thermal','budget'])
def test_deferral_preserves_subscription_and_generates_nothing(reason):
    db,lab,cycles,scheduler,governor,executor,sample=setup(global_enabled=reason!='missing_global')
    if reason=='foreground': executor.foreground_arrived()
    if reason=='thermal': executor.hardware=lambda:replace(sample,thermal_limited=True)
    if reason=='budget': governor.artifact_bytes=999999
    attempts,run=cycles.pulse_guarded('alice',authorized=True,executor=executor)
    assert not attempts and not run.done
    assert cycles.status('alice',authorized=True).remaining_ticks==2
    assert lab.progress('alice',authorized=True).demo_attempts==0
    assert scheduler.usage('background').empty


def test_foreground_between_artifacts_stops_partial_tick(monkeypatch):
    db,lab,cycles,scheduler,governor,executor,sample=setup()
    original=lab.run_batch
    def generate(*args,**kwargs):
        result=original(*args,**kwargs)
        executor.foreground_arrived()
        return result
    monkeypatch.setattr(lab,'run_batch',generate)
    attempts,run=cycles.pulse_guarded('alice',authorized=True,executor=executor)
    assert len(attempts)==1 and run.done
    assert governor.artifact_bytes==lab.policy.max_artifact_bytes
    assert cycles.status('alice',authorized=True).remaining_ticks==1
    assert scheduler.usage('background').empty


def test_revocation_between_artifacts_stops_partial_tick(monkeypatch):
    db,lab,cycles,scheduler,governor,executor,sample=setup()
    original=lab.run_batch
    def generate(*args,**kwargs):
        result=original(*args,**kwargs)
        cycles.disable('alice',authorized=True)
        return result
    monkeypatch.setattr(lab,'run_batch',generate)
    attempts,_=cycles.pulse_guarded('alice',authorized=True,executor=executor)
    assert len(attempts)==1 and not cycles.status('alice',authorized=True).enabled


def test_cross_owner_executor_rejected():
    *_,executor,sample=setup()
    executor.session = DragonResourceSession(tenant='mallory')
    db,lab,cycles,*_=setup()
    with pytest.raises(PermissionError): cycles.pulse_guarded('alice',authorized=True,executor=executor)


def test_heat_between_artifacts_stops_partial_tick(monkeypatch):
    db,lab,cycles,scheduler,governor,executor,sample=setup()
    original=lab.run_batch
    def generate(*args,**kwargs):
        result=original(*args,**kwargs)
        executor.hardware=lambda:replace(sample,thermal_limited=True)
        return result
    monkeypatch.setattr(lab,'run_batch',generate)
    attempts,_=cycles.pulse_guarded('alice',authorized=True,executor=executor)
    assert len(attempts)==1 and scheduler.usage('background').empty


def test_last_tick_revocation_is_detected(monkeypatch):
    db,lab,cycles,scheduler,governor,executor,sample=setup()
    cycles.enable('alice',authorized=True,human_approved=True,now=10,expires_at=3010,max_ticks=1,demos_per_tick=2)
    original=lab.run_batch
    def generate(*args,**kwargs):
        result=original(*args,**kwargs)
        cycles.disable('alice',authorized=True)
        return result
    monkeypatch.setattr(lab,'run_batch',generate)
    attempts,_=cycles.pulse_guarded('alice',authorized=True,executor=executor)
    assert len(attempts)==1
    assert cycles.status('alice',authorized=True).remaining_ticks==0


def test_native_artifact_limit_rolls_back_attempt():
    from skeleton.ai.webcrawler.dragon_native_practice import DragonNativePracticeLab
    db,lab,cycles,*_=setup(native=True)
    lab.policy=replace(lab.policy,max_artifact_bytes=1)
    native=DragonNativePracticeLab(db,lab)
    with pytest.raises(ValueError,match='artifact exceeds'):
        native.generate('alice',target_id='game_boy',style='arcade_score_attack',now=10,authorized=True,consent=True)
    assert db.execute('SELECT COUNT(*) FROM dragon_native_game_attempts').fetchone()[0]==0
