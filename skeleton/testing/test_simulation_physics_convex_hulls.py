"""Canonical convex-hull topology, mass, query, collision, and CCD regressions."""
from __future__ import annotations

import math

import pytest

from skeleton.simulation.physics import (
    BoxShape,
    ConvexHullShape,
    ContinuousCollisionDetector,
    PhysicsSettings,
    PhysicsValidationError,
    PhysicsWorld,
    PlaneShape,
    Quat,
    Ray,
    RigidBody,
    SphereShape,
    Vec3,
    detect_collision,
    raycast_body,
    sphere_cast_body,
)


def _cube_vertices(half: float = 1.0) -> tuple[Vec3, ...]:
    h = half
    return (
        Vec3(-h, -h, -h), Vec3(-h, -h, h), Vec3(-h, h, -h), Vec3(-h, h, h),
        Vec3(h, -h, -h), Vec3(h, -h, h), Vec3(h, h, -h), Vec3(h, h, h),
    )


def _cube_triangles() -> tuple[tuple[int, int, int], ...]:
    return ((0,3,2),(0,1,3),(4,6,7),(4,7,5),(0,4,5),(0,5,1),(2,3,7),(2,7,6),(0,2,6),(0,6,4),(1,5,7),(1,7,3))


def _cube(half: float = 1.0) -> ConvexHullShape:
    return ConvexHullShape(_cube_vertices(half), _cube_triangles())


def test_convex_hull_rejects_unreferenced_vertex() -> None:
    """Every authored vertex must participate in the closed hull boundary.

    Otherwise support/world identity can observe geometry that mass integration
    ignores, making canonical physical identity depend on dead authored data.
    """
    vertices = _cube_vertices() + (Vec3.zero(),)
    with pytest.raises(PhysicsValidationError, match="referenced|boundary"):
        ConvexHullShape(vertices, _cube_triangles())
