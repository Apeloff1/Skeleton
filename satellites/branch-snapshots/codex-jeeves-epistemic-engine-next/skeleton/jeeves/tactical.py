"""Tactical Jeeves — game-loop advisor bound to a Forge era pack.

Priority cascade (highest first):
  3 CRITICAL  heat ≥ era critical, collapse window, player glass
  2 HIGH      heat rising, missing weapon, extract window
  1 NORMAL    forge recipe suggestion, enemy TTK note
  0 LOW       idle coaching

Deterministic given (era, telemetry). No LLM required.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from skeleton.forge.eras import compile_era


@dataclass(frozen=True)
class Advice:
    text: str
    priority: int  # 0 LOW .. 3 CRITICAL
    axis: str
    action: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"text": self.text, "priority": self.priority, "axis": self.axis, "action": self.action}


@dataclass
class WorldModel:
    era: str
    heat_ratio: float = 0.0
    collapse_ratio: float = 0.0
    cores: int = 0
    has_weapon: bool = False
    dps: float = 0.0
    alive: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "era": self.era,
            "heat_ratio": round(self.heat_ratio, 3),
            "collapse_ratio": round(self.collapse_ratio, 3),
            "cores": self.cores,
            "has_weapon": self.has_weapon,
            "dps": self.dps,
            "alive": self.alive,
        }


class TacticalBrain:
    """Priority-cascade advisor. Bind an era, then tick telemetry."""

    def __init__(self, era: str = "extraction_now") -> None:
        self.bind_era(era)
        self.log: List[Advice] = []

    def bind_pack(self, pack: Dict[str, Any]) -> Dict[str, Any]:
        self.pack = pack
        self.era = str(pack.get("era") or "extraction_now")
        j = pack.get("jeeves") or {}
        self.heat_rising = float(j.get("heat_rising", 0.65))
        self.heat_critical = float(j.get("heat_critical", 0.92))
        self.collapse_extract = 0.40
        self.collapse_late = 0.75
        return self.pack

    def bind_era(self, era: str) -> Dict[str, Any]:
        return self.bind_pack(compile_era(era))

    def observe(self, telemetry: Dict[str, Any]) -> WorldModel:
        heat = float(telemetry.get("heat", 0.0) or 0.0)
        max_heat = float(telemetry.get("max_heat") or self.pack["heat"]["max_heat"] or 1.0)
        collapse = float(telemetry.get("collapse_timer", self.pack["session"]["collapse_max"]) or 0.0)
        collapse_max = float(telemetry.get("collapse_max") or self.pack["session"]["collapse_max"] or 1.0)
        return WorldModel(
            era=self.era,
            heat_ratio=heat / max(max_heat, 0.001),
            collapse_ratio=1.0 - (collapse / max(collapse_max, 0.001)),
            cores=int(telemetry.get("cores") or 0),
            has_weapon=bool(telemetry.get("has_weapon")),
            dps=float(self.pack["primary_dps"]),
            alive=bool(telemetry.get("alive", True)),
        )

    def advise(self, telemetry: Dict[str, Any]) -> List[Advice]:
        world = self.observe(telemetry)
        out: List[Advice] = []
        if not world.alive:
            out.append(Advice("Operator down. Debrief loadout, then re-drop.", 3, "survival", "respawn"))
            self.log.extend(out)
            return out
        if world.heat_ratio >= self.heat_critical:
            out.append(Advice(
                f"Heat critical ({world.heat_ratio:.0%}). Vent or swap to kinetic — era {self.era} punishes overheat.",
                3, "heat", "vent"))
        elif world.heat_ratio >= self.heat_rising:
            out.append(Advice(
                f"Heat rising ({world.heat_ratio:.0%}). Sprint tax is live.",
                2, "heat", "cool"))
        if world.collapse_ratio >= self.collapse_late:
            out.append(Advice(
                "Collapse late. Extract now or you donate the run.",
                3, "collapse", "extract"))
        elif world.collapse_ratio >= self.collapse_extract and world.cores:
            out.append(Advice(
                f"{world.cores} core(s) held and extract window open.",
                2, "extract", "extract"))
        if not world.has_weapon:
            rec = (self.pack.get("recipes") or [{}])[0]
            out.append(Advice(
                f"No weapon. Assemble {rec.get('id', 'kinetic_basic')} first.",
                2, "forge", rec.get("id")))
        if not out:
            elite = next((e for e in self.pack["enemies"] if e["id"] == "elite"), None)
            out.append(Advice(
                f"{self.era} idle: primary DPS {world.dps}. Elite TTK ~{elite['ttk_target'] if elite else '?'}s.",
                0, "combat", None))
        out.sort(key=lambda a: -a.priority)
        self.log.extend(out)
        return out

    def recommend_next(self, telemetry: Dict[str, Any]) -> Advice:
        return self.advise(telemetry)[0]

    def status(self) -> Dict[str, Any]:
        return {
            "era": self.era,
            "primary_dps": self.pack["primary_dps"],
            "heat_rising": self.heat_rising,
            "heat_critical": self.heat_critical,
            "advice_log": len(self.log),
        }
