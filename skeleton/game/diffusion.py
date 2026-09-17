"""Discrete heat Laplacian on the labyrinth. Tokens stay periodic."""

from __future__ import annotations

from typing import Any

from skeleton.game.labyrinth import adjacency
from skeleton.game.token_clock import TOKEN_PERIOD


class DiffusionError(ValueError):
    """Heat diffusion contract violation."""


def field(graph: dict[str, Any]) -> dict[str, int]:
    return {str(node["id"]): int(node.get("heat") or 0) for node in graph.get("nodes") or []}


def step(graph: dict[str, Any], heat: dict[str, int], inject: dict[str, int] | None = None) -> dict[str, int]:
    adj = adjacency(graph)
    if set(heat) != set(adj):
        raise DiffusionError("heat field mismatch")
    nxt = dict(heat)
    extra = dict(inject or {})
    for node, nbrs in adj.items():
        if not nbrs:
            continue
        flow = 0
        here = heat[node]
        for nbr in nbrs:
            delta = heat[nbr] - here
            if delta > 0:
                flow += 1
            elif delta < 0:
                flow -= 1
        nxt[node] = max(0, min(16, here + (1 if flow > 0 else -1 if flow < 0 else 0) + int(extra.get(node, 0))))
    return nxt


def run(graph: dict[str, Any], ticks: int = 12, inject_at: str | None = None) -> dict[str, Any]:
    if ticks < 1 or ticks > 64:
        raise DiffusionError("ticks out of range")
    heat = field(graph)
    frames = [dict(heat)]
    tokens = 0
    for index in range(ticks):
        burst = {inject_at: 2} if inject_at and index % 3 == 0 else None
        heat = step(graph, heat, burst)
        if index % TOKEN_PERIOD == TOKEN_PERIOD - 1:
            tokens += 1
        frames.append(dict(heat))
    peak = max(heat.values()) if heat else 0
    return {
        "kind": "diffusion",
        "ticks": ticks,
        "final": heat,
        "peak": peak,
        "tokens": tokens,
        "every_frame": False,
        "frames": len(frames),
        "stored_prose": 0,
    }
