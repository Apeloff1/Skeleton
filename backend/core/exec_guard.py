"""Shared guard for user-controlled code execution."""

import os


def code_execution_enabled() -> bool:
    """Return whether user-controlled code execution is explicitly allowed."""
    value = os.environ.get("ALLOW_UNSAFE_CODE_EXECUTION", "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def execution_disabled_message(action: str = "Code execution") -> str:
    return (
        f"{action} is disabled by default. "
        "Set ALLOW_UNSAFE_CODE_EXECUTION=true in a trusted environment to opt in."
    )


def execution_disabled_response(action: str = "Code execution") -> dict:
    return {
        "ok": False,
        "disabled": True,
        "error": execution_disabled_message(action),
    }


def require_execution_allowed(action: str = "Code execution") -> bool:
    """Return whether the requested execution action is explicitly enabled."""
    return code_execution_enabled()
