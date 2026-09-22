"""Import-free audit of process-ownership and seal environment flags.

Durable cortex restore is opt-in via ``SKELETON_OWN``. HMAC secrets and the
public-dev surface flag live in other modules. This snapshot lists those
``os.environ.get`` keys without importing cortex, HMAC, or the API package.
"""

from __future__ import annotations

from typing import Final

from .audit_parse import AUDITED_ENV_MODULES, audited_environ_flags
from .capability_manifest import CAPABILITY_MANIFEST_VERSION


ENV_FLAG_AUDIT_KIND: Final = "env_flag_audit"


def env_flag_audit_snapshot() -> dict[str, object]:
    """Return a JSON-serializable environment-flag audit."""

    flags = audited_environ_flags()
    rows: list[dict[str, object]] = []
    for item in flags:
        rows.append(
            {
                "name": item["name"],
                "module": item["module"],
            }
        )
    return {
        "schema_version": CAPABILITY_MANIFEST_VERSION,
        "kind": ENV_FLAG_AUDIT_KIND,
        "modules": list(AUDITED_ENV_MODULES),
        "flags": rows,
        "names": [str(item["name"]) for item in rows],
    }


def get_env_flag_audit_row(flag_id: str) -> dict[str, object]:
    """Return one environment-flag audit row by variable name."""

    if not isinstance(flag_id, str):
        raise TypeError("flag_id must be a string")
    normalized = flag_id.strip()
    if not normalized:
        raise ValueError("flag_id must not be empty")
    for row in env_flag_audit_snapshot()["flags"]:
        if row["name"] == normalized:
            return dict(row)
    raise KeyError(f"unknown flag: {normalized}")
