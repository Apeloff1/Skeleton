"""godot_engine.health — one-shot deep health snapshot for the engine stack.

Combines the binary probe, host disk headroom, and project-dir writability
into a single report suitable for /health endpoints and readiness gates.
Cheap to call repeatedly: the binary profile is cached after first probe.
"""
from __future__ import annotations

import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from gameforge.godot_engine.binary import binary_status, get_binary

_BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECTS_DIR = _BACKEND_DIR / "data" / "godot_projects"
LOW_DISK_BYTES = 500 << 20  # 500 MiB floor


@dataclass
class HealthReport:
    ok: bool = True
    problems: list[str] = field(default_factory=list)
    binary_available: bool = False
    engine_version: str | None = None
    headless_ok: bool | None = None
    probe_ms: float | None = None
    disk_free_mb: int | None = None
    projects_dir: str = str(PROJECTS_DIR)
    projects_dir_writable: bool | None = None
    checked_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok and not self.problems,
            "binary_available": self.binary_available,
            "engine_version": self.engine_version,
            "headless_ok": self.headless_ok,
            "probe_ms": round(self.probe_ms, 1) if self.probe_ms is not None else None,
            "disk_free_mb": self.disk_free_mb,
            "projects_dir": self.projects_dir,
            "projects_dir_writable": self.projects_dir_writable,
            "problems": self.problems,
            "checked_at": self.checked_at,
        }


async def deep_health(probe_timeout: int = 45) -> HealthReport:
    """Run all engine health checks and return one report."""
    report = HealthReport()

    status = binary_status()
    if not status.get("available"):
        report.ok = False
        report.problems.append(status.get("error", "godot binary missing"))
    else:
        report.binary_available = True
        started = time.monotonic()
        try:
            profile = await get_binary().probe()
            report.engine_version = profile.version
            report.headless_ok = profile.headless_ok
            if not profile.headless_ok:
                report.problems.append("headless self-test failed")
        except Exception as e:
            report.ok = False
            report.problems.append(f"engine probe failed: {type(e).__name__}: {e}"[:200])
        report.probe_ms = (time.monotonic() - started) * 1000

    try:
        usage = shutil.disk_usage(str(_BACKEND_DIR))
        report.disk_free_mb = usage.free // (1 << 20)
        if usage.free < LOW_DISK_BYTES:
            report.problems.append("low disk headroom (<500 MiB free)")
    except Exception:
        pass

    try:
        PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=PROJECTS_DIR, delete=True):
            pass
        report.projects_dir_writable = True
    except Exception as e:
        report.projects_dir_writable = False
        report.problems.append(f"projects dir not writable: {type(e).__name__}")

    if report.problems:
        report.ok = False
    return report
