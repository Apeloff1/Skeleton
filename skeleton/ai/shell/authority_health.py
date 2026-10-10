"""Compatibility shim — re-exports `skeleton.shells.ai.authority_health`.

This shim exists so callers of `skeleton.ai.shell.authority_health` keep working while `skeleton.shells.ai.authority_health` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.authority_health import (
    AuthorityHealthState,
    AuthorityHealthResult,
    AuthorityHealthProbe,
    CallableAuthorityHealthProbe,
    VersionedStateHealthProbe,
    AuthorityHealthPolicy,
    AuthorityHealthReport,
    AIAuthorityHealthGuard,
)

__all__ = ['AuthorityHealthState', 'AuthorityHealthResult', 'AuthorityHealthProbe', 'CallableAuthorityHealthProbe', 'VersionedStateHealthProbe', 'AuthorityHealthPolicy', 'AuthorityHealthReport', 'AIAuthorityHealthGuard']
