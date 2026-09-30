"""keyholder — process signing identity (gameforge-rs keyholder.rs port).

One keypair per process, minted at first use or loaded from
``GF_KEYHOLDER_SEED`` (hex, 32 bytes). The public identity is derived;
the seed never leaves this module — callers get signatures, not keys.

Placeholder crypto (sha256) matching the RS interface; swap to real
ed25519 later without touching callers.
"""

from __future__ import annotations

import hashlib
import os
import threading
import time
from dataclasses import dataclass
import hmac
import json
from typing import Mapping, Optional

_ENV = "GF_KEYHOLDER_SEED"
_lock = threading.Lock()
_instance: Optional["Keyholder"] = None


def _sha256(*parts: bytes) -> bytes:
    h = hashlib.sha256()
    for p in parts:
        h.update(p)
    return h.digest()


class Keyholder:
    """Process-local signing identity."""

    def __init__(self, seed: bytes) -> None:
        if len(seed) != 32:
            raise ValueError("keyholder seed must be 32 bytes")
        self._seed = seed
        # public = sha256(seed) truncated — placeholder until real ed25519.
        self._public = _sha256(seed)[:16].hex()

    @classmethod
    def mint(cls, seed: bytes) -> "Keyholder":
        return cls(seed)

    @classmethod
    def from_env(cls, env: Optional[str] = None) -> "Keyholder":
        raw = env if env is not None else os.environ.get(_ENV)
        if raw:
            try:
                decoded = bytes.fromhex(raw.strip())
            except ValueError as exc:
                raise ValueError("GF_KEYHOLDER_SEED must be hex") from exc
            if len(decoded) != 32:
                raise ValueError("GF_KEYHOLDER_SEED must decode to 32 bytes")
            return cls.mint(decoded)
        # Ephemeral: mix time + pid then sha256 → 32 bytes.
        now = time.time_ns().to_bytes(8, "little", signed=False)
        pid = os.getpid().to_bytes(4, "little", signed=False)
        pad = b"\x00" * 20
        material = (now + pid + pad)[:32]
        return cls.mint(_sha256(material))

    @property
    def public_hex(self) -> str:
        return self._public

    def sign(self, msg: bytes) -> str:
        """Deterministic placeholder: sha256(seed || msg)."""
        return _sha256(self._seed, msg).hex()

    def verify(self, msg: bytes, signature: str) -> bool:
        return hmac.compare_digest(self.sign(msg), signature)


@dataclass(frozen=True, slots=True)
class SignedEnvelope:
    """Signature bound to one key-continuity generation."""

    key_id: str
    generation: int
    signature: str

    def __post_init__(self) -> None:
        if len(self.key_id) != 32:
            raise ValueError("key_id must be 32 hex characters")
        try:
            bytes.fromhex(self.key_id)
        except ValueError as exc:
            raise ValueError("key_id must be hexadecimal") from exc
        if isinstance(self.generation, bool) or not isinstance(self.generation, int):
            raise ValueError("generation must be an integer")
        if self.generation < 1:
            raise ValueError("generation must be positive")
        if len(self.signature) != 64:
            raise ValueError("signature must be SHA-256 hex")
        try:
            bytes.fromhex(self.signature)
        except ValueError as exc:
            raise ValueError("signature must be hexadecimal") from exc


