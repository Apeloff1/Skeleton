"""Atomic preflight and batch admission for swarm tasks."""
from __future__ import annotations
from dataclasses import dataclass
from skeleton.agents.swarm_runtime import AdmissionError,SwarmRuntime,SwarmTask
@dataclass(frozen=True,slots=True)
class BatchResult: task_ids:tuple[str,...]; admitted:int

def preflight(runtime:SwarmRuntime,tasks:list[SwarmTask])->None:
    ids=[t.id for t in tasks]
    if len(ids)!=len(set(ids)): raise AdmissionError("duplicate task id inside batch")
    if len(runtime.tasks())+len(tasks)>runtime.max_tasks: raise AdmissionError("batch exceeds runtime task capacity")
    for t in tasks:
        if not t.id.strip(): raise AdmissionError("task id must not be empty")
        if runtime.task(t.id) is not None: raise AdmissionError(f"duplicate task id: {t.id}")
        if t.max_attempts<1: raise AdmissionError("max_attempts must be positive")

def submit_batch(runtime:SwarmRuntime,tasks:list[SwarmTask])->BatchResult:
    """Preflight the complete batch before mutating runtime state."""
    preflight(runtime,tasks)
    admitted=tuple(runtime.submit(task).id for task in tasks)
    return BatchResult(admitted,len(admitted))
