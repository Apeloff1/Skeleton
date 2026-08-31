"""Hardware-aware multi-cap table.

Probe RAM / CPU / GPU, pick a tier, then apply headroom so the
organism never sits on the hardware wall. Default headroom 0.62 —
a little lower than raw capacity on purpose.

Override:
  SKELETON_HEADROOM=0.55
  SKELETON_TIER=small
"""
from __future__ import annotations

import os
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional


HEADROOM = 0.62


@dataclass(frozen=True)
class Caps:
    tier: str
    headroom: float
    ram_mb: int
    avail_mb: int
    cpus: int
    gpu: bool
    atoms: int
    vault: int
    rules: int
    query: int
    residual: int
    replay: int
    social_cards: int
    idle_cadence: int
    growth_clip: float
    cdx_bytes: int
    banks_list: int


def _meminfo() -> tuple[int, int]:
    total = avail = 0
    path = Path("/proc/meminfo")
    if not path.exists():
        return 4096, 2048
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("MemTotal:"):
                total = int(line.split()[1]) // 1024
            elif line.startswith("MemAvailable:"):
                avail = int(line.split()[1]) // 1024
    except (OSError, ValueError):
        return 4096, 2048
    if total <= 0:
        total = 4096
    if avail <= 0:
        avail = max(512, total // 2)
    return total, avail


def _cpus() -> int:
    return max(1, int(os.cpu_count() or 1))


def _gpu() -> bool:
    if Path("/dev/nvidia0").exists() or Path("/dev/kfd").exists():
        return True
    if os.environ.get("CUDA_VISIBLE_DEVICES") not in {None, "", "-1"}:
        return True
    return False


def _tier(avail_mb: int, forced: str = "") -> str:
    if forced in {"tiny", "small", "medium", "large", "max"}:
        return forced
    if avail_mb < 1536:
        return "tiny"
    if avail_mb < 6144:
        return "small"
    if avail_mb < 14336:
        return "medium"
    if avail_mb < 28672:
        return "large"
    return "max"


def _scale(headroom: float, gpu: bool, cpus: int) -> float:
    s = float(headroom)
    if gpu:
        s *= 1.08
    if cpus >= 8:
        s *= 1.04
    return min(0.85, s)


def compute(*, headroom: Optional[float] = None, tier: Optional[str] = None,
            ram_mb: Optional[int] = None, avail_mb: Optional[int] = None,
            cpus: Optional[int] = None, gpu: Optional[bool] = None) -> Caps:
    env_h = os.environ.get("SKELETON_HEADROOM")
    h = float(headroom if headroom is not None else (env_h or HEADROOM))
    h = min(0.85, max(0.35, h))
    tot, av = _meminfo()
    tot = int(ram_mb if ram_mb is not None else tot)
    av = int(avail_mb if avail_mb is not None else av)
    ncpu = int(cpus if cpus is not None else _cpus())
    has_gpu = bool(_gpu() if gpu is None else gpu)
    name = _tier(av, str(tier or os.environ.get("SKELETON_TIER") or ""))
    s = _scale(h, has_gpu, ncpu)
    usable_gb = max(0.4, (av / 1024.0) * s)
    atoms = int(min(1800, max(48, usable_gb * 70)))
    vault = atoms
    rules = int(min(63, max(7, usable_gb * 3.2)))
    query = int(min(48, max(8, usable_gb * 2.4)))
    residual = int(min(32, max(8, 8 + usable_gb)))
    replay = int(min(12, max(3, 3 + usable_gb * 0.4)))
    social = int(min(8, max(2, 2 + usable_gb * 0.35)))
    idle = 5 if name in {"tiny", "small"} else 4
    growth = 1.12 if name == "tiny" else 1.16 if name == "small" else 1.20 if name == "medium" else 1.22
    cdx = 1024 if name == "tiny" else 1536 if name == "small" else 2048
    banks = int(min(48, max(12, usable_gb * 3)))
    return Caps(
        tier=name, headroom=round(s, 4), ram_mb=tot, avail_mb=av, cpus=ncpu, gpu=has_gpu,
        atoms=atoms, vault=vault, rules=rules, query=query, residual=residual,
        replay=replay, social_cards=social, idle_cadence=idle,
        growth_clip=growth, cdx_bytes=cdx, banks_list=banks,
    )


_LIVE: Optional[Caps] = None


def live() -> Caps:
    global _LIVE
    if _LIVE is None:
        _LIVE = compute()
    return _LIVE


def reset_caps() -> None:
    global _LIVE
    _LIVE = None


def card() -> Dict[str, Any]:
    c = live()
    d = asdict(c)
    d["kind"] = "caps"
    d["law"] = "headroom-below-wall"
    d["stored_prose"] = 0
    try:
        usage = shutil.disk_usage(Path.cwd())
        d["disk_free_mb"] = int(usage.free // (1024 * 1024))
    except OSError:
        d["disk_free_mb"] = 0
    return d
