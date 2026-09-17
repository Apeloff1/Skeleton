"""Asset-lane provenance card. Rights gate is structural only."""

from __future__ import annotations

from typing import Any


ALLOWED_RIGHTS = frozenset({"original", "cc0", "cc-by", "internal"})


class RightsError(ValueError):
    """Provenance / rights violation."""


def rights_card(
    *,
    asset_id: str,
    source: str,
    license_id: str = "internal",
) -> dict[str, Any]:
    name = str(asset_id or "").strip()
    origin = str(source or "").strip()
    license_name = str(license_id or "").strip().lower()
    if not name or len(name) > 64:
        raise RightsError("asset_id invalid")
    if not origin.startswith("https://") and not origin.startswith("repo:"):
        raise RightsError("source must be https or repo pointer")
    if license_name not in ALLOWED_RIGHTS:
        raise RightsError("unknown license")
    return {
        "kind": "rights",
        "asset_id": name,
        "source": origin,
        "license": license_name,
        "release_ok": license_name in {"original", "cc0", "internal"},
        "stored_prose": 0,
    }
