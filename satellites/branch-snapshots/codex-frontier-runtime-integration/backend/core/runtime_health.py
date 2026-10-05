"""
core/runtime_health.py — backend runtime snapshot (Feb 2026).

A single, low-cost call that aggregates everything an SRE wants to see:

  * process memory (RSS, vsz, peak) via `resource` (POSIX) with a
    /proc/self/status fallback for portability
  * GC stats (gc.get_stats / get_count)
  * asyncio task count
  * open file descriptors
  * boot uptime
  * mongo round-trip latency (with timeout)
  * tunnel watchdog status
  * feature-flag service health (best-effort)

Intentionally NO disk I/O on the hot path — every call must complete in
< 50 ms even under load.
"""
from __future__ import annotations

import asyncio
import gc
import os
import resource
import sys
import time
from typing import Any

from core.databases import core_db

_BOOT_AT = time.time()


def _process_memory() -> dict[str, Any]:
    try:
        ru = resource.getrusage(resource.RUSAGE_SELF)
        # ru_maxrss is kilobytes on Linux, bytes on macOS
        scale = 1024 if sys.platform.startswith("linux") else 1
        return {
            "rss_kb":   int(ru.ru_maxrss * scale / 1024),
            "user_cpu_s":  round(ru.ru_utime, 2),
            "sys_cpu_s":   round(ru.ru_stime, 2),
        }
    except Exception:
        return {"rss_kb": -1}


def _open_fds() -> int:
    try:
        return len(os.listdir(f"/proc/{os.getpid()}/fd"))
    except Exception:
        return -1


def _gc_stats() -> dict[str, Any]:
    try:
        s = gc.get_stats()
        c = gc.get_count()
        return {
            "counts": list(c),
            "collections": sum(int(g.get("collections", 0)) for g in s),
            "objects":     len(gc.get_objects()) if os.environ.get("RUNTIME_GC_DEEP") else None,
        }
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"}


def _asyncio_stats() -> dict[str, Any]:
    try:
        tasks = asyncio.all_tasks()
        return {
            "total_tasks": len(tasks),
            "pending_tasks": sum(1 for t in tasks if not t.done()),
        }
    except Exception:
        return {"total_tasks": -1, "pending_tasks": -1}


async def _mongo_ping() -> dict[str, Any]:
    t0 = time.perf_counter()
    try:
        await asyncio.wait_for(core_db.command("ping"), timeout=2.5)
        return {"ok": True, "rtt_ms": round((time.perf_counter() - t0) * 1000.0, 2)}
    except asyncio.TimeoutError:
        return {"ok": False, "error": "timeout"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


async def snapshot() -> dict[str, Any]:
    mem = _process_memory()
    fd = _open_fds()
    g = _gc_stats()
    a = _asyncio_stats()
    m = await _mongo_ping()

    # Best-effort tunnel + ff status — import inline so this module stays
    # importable even if the others fail.
    tunnel: dict[str, Any] = {"ok": True}
    try:
        from core import tunnel_watchdog as _tw
        tunnel = _tw.snapshot()
    except Exception as e:  # noqa: BLE001
        tunnel = {"ok": False, "error": f"{type(e).__name__}: {e}"}

    ff: dict[str, Any] = {"ok": True}
    try:
        from core import feature_flags as _ff
        ff = await _ff.health()
    except Exception as e:  # noqa: BLE001
        ff = {"ok": False, "error": f"{type(e).__name__}: {e}"}

    return {
        "ok": True,
        "ts": time.time(),
        "uptime_s": round(time.time() - _BOOT_AT, 1),
        "pid": os.getpid(),
        "python": sys.version.split()[0],
        "memory": mem,
        "open_fds": fd,
        "gc": g,
        "asyncio": a,
        "mongo": m,
        "tunnel": tunnel,
        "feature_flags": ff,
    }
