"""pipeline.py — headless Godot job runners, built on scheduler + logbuffer.

Each runner owns one subprocess, streams its output into the per-job ring
buffer, and reports into the ScheduledJob. The scheduler handles queueing,
staggering, concurrency, and cancellation.
"""
from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from core.exec_guard import execution_disabled_message, require_execution_allowed
from gameforge.godot_engine.binary import get_binary, reap_process
from gameforge.godot_engine.logbuffer import get_buffer
from gameforge.godot_engine.scheduler import JobScheduler, JobStatus, ScheduledJob, scheduler

DEFAULT_TIMEOUT = 600


async def _run_godot(job: ScheduledJob, argv: list[str], timeout: int) -> None:
    if not require_execution_allowed("Godot engine execution"):
        job.status = JobStatus.FAILED
        job.error = execution_disabled_message("Godot engine execution")
        return
    admission = await asyncio.to_thread(get_binary().prepare_execution)
    argv = [str(admission.path), *argv[1:]]
    admission.assert_current()
    buf = get_buffer(job.id)
    buf.append("system", "Godot execution admitted")
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    job._proc = proc

    async def _pump(stream, name):
        while True:
            line = await stream.read(4096)
            if not line:
                return
            buf.append(name, line.decode(errors="replace").rstrip())

    async def finish():
        _, _, rc = await asyncio.gather(
            _pump(proc.stdout, "stdout"), _pump(proc.stderr, "stderr"), proc.wait()
        )
        return rc

    try:
        rc = await asyncio.wait_for(finish(), timeout=timeout)
    except asyncio.TimeoutError:
        job.status = JobStatus.TIMED_OUT
        job.error = f"killed after {timeout}s"
        return
    finally:
        try:
            if proc.returncode is None:
                await reap_process(proc)
        finally:
            job._proc = None

    job.result = {
        "returncode": rc,
        "engine_sha256": admission.sha256,
        "engine_integrity": admission.integrity,
        "stdout_tail": buf.tail("stdout", 120),
        "stderr_tail": buf.tail("stderr", 60),
    }
    if rc != 0:
        job.error = f"godot exited {rc}"


def _argv(job: ScheduledJob) -> list[str]:
    p = job.payload
    argv = ["godot", "--headless"]
    if p.get("project_dir"):
        argv += ["--path", p["project_dir"]]
    kind = job.kind
    if kind == "import":
        argv.append("--import")
    elif kind == "check":
        argv += ["--check-only", "--script", p["script"]]
    elif kind == "export":
        argv += ["--export-release", p["preset"], p["output"]]
    elif kind == "dump_gdextension":
        argv.append("--dump-gdextension-interface")
    elif kind == "script":
        # Run an arbitrary editor script: --headless -s res://tools/x.gd
        argv += ["-s", p["script"]]
    else:
        raise ValueError(f"unknown job kind {kind!r}")
    return argv


async def _runner(job: ScheduledJob) -> None:
    await _run_godot(job, _argv(job), int(job.payload.get("timeout", DEFAULT_TIMEOUT)))


for _kind in ("import", "check", "export", "dump_gdextension", "script"):
    scheduler.register_runner(_kind, _runner)


def get_scheduler() -> JobScheduler:
    return scheduler


class GodotPipeline:
    """Job registry and submission facade for the Godot execution scheduler."""

    def __init__(self) -> None:
        self._jobs: dict[str, ScheduledJob] = {}

    async def submit(
        self,
        kind: str,
        project_dir: Path | None,
        *,
        timeout: int = DEFAULT_TIMEOUT,
        **payload,
    ) -> ScheduledJob:
        runner = scheduler.runner_for(kind)
        if not 1 <= timeout <= 3600:
            raise ValueError("invalid job timeout")
        terminal = {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED, JobStatus.TIMED_OUT}
        if len(self._jobs) >= 256:
            for old_id, old in list(self._jobs.items()):
                if old.status in terminal:
                    self._jobs.pop(old_id)
                    if len(self._jobs) < 256:
                        break
        if len(self._jobs) >= 256:
            raise ValueError("Godot job capacity reached")
        job_id = uuid.uuid4().hex
        job = ScheduledJob(
            id=job_id,
            kind=kind,
            payload={
                **payload,
                "project_dir": str(project_dir) if project_dir else None,
                "timeout": timeout,
            },
        )
        self._jobs[job_id] = job
        async def execute() -> None:
            job.status = JobStatus.RUNNING
            try:
                await runner(job)
                if job.status == JobStatus.RUNNING:
                    job.status = (
                        JobStatus.COMPLETED
                        if not job.error
                        else JobStatus.FAILED
                    )
            except asyncio.CancelledError:
                job.status = JobStatus.CANCELLED
                raise
            except Exception:
                job.status = JobStatus.FAILED
                job.error = "godot_job_failed"

        await scheduler.run(job_id, execute)
        return job

    def get(self, job_id: str) -> ScheduledJob | None:
        return self._jobs.get(job_id)

    def list(self, limit: int = 50) -> list[ScheduledJob]:
        return list(self._jobs.values())[-max(1, min(limit, 200)):]

    def stats(self) -> dict:
        return scheduler.snapshot()


_pipeline = GodotPipeline()


def get_pipeline() -> GodotPipeline:
    return _pipeline
