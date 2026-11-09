"""
╔══════════════════════════════════════════════════════════════════════════╗
║  GALAXY STUDIO — BUILD-PIPELINE RESILIENCE (memory watchdog + cooldown)    ║
║  Extracted from galaxy_studio.py (2026-06) to shrink the monolith.        ║
║                                                                            ║
║  Pure, self-contained back-pressure helpers — they depend ONLY on os/env  ║
║  + /proc + stdlib (gc, time, ctypes, resource). No build state, no DB, no  ║
║  circular import back into galaxy_studio.py. The owning module imports     ║
║  these symbols and drives them from the worker loop.                       ║
║                                                                            ║
║  When the process RSS crosses GALAXY_RSS_SOFT_MB we sleep between batches  ║
║  to let GC / disk flush reclaim memory. When it crosses GALAXY_RSS_HARD_MB ║
║  the caller flushes to vault + freezes heavy file generation (writes only  ║
║  a metadata stub) so a small prod pod completes the build without an OOM   ║
║  kill. All limits are env-configurable per-pod.                            ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
import os

# ═══ Memory thresholds (env-tunable per pod) ═══
#   GALAXY_RSS_SOFT_MB   default 600   — pause briefly between batches
#   GALAXY_RSS_HARD_MB   default 850   — flush + freeze generation, skip remaining
#   GALAXY_WATCHDOG      default on    — set to "off" to disable entirely
#   GALAXY_RSS_AUTOCAL   default on    — self-calibrate limits from the cgroup
#                                        memory ceiling (see below)
_RSS_SOFT_MB = int(os.environ.get("GALAXY_RSS_SOFT_MB", "600"))
_RSS_HARD_MB = int(os.environ.get("GALAXY_RSS_HARD_MB", "850"))
_WATCHDOG_ON = os.environ.get("GALAXY_WATCHDOG", "on").lower() not in ("off", "0", "false", "no")


def _read_cgroup_limit_mb():
    """Return the container's memory ceiling in MB (cgroup v2 then v1), or None.

    Guards against the sentinel 'max' (unlimited) and absurd values (some
    kernels report 2^63 for "no limit"). This makes the watchdog portable:
    the same image self-tunes on a 512 MB pod and on an 8 GB pod.
    """
    for path in ("/sys/fs/cgroup/memory.max",
                 "/sys/fs/cgroup/memory/memory.limit_in_bytes"):
        try:
            with open(path) as f:
                raw = f.read().strip()
            if raw == "max":
                continue
            mb = int(raw) / 1024 / 1024
            if 64 <= mb <= 1_048_576:  # 64 MB .. 1 TB sane window
                return mb
        except Exception:
            continue
    return None


# ═══ SELF-CALIBRATION (2026-06 bug-fix) ═══
# A prior tuning hard-coded SOFT=315 / HARD=450 MB for a tiny pod. The pod now
# has an 8 GB cgroup ceiling, so freezing at 450 MB throttled every build down
# to ~1 file. We now derive pod-appropriate limits from the cgroup ceiling and
# take max(env_floor, calibrated) — so the stale env values can only RAISE
# safety, never cripple a large pod, while a small pod still auto-shrinks.
_AUTOCAL = os.environ.get("GALAXY_RSS_AUTOCAL", "on").lower() not in ("off", "0", "false", "no")
_CGROUP_LIMIT_MB = _read_cgroup_limit_mb()
if _AUTOCAL and _CGROUP_LIMIT_MB:
    # Headroom %s, but ALSO absolute caps: a huge pod (8 GB+) must not let a
    # single build hoard multi-GB of in-RAM file dicts — that blocks the event
    # loop (slow /api/health) and risks thrash. Files stream to the vault, so a
    # ~1.2/2.0 GB working buffer already sustains 20k+ file builds while keeping
    # the process responsive. Small pods scale down via the %s.
    _cal_soft = min(int(_CGROUP_LIMIT_MB * 0.30), 1200)   # pause + flush
    _cal_hard = min(int(_CGROUP_LIMIT_MB * 0.45), 2000)   # freeze generation
    _RSS_SOFT_MB = max(_RSS_SOFT_MB, _cal_soft)
    _RSS_HARD_MB = max(_RSS_HARD_MB, _cal_hard)
    print(f"[GALAXY watchdog] auto-calibrated to cgroup={_CGROUP_LIMIT_MB:.0f}MB "
          f"→ SOFT={_RSS_SOFT_MB}MB HARD={_RSS_HARD_MB}MB")

# ═══ Worker cooldown (stagger) ═══
# Sleep between successive batch submissions so GC + malloc_trim can reclaim
# heap before the next allocation wave. Higher = safer + slightly slower.
_WORKER_COOLDOWN_MS = int(os.environ.get("GALAXY_WORKER_COOLDOWN_MS", "0"))
_BATCH_PAUSE_MS = int(os.environ.get("GALAXY_BATCH_PAUSE_MS", "0"))


def _malloc_trim() -> None:
    """Force glibc to return freed heap to the OS. No-op on non-Linux or musl."""
    try:
        import ctypes
        libc = ctypes.CDLL("libc.so.6")
        libc.malloc_trim(0)
    except Exception:
        pass


try:
    import resource as _resource  # stdlib, Linux/macOS
    _RSS_PROC_STATUS = "/proc/self/status"
    _HAS_PROC_STATUS = os.path.exists(_RSS_PROC_STATUS)

    def _get_rss_mb() -> float:
        """Current RSS in MB (NOT peak). Prefers /proc/self/status for live reads."""
        # Linux: read live VmRSS from /proc (monotonic-safe, reflects GC reclaim)
        if _HAS_PROC_STATUS:
            try:
                with open(_RSS_PROC_STATUS, "r") as f:
                    for line in f:
                        if line.startswith("VmRSS:"):
                            # "VmRSS:   12345 kB"
                            kb = int(line.split()[1])
                            return kb / 1024
            except Exception:
                pass
        # Fallback: ru_maxrss is peak RSS (not live) — better than nothing
        try:
            kb = _resource.getrusage(_resource.RUSAGE_SELF).ru_maxrss
            if kb > 100 * 1024 * 1024:  # macOS reports bytes
                return kb / 1024 / 1024
            return kb / 1024
        except Exception:
            return 0.0
except Exception:
    def _get_rss_mb() -> float:
        return 0.0


def _worker_cooldown(context: str = "") -> None:
    """Hybrid cooldown: GC + malloc_trim + sleep.
    Invoked between batch harvest and next-batch enqueue so RSS drops before
    we add another batch's worth of allocations. Also dynamically extends
    the sleep if RSS is above the soft limit."""
    if _WORKER_COOLDOWN_MS <= 0 and not _WATCHDOG_ON:
        return
    import gc, time as _t
    gc.collect()
    _malloc_trim()
    base = max(0, _WORKER_COOLDOWN_MS) / 1000.0
    # Dynamic extension when near memory limits.
    try:
        rss = _get_rss_mb()
        if _WATCHDOG_ON and rss >= _RSS_SOFT_MB:
            # Scale extra sleep proportional to how far over soft limit we are.
            overshoot_ratio = min(2.0, (rss - _RSS_SOFT_MB) / max(1, _RSS_HARD_MB - _RSS_SOFT_MB))
            base += 0.5 + 1.5 * overshoot_ratio  # up to +2s additional
            if context:
                print(f"[GALAXY cooldown] {context} RSS={rss:.0f}MB over soft {_RSS_SOFT_MB}MB → extended sleep {base:.2f}s")
    except Exception:
        pass
    if base > 0:
        _t.sleep(base)


def _memory_check(context: str = "batch") -> str:
    """Returns one of 'ok' | 'soft' | 'hard'. Hard means skip further generation."""
    if not _WATCHDOG_ON:
        return "ok"
    rss = _get_rss_mb()
    if rss >= _RSS_HARD_MB:
        import gc
        gc.collect()
        rss_after = _get_rss_mb()
        if rss_after >= _RSS_HARD_MB:
            print(f"[GALAXY watchdog] HARD limit hit in {context}: RSS={rss_after:.0f}MB >= {_RSS_HARD_MB}MB — freezing further file generation")
            return "hard"
        rss = rss_after
    if rss >= _RSS_SOFT_MB:
        import time as _t
        print(f"[GALAXY watchdog] SOFT limit in {context}: RSS={rss:.0f}MB >= {_RSS_SOFT_MB}MB — pausing 0.5s for GC")
        _t.sleep(0.5)
        return "soft"
    return "ok"
