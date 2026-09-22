"""Handoff protocol card. Delegates to Mesh."""

from __future__ import annotations

from skeleton.swarm.mesh import Mesh


def handoff(a: str, b: str, task: str, mesh: Mesh | None = None) -> dict:
    return (mesh or Mesh()).handoff(a, b, task)
