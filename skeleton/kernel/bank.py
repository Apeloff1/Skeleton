"""Live kernel bank. Instantiates only the active profile roster."""
from __future__ import annotations

from typing import Any, Dict

from skeleton.kernel.admission import Admission
from skeleton.kernel.affinity import Affinity
from skeleton.kernel.bloom import Bloom
from skeleton.kernel.fuse import Fuse
from skeleton.kernel.isolate import Isolate
from skeleton.kernel.prefetch import Prefetch
from skeleton.kernel.priority import Priority
from skeleton.kernel.quota import Quota
from skeleton.kernel.reclaim import Reclaim
from skeleton.kernel.throttle import Throttle
from skeleton.kernel.page import Page
from skeleton.kernel.tile import Tile
from skeleton.kernel.speculate import Speculate
from skeleton.kernel.prefix import Prefix
from skeleton.kernel.batch import Batch
from skeleton.kernel.radix import Radix
from skeleton.kernel.split import Split
from skeleton.kernel.slo import SLO
from skeleton.kernel.pin import Pin
from skeleton.kernel.pack import Pack
from skeleton.kernel.ops.engine import Engine
from skeleton.kernel.ops.gpu import GpuKernel
from skeleton.kernel.ram.arena import Arena
from skeleton.kernel.pipeline import Pipeline
from skeleton.kernel.wrap import BreakerCard, BulkheadCard
from skeleton.kernel.ops.embed import Embed
from skeleton.kernel.ops.dma import Dma
from skeleton.kernel.ops.catalog import Catalog
from skeleton.kernel.ram.check import Check
from skeleton.kernel.stock import Stock
from skeleton.kernel.ops.block import Block
from skeleton.kernel.stock_live import StockLive

_MAKERS = {
    "admission": lambda ov: Admission(window=16 if ov else 32),
    "quota": lambda ov: Quota(atoms=48 if ov else 180, walks=2 if ov else 8, dumps=1),
    "affinity": lambda ov: Affinity(),
    "throttle": lambda ov: Throttle(rate=2.0 if ov else 6.0, burst=4.0 if ov else 12.0),
    "bloom": lambda ov: Bloom(bits=512 if ov else 2048),
    "priority": lambda ov: Priority(),
    "reclaim": lambda ov: Reclaim(floor=32 if ov else 96),
    "isolate": lambda ov: Isolate(),
    "prefetch": lambda ov: Prefetch(depth=1 if ov else 3),
    "fuse": lambda ov: Fuse(cap=2 if ov else 8),
    "page": lambda ov: Page(frames=16 if ov else 64, size=8 if ov else 16),
    "tile": lambda ov: Tile(width=4 if ov else 8),
    "speculate": lambda ov: Speculate(k=2 if ov else 4),
    "prefix": lambda ov: Prefix(cap=8 if ov else 32),
    "batch": lambda ov: Batch(cap=1 if ov else 4),
    "radix": lambda ov: Radix(),
    "split": lambda ov: Split(prefill=2 if ov else 4, decode=4 if ov else 8),
    "slo": lambda ov: SLO(miss_cap=2 if ov else 5),
    "pin": lambda ov: Pin(cap=4 if ov else 12),
    "pack": lambda ov: Pack(width=4 if ov else 8),
    "ops": lambda ov: Engine(d=8 if ov else 16),
    "gpu": lambda ov: GpuKernel(d=8 if ov else 16),
    "ram": lambda ov: Arena(mobile=bool(ov)),
    "pipeline": lambda ov: Pipeline(mobile=bool(ov)),
    "breaker": lambda ov: BreakerCard(mobile=bool(ov)),
    "bulkhead": lambda ov: BulkheadCard(mobile=bool(ov)),
    "embed": lambda ov: Embed(d=8 if ov else 16),
    "dma": lambda ov: Dma(),
    "catalog": lambda ov: Catalog(),
    "check": lambda ov: Check(),
    "stock": lambda ov: Stock(),
    "block": lambda ov: Block(d=8 if ov else 16),
    "stock_live": lambda ov: StockLive(mobile=bool(ov)),
}

_LIVE: Dict[str, Any] = {}
_PROFILE = ""


def boot(profile: str = "", overlay: Dict[str, Any] | None = None) -> Dict[str, Any]:
    global _LIVE, _PROFILE
    from skeleton.kernel.profiles import card as profiles_card

    info = profiles_card()
    name = profile or str(info.get("profile") or "mobile")
    ov = overlay if overlay is not None else (info.get("overlay") or {})
    tight = bool(ov) or name in {"mobile", "tight"}
    wanted = list(info.get("kernels") or [])
    extra = [k for k in _MAKERS if k in wanted or k in (info.get("extra") or ())]
    # profile kernels are old names; new ten always candidate
    chosen = list(_MAKERS.keys())
    if name == "tight":
        chosen = ["throttle", "quota", "reclaim", "bloom", "page", "slo", "ops", "ram", "pipeline", "breaker"]
    elif name == "mobile":
        chosen = [
            "throttle", "quota", "reclaim", "bloom", "isolate", "prefetch", "admission",
            "page", "prefix", "batch", "slo", "pack", "ops", "ram", "gpu",
            "pipeline", "breaker", "bulkhead", "embed", "dma", "catalog",
            "check", "stock", "block", "stock_live",
        ]
    _LIVE = {k: _MAKERS[k](tight) for k in chosen}
    _PROFILE = name
    return {"kind": "kernel-bank", "profile": name, "n": len(_LIVE), "names": list(_LIVE), "stored_prose": 0}


def live() -> Dict[str, Any]:
    if not _LIVE:
        boot()
    return _LIVE


def get(name: str):
    return live().get(name)


def snapshot() -> Dict[str, Any]:
    bank = live()
    cards = {k: (v.card() if hasattr(v, "card") else {"kind": k}) for k, v in bank.items()}
    return {
        "kind": "kernel-bank",
        "profile": _PROFILE,
        "n": len(bank),
        "kernels": cards,
        "stored_prose": 0,
    }
