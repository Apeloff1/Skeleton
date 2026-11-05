"""Thread-safe, bounded, prompt-free supervisor state observations."""
from __future__ import annotations
from dataclasses import dataclass,field
from threading import RLock
from .clock import now_ns,age_ms
from .contracts import DaemonError

PHASES=frozenset(('new','starting','running','draining','stopped','held'))

@dataclass(slots=True)
class DaemonStatus:
    _phase:str='new'
    _jobs:int=0
    _idle_polls:int=0
    _busy_polls:int=0
    _failures:int=0
    _last_error_type:str|None=None
    _last_job:str|None=None
    _active_job:str|None=None
    _created_ns:int=field(default_factory=now_ns)
    _pulse_ns:int=field(default_factory=now_ns)
    _lock:RLock=field(default_factory=RLock,repr=False)

    def set_phase(self,name:str)->None:
        if name not in PHASES:raise DaemonError('invalid supervisor phase')
        with self._lock:
            self._phase=name;self._pulse_ns=now_ns()

    def started_job(self)->None:
        with self._lock:
            self._active_job='inference-active';self._pulse_ns=now_ns()

    def completed_job(self,job_id:str)->None:
        # Job ID is not a prompt, but only the count is needed at HTTP level.
        with self._lock:
            self._active_job=None;self._last_job=job_id
            self._jobs+=1;self._pulse_ns=now_ns()

    def no_active(self)->None:
        with self._lock:
            self._active_job=None;self._pulse_ns=now_ns()

    def idle(self,*,capacity:bool=False)->None:
        with self._lock:
            if capacity:self._busy_polls+=1
            else:self._idle_polls+=1
            self._pulse_ns=now_ns()

    def fail(self,exc:BaseException)->None:
        with self._lock:
            self._failures+=1;self._last_error_type=type(exc).__name__[:64]
            self._active_job=None;self._phase='held';self._pulse_ns=now_ns()

    def snapshot(self,*,stall_ms:int=120000)->dict:
        if type(stall_ms)is not int or stall_ms<1000:raise DaemonError('invalid health bound')
        with self._lock:
            instant=now_ns()
            age=age_ms(self._pulse_ns,instant)
            return {'schema':'skeleton.ai.native-supervisor.v1',
                'phase':self._phase,'completed_jobs':self._jobs,
                'idle_polls':self._idle_polls,'capacity_polls':self._busy_polls,
                'failures':self._failures,'last_error_type':self._last_error_type,
                'active_inference':self._active_job is not None,
                'age_since_progress_ms':age,
                'stall_observed':self._phase in ('running','draining') and age>stall_ms,
                'uptime_ms':age_ms(self._created_ns,instant),
                'readiness':'scheduler-only-not-model-quality'}
