"""Stable error taxonomy for fail-closed frontier components."""
class FrontierError(Exception):
    """Base error for frontier contract violations."""

class AdmissionRejected(FrontierError):
    """Raised only by strict callers that require admission."""

class ContractViolation(FrontierError):
    """Raised when a component breaks a declared contract."""
