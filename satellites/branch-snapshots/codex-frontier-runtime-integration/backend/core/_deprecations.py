"""
core/_deprecations.py — Centralised, one-shot deprecation announcer.

Self-deprecation pattern: modules that still use a legacy approach can emit
a SINGLE deprecation warning at first import to nudge migration. As of
2026-02, all known direct-``MongoClient(...)`` callers have been migrated
to use ``core.databases.get_sync_db()`` (the P2 funnel).

Why one-shot?
    Logs in K8s are precious — a warning that fires on every request is
    noise. The ``_seen`` set guarantees each (module, key) is announced at
    most once per process lifetime.

Usage:
    from core._deprecations import warn_deprecated
    warn_deprecated(
        __name__,
        "direct MongoClient — migrate to core.databases.get_sync_db()",
        "P2-mongo-funnel",
    )
"""
from __future__ import annotations

import sys
import warnings
from typing import Optional

_seen: set[tuple[str, str]] = set()


def warn_deprecated(
    module_name: str,
    message: str,
    migration_key: Optional[str] = None,
    stacklevel: int = 3,
) -> None:
    """Announce a deprecation exactly once per (module, migration_key).

    Args:
        module_name:    Usually ``__name__`` from the caller.
        message:        Short human-readable hint, e.g. "use X instead".
        migration_key:  Optional stable id; defaults to ``message``. Used
                        for the one-shot de-duplication key.
        stacklevel:     Forwarded to ``warnings.warn`` so the warning
                        points at the caller, not at this helper.
    """
    key = (module_name, migration_key or message)
    if key in _seen:
        return
    _seen.add(key)

    formatted = f"[deprecated] {module_name}: {message}"
    #  Stderr print — guaranteed visibility in container logs even when
    #  the warnings filter is set to 'ignore' (which uvicorn sometimes does).
    print(formatted, flush=True, file=sys.stderr)
    #  Standard Python warning — picked up by ``-Wd``, pytest, and IDEs.
    try:
        warnings.warn(formatted, DeprecationWarning, stacklevel=stacklevel)
    except Exception:
        #  Never let the announcer itself crash the importer.
        pass


def reset() -> None:
    """Test helper — clear the one-shot dedup set."""
    _seen.clear()
