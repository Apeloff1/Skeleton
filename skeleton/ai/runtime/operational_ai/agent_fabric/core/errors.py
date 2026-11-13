"""Closed set of domain failures; model text never becomes an exception message."""
class FabricError(RuntimeError):
    """An AI fabric contract or custody requirement is not satisfied."""
class Invalid(FabricError):pass
class Conflict(FabricError):pass
class Integrity(FabricError):pass
class Busy(FabricError):pass
class Held(FabricError):pass
class Unauthorized(FabricError):pass
class Exhausted(FabricError):pass
