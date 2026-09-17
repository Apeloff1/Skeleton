"""Deterministic engine-neutral 3D physics foundation."""

from .body import BodyType, RigidBody
from .collision import (
    BroadPhasePair,
    ContactManifold,
    ContactPoint,
    SweepAndPruneBroadPhase,
    detect_collision,
    generate_manifolds,
)
from .errors import (
    BodyNotFoundError,
    DegenerateGeometryError,
    DuplicateBodyError,
    PhysicsError,
    PhysicsValidationError,
    SolverError,
    UnsupportedCollisionError,
)
from .gameplay import (
    GamePhysicsProfile,
    GameplayScale,
    JumpTuning,
    ProjectileSolution,
)
from .materials import CombineRule, ContactMaterial, PhysicsMaterial, combine_materials
from .math3d import AABB, Mat3, Quat, Transform, Vec3
from .queries import Ray, RayHit, raycast_body, sphere_cast_body
from .shapes import BoxShape, CollisionShape, MassProperties, PlaneShape, ShapeKind, SphereShape
from .solver import SequentialImpulseSolver, SolverStats
from .world import PhysicsSettings, PhysicsStepReceipt, PhysicsWorld

__all__ = [
    "AABB",
    "BodyNotFoundError",
    "BodyType",
    "BoxShape",
    "BroadPhasePair",
    "CollisionShape",
    "CombineRule",
    "ContactManifold",
    "ContactMaterial",
    "ContactPoint",
    "DegenerateGeometryError",
    "DuplicateBodyError",
    "GamePhysicsProfile",
    "GameplayScale",
    "JumpTuning",
    "MassProperties",
    "Mat3",
    "PhysicsError",
    "PhysicsMaterial",
    "PhysicsSettings",
    "PhysicsStepReceipt",
    "PhysicsValidationError",
    "PhysicsWorld",
    "PlaneShape",
    "ProjectileSolution",
    "Quat",
    "Ray",
    "RayHit",
    "RigidBody",
    "SequentialImpulseSolver",
    "ShapeKind",
    "SolverError",
    "SolverStats",
    "SphereShape",
    "SweepAndPruneBroadPhase",
    "Transform",
    "UnsupportedCollisionError",
    "Vec3",
    "combine_materials",
    "detect_collision",
    "generate_manifolds",
    "raycast_body",
    "sphere_cast_body",
]
