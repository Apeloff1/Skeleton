"""Mesh handoff. offer / accept / refuse / expire. N-cap 8."""

from __future__ import annotations

from skeleton.swarm.law import N_CAP


class Mesh:
    def __init__(self) -> None:
        self.offers: dict[str, str] = {}
        self.accepted: list[tuple[str, str]] = []
        self.refused: list[str] = []
        self.expired: list[str] = []

    def offer(self, agent: str, task: str) -> str:
        if len(self.offers) >= N_CAP:
            raise ValueError("n-cap")
        self.offers[agent] = task
        return "offer"

    def accept(self, agent: str, peer: str) -> str:
        if agent not in self.offers:
            return "refuse"
        self.accepted.append((agent, peer))
        return "accept"

    def refuse(self, agent: str) -> str:
        self.refused.append(agent)
        self.offers.pop(agent, None)
        return "refuse"

    def expire(self, agent: str) -> str:
        self.expired.append(agent)
        self.offers.pop(agent, None)
        return "expire"

    def handoff(self, a: str, b: str, task: str) -> dict:
        self.offer(a, task)
        state = self.accept(a, b)
        return {
            "kind": "handoff",
            "state": state,
            "from": a,
            "to": b,
            "task": task,
            "stored_prose": 0,
        }
