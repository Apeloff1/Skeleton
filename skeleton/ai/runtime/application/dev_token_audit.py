"""Import-free audit of ``SKELETON_PUBLIC_DEV_SURFACES`` truthy tokens.

The flag name is locked by F-43. The accepted token set is a separate
fail-open surface: ``bool("false")`` is True in Python, but this parser
lower-cases and allow-lists. This snapshot reports those tokens without
reopening the env-flag name list.
"""

from __future__ import annotations

from typing import Final

from .audit_parse import public_dev_surface_tokens
from .capability_manifest import CAPABILITY_MANIFEST_VERSION


DEV_TOKEN_AUDIT_KIND: Final = "dev_token_audit"


def dev_token_audit_snapshot() -> dict[str, object]:
    """Return a JSON-serializable public-dev truthy-token audit."""

    tokens = public_dev_surface_tokens()
    rows = [{"token": token} for token in tokens]
    return {
        "schema_version": CAPABILITY_MANIFEST_VERSION,
        "kind": DEV_TOKEN_AUDIT_KIND,
        "tokens": rows,
        "names": tokens,
    }


def get_dev_token_audit_row(token_id: str) -> dict[str, object]:
    """Return one public-dev token row by token string."""

    if not isinstance(token_id, str):
        raise TypeError("token_id must be a string")
    normalized = token_id.strip().lower()
    if not normalized:
        raise ValueError("token_id must not be empty")
    for row in dev_token_audit_snapshot()["tokens"]:
        if row["token"] == normalized:
            return dict(row)
    raise KeyError(f"unknown token: {normalized}")
