"""OS-backed single-writer custody for operator-owned AI runtime sessions."""
from .session import ProcessSessionFence, SessionFenceError
__all__ = ["ProcessSessionFence", "SessionFenceError"]
