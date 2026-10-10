from dataclasses import replace
import time
import pytest
from skeleton.ai.webcrawler.dragon_chunk_executor import DragonChunkExecutor, ChunkResult
from skeleton.ai.webcrawler.dragon_resource_session import DragonResourceSession, SessionTask, HardwareSample
from skeleton.ai.game_builder.resource_governor import ResourceGovernor, ResourceEnvelope, ResourceDelta, ResourceLimitError
from skeleton.kernel.global_resource_scheduler import GlobalResourceScheduler, GlobalResourcePolicy, ResourceVector, PlanePolicy


def fixture(global_enabled=True):
    scheduler = GlobalResourceScheduler(GlobalResourcePolicy(ResourceVector(cpu_millis=4000,memory_mb=256,provider_tokens=1000),
        (PlanePolicy('interactive',2,ResourceVector(),1.),PlanePolicy('background',1,ResourceVector(),1.))))
    session = DragonResourceSession(global_resources=scheduler if global_enabled else None,tenant='a')
    governor = ResourceGovernor(ResourceEnvelope(100,10,10000,3,1,1,10))
    hardware = lambda: HardwareSample(256*1024**2,4,.1,.9,True,False,10)
    return scheduler, session, governor, DragonChunkExecutor(session,governor,hardware,clock=lambda:10)


def test_runs_real_callback_and_releases_global_grants():
    scheduler, session, governor, worker = fixture()
    called=[]
    def callback(plan, stop):
        assert not stop()
        assert scheduler.usage('interactive').provider_tokens == 20
        called.append(plan.effort)
        return ChunkResult(len(called)==3,f'checkpoint-{len(called)}',ResourceDelta(tokens=10,artifact_bytes=100))
    result = worker.run(SessionTask('chat','user',1024,1,provider_tokens=20),callback,authorized=True,consent=True,max_chunks=5,reserved_usage=ResourceDelta(tokens=20,artifact_bytes=100))
    assert result.done and result.completed_chunks==3 and len(called)==3
    assert governor.tokens==30 and governor.artifact_bytes==300
    assert scheduler.usage('interactive').empty


def test_missing_global_ledger_never_calls_worker():
    _,_,_,worker=fixture(False)
    result=worker.run(SessionTask('task','idle',1024,1),lambda *_:pytest.fail('unauthorized execution'),authorized=True,consent=True)
    assert result.reason=='global_ledger_required'


def test_exception_releases_resources_without_retries():
    scheduler, _, _, worker=fixture()
    def fail(*_): raise RuntimeError('worker_failed')
    with pytest.raises(RuntimeError):
        worker.run(SessionTask('task','idle',1024,1),fail,authorized=True,consent=True)
    assert scheduler.usage('background').empty


def test_hardware_resampled_before_every_chunk():
    scheduler,session,governor,worker=fixture()
    readings=[]
    def hardware():
        readings.append(1)
        return HardwareSample(256*1024**2,4,.1,.9,True,len(readings)>1,10)
    worker.hardware=hardware
    result=worker.run(SessionTask('task','idle',1024,1),lambda *_:ChunkResult(False,'checkpoint',ResourceDelta()),authorized=True,consent=True,max_chunks=10)
    assert result.completed_chunks==1 and result.reason=='thermal_or_pressure' and len(readings)==2
    assert scheduler.usage('background').empty


def test_foreground_interrupt_yields_at_completed_checkpoint():
    scheduler, _, _, worker=fixture()
    def callback(plan, stop):
        worker.foreground_arrived()
        assert stop()
        return ChunkResult(False,'saved-before-yield',ResourceDelta())
    result=worker.run(SessionTask('task','idle',1024,1),callback,authorized=True,consent=True,max_chunks=10)
    assert result.completed_chunks==1 and result.reason=='foreground_waiting'
    assert scheduler.usage('background').empty
    worker.foreground_finished()


def test_provider_reservation_and_cumulative_budget_enforced():
    scheduler,_,governor,worker=fixture()
    task=SessionTask('chat','user',1024,1,provider_tokens=80)
    result=worker.run(task,lambda *_:ChunkResult(False,'cp',ResourceDelta(tokens=80)),authorized=True,consent=True,max_chunks=10)
    assert result.completed_chunks==1 and result.reason=='token_budget'
    assert governor.tokens==80 and scheduler.usage('interactive').empty
    with pytest.raises(ResourceLimitError):
        worker.run(SessionTask('bad','user',1024,1,provider_tokens=1),lambda *_:ChunkResult(True,'cp',ResourceDelta(tokens=2)),authorized=True,consent=True)
    assert scheduler.usage('interactive').empty