@dataclass(frozen=True, slots=True)
class KeyRotationReceipt:
    """Content-addressed receipt proving one continuity rotation."""

    previous_key_id: str
    new_key_id: str
    generation: int
    revoked_previous: bool

    @property
    def receipt_digest(self) -> str:
        payload = json.dumps(
            {
                "generation": self.generation,
                "new_key_id": self.new_key_id,
                "previous_key_id": self.previous_key_id,
                "revoked_previous": self.revoked_previous,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True, slots=True)
class KeyContinuityEntry:
    key_id: str
    introduced_generation: int
    revoked_generation: int | None = None


class KeyContinuityError(RuntimeError):
    """Key rotation, revocation, or restoration violated continuity."""


class KeyRevokedError(KeyContinuityError):
    """A signature references a key revoked for the requested generation."""


class KeyContinuityRing:
    """In-memory process key history with explicit rotation and revocation.

    The ring keeps private seeds internal, emits only public key identifiers in
    snapshots, and supports verification both against current policy and against
    an explicitly requested historical generation.
    """

    def __init__(self, initial: Keyholder) -> None:
        if not isinstance(initial, Keyholder):
            raise TypeError("initial must be Keyholder")
        key_id = initial.public_hex
        self._keys: dict[str, Keyholder] = {key_id: initial}
        self._entries: dict[str, KeyContinuityEntry] = {
            key_id: KeyContinuityEntry(key_id, 1, None)
        }
        self._active_key_id = key_id
        self._generation = 1

    @property
    def generation(self) -> int:
        return self._generation

    @property
    def active_key_id(self) -> str:
        return self._active_key_id

    def entries(self) -> tuple[KeyContinuityEntry, ...]:
        return tuple(
            sorted(
                self._entries.values(),
                key=lambda item: (item.introduced_generation, item.key_id),
            )
        )

    def sign(self, msg: bytes) -> SignedEnvelope:
        if not isinstance(msg, bytes):
            raise TypeError("msg must be bytes")
        key = self._keys[self._active_key_id]
        return SignedEnvelope(
            key_id=self._active_key_id,
            generation=self._generation,
            signature=key.sign(msg),
        )

    def rotate(
        self,
        seed: bytes,
        *,
        revoke_previous: bool = False,
    ) -> KeyRotationReceipt:
        previous = self._active_key_id
        replacement = Keyholder.mint(seed)
        new_key_id = replacement.public_hex
        if new_key_id in self._keys:
            raise KeyContinuityError("rotation key already exists in continuity history")

        self._generation += 1
        generation = self._generation
        self._keys[new_key_id] = replacement
        self._entries[new_key_id] = KeyContinuityEntry(
            new_key_id,
            generation,
            None,
        )
        if revoke_previous:
            old = self._entries[previous]
            self._entries[previous] = KeyContinuityEntry(
                old.key_id,
                old.introduced_generation,
                generation,
            )
        self._active_key_id = new_key_id
        return KeyRotationReceipt(
            previous_key_id=previous,
            new_key_id=new_key_id,
            generation=generation,
            revoked_previous=revoke_previous,
        )

    def revoke(self, key_id: str) -> KeyContinuityEntry:
        if key_id == self._active_key_id:
            raise KeyContinuityError("active key must be rotated before revocation")
        current = self._entries.get(key_id)
        if current is None:
            raise KeyContinuityError("cannot revoke unknown key")
        if current.revoked_generation is not None:
            return current
        self._generation += 1
        revoked = KeyContinuityEntry(
            current.key_id,
            current.introduced_generation,
            self._generation,
        )
        self._entries[key_id] = revoked
        return revoked

    def _key_for_generation(
        self,
        envelope: SignedEnvelope,
        *,
        generation: int,
    ) -> Keyholder:
        if isinstance(generation, bool) or not isinstance(generation, int):
            raise ValueError("generation must be an integer")
        if generation < 1 or generation > self._generation:
            raise ValueError("generation is outside continuity history")
        entry = self._entries.get(envelope.key_id)
        if entry is None:
            raise KeyContinuityError("signature key is unknown")
        if envelope.generation < entry.introduced_generation:
            raise KeyContinuityError("signature predates key introduction")
        if envelope.generation > generation:
            raise KeyContinuityError("signature postdates requested generation")
        if entry.introduced_generation > generation:
            raise KeyContinuityError("key did not exist at requested generation")
        if (
            entry.revoked_generation is not None
            and generation >= entry.revoked_generation
        ):
            raise KeyRevokedError("key was revoked at requested generation")
        return self._keys[envelope.key_id]

    def verify(self, msg: bytes, envelope: SignedEnvelope) -> bool:
        """Verify under current revocation policy."""

        key = self._key_for_generation(
            envelope,
            generation=self._generation,
        )
        return key.verify(msg, envelope.signature)

    def verify_historical(
        self,
        msg: bytes,
        envelope: SignedEnvelope,
        *,
        at_generation: int,
    ) -> bool:
        """Verify as policy existed at an earlier continuity generation."""

        key = self._key_for_generation(
            envelope,
            generation=at_generation,
        )
        return key.verify(msg, envelope.signature)

    def snapshot(self) -> dict[str, object]:
        """Return a seed-free identity snapshot suitable for durable storage."""

        return {
            "schema_version": 1,
            "generation": self._generation,
            "active_key_id": self._active_key_id,
            "entries": [
                {
                    "key_id": item.key_id,
                    "introduced_generation": item.introduced_generation,
                    "revoked_generation": item.revoked_generation,
                }
                for item in self.entries()
            ],
        }

    @classmethod
    def restore(
        cls,
        snapshot: Mapping[str, object],
        *,
        seeds_by_key_id: Mapping[str, bytes],
    ) -> "KeyContinuityRing":
        """Restore continuity only when every retained public identity matches.

        Private seeds are supplied out-of-band; the durable snapshot never
        contains them.
        """

        if not isinstance(snapshot, Mapping):
            raise TypeError("snapshot must be a mapping")
        if snapshot.get("schema_version") != 1:
            raise KeyContinuityError("unsupported key continuity schema")
        generation = snapshot.get("generation")
        active_key_id = snapshot.get("active_key_id")
        entries = snapshot.get("entries")
        if isinstance(generation, bool) or not isinstance(generation, int):
            raise KeyContinuityError("snapshot generation is invalid")
        if generation < 1:
            raise KeyContinuityError("snapshot generation is invalid")
        if not isinstance(active_key_id, str):
            raise KeyContinuityError("snapshot active key is invalid")
        if not isinstance(entries, list) or not entries:
            raise KeyContinuityError("snapshot entries are invalid")

        parsed: dict[str, KeyContinuityEntry] = {}
        restored_keys: dict[str, Keyholder] = {}
        for raw in entries:
            if not isinstance(raw, Mapping):
                raise KeyContinuityError("snapshot entry is invalid")
            key_id = raw.get("key_id")
            introduced = raw.get("introduced_generation")
            revoked = raw.get("revoked_generation")
            if not isinstance(key_id, str):
                raise KeyContinuityError("snapshot key id is invalid")
            if isinstance(introduced, bool) or not isinstance(introduced, int):
                raise KeyContinuityError("snapshot introduction generation is invalid")
            if introduced < 1 or introduced > generation:
                raise KeyContinuityError("snapshot introduction generation is invalid")
            if revoked is not None and (
                isinstance(revoked, bool)
                or not isinstance(revoked, int)
                or revoked <= introduced
                or revoked > generation
            ):
                raise KeyContinuityError("snapshot revocation generation is invalid")
            if key_id in parsed:
                raise KeyContinuityError("snapshot contains duplicate key id")
            seed = seeds_by_key_id.get(key_id)
            if seed is None:
                raise KeyContinuityError("missing seed for retained key identity")
            key = Keyholder.mint(seed)
            if not hmac.compare_digest(key.public_hex, key_id):
                raise KeyContinuityError("restored seed does not match key identity")
            parsed[key_id] = KeyContinuityEntry(key_id, introduced, revoked)
            restored_keys[key_id] = key

        active = parsed.get(active_key_id)
        if active is None:
            raise KeyContinuityError("active key is absent from continuity history")
        if active.revoked_generation is not None:
            raise KeyContinuityError("active key is revoked")

        ring = cls.__new__(cls)
        ring._keys = restored_keys
        ring._entries = parsed
        ring._active_key_id = active_key_id
        ring._generation = generation
        return ring


def get_keyholder() -> Keyholder:
    """Process singleton — mirrors RS ``Keyholder::get`` / OnceLock."""
    global _instance
    if _instance is not None:
        return _instance
    with _lock:
        if _instance is None:
            _instance = Keyholder.from_env()
        return _instance


def reset_keyholder_for_tests() -> None:
    """Clear the singleton (tests only)."""
    global _instance
    with _lock:
        _instance = None
