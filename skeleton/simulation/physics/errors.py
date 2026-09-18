"""Physics-domain exceptions.

The physics package fails closed on invalid or non-finite state.  Domain-specific
exceptions let callers distinguish malformed input, unsupported geometry, and
solver failures without depending on implementation details.
"""


class PhysicsError(Exception):
    """Base class for deterministic physics failures."""


class PhysicsValidationError(PhysicsError, ValueError):
    """Raised when public physics input violates an invariant."""


class DuplicateBodyError(PhysicsError):
    """Raised when a world receives an already registered body id."""


class BodyNotFoundError(PhysicsError, KeyError):
    """Raised when a requested rigid body does not exist."""


class UnsupportedCollisionError(PhysicsError):
    """Raised when a shape pair has no narrow-phase implementation."""


class DegenerateGeometryError(PhysicsError):
    """Raised when geometry cannot define a stable physical quantity."""


class SolverError(PhysicsError):
    """Raised when a solver encounters invalid or non-finite state."""


class ConvexQueryError(PhysicsError):
    """Raised when bounded convex geometry cannot produce a stable result."""


class DuplicateJointError(PhysicsError):
    """Raised when a world receives an already registered joint id."""


class JointNotFoundError(PhysicsError, KeyError):
    """Raised when a requested joint does not exist."""


class PhysicsSnapshotError(PhysicsError):
    """Raised when a physics snapshot is invalid or incompatible."""


class PhysicsReplayError(PhysicsError):
    """Raised when physics replay evidence is malformed."""


class PhysicsReplayDivergenceError(PhysicsReplayError):
    """Raised when deterministic physics replay diverges from recorded evidence."""