def test_hardware_unknown_defers_before_global_or_callback():
    _, _, _, worker=fixture()
    worker.hardware=lambda:HardwareSample(0,1,.1,1.,True,False,10)
    result=worker.run(SessionTask('task','idle',1024,1),lambda *_:pytest.fail('called'),authorized=True,consent=True)
    assert not result.done and result.reason=='memory_reserve'


def test_live_adapter_refuses_probe_fallback():
    from types import SimpleNamespace
    from skeleton.ai.webcrawler.dragon_live_hardware import DragonLiveHardware
    class Probe:
        def profile(self): return SimpleNamespace(cpu_cores=2,battery_present=True)
        def read_state(self): return SimpleNamespace(memory_sample_verified=False,memory_available_mb=2048,
            cpu_load=.1,memory_pressure=.1,swap_pressure=.1,battery_level=None,battery_charging=None,temps_celsius=[],read_at=10)
    sample=DragonLiveHardware(Probe()).sample()
    assert sample.available_memory_bytes==0 and sample.battery_fraction==0 and not sample.charging


def test_linux_native_live_read_has_explicit_verified_flag():
    from skeleton.automation.overseer.hardware import HardwareProbe
    state=HardwareProbe().read_state()
    assert isinstance(state.memory_sample_verified,bool)
    assert state.memory_available_mb>=0


def test_windows_probe_success_uses_actual_available_memory(monkeypatch):
    from skeleton.automation.overseer.hardware import HardwareProbe
    probe=HardwareProbe();probe._sys='windows'
    monkeypatch.setattr(probe,'_windows_memory_mb',lambda:(4096,512))
    assert probe._memory_state()==(3584,512,.875,0.)
    assert probe._memory_verified
    monkeypatch.setattr(probe,'_windows_memory_mb',lambda:(_ for _ in ()).throw(OSError()))
    probe._memory_state()
    assert not probe._memory_verified


def test_macos_read_uses_free_pages_not_assumed_half(monkeypatch):
    from skeleton.automation.overseer.hardware import HardwareProbe
    import subprocess
    probe=HardwareProbe();probe._sys='darwin'
    def read(args,**kwargs):
        return b'1073741824' if args[0]=='sysctl' else b'Mach Virtual Memory Statistics: (page size of 4096 bytes)\nPages free: 256.\n'
    monkeypatch.setattr(subprocess,'check_output',read)
    used,avail,pressure,swap=probe._memory_state()
    assert avail==1 and used==1023 and probe._memory_verified


def test_nested_foreground_requests_remain_prioritized():
    _,_,_,worker=fixture()
    worker.foreground_arrived(); worker.foreground_arrived()
    worker.foreground_finished()
    assert worker.foreground_waiting.is_set()
    worker.foreground_finished()
    assert not worker.foreground_waiting.is_set()
    with pytest.raises(ValueError): worker.foreground_finished()

def test_artifact_budget_checked_before_callback():
    _,_,governor,worker=fixture()
    governor.artifact_bytes=9999
    result=worker.run(SessionTask('task','idle',1024,1),lambda *_:pytest.fail('overspend'),
        authorized=True,consent=True,reserved_usage=ResourceDelta(artifact_bytes=2))
    assert result.reason=='artifact_bytes_budget' and governor.artifact_bytes==9999

def test_undeclared_tool_usage_rejected_and_grant_released():
    scheduler,_,_,worker=fixture()
    with pytest.raises(ResourceLimitError):
        worker.run(SessionTask('task','idle',1024,1),lambda *_:ChunkResult(True,'cp',ResourceDelta(tool_calls=1)),
            authorized=True,consent=True)
    assert scheduler.usage('background').empty


def test_windows_unknown_power_is_not_assumed_desktop(monkeypatch):
    from skeleton.automation.overseer.hardware import HardwareProbe
    probe=HardwareProbe(); probe._sys='windows'
    monkeypatch.setattr(probe,'_windows_power_status',lambda:(255,255,255))
    assert probe._battery_present() and probe._battery_state()==(None,None)
    monkeypatch.setattr(probe,'_windows_power_status',lambda:(0,1,12))
    assert probe._battery_state()==(.12,False)
    monkeypatch.setattr(probe,'_windows_power_status',lambda:(1,128,255))
    assert not probe._battery_present()
