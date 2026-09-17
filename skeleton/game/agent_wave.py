"""Wave-4 agents + pressure nodes."""

from __future__ import annotations

from typing import Any


class AgentWaveError(ValueError):
    pass


class PressureWaveError(ValueError):
    pass


AGENTS = tuple(f"ag_{i:02d}" for i in range(20))
PRESS = tuple(f"pr_{i:02d}" for i in range(24))


def agent_tick(agent: dict[str, Any], player: str, t: int) -> dict[str, Any]:
    name = str(agent.get("id") or "")
    if name not in AGENTS:
        raise AgentWaveError(name)
    i = AGENTS.index(name)
    nxt = dict(agent)
    nxt["id"] = name
    nxt["room"] = f"f{i // 5}r{(t + i) % 8}"
    nxt["alert"] = int(nxt["room"] == player)
    nxt["stored_prose"] = 0
    return nxt


def squad() -> list[dict[str, Any]]:
    return [{"id": name, "room": "f0r0", "alert": 0} for name in AGENTS]


def pressure_relax(name: str, value: int, neighbors: list[int]) -> int:
    if name not in PRESS:
        raise PressureWaveError(name)
    i = PRESS.index(name)
    if not neighbors:
        return max(0, min(16, int(value) + ((i % 5) - 2)))
    avg = sum(int(n) for n in neighbors) / len(neighbors)
    return max(0, min(16, int(round((int(value) * 2 + avg + (i % 3)) / 3))))
