"""Job orchestrator — long-running batch job coordination.

Coordinates multi-hour batch jobs (reindex, backfill, compaction)
with chunked execution, progress checkpoints, pause/resume, and
failure recovery from the last committed chunk. Integrates with the
scheduler for recurring batches and the task queue for distribution.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterator, List, Optional


@dataclass
class JobState:
    job_id: str
    name: str
    status: str = "pending"
    total_chunks: int = 0
    completed_chunks: int = 0
    started_ns: int = 0
    checkpoint: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    def progress(self) -> float:
        return self.completed_chunks / self.total_chunks if self.total_chunks else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "name": self.name,
            "status": self.status,
            "progress": round(self.progress(), 3),
            "completed_chunks": self.completed_chunks,
            "total_chunks": self.total_chunks,
            "error": self.error,
        }


class JobOrchestrator:
    """Chunked batch job execution with checkpoints."""

    def __init__(self):
        self._jobs: Dict[str, JobState] = {}
        self._counter = 0

    def submit(self, name: str, chunks: Iterator[Any],
               process_chunk: Callable[[Any, Dict[str, Any]], None],
               total: Optional[int] = None) -> JobState:
        self._counter += 1
        chunk_list = list(chunks)
        state = JobState(
            job_id=f"job-{self._counter:04d}",
            name=name,
            total_chunks=total or len(chunk_list),
            started_ns=time.time_ns(),
        )
        state.checkpoint["chunks"] = chunk_list
        state.checkpoint["process"] = process_chunk
        self._jobs[state.job_id] = state
        return state

    def run(self, job_id: str, max_chunks: Optional[int] = None) -> Dict[str, Any]:
        state = self._jobs[job_id]
        if state.status == "completed":
            return {"status": "completed"}
        if state.status == "failed":
            return {"status": "failed", "error": state.error}
        state.status = "running"
        chunks: List[Any] = state.checkpoint["chunks"]
        process = state.checkpoint["process"]
        ran = 0
        while state.completed_chunks < len(chunks) and (max_chunks is None or ran < max_chunks):
            if state.status == "paused":
                break
            chunk = chunks[state.completed_chunks]
            try:
                process(chunk, state.checkpoint)
                state.completed_chunks += 1
                ran += 1
            except Exception as exc:  # noqa: BLE001
                state.status = "failed"
                state.error = f"chunk {state.completed_chunks}: {exc}"
                return {"status": "failed", **state.to_dict()}
        if state.completed_chunks >= len(chunks):
            state.status = "completed"
        return state.to_dict()

    def pause(self, job_id: str) -> bool:
        state = self._jobs.get(job_id)
        if state and state.status == "running":
            state.status = "paused"
            return True
        return False

    def resume(self, job_id: str, max_chunks: Optional[int] = None) -> Dict[str, Any]:
        state = self._jobs.get(job_id)
        if not state or state.status != "paused":
            return {"resumed": False}
        state.status = "running"
        return self.run(job_id, max_chunks)

    def retry_failed(self, job_id: str, max_chunks: Optional[int] = None) -> Dict[str, Any]:
        state = self._jobs.get(job_id)
        if not state or state.status != "failed":
            return {"retried": False}
        state.status = "running"
        state.error = None
        return self.run(job_id, max_chunks)

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "job-orchestrator-card",
            "jobs": {jid: s.to_dict() for jid, s in self._jobs.items()},
            "running": len([s for s in self._jobs.values() if s.status == "running"]),
            "completed": len([s for s in self._jobs.values() if s.status == "completed"]),
            "failed": len([s for s in self._jobs.values() if s.status == "failed"]),
        }
