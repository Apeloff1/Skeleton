"""Public configuration snapshots.

Settings objects may hold service tokens. Anything returned to logs, health
payloads, or HTTP must pass through :func:`public_settings_snapshot`, which
rejects secret-shaped keys even if a future summary starts including them.
"""

from __future__ import annotations

from typing import Any, Mapping


_SECRET_MARKERS = (
    "secret",
    "password",
    "token",
    "api_key",
    "credential",
    "private_key",
    "authorization",
)


class PublicConfigError(ValueError):
    """A configuration snapshot would expose secret material."""


def assert_public_mapping(payload: object, *, path: str = "") -> None:
    """Reject mappings whose keys look like secrets. Values are not returned."""

    if isinstance(payload, Mapping):
        for key, value in payload.items():
            name = str(key)
            lowered = name.casefold()
            if any(marker in lowered for marker in _SECRET_MARKERS):
                where = f"{path}.{name}" if path else name
                raise PublicConfigError(f"configuration snapshot contains secret key {where}")
            assert_public_mapping(value, path=f"{path}.{name}" if path else name)
        return
    if isinstance(payload, (list, tuple)):
        for index, value in enumerate(payload):
            assert_public_mapping(value, path=f"{path}[{index}]")


def public_settings_snapshot(settings: object) -> dict[str, Any]:
    """Return ``settings.summary()`` after a secret-key check."""

    summary = getattr(settings, "summary", None)
    if not callable(summary):
        raise PublicConfigError("settings object has no summary()")
    payload = summary()
    if not isinstance(payload, dict):
        raise PublicConfigError("settings summary must be an object")
    assert_public_mapping(payload)
    return payload


__all__ = ["PublicConfigError", "assert_public_mapping", "public_settings_snapshot"]
