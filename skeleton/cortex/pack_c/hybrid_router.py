"""Hybrid router — PFC small (attn=False), midbrain/neo own transformers."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


class Scale(str, Enum):
    SMALL = "small"      # PFC — n-gram / skip-gram only
    MEDIUM = "medium"    # midbrain
    NEO = "neo"


@dataclass(frozen=True)
class Stimulus:
    text: str
    urgency: float = 0.5
    tags: Tuple[str, ...] = ()
    numbers: Tuple[float, ...] = ()

    def token_hint(self) -> int:
        return max(1, len(self.text.split()))


@dataclass(frozen=True)
class RouteHop:
    slot: str
    scale: Scale
    weight: float
    allow_transformer: bool
    reason: str


@dataclass(frozen=True)
class RoutePlan:
    hops: Tuple[RouteHop, ...]
    primary: str
    notes: Tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "primary": self.primary,
            "hops": [
                {
                    "slot": h.slot,
                    "scale": h.scale.value,
                    "weight": h.weight,
                    "allow_transformer": h.allow_transformer,
                    "reason": h.reason,
                }
                for h in self.hops
            ],
            "notes": list(self.notes),
        }


@dataclass
class HybridRouter:
    """Plan cortex slot visitation without violating PFC scale locks."""

    pfc_attn: bool = False
    prefer_neo_on_urgency: float = 0.75

    def __post_init__(self) -> None:
        if self.pfc_attn:
            raise ValueError("Pack C lock: PFC must keep attn=False")

    def plan(self, stim: Stimulus) -> RoutePlan:
        hops: List[RouteHop] = [
            RouteHop(
                slot="pfc",
                scale=Scale.SMALL,
                weight=0.35 if stim.urgency < self.prefer_neo_on_urgency else 0.2,
                allow_transformer=False,
                reason="PFC small-scale LM; attn=False lock",
            ),
            RouteHop(
                slot="midbrain",
                scale=Scale.MEDIUM,
                weight=0.3,
                allow_transformer=True,
                reason="midbrain owns medium transformer",
            ),
            RouteHop(
                slot="neo",
                scale=Scale.NEO,
                weight=0.45 if stim.urgency >= self.prefer_neo_on_urgency else 0.35,
                allow_transformer=True,
                reason="neo amalgam / speaking LM",
            ),
        ]
        # normalize weights
        total = sum(h.weight for h in hops) or 1.0
        hops = [
            RouteHop(h.slot, h.scale, round(h.weight / total, 4), h.allow_transformer, h.reason)
            for h in hops
        ]
        primary = max(hops, key=lambda h: h.weight).slot
        notes = (
            "pfc.allow_transformer=False",
            f"tokens~{stim.token_hint()}",
            f"urgency={stim.urgency:.3f}",
        )
        return RoutePlan(hops=tuple(hops), primary=primary, notes=notes)

    def assert_pfc_lock(self, plan: RoutePlan) -> None:
        for h in plan.hops:
            if h.slot == "pfc":
                assert h.allow_transformer is False
                assert h.scale is Scale.SMALL


# Route scenario board (structured catalog).
ROUTE_BOARD: Tuple[Mapping[str, Any], ...] = tuple(
    {
        "id": f"route-{i:04d}",
        "text": f"stimulus board row {i}",
        "urgency": round((i % 20) / 20.0, 3),
        "tags": ("pack_c", "router", f"g{i % 8}"),
    }
    for i in range(1, 501)
)


def plan_board(router: Optional[HybridRouter] = None) -> list[dict[str, Any]]:
    r = router or HybridRouter()
    out = []
    for row in ROUTE_BOARD:
        plan = r.plan(
            Stimulus(text=str(row["text"]), urgency=float(row["urgency"]), tags=tuple(row["tags"]))
        )
        r.assert_pfc_lock(plan)
        out.append({"id": row["id"], "primary": plan.primary, "plan": plan.as_dict()})
    return out
