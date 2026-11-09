"""Deterministic, bounded keyboard/controller movement against static world colliders.

This is a pure simulation input adapter, not evidence of a native Godot player.
Input is quantized before simulation so identical commands replay identically.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .flgb_simulation_runtime import (
    AABB, CharacterController, SimulationContractError, MAX_COORD, _is_int,
    narrowphase_aabb,
)

AXIS_LIMIT = 1000
MAX_COLLIDERS = 4096
MAX_STEP_NS = 100_000_000


@dataclass(frozen=True)
class MovementInput:
    horizontal: int
    vertical: int

    def __post_init__(self) -> None:
        for value in (self.horizontal, self.vertical):
            if not _is_int(value) or abs(value) > AXIS_LIMIT:
                raise SimulationContractError("invalid quantized movement axis")


@dataclass(frozen=True)
class MovementResult:
    controller: CharacterController
    blocked_x: bool
    blocked_y: bool


def step_character(
    controller: CharacterController,
    command: MovementInput,
    step_ns: int,
    obstacles: Sequence[AABB],
    *,
    half_extent: int = 1,
) -> MovementResult:
    """Apply axis-separated collision at a fixed tick, without tunnelling.

    Each axis is swept in integer world units. Collision is conservative:
    obstacles touching a swept rectangle block movement, including corners.
    This intentionally does not claim continuous 3D rigid-body physics.
    """
    if not _is_int(step_ns) or not 0 < step_ns <= MAX_STEP_NS:
        raise SimulationContractError("invalid character step duration")
    if not _is_int(half_extent) or not 0 < half_extent <= MAX_COORD:
        raise SimulationContractError("invalid character half extent")
    if not isinstance(obstacles, (list, tuple)) or len(obstacles) > MAX_COLLIDERS:
        raise SimulationContractError("invalid collision obstacle budget")
    if any(not isinstance(box, AABB) for box in obstacles):
        raise SimulationContractError("invalid collision obstacle")
    if len({box.collider_id for box in obstacles}) != len(obstacles):
        raise SimulationContractError("duplicate collision obstacle")
    if controller.entity_id in {box.collider_id for box in obstacles}:
        raise SimulationContractError("player collider identity conflict")
    if not isinstance(command, MovementInput):
        raise SimulationContractError("invalid movement input")
    # Normalize diagonals to avoid faster diagonal movement.
    magnitude = max(AXIS_LIMIT, abs(command.horizontal) + abs(command.vertical))
    budget = controller.max_speed_per_sec * step_ns // 1_000_000_000
    dx = budget * command.horizontal // magnitude
    dy = budget * command.vertical // magnitude
    x, y, z = controller.position

    def occupied(nx: int, ny: int, ox: int, oy: int) -> bool:
        if any(abs(v) + half_extent > MAX_COORD for v in (nx, ny, ox, oy, z)):
            raise SimulationContractError("movement world bounds exceeded")
        candidate = AABB(
            controller.entity_id,
            (min(ox, nx) - half_extent, min(oy, ny) - half_extent, z - half_extent),
            (max(ox, nx) + half_extent + 1, max(oy, ny) + half_extent + 1, z + half_extent + 1),
        )
        return any(narrowphase_aabb(candidate, obstacle) is not None for obstacle in obstacles)

    bx = bool(dx) and occupied(x + dx, y, x, y)
    nx = x if bx else x + dx
    by = bool(dy) and occupied(nx, y + dy, nx, y)
    ny = y if by else y + dy
    moved = controller.move((nx - x, ny - y, 0), step_ns)
    return MovementResult(moved, bx, by)
