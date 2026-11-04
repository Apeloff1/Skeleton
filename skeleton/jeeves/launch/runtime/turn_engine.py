"""Launch-ready turn engine and multi-agent coordinator.

Operational systems for running game sessions and coordinating
multiple AI agents during autonomous game construction.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass, field
import time
import uuid


@dataclass
class TurnResult:
    turn: int
    actions: List[Dict[str, Any]]
    state_delta: Dict[str, Any]
    events: List[str]
    ok: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "turn": self.turn,
            "actions": self.actions,
            "state_delta": self.state_delta,
            "events": self.events,
            "ok": self.ok,
        }


class TurnEngine:
    """
    Tick-based game loop for local AI sessions.

    Each tick:
      1. Collects agent actions
      2. Resolves combat/movement/interaction
      3. Emits events
      4. Advances state
    """

    def __init__(self, seed: int = 0) -> None:
        self.turn = 0
        self.seed = seed
        self._agents: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {}
        self._state: Dict[str, Any] = {"health": 100, "position": "start", "inventory": []}
        self._log: List[TurnResult] = []

    def register(self, agent_id: str, decide: Callable[[Dict[str, Any]], Dict[str, Any]]) -> None:
        self._agents[agent_id] = decide

    def tick(self) -> TurnResult:
        self.turn += 1
        actions = []
        events = []
        delta: Dict[str, Any] = {}

        for aid, decide in self._agents.items():
            try:
                act = decide(self._state)
                actions.append({"agent": aid, **act})
                if act.get("action") == "attack":
                    events.append(f"{aid}_attacked")
                    delta["last_attack"] = aid
                elif act.get("action") == "move":
                    events.append(f"{aid}_moved")
                    self._state["position"] = act.get("target", self._state.get("position"))
                elif act.get("action") == "pickup":
                    item = act.get("item")
                    if item:
                        self._state.setdefault("inventory", []).append(item)
                        events.append(f"{aid}_picked_{item}")
            except Exception as e:
                events.append(f"{aid}_error:{type(e).__name__}")

        result = TurnResult(turn=self.turn, actions=actions, state_delta=delta, events=events)
        self._log.append(result)
        return result

    def run(self, ticks: int = 10) -> List[Dict[str, Any]]:
        results = []
        for _ in range(max(1, ticks)):
            results.append(self.tick().to_dict())
        return results

    def state(self) -> Dict[str, Any]:
        return dict(self._state)

    def history(self) -> List[Dict[str, Any]]:
        return [r.to_dict() for r in self._log]


class AgentCoordinator:
    """
    Coordinates multiple specialized AI agents during game construction.

    Agents report capabilities; the coordinator assigns work and collects results.
    """

    def __init__(self) -> None:
        self._agents: Dict[str, Dict[str, Any]] = {}
        self._tasks: List[Dict[str, Any]] = []
        self._results: List[Dict[str, Any]] = []

    def register_agent(self, agent_id: str, capabilities: List[str], handler: Optional[Callable] = None) -> Dict[str, Any]:
        if not agent_id or not capabilities:
            return {"ok": False, "reason": "missing_id_or_caps"}
        self._agents[agent_id] = {
            "capabilities": capabilities,
            "handler": handler,
            "busy": False,
            "completed": 0,
        }
        return {"ok": True, "agent_id": agent_id, "capabilities": capabilities}

    def assign(self, task: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not task:
            return {"ok": False, "reason": "empty_task"}
        capable = [aid for aid, a in self._agents.items() if task in a["capabilities"] and not a["busy"]]
        if not capable:
            return {"ok": False, "reason": "no_capable_agent", "task": task}
        chosen = capable[0]
        self._agents[chosen]["busy"] = True
        task_id = str(uuid.uuid4())[:8]
        entry = {"task_id": task_id, "task": task, "agent": chosen, "payload": payload or {}, "status": "assigned"}
        self._tasks.append(entry)
        return {"ok": True, **entry}

    def complete(self, task_id: str, result: Dict[str, Any]) -> Dict[str, Any]:
        for t in self._tasks:
            if t["task_id"] == task_id:
                t["status"] = "done"
                t["result"] = result
                agent = t["agent"]
                if agent in self._agents:
                    self._agents[agent]["busy"] = False
                    self._agents[agent]["completed"] += 1
                self._results.append({"task_id": task_id, "result": result})
                return {"ok": True, "task_id": task_id}
        return {"ok": False, "reason": "task_not_found"}

    def status(self) -> Dict[str, Any]:
        return {
            "agents": len(self._agents),
            "tasks": len(self._tasks),
            "completed": sum(1 for t in self._tasks if t["status"] == "done"),
            "busy": sum(1 for a in self._agents.values() if a["busy"]),
        }
