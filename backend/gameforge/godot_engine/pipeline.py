"""
godot_engine.pipeline — run headless Godot jobs as tracked async tasks.

Job kinds:
    * ``import``           — ``--headless --import`` (warm the .godot cache)
    * ``check``            — ``--headless --check-only --script <gd>`` (lint GDScript)
    * ``export``           — ``--headless --export-release <preset> <out>``
    * ``dump_gdextension`` — ``--headless --dump-gdextension-interface``

Each job runs in a subprocess with a timeout; stdout/stderr and the exit
code are captured into a :class:`GodotJob` record retrievable by id.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from gameforge.godot_engine.binary import get_binary

DEFAULT_TIMEOUT = 600  # seconds


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


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

    def __init__(self) -> None:
        self.jobs: dict[str, GodotJob] = {}

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
            argv += ["--check-only", "--script", str(script)]
        elif kind == "export":
            if not preset or output is None:
                raise ValueError("export jobs require preset= and output=")
            argv += ["--export-release", preset, str(output)]
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
        asyncio.create_task(self._run(job, timeout))
        return job

    async def _run(self, job: GodotJob, timeout: int) -> None:
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
            job.stdout = out.decode(errors="replace")
            job.stderr = err.decode(errors="replace")
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


_pipeline: GodotPipeline | None = None


def get_pipeline() -> GodotPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = GodotPipeline()
    return _pipeline
