"""pipeline.py — headless Godot job runners, built on scheduler + logbuffer.

Each runner owns one subprocess, streams its output into the per-job ring
buffer, and reports into the ScheduledJob. The scheduler handles queueing,
staggering, concurrency, and cancellation.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from gameforge.godot_engine.binary import get_binary
from gameforge.godot_engine.logbuffer import get_buffer
from gameforge.godot_engine.scheduler import JobScheduler, JobStatus, ScheduledJob, scheduler

DEFAULT_TIMEOUT = 600


async def _run_godot(job: ScheduledJob, argv: list[str], timeout: int) -> None:
    buf = get_buffer(job.id)
    buf.append("system", f"exec: {' '.join(argv)}")
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    job._proc = proc

    async def _pump(stream, name):
        while True:
            line = await stream.readline()
            if not line:
                return
            buf.append(name, line.decode(errors="replace").rstrip())

    try:
        await asyncio.wait_for(
            asyncio.gather(_pump(proc.stdout, "stdout"), _pump(proc.stderr, "stderr")),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        job.status = JobStatus.TIMED_OUT
        job.error = f"killed after {timeout}s"
        return

    rc = await proc.wait()
    job.result = {
        "returncode": rc,
        "stdout_tail": buf.tail("stdout", 120),
        "stderr_tail": buf.tail("stderr", 60),
    }
    if rc != 0:
        job.error = f"godot exited {rc}"


def _argv(job: ScheduledJob) -> list[str]:
    p = job.payload
    argv = [str(get_binary().path), "--headless"]
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
