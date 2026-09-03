"""Multi-kernel profiles. Hardware picks the roster.

House kernels already in-tree: scheduler, fair_queue, backpressure,
supervisor, watchdog, leases, election, merkle_log, clocks, vclock,
sandbox, work_queue, gossip, saga.

Profiles:
  tight   — pressure wall. life + pressure + log only.
  mobile  — phone/SoC. no election, gossip, saga. shorter leases.
  desktop — full roster.
  max     — full + gpu-tilted walk.

SOTA cited as handles only (MobileKernelBench, COSM, FlexServe,
MobileMoE, HeRo). No paper bodies. No generated CUDA/MNN kernels.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Tuple

CITE = (
    "https://arxiv.org/abs/2603.11935",
    "https://arxiv.org/abs/2606.30553",
    "https://arxiv.org/abs/2606.23370",
    "https://arxiv.org/abs/2605.27358",
    "https://arxiv.org/abs/2603.01661",
)

ROSTER: Dict[str, Tuple[str, ...]] = {
    "schedule": ("skeleton.kernel.scheduler", "skeleton.kernel.fair_queue"),
    "pressure": ("skeleton.kernel.backpressure",),
    "life": ("skeleton.kernel.supervisor", "skeleton.kernel.watchdog"),
    "fence": ("skeleton.kernel.leases", "skeleton.kernel.election"),
    "log": ("skeleton.kernel.merkle_log",),
    "time": ("skeleton.kernel.clocks", "skeleton.kernel.vclock"),
    "box": ("skeleton.kernel.sandbox",),
    "work": ("skeleton.kernel.work_queue",),
    "gossip": ("skeleton.kernel.gossip",),
    "saga": ("skeleton.kernel.saga",),
}

PROFILES: Dict[str, Tuple[str, ...]] = {
    "tight": ("pressure", "life", "log"),
    "mobile": ("schedule", "pressure", "life", "log", "time", "box"),
    "desktop": ("schedule", "pressure", "life", "fence", "log", "time", "box", "work", "gossip", "saga"),
    "max": ("schedule", "pressure", "life", "fence", "log", "time", "box", "work", "gossip", "saga"),
}

MOBILE_OVERLAY = {
    "walk_n": 2,
    "idle_cadence": 6,
    "dump_hot_bytes": 1 * 1024 * 1024,
    "ambition_cap": 4,
    "replay": 3,
    "social_cards": 2,
    "headroom": 0.50,
}


def pick(*, tier: str = "", pressure: float = 0.0, cpus: int = 1,
         avail_mb: int = 4096, gpu: bool = False) -> str:
    forced = str(os.environ.get("SKELETON_KERNEL") or "").lower()
    if forced in PROFILES:
        return forced
    if pressure >= 0.82 or tier == "tiny":
        return "tight"
    if tier in {"tiny", "small"} or cpus <= 4 or avail_mb < 4096 or not gpu:
        if tier in {"tiny", "small"} or cpus <= 4 or avail_mb < 3072:
            return "mobile"
    if gpu and tier in {"large", "max"}:
        return "max"
    return "desktop"


def card(*, caps: Dict[str, Any] | None = None) -> Dict[str, Any]:
    if caps is None:
        try:
            from skeleton.organism.caps import card as caps_card
            caps = caps_card()
        except Exception:
            caps = {"tier": "small", "pressure": 0.4, "cpus": 2, "avail_mb": 2048, "gpu": False}
    name = pick(
        tier=str(caps.get("tier") or "small"),
        pressure=float(caps.get("pressure") or 0),
        cpus=int(caps.get("cpus") or 1),
        avail_mb=int(caps.get("avail_mb") or caps.get("ram_mb") or 4096),
        gpu=bool(caps.get("gpu")),
    )
    kernels = list(PROFILES[name])
    overlay = dict(MOBILE_OVERLAY) if name in {"mobile", "tight"} else {}
    if name == "tight":
        overlay["walk_n"] = 1
        overlay["ambition_cap"] = 2
        overlay["headroom"] = 0.42
    present = []
    missing = []
    for k in kernels:
        ok = True
        for mod in ROSTER[k]:
            try:
                __import__(mod)
            except Exception:
                ok = False
        (present if ok else missing).append(k)
    return {
        "kind": "kernels",
        "profile": name,
        "kernels": present,
        "missing": missing,
        "overlay": overlay,
        "cite": list(CITE),
        "stored_prose": 0,
    }


def apply_overlay(org=None, *, neo=None) -> Dict[str, Any]:
    """Push mobile/tight overlay onto live scope ambition and dump heat."""
    info = card()
    overlay = info.get("overlay") or {}
    if overlay.get("dump_hot_bytes"):
        try:
            from skeleton.organism.chronicle import books
            books.HOT_BYTES = int(overlay["dump_hot_bytes"])
        except Exception:
            pass
    return info
