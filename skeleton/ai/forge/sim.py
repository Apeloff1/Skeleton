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
    heat_end: float = 0.0

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
            "heat_end": round(self.heat_end, 3),
        }


@dataclass
class SessionReport:
    era: str
    primary_dps: float
    encounters: List[EncounterResult]
    collapse_max: float
    passed: bool
    notes: List[str] = field(default_factory=list)
    walk: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "era": self.era,
            "primary_dps": self.primary_dps,
            "passed": self.passed,
            "collapse_max": self.collapse_max,
            "encounters": [e.to_dict() for e in self.encounters],
            "notes": list(self.notes),
            "walk": self.walk,
        }


def _number(value: Any, label: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a number")
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        raise ValueError(f"{label} must be finite")
    if positive and not number > 0:
        raise ValueError(f"{label} must be positive")
    if number < 0:
        raise ValueError(f"{label} must be non-negative")
    return number


def _recipe(pack: Dict[str, Any]) -> Dict[str, Any]:
    recipes = pack.get("recipes")
    if not isinstance(recipes, list) or not recipes or not isinstance(recipes[0], dict):
        raise ValueError("a weapon recipe is required")
    return recipes[0]


def simulate_encounter(pack: Dict[str, Any], enemy: Dict[str, Any], *,
                       mode: str = "ideal", dt: float = 1.0 / 60.0,
                       max_t: Optional[float] = None,
                       heat0: float = 0.0) -> EncounterResult:
    if isinstance(dt, bool) or not isinstance(dt, (int, float)) or not float(dt) > 0:
        raise ValueError("dt must be positive")
    heat0 = _number(heat0, "heat0")
    rec = _recipe(pack)
    dmg = _number(rec.get("damage"), "damage", positive=True)
    rpm = _number(rec.get("rpm"), "rpm", positive=True)
    shot_heat = _number(rec.get("heat"), "heat")
    interval = 60.0 / rpm
    nominal_dps = dmg * rpm / 60.0
    primary = _number(pack.get("primary_dps", nominal_dps), "primary_dps", positive=True)
    if nominal_dps > 0:
        dmg *= primary / nominal_dps
    hp = _number(enemy.get("hp"), "hp", positive=True)
    if "ttk_target" in enemy:
        target = _number(enemy.get("ttk_target"), "ttk_target", positive=True)
    else:
        target = hp / primary
    heat_cfg = pack.get("heat") if isinstance(pack.get("heat"), dict) else {}
    max_heat = _number(heat_cfg["max_heat"], "max_heat", positive=True) if "max_heat" in heat_cfg else 100.0
    cool = _number(heat_cfg["passive_cool"], "passive_cool") if "passive_cool" in heat_cfg else 7.5
    crit = _number(heat_cfg["critical_ratio"], "critical_ratio", positive=True) if "critical_ratio" in heat_cfg else 0.78
    jeeves = pack.get("jeeves") if isinstance(pack.get("jeeves"), dict) else {}
    rising = _number(jeeves["heat_rising"], "heat_rising") if "heat_rising" in jeeves else 0.65
    session = pack.get("session") if isinstance(pack.get("session"), dict) else {}
    if "collapse_max" not in session:
        raise ValueError("collapse_max is required")
    collapse_max = _number(session.get("collapse_max"), "collapse_max", positive=True)
    if max_t is not None:
        ceiling = _number(max_t, "max_t", positive=True)
    else:
        ceiling = min(collapse_max, target * 8.0 + 5.0)

    if mode == "ideal":
        measured = hp / primary
        shots = max(1, int((hp + dmg - 1e-9) // dmg))
        killed = measured <= collapse_max
        return EncounterResult(
            enemy_id=str(enemy.get("id")), mode=mode, target_ttk=target,
            measured_ttk=measured, shots=int(shots), vents=0, overheat=False,
            collapsed=not killed, killed=killed,
            events=[SimEvent(measured, "ideal", "closed-form HP/DPS")],
            heat_end=heat0,
        )

    hp_left = hp
    heat = heat0
    t = 0.0
    cooldown = 0.0
    shots = 0
    vents = 0
    venting = heat / max(max_heat, 0.001) >= crit
    events: List[SimEvent] = []
    overheat = venting

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
                collapsed=True, killed=False, events=events, heat_end=heat,
            )

    killed = hp_left <= 0
    return EncounterResult(
        enemy_id=str(enemy.get("id")), mode=mode, target_ttk=target,
        measured_ttk=t if killed else ceiling, shots=shots, vents=vents,
        overheat=overheat, collapsed=False, killed=killed, events=events,
        heat_end=heat,
    )


def simulate_session(
    pack: Dict[str, Any],
    *,
    modes: tuple = ("ideal", "thermal"),
    graph: Optional[Dict[str, Any]] = None,
    plan: Optional[Dict[str, Any]] = None,
) -> SessionReport:
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
    walk_payload: Optional[Dict[str, Any]] = None
    from skeleton.forge.walk import walk_graph
    from skeleton.forge.world import generate_rooms
    if graph is None:
        graph = generate_rooms(
            pack, seed=str((plan or {}).get("seed") or pack.get("era")), plan=plan,
        )
    wr_ideal = walk_graph(pack, graph, plan=plan, mode="ideal")
    wr_therm = walk_graph(pack, graph, plan=plan, mode="thermal")
    if wr_therm.t + interval * max(1, wr_therm.fights) < wr_ideal.t:
        passed = False
        notes.append(
            f"thermal walk {wr_therm.t:.3f}s shorter than ideal {wr_ideal.t:.3f}s — heat clock inverted"
        )
    if not wr_therm.passed:
        passed = False
        notes.append("thermal walk failed: " + "; ".join(wr_therm.notes[:4]))
    elif not wr_ideal.passed:
        passed = False
        notes.append("ideal walk failed: " + "; ".join(wr_ideal.notes[:4]))
    walk_payload = wr_therm.to_dict()
    walk_payload["collapse_max"] = _number((pack.get("session") or {}).get("collapse_max"), "collapse_max", positive=True)
    walk_payload["ideal"] = {
        "t": round(wr_ideal.t, 4),
        "extracted": wr_ideal.extracted,
        "passed": wr_ideal.passed,
        "hops": wr_ideal.hops,
        "fights": wr_ideal.fights,
    }
    if not notes:
        notes.append("compiler identity holds; thermal ≥ ideal")
    if wr_therm.passed:
        notes.append(
            f"walk extracted thermal={wr_therm.t:.2f}s ideal={wr_ideal.t:.2f}s "
            f"hops={wr_therm.hops} heat_peak={wr_therm.heat_peak:.1f}"
        )
    return SessionReport(
        era=str(pack.get("era")),
        primary_dps=_number(pack.get("primary_dps"), "primary_dps", positive=True),
        encounters=encounters,
        collapse_max=_number((pack.get("session") or {}).get("collapse_max"), "collapse_max", positive=True),
        passed=passed,
        notes=notes,
        walk=walk_payload,
    )
