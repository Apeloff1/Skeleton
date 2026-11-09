from __future__ import annotations
"""
Artificial Prefrontal Cortex — executive control for the exocortex.

  dlPFC — working memory / task orchestrator
  vmPFC — risk & value / biological cost gate
  OFC   — context-dependent switchboard
  aPFC  — meta-goal / multi-goal master tracker
"""

import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class WorkingFrame:
    frame_id: str
    goal: str
    items: List[Dict[str, Any]] = field(default_factory=list)
    sequence: List[str] = field(default_factory=list)
    constraints: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict:
        return asdict(self)


class DorsolateralPFC:
    """Working memory & task orchestration — pulls history + constraints into one cache."""

    def __init__(self, capacity: int = 7):
        self.capacity = capacity  # Miller-ish slots
        self.frames: Dict[str, WorkingFrame] = {}
        self.active_id: Optional[str] = None
        self.logs: List[dict] = []

    def allocate(
        self,
        goal: str,
        *,
        historical: Optional[List[Dict[str, Any]]] = None,
        constraints: Optional[Dict[str, Any]] = None,
        tools: Optional[List[str]] = None,
        steps: Optional[List[str]] = None,
    ) -> WorkingFrame:
        items = []
        for h in (historical or [])[:3]:
            items.append({"type": "history", "data": h})
        if constraints:
            items.append({"type": "constraints", "data": constraints})
        for t in (tools or [])[:4]:
            items.append({"type": "tool", "data": t})
        # trim to capacity
        items = items[: self.capacity]
        seq = steps or [f"use:{t}" for t in (tools or [])] or ["analyze", "execute", "log"]
        frame = WorkingFrame(
            frame_id=str(uuid.uuid4())[:10],
            goal=goal,
            items=items,
            sequence=seq,
            constraints=constraints or {},
        )
        self.frames[frame.frame_id] = frame
        self.active_id = frame.frame_id
        self.logs.append({"ts": datetime.utcnow().isoformat(), "event": "allocate", "goal": goal, "slots": len(items)})
        return frame

    def active(self) -> Optional[WorkingFrame]:
        return self.frames.get(self.active_id) if self.active_id else None

    def release(self, frame_id: Optional[str] = None):
        fid = frame_id or self.active_id
        if fid and fid in self.frames:
            del self.frames[fid]
            if self.active_id == fid:
                self.active_id = next(iter(self.frames), None)
            self.logs.append({"ts": datetime.utcnow().isoformat(), "event": "release", "frame_id": fid})


class VentromedialPFC:
    """
    Cost-benefit / resource pricing from biological state.
    Certainty-oriented: hard thresholds, not probability clouds.
    """

    def __init__(self, energy_floor: float = 0.35, pain_ceiling: float = 0.6, sleep_floor: float = 5.5):
        self.energy_floor = energy_floor
        self.pain_ceiling = pain_ceiling
        self.sleep_floor = sleep_floor
        self.logs: List[dict] = []

    def evaluate(
        self,
        *,
        energy: float,
        pain: float = 0.0,
        sleep_hours: float = 7.0,
        valence: float = 0.0,
        task_cost: float = 0.5,  # 0..1 relative cognitive cost
        task_label: str = "",
    ) -> Dict[str, Any]:
        reasons = []
        block = False
        if energy < self.energy_floor:
            block = True
            reasons.append(f"energy {energy} < floor {self.energy_floor}")
        if pain >= self.pain_ceiling:
            block = True
            reasons.append(f"pain {pain} >= ceiling {self.pain_ceiling}")
        if sleep_hours < self.sleep_floor and task_cost >= 0.4:
            block = True
            reasons.append(f"sleep {sleep_hours}h insufficient for task_cost {task_cost}")
        if valence < -0.35 and task_cost >= 0.6:
            block = True
            reasons.append("low valence + high cost")

        # value score exact weighted sum (not probability)
        value = (
            0.35 * energy
            + 0.25 * max(0.0, 1.0 - pain)
            + 0.25 * min(1.0, sleep_hours / 8.0)
            + 0.15 * max(0.0, min(1.0, (valence + 1) / 2))
            - 0.4 * task_cost
        )
        decision = "block" if block else ("allow_light" if value < 0.25 else "allow")
        msg = (
            f"vmPFC blocks '{task_label or 'task'}': " + "; ".join(reasons)
            if block
            else f"vmPFC allows '{task_label or 'task'}' (value={value:.3f})"
        )
        out = {
            "decision": decision,
            "blocked": block,
            "value": round(value, 3),
            "reasons": reasons,
            "message": msg,
            "jeeves": msg if block else None,
        }
        self.logs.append({"ts": datetime.utcnow().isoformat(), **out})
        return out


