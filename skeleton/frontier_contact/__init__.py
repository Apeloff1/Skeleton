"""Authoritative broadphase, contact manifolds and segmented mass.

Sphere-sphere CCD calls the existing ``sweep_spheres`` solver. Sphere-box faces
call ``sweep_sphere_plane`` and clip to the rectangle. A spatial hash supplies
candidate pairs from bounds that are rebuilt from moving or deformable terrain
immediately before the query. Restitution and Coulomb friction are applied to
the manifold. Segmented bodies keep a torso and at least two limbs, a
pose-aware center of mass inside the segment hull, and a bone-length-preserving
retarget onto the same segment count.

Conservation bounds live in ``skeleton.frontier_contact.conservation``.
"""

from __future__ import annotations

from skeleton.frontier_contact.bodies import (
    AABB,
    BoxBody,
    SphereBody,
    deform_box,
    move_box,
)
from skeleton.frontier_contact.broadphase import overlapping_pairs, swept_bounds
from skeleton.frontier_contact.conservation import (
    ENERGY_INCREASE_EPSILON_J,
    IMPULSE_SUM_EPSILON_NS,
    LINEAR_MOMENTUM_EPSILON_NS,
)
from skeleton.frontier_contact.errors import ContactRejected
from skeleton.frontier_contact.hull import point_in_convex_hull
from skeleton.frontier_contact.manifold import (
    ContactManifold,
    discrete_slab_miss,
    sphere_box_manifold,
    sphere_sphere_manifold,
)
from skeleton.frontier_contact.segments import (
    MassSegment,
    PointImpulse,
    SegmentedBody,
    SegmentedRuntime,
    SegmentedStepResult,
    center_of_mass,
    place_body,
    pose_body,
    retarget_animation,
    segment_endpoints,
    segment_mass_points,
    standing_body,
    step_segmented,
    total_mass_kg,
)
from skeleton.frontier_contact.world import (
    ContactRecord,
    ContactRuntime,
    ContactStepResult,
    step_contacts,
)

__all__ = [
    "AABB",
    "ENERGY_INCREASE_EPSILON_J",
    "IMPULSE_SUM_EPSILON_NS",
    "LINEAR_MOMENTUM_EPSILON_NS",
    "BoxBody",
    "ContactManifold",
    "ContactRecord",
    "ContactRejected",
    "ContactRuntime",
    "ContactStepResult",
    "MassSegment",
    "PointImpulse",
    "SegmentedBody",
    "SegmentedRuntime",
    "SegmentedStepResult",
    "SphereBody",
    "center_of_mass",
    "deform_box",
    "discrete_slab_miss",
    "move_box",
    "overlapping_pairs",
    "place_body",
    "point_in_convex_hull",
    "pose_body",
    "retarget_animation",
    "segment_endpoints",
    "segment_mass_points",
    "sphere_box_manifold",
    "sphere_sphere_manifold",
    "standing_body",
    "step_contacts",
    "step_segmented",
    "swept_bounds",
    "total_mass_kg",
]
