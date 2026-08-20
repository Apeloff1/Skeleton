"""
godot_engine.pipeline — run headless Godot jobs as tracked async tasks.

Job kinds:
    * ``import``           — ``--headless --import`` (warm the .godot cache)
    * ``check``            — ``--headless --check-only --script <gd>`` (lint GDScript)
    * ``export``           — ``--headless --export-release <preset> <out>``
    * ``dump_gdextension`` — ``--headless --dump-gdextension-interface``

Each job runs in a subprocess with a timeout; stdout/stderr and the exit
code are captured into a :class:`GodotJob` record retrievable by id.

Reliability guardrails
----------------------
* ``GODOT_MAX_CONCURRENT_JOBS`` (default 2) — a semaphore keeps headless
  Godot processes from stampeding the box; extra submissions queue behind it.
* Job history is bounded: finished jobs are evicted oldest-first past
  ``MAX_JOB_HISTORY``, so a long-running server can't grow it forever.
* Captured stdout/stderr are each capped at ``MAX_CAPTURE_BYTES``; the job
  keeps the *tail*, which is what you actually read when something fails.
* Argument values are sanitized — anything that would be parsed as a Godot
  flag (leading ``-``) is rejected before the subprocess is built.
"""
from __future__ import annotations

import asyncio
import os
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from gameforge.godot_engine.binary import get_binary

DEFAULT_TIMEOUT = 600  # seconds
MAX_JOB_HISTORY = 200          # finished jobs retained, oldest evicted first
MAX_CAPTURE_BYTES = 256 * 1024  # per stream; keep the tail


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


_FINISHED = (JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.TIMED_OUT)


def _clean_arg(value: str, what: str) -> str:
    """Reject values that would smuggle a flag into the Godot argv."""
    if value.startswith("-"):
        raise ValueError(f"{what} must not start with '-': {value!r}")
    if "\x00" in value:
        raise ValueError(f"{what} contains a NUL byte")
    return value


@dataclass
class GodotJob:
    id: str
    kind: str
    argv: list[str]
    project_dir: str | None = None
    status: JobStatus = JobStatus.QUEUED
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "argv": self.argv,
            "project_dir": self.project_dir,
            "status": self.status.value,
            "returncode": self.returncode,
            "stdout_tail": self.stdout[-4000:],
            "stderr_tail": self.stderr[-4000:],
            "created_at": self.created_at,
            "finished_at": self.finished_at,
            "duration_s": (
                round(self.finished_at - self.created_at, 2) if self.finished_at else None
            ),
        }


class GodotPipeline:
    """Submits and tracks headless Godot jobs."""

    def __init__(self, max_concurrent: int | None = None) -> None:
        self.jobs: dict[str, GodotJob] = {}
        if max_concurrent is None:
            max_concurrent = int(os.environ.get("GODOT_MAX_CONCURRENT_JOBS", "2"))
        self._slots = asyncio.Semaphore(max(1, max_concurrent))
        self._evict_lock = asyncio.Lock()

    @staticmethod
    def _base(project_dir: Path | None) -> list[str]:
        argv = [str(get_binary().path), "--headless"]
        if project_dir is not None:
            argv += ["--path", str(project_dir)]
        return argv

    def build_argv(
        self,
        kind: str,
        project_dir: Path | None = None,
        *,
        preset: str | None = None,
        output: Path | None = None,
        script: Path | None = None,
    ) -> list[str]:
        argv = self._base(project_dir)
        if kind == "import":
            argv.append("--import")
        elif kind == "check":
            if script is None:
                raise ValueError("check jobs require script=")
            argv += ["--check-only", "--script", _clean_arg(str(script), "script")]
        elif kind == "export":
            if not preset or output is None:
                raise ValueError("export jobs require preset= and output=")
            argv += [
                "--export-release",
                _clean_arg(preset, "preset"),
                _clean_arg(str(output), "output"),
            ]
        elif kind == "dump_gdextension":
            argv.append("--dump-gdextension-interface")
        else:
            raise ValueError(f"unknown job kind: {kind!r}")
        return argv

    async def submit(
        self,
        kind: str,
        project_dir: Path | None = None,
        timeout: int = DEFAULT_TIMEOUT,
        **kwargs,
    ) -> GodotJob:
        argv = self.build_argv(kind, project_dir, **kwargs)
        job = GodotJob(
            id=uuid.uuid4().hex[:12],
            kind=kind,
            argv=argv,
            project_dir=str(project_dir) if project_dir else None,
        )
        self.jobs[job.id] = job
        await self._evict_finished()
        asyncio.create_task(self._run(job, timeout))
        return job

    async def _evict_finished(self) -> None:
        """Bound the history: drop oldest *finished* jobs past the cap."""
        async with self._evict_lock:
            finished = [j for j in self.jobs.values() if j.status in _FINISHED]
            if len(finished) <= MAX_JOB_HISTORY:
                return
            finished.sort(key=lambda j: j.created_at)
            for j in finished[: len(finished) - MAX_JOB_HISTORY]:
                self.jobs.pop(j.id, None)

    async def _run(self, job: GodotJob, timeout: int) -> None:
        async with self._slots:
            job.status = JobStatus.RUNNING
            try:
                proc = await asyncio.create_subprocess_exec(
                    *job.argv,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                try:
                    out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()
                    job.status = JobStatus.TIMED_OUT
                    job.stderr = f"killed after {timeout}s"
                    return
                job.returncode = proc.returncode
                job.stdout = out[-MAX_CAPTURE_BYTES:].decode(errors="replace")
                job.stderr = err[-MAX_CAPTURE_BYTES:].decode(errors="replace")
                job.status = JobStatus.SUCCEEDED if proc.returncode == 0 else JobStatus.FAILED
            except Exception as e:  # binary missing, spawn failure, ...
                job.status = JobStatus.FAILED
                job.stderr = f"{type(e).__name__}: {e}"
            finally:
                job.finished_at = time.time()

    def get(self, job_id: str) -> GodotJob | None:
        return self.jobs.get(job_id)

    def list(self, limit: int = 50) -> list[GodotJob]:
        return sorted(self.jobs.values(), key=lambda j: j.created_at, reverse=True)[:limit]

    def stats(self) -> dict:
        counts: dict[str, int] = {}
        for j in self.jobs.values():
            counts[j.status.value] = counts.get(j.status.value, 0) + 1
        return {"total_jobs": len(self.jobs), "by_status": counts}


_pipeline: GodotPipeline | None = None


def get_pipeline() -> GodotPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = GodotPipeline()
    return _pipeline
