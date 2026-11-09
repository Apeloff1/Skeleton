"""Compatibility entrypoint for the canonical bot activation security gate.

The implementation lives under skeleton.security.activation_security so
application modules do not depend on the ambiguous top-level core namespace.
This module remains as a stable CLI/import shim for older callers.
"""
from __future__ import annotations

from skeleton.security.activation_security import (
    ActivationSecurityError,
    GATED_WORKFLOWS,
    REPO_ROOT,
    SECURITY_GATES,
    _CREDENTIAL_ENV,
    _VERIFIED,
    _credential_free_env,
    enforce_bot_activation_security,
    main,
    run_bot_activation_security_baseline,
)

__all__ = [
    "ActivationSecurityError",
    "GATED_WORKFLOWS",
    "REPO_ROOT",
    "SECURITY_GATES",
    "enforce_bot_activation_security",
    "main",
    "run_bot_activation_security_baseline",
]


if __name__ == "__main__":
    raise SystemExit(main())
