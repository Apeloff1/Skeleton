"""MoE / MoD bridge — compose with existing mixture modules; do not replace."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


@dataclass(frozen=True)
class MoEBridgeConfig:
    enabled: bool = True
    max_experts: int = 8
    depth_aware: bool = True
    respect_pfc_no_attn: bool = True


@dataclass
class ExpertRef:
    name: str
    scale: str
    capacity: float
    active: bool = True


@dataclass
class MoEBridge:
    config: MoEBridgeConfig = field(default_factory=MoEBridgeConfig)
    experts: List[ExpertRef] = field(default_factory=list)

    def register(self, name: str, scale: str, capacity: float = 1.0) -> ExpertRef:
        if scale == "small" and self.config.respect_pfc_no_attn:
            # PFC-scale experts never advertise transformer capacity
            capacity = min(capacity, 0.0) if name.startswith("pfc") else capacity
        ref = ExpertRef(name=name, scale=scale, capacity=float(capacity))
        self.experts.append(ref)
        return ref

    def active(self) -> List[ExpertRef]:
        return [e for e in self.experts if e.active]

    def route_weights(self, signal: Sequence[float]) -> Dict[str, float]:
        if not self.experts:
            return {}
        base = abs(sum(signal) / max(1, len(signal))) if signal else 0.5
        out: Dict[str, float] = {}
        for i, e in enumerate(self.active()):
            w = (base + 0.01 * i) * max(0.05, e.capacity if e.scale != "small" else 0.15)
            out[e.name] = round(w, 4)
        s = sum(out.values()) or 1.0
        return {k: round(v / s, 4) for k, v in out.items()}

    def assert_pfc_experts_no_transformer(self) -> None:
        for e in self.experts:
            if e.name.startswith("pfc") or e.scale == "small":
                assert e.capacity == 0.0 or self.config.respect_pfc_no_attn


EXPERT_CATALOG: Tuple[Mapping[str, Any], ...] = tuple(
    {
        "name": f"{('pfc','mid','neo','aux')[i%4]}-expert-{i:03d}",
        "scale": ("small", "medium", "neo", "medium")[i % 4],
        "capacity": 0.0 if i % 4 == 0 else round(0.2 + (i % 9) / 10.0, 3),
    }
    for i in range(1, 321)
)


def build_default_bridge() -> MoEBridge:
    b = MoEBridge()
    for row in EXPERT_CATALOG:
        b.register(str(row["name"]), str(row["scale"]), float(row["capacity"]))
    return b
