"""Key-encryption-key (KEK) provider port and adapters.

Webhook signing secrets are envelope-encrypted (see ``envelope``): each
secret gets a fresh data key (DEK) which is wrapped by a KEK. KEKs are
identified by a short ``key_id`` that is stored in clear in the envelope
header so the right KEK can be found on read and so rotation can find rows
still wrapped by an old key.

Adapters:

* ``StaticKeyProvider``  - explicit in-process keys (tests, composition).
* ``EnvKeyProvider``     - keys from environment variables (deployments).

Only *test* keys ever appear in this repository. Real keys are supplied by
the environment / secret manager at runtime.
"""
from __future__ import annotations

import base64
import binascii
import os
import re
from typing import Mapping, Protocol

KEY_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,31}$")
KEK_BYTES = 32  # AES-256

KEYS_ENV = "SKELETON_BACKEND_CORE_KEKS"            # "kid1:<b64>,kid2:<b64>"
ACTIVE_ENV = "SKELETON_BACKEND_CORE_ACTIVE_KEK"    # "kid2"
REQUIRE_ENV = "SKELETON_BACKEND_CORE_REQUIRE_KEK"  # "1" -> fail closed when unset


class KeyProviderError(RuntimeError):
    """Raised for missing/unknown/malformed keys. Never carries key material."""


class KeyProvider(Protocol):
    def active_key_id(self) -> str: ...
    def get(self, key_id: str) -> bytes:
        """Return the 32-byte KEK for ``key_id`` or raise ``KeyProviderError``."""
    def key_ids(self) -> tuple[str, ...]: ...


def _check(key_id: str, key: bytes) -> None:
    if not isinstance(key_id, str) or not KEY_ID_RE.match(key_id):
        raise KeyProviderError("invalid key id")
    if not isinstance(key, (bytes, bytearray)) or len(key) != KEK_BYTES:
        raise KeyProviderError(f"key {key_id!r} must be {KEK_BYTES} bytes")


class StaticKeyProvider:
    """Immutable provider over an explicit mapping. ``active`` must be present."""

    def __init__(self, keys: Mapping[str, bytes], active: str) -> None:
        if not keys:
            raise KeyProviderError("at least one key is required")
        for kid, key in keys.items():
            _check(kid, key)
        if active not in keys:
            raise KeyProviderError("active key id is not among the configured keys")
        self._keys = {k: bytes(v) for k, v in keys.items()}
        self._active = active

    def active_key_id(self) -> str:
        return self._active

    def get(self, key_id: str) -> bytes:
        try:
            return self._keys[key_id]
        except KeyError:
            raise KeyProviderError(f"unknown key id {key_id!r}") from None

    def key_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._keys))

    def with_active(self, key_id: str) -> "StaticKeyProvider":
        """Return a copy that wraps new data under ``key_id`` (rotation step)."""
        return StaticKeyProvider(self._keys, key_id)

    def __repr__(self) -> str:  # never print key material
        return f"StaticKeyProvider(active={self._active!r}, key_ids={self.key_ids()!r})"


def parse_keyring(spec: str) -> dict[str, bytes]:
    """Parse ``"kid:<base64>,kid2:<base64>"`` (standard or urlsafe base64)."""
    keys: dict[str, bytes] = {}
    for part in filter(None, (p.strip() for p in spec.split(","))):
        if ":" not in part:
            raise KeyProviderError("keyring entries must look like '<key_id>:<base64 key>'")
        kid, b64 = part.split(":", 1)
        kid, b64 = kid.strip(), b64.strip()
        try:
            key = base64.b64decode(b64 + "=" * (-len(b64) % 4), altchars=b"-_", validate=False)
        except (binascii.Error, ValueError):
            raise KeyProviderError(f"key {kid!r} is not valid base64") from None
        _check(kid, key)
        if kid in keys:
            raise KeyProviderError(f"duplicate key id {kid!r}")
        keys[kid] = key
    return keys


class EnvKeyProvider(StaticKeyProvider):
    """Reads ``SKELETON_BACKEND_CORE_KEKS`` / ``SKELETON_BACKEND_CORE_ACTIVE_KEK``.

    When ``ACTIVE`` is unset and exactly one key is configured, that key is
    active. With several keys an explicit active id is required so a deploy
    never silently changes which key wraps new secrets.
    """

    def __init__(self, environ: Mapping[str, str] | None = None) -> None:
        env = os.environ if environ is None else environ
        keys = parse_keyring(env.get(KEYS_ENV, ""))
        if not keys:
            raise KeyProviderError(f"{KEYS_ENV} is not set")
        active = env.get(ACTIVE_ENV, "").strip()
        if not active:
            if len(keys) != 1:
                raise KeyProviderError(f"{ACTIVE_ENV} is required when several keys are configured")
            active = next(iter(keys))
        super().__init__(keys, active)


def provider_from_env(environ: Mapping[str, str] | None = None) -> KeyProvider | None:
    """Env provider, ``None`` when no keyring is configured and not required.

    ``SKELETON_BACKEND_CORE_REQUIRE_KEK=1`` turns a missing keyring into an
    error (fail closed); production deployments should set it.
    """
    env = os.environ if environ is None else environ
    if not env.get(KEYS_ENV, "").strip():
        if env.get(REQUIRE_ENV, "").strip().lower() in {"1", "true", "yes"}:
            raise KeyProviderError(f"{KEYS_ENV} is required ({REQUIRE_ENV} is set)")
        return None
    return EnvKeyProvider(env)


def encode_key(key: bytes) -> str:
    """Helper for operators/tests: base64 text for a KEK."""
    return base64.b64encode(key).decode()


__all__ = ["KeyProvider", "KeyProviderError", "StaticKeyProvider", "EnvKeyProvider",
           "provider_from_env", "parse_keyring", "encode_key", "KEK_BYTES",
           "KEYS_ENV", "ACTIVE_ENV", "REQUIRE_ENV"]
