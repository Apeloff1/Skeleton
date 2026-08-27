"""Discrete-time combat/session simulator — the compiler's proof.

Ideal mode ignores heat: TTK must equal HP / primary_dPS (the identity
the era compiler claims). Thermal mode pays the heat tax: measured TTK
is never shorter than ideal, and a collapse clock can fail the run.
This is the piece that makes the cube falsifiable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SimEvent:
    t: float
    kind: str
    detail: str


@dataclass
class EncounterResult:
    enemy_id: str
    mode: str
    target_ttk: float
    measured_ttk: float
    shots: int
    vents: int
    overheat: bool
    collapsed: bool
    killed: bool
    events: List[SimEvent] = field(default_factory=list)

    @property
    def error(self) -> float:
        if self.target_ttk <= 0:
            return 0.0
        return abs(self.measured_ttk - self.target_ttk) / self.target_ttk

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enemy_id": self.enemy_id,
            "mode": self.mode,
            "target_ttk": round(self.target_ttk, 4),
            "measured_ttk": round(self.measured_ttk, 4),
            "error": round(self.error, 4),
            "shots": self.shots,
            "vents": self.vents,
            "overheat": self.overheat,
            "collapsed": self.collapsed,
            "killed": self.killed,
        }


@dataclass
class SessionReport:
    era: str
    primary_dps: float
    encounters: List[EncounterResult]
    collapse_max: float
    passed: bool
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "era": self.era,
            "primary_dps": self.primary_dps,
            "passed": self.passed,
            "collapse_max": self.collapse_max,
            "encounters": [e.to_dict() for e in self.encounters],
            "notes": list(self.notes),
        }


def _recipe(pack: Dict[str, Any]) -> Dict[str, Any]:
    recipes = pack.get("recipes") or []
    return recipes[0] if recipes else {"damage": 18, "rpm": 360, "heat": 6.2, "family": "kinetic"}


def simulate_encounter(pack: Dict[str, Any], enemy: Dict[str, Any], *,
                       mode: str = "ideal", dt: float = 1.0 / 60.0,
                       max_t: Optional[float] = None) -> EncounterResult:
    rec = _recipe(pack)
    dmg = float(rec.get("damage") or 18)
    rpm = float(rec.get("rpm") or 360)
    shot_heat = float(rec.get("heat") or 6.2)
    interval = 60.0 / max(rpm, 1.0)
    nominal_dps = dmg * rpm / 60.0
    primary = float(pack.get("primary_dps") or nominal_dps or 1.0)
    # scale shot damage so discrete DPS matches the compiler identity
    if nominal_dps > 0:
        dmg *= primary / nominal_dps
    hp = float(enemy.get("hp") or 1.0)
    target = float(enemy.get("ttk_target") or (hp / max(primary, 1e-6)))
    heat_cfg = pack.get("heat") or {}
    max_heat = float(heat_cfg.get("max_heat") or 100.0)
    cool = float(heat_cfg.get("passive_cool") or 7.5)
    crit = float(heat_cfg.get("critical_ratio") or 0.78)
    rising = float((pack.get("jeeves") or {}).get("heat_rising") or 0.65)
    collapse_max = float((pack.get("session") or {}).get("collapse_max") or 9999)
    ceiling = max_t if max_t is not None else min(collapse_max, target * 8.0 + 5.0)

    if mode == "ideal":
        measured = hp / max(primary, 1e-9)
        shots = max(1, int((hp + dmg - 1e-9) // dmg))
        return EncounterResult(
            enemy_id=str(enemy.get("id")), mode=mode, target_ttk=target,
            measured_ttk=measured, shots=int(shots), vents=0, overheat=False,
            collapsed=False, killed=True, events=[SimEvent(measured, "ideal", "closed-form HP/DPS")],
        )

    hp_left = hp
    heat = 0.0
    t = 0.0
    cooldown = 0.0
    shots = 0
    vents = 0
    venting = False
    events: List[SimEvent] = []
    overheat = False

    while t < ceiling and hp_left > 0:
        t += dt
        cooldown = max(0.0, cooldown - dt)
        heat = max(0.0, heat - cool * dt)
        if mode == "thermal":
            ratio = heat / max(max_heat, 0.001)
            if ratio >= crit:
                if not venting:
                    vents += 1
                    overheat = True
                    events.append(SimEvent(t, "overheat", f"ratio={ratio:.2f}"))
                venting = True
            elif venting and ratio <= rising:
                venting = False
                events.append(SimEvent(t, "vent_clear", f"ratio={ratio:.2f}"))
        firing = (mode == "ideal") or not venting
        if firing and cooldown <= 0.0:
            hp_left -= dmg
            shots += 1
            cooldown = interval
            if mode == "thermal":
                heat = min(max_heat * 1.15, heat + shot_heat)
        if t >= collapse_max:
            events.append(SimEvent(t, "collapse", "timer elapsed"))
            return EncounterResult(
                enemy_id=str(enemy.get("id")), mode=mode, target_ttk=target,
                measured_ttk=t, shots=shots, vents=vents, overheat=overheat,
                collapsed=True, killed=False, events=events,
            )

    killed = hp_left <= 0
    return EncounterResult(
        enemy_id=str(enemy.get("id")), mode=mode, target_ttk=target,
        measured_ttk=t if killed else ceiling, shots=shots, vents=vents,
        overheat=overheat, collapsed=False, killed=killed, events=events,
    )


def simulate_session(pack: Dict[str, Any], *, modes: tuple = ("ideal", "thermal")) -> SessionReport:
    notes: List[str] = []
    encounters: List[EncounterResult] = []
    passed = True
    for enemy in pack.get("enemies") or []:
        for mode in modes:
            result = simulate_encounter(pack, enemy, mode=mode)
            encounters.append(result)
            if mode == "ideal" and enemy.get("id") == "trash":
                if not result.killed or result.error > 0.20:
                    passed = False
                    notes.append(
                        f"ideal trash TTK error {result.error:.2%} "
                        f"(measured {result.measured_ttk:.3f}s vs {result.target_ttk:.3f}s)"
                    )
            if mode == "thermal" and result.target_ttk >= 1.0 and result.measured_ttk + 0.2 < result.target_ttk * 0.75:
                passed = False
                notes.append(f"thermal {enemy.get('id')} faster than compiler allows")
    by_key = {(e.enemy_id, e.mode): e for e in encounters}
    rec = _recipe(pack)
    interval = 60.0 / max(float(rec.get("rpm") or 360), 1.0)
    if ("trash", "ideal") in by_key and ("trash", "thermal") in by_key:
        # one shot-interval of quantization slack: discrete overkill can beat HP/DPS by < 1 shot
        if by_key[("trash", "thermal")].measured_ttk + interval < by_key[("trash", "ideal")].measured_ttk:
            passed = False
            notes.append("thermal TTK shorter than ideal — heat model inverted")
    if not notes:
        notes.append("compiler identity holds; thermal ≥ ideal")
    return SessionReport(
        era=str(pack.get("era")),
        primary_dps=float(pack.get("primary_dps") or 0.0),
        encounters=encounters,
        collapse_max=float((pack.get("session") or {}).get("collapse_max") or 0.0),
        passed=passed,
        notes=notes,
    )
