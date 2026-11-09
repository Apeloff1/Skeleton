from concurrent.futures import ThreadPoolExecutor
import pytest
from skeleton.ai.webcrawler.dragon_execution_pool import DragonExecutionPool, DragonPoolCapacityError
from skeleton.ai.webcrawler.dragon_resource_session import HardwareSample, SessionTask
from skeleton.ai.webcrawler.dragon_chunk_executor import ChunkResult
from skeleton.ai.game_builder.resource_governor import ResourceEnvelope, ResourceDelta
from skeleton.kernel.global_resource_scheduler import GlobalResourceScheduler, GlobalResourcePolicy, ResourceVector, PlanePolicy


def pool(**options):
    scheduler=GlobalResourceScheduler(GlobalResourcePolicy(ResourceVector(cpu_millis=4000,memory_mb=256,provider_tokens=1000),
        (PlanePolicy('interactive',2,ResourceVector(),1.),PlanePolicy('background',1,ResourceVector(),1.))))
    return DragonExecutionPool(scheduler,ResourceEnvelope(100,10,10000,3,1,1,10),
        hardware=lambda:HardwareSample(256*1024**2,4,.1,.9,True,False,10),clock=lambda:10,**options)


def test_accounting_retained_between_real_runs():
    runtime=pool()
    first=runtime.executor('alice')
    task=SessionTask('chat','user',1024,1,provider_tokens=80)
    result=first.run(task,lambda *_:ChunkResult(True,'cp',ResourceDelta(tokens=80)),authorized=True,consent=True)
    assert result.done
    second=runtime.executor('alice')
    assert first is second
    result=second.run(task,lambda *_:pytest.fail('budget reset'),authorized=True,consent=True)
    assert result.reason=='token_budget' and runtime.status()['provider_tokens']==80


def test_cross_owner_foreground_pauses_existing_and_new_workers():
    runtime=pool()
    worker=runtime.executor('background-owner')
    with runtime.foreground('alice'):
        assert worker.foreground_waiting.is_set()
        assert runtime.executor('new-owner').foreground_waiting.is_set()
        result=worker.run(SessionTask('idle','idle',1024,1),lambda *_:pytest.fail('background work'),authorized=True,consent=True)
        assert result.reason=='foreground_waiting'
        with runtime.foreground('bob'):
            assert runtime.status()['foreground_requests']==2
        assert worker.foreground_waiting.is_set()
    assert not worker.foreground_waiting.is_set() and not runtime.executor('new-owner').foreground_waiting.is_set()


def test_exception_releases_foreground_without_erasing_accounting():
    runtime=pool()
    with pytest.raises(RuntimeError):
        with runtime.foreground('alice'):
            raise RuntimeError('request cancelled')
    assert runtime.status()['foreground_requests']==0
    assert runtime.status()['owners']==0


def test_capacity_never_evicts_budget_or_allocates_unbounded_owners():
    runtime=pool(capacity=1,max_foreground=1)
    retained=runtime.executor('alice')
    with pytest.raises(DragonPoolCapacityError): runtime.executor('bob')
    assert runtime.executor('alice') is retained
    with runtime.foreground('alice'):
        with pytest.raises(DragonPoolCapacityError):
            with runtime.foreground('alice'): pass
    assert runtime.status()['foreground_requests']==0


def test_concurrent_owner_creation_is_one_retained_worker():
    runtime=pool()
    with ThreadPoolExecutor(max_workers=8) as workers:
        results=list(workers.map(lambda _:runtime.executor('alice'),range(32)))
    assert all(x is results[0] for x in results)
    assert runtime.status()['owners']==1


def test_principal_identity_has_tenant_isolation_and_normalization():
    key=DragonExecutionPool.owner_key
    assert key(' tenant ', ' ALICE@EXAMPLE.TEST ')==key('tenant','alice@example.test')
    assert key('tenant','alice@example.test')!=key('other','alice@example.test')
    with pytest.raises(ValueError): key('tenant','alice\n')


def test_full_pet_pool_does_not_block_new_foreground_user():
    runtime=pool(capacity=1)
    existing=runtime.executor('alice')
    with runtime.foreground('bob'):
        assert existing.foreground_waiting.is_set()
    assert runtime.status()['owners']==1
