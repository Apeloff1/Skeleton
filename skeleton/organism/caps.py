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
    load: float
    pressure: float


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


def _loadavg() -> float:
    path = Path("/proc/loadavg")
    if not path.exists():
        return 0.0
    try:
        return float(path.read_text(encoding="utf-8").split()[0])
    except (OSError, ValueError, IndexError):
        return 0.0


def _pressure(avail_mb: int, ram_mb: int, load: float, cpus: int) -> float:
    mem_p = 1.0 - (float(avail_mb) / max(1.0, float(ram_mb)))
    cpu_p = min(1.0, float(load) / max(1.0, float(cpus)))
    return max(0.0, min(1.0, 0.65 * mem_p + 0.35 * cpu_p))


def _scale(headroom: float, gpu: bool, cpus: int, pressure: float) -> float:
    s = float(headroom)
    if gpu:
        s *= 1.08
    if cpus >= 8:
        s *= 1.04
    s *= max(0.45, 1.0 - 0.40 * float(pressure))
    return min(0.85, max(0.32, s))


def compute(*, headroom: Optional[float] = None, tier: Optional[str] = None,
            ram_mb: Optional[int] = None, avail_mb: Optional[int] = None,
            cpus: Optional[int] = None, gpu: Optional[bool] = None,
            load: Optional[float] = None) -> Caps:
    env_h = os.environ.get("SKELETON_HEADROOM")
    h = float(headroom if headroom is not None else (env_h or HEADROOM))
    h = min(0.85, max(0.35, h))
    tot, av = _meminfo()
    tot = int(ram_mb if ram_mb is not None else tot)
    av = int(avail_mb if avail_mb is not None else av)
    ncpu = int(cpus if cpus is not None else _cpus())
    has_gpu = bool(_gpu() if gpu is None else gpu)
    ld = float(load if load is not None else _loadavg())
    press = _pressure(av, tot, ld, ncpu)
    name = _tier(av, str(tier or os.environ.get("SKELETON_TIER") or ""))
    s = _scale(h, has_gpu, ncpu, press)
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
        load=round(ld, 3), pressure=round(press, 4),
    )


_LIVE: Optional[Caps] = None
_EASY = 0
_LAST_ACTION = "hold"


def live() -> Caps:
    global _LIVE
    if _LIVE is None:
        _LIVE = compute()
    return _LIVE


def reset_caps() -> None:
    global _LIVE, _EASY, _LAST_ACTION
    _LIVE = None
    _EASY = 0
    _LAST_ACTION = "hold"


def adapt(*, probe: Optional[Caps] = None) -> Dict[str, Any]:
    """Shrink immediately under pressure. Ease only after two calm probes."""
    global _LIVE, _EASY, _LAST_ACTION
    fresh = probe or compute()
    cur = live()
    if fresh.atoms < cur.atoms or fresh.pressure > cur.pressure + 0.08:
        _LIVE = fresh
        _EASY = 0
        _LAST_ACTION = "tighten"
    elif fresh.atoms > cur.atoms and fresh.pressure + 0.05 < cur.pressure:
        _EASY += 1
        if _EASY >= 2:
            _LIVE = fresh
            _EASY = 0
            _LAST_ACTION = "ease"
        else:
            _LAST_ACTION = "hold"
    else:
        _LAST_ACTION = "hold"
    return {
        "kind": "caps-adapt",
        "action": _LAST_ACTION,
        "pressure": live().pressure,
        "atoms": live().atoms,
        "tier": live().tier,
        "stored_prose": 0,
    }


def trim_mesh(mesh, caps: Optional[Caps] = None) -> Dict[str, Any]:
    """Drop oldest low-value captures when the shelf exceeds the live cap."""
    cap = caps or live()
    seen = {}
    for lib in (*mesh.brains.values(), mesh.wiki):
        for atom in lib.all():
            if not atom.superseded_by:
                seen[atom.id] = atom
    evicted = 0
    extra = len(seen) - int(cap.atoms)
    if extra > 0:
        victims = sorted(
            (a for a in seen.values() if a.kind in {"capture", "zettel", "index"} and "internalized" not in (a.tags or ())),
            key=lambda a: (a.confidence, a.ts),
        )
        for atom in victims[:extra]:
            atom.superseded_by = "cap-trim"
            evicted += 1
    rules = [a for a in seen.values() if a.kind == "principle" and not a.superseded_by]
    if len(rules) > int(cap.rules):
        for atom in sorted(rules, key=lambda a: a.confidence)[: len(rules) - int(cap.rules)]:
            atom.superseded_by = "cap-trim"
            evicted += 1
    return {"kind": "cap-trim", "evicted": evicted, "atoms_cap": cap.atoms, "stored_prose": 0}


def card() -> Dict[str, Any]:
    c = live()
    d = asdict(c)
    d["kind"] = "caps"
    d["law"] = "headroom-below-wall"
    d["action"] = _LAST_ACTION
    d["stored_prose"] = 0
    try:
        usage = shutil.disk_usage(Path.cwd())
        d["disk_free_mb"] = int(usage.free // (1024 * 1024))
    except OSError:
        d["disk_free_mb"] = 0
    try:
        from skeleton.kernel.profiles import card as kernels_card
        d["kernels"] = kernels_card(caps=d)
    except Exception:
        pass
    try:
        d["mix"] = __import__("skeleton.organism.context_step", fromlist=["mix_card"]).mix_card()
    except Exception:
        pass
    return d