class OrbitofrontalSwitchboard:
    """Context-dependent protocol switch on environment / country / anomaly."""

    def __init__(self):
        self.protocol: Dict[str, Any] = {
            "country": "NO",
            "city": "Lillestrøm",
            "reward_weight": 1.0,
            "holiday_set": "NO",
            "priority_mode": "standard",
        }
        self.logs: List[dict] = []

    def apply_location(self, country: str, city: str) -> Dict[str, Any]:
        prev = dict(self.protocol)
        self.protocol["country"] = country.upper()
        self.protocol["city"] = city
        self.protocol["holiday_set"] = country.upper()
        self.protocol["priority_mode"] = "travel_adapt"
        self.protocol["reward_weight"] = 1.1  # slightly higher reward under travel load
        ev = {"event": "location_switch", "prev": prev, "protocol": dict(self.protocol)}
        self.logs.append({"ts": datetime.utcnow().isoformat(), **ev})
        return {"ok": True, **ev}

    def apply_anomaly(self, *, noise_db: float = 0.0, emergency: bool = False) -> Dict[str, Any]:
        prev = dict(self.protocol)
        if emergency:
            self.protocol["priority_mode"] = "emergency"
            self.protocol["reward_weight"] = 0.5
        elif noise_db >= 70:
            self.protocol["priority_mode"] = "sensory_protect"
            self.protocol["reward_weight"] = 1.25
        ev = {"event": "anomaly", "noise_db": noise_db, "emergency": emergency, "protocol": dict(self.protocol)}
        self.logs.append({"ts": datetime.utcnow().isoformat(), **ev})
        return {"ok": True, "prev": prev, **ev}

    def status(self) -> Dict[str, Any]:
        return dict(self.protocol)


@dataclass
class MetaGoal:
    goal_id: str
    title: str
    horizon: str  # e.g. 10y | 1y | quarter
    progress_pct: float = 0.0
    suspended: bool = False
    subgoals: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class AnteriorPFC:
    """Meta-goal manager — holds master blueprint while sub-tasks run."""

    def __init__(self):
        self.goals: Dict[str, MetaGoal] = {}
        self.logs: List[dict] = []

    def register(self, title: str, horizon: str = "10y", subgoals: Optional[List[str]] = None) -> MetaGoal:
        g = MetaGoal(
            goal_id=str(uuid.uuid4())[:10],
            title=title,
            horizon=horizon,
            subgoals=subgoals or [],
        )
        self.goals[g.goal_id] = g
        self.logs.append({"ts": datetime.utcnow().isoformat(), "event": "register", "goal": title})
        return g

    def suspend(self, goal_id: str) -> Dict[str, Any]:
        g = self.goals.get(goal_id)
        if not g:
            return {"ok": False, "error": "not_found"}
        g.suspended = True
        self.logs.append({"ts": datetime.utcnow().isoformat(), "event": "suspend", "goal_id": goal_id})
        return {"ok": True, "goal": g.to_dict()}

    def resume(self, goal_id: str) -> Dict[str, Any]:
        g = self.goals.get(goal_id)
        if not g:
            return {"ok": False, "error": "not_found"}
        g.suspended = False
        self.logs.append({"ts": datetime.utcnow().isoformat(), "event": "resume", "goal_id": goal_id})
        return {"ok": True, "goal": g.to_dict()}

    def route_progress(self, goal_id: str, delta_pct: float) -> Dict[str, Any]:
        g = self.goals.get(goal_id)
        if not g:
            return {"ok": False, "error": "not_found"}
        g.progress_pct = max(0.0, min(100.0, g.progress_pct + delta_pct))
        self.logs.append(
            {
                "ts": datetime.utcnow().isoformat(),
                "event": "progress",
                "goal_id": goal_id,
                "delta": delta_pct,
                "now": g.progress_pct,
            }
        )
        return {"ok": True, "goal": g.to_dict()}

    def master_view(self) -> Dict[str, Any]:
        return {
            "goals": [g.to_dict() for g in self.goals.values()],
            "active": [g.to_dict() for g in self.goals.values() if not g.suspended],
            "suspended": [g.to_dict() for g in self.goals.values() if g.suspended],
        }


class PrefrontalCortex:
    """Unified PFC executive."""

    def __init__(self):
        self.dlpfc = DorsolateralPFC()
        self.vmpfc = VentromedialPFC()
        self.ofc = OrbitofrontalSwitchboard()
        self.apfc = AnteriorPFC()

    def executive_decide(
        self,
        goal: str,
        *,
        energy: float,
        pain: float = 0.0,
        sleep_hours: float = 7.0,
        valence: float = 0.0,
        task_cost: float = 0.5,
        historical: Optional[List[Dict[str, Any]]] = None,
        tools: Optional[List[str]] = None,
        steps: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        # vmPFC gate first
        gate = self.vmpfc.evaluate(
            energy=energy,
            pain=pain,
            sleep_hours=sleep_hours,
            valence=valence,
            task_cost=task_cost,
            task_label=goal,
        )
        if gate["blocked"]:
            return {
                "allowed": False,
                "gate": gate,
                "frame": None,
                "protocol": self.ofc.status(),
                "master": self.apfc.master_view(),
            }
        frame = self.dlpfc.allocate(
            goal,
            historical=historical,
            constraints={"energy": energy, "protocol": self.ofc.status()},
            tools=tools,
            steps=steps,
        )
        return {
            "allowed": True,
            "gate": gate,
            "frame": frame.to_dict(),
            "protocol": self.ofc.status(),
            "master": self.apfc.master_view(),
        }

    def status(self) -> Dict[str, Any]:
        return {
            "dlpfc_active": self.dlpfc.active().to_dict() if self.dlpfc.active() else None,
            "vmpfc_tail": self.vmpfc.logs[-3:],
            "ofc": self.ofc.status(),
            "apfc": self.apfc.master_view(),
        }
