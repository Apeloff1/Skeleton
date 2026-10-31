"""Authenticated, byte-exact context frames under the canonical conversation owner.

The encrypted archive is a *recovery representation*, not another conversation
source of truth and not a way to enlarge a model's attention window. Consumers
MUST compare the final reconstructed head with a head independently committed
by their existing authoritative conversation repository. Client-provided heads
have no replay-protection authority.

No secrets, trace contents or plaintext appear in exceptions or receipts.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
import hashlib
import json
import secrets
from typing import Iterable, Mapping

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


SCHEMA_VERSION = 1
GENESIS_COMMITMENT = "0" * 64
_DOMAIN = b"skeleton.context.sealed_sandwich.v1\x00"
_MAX_FRAME_BYTES = 4 * 1024 * 1024
_MAX_ENVELOPE_BYTES = _MAX_FRAME_BYTES * 2 + 8192
_MAX_FRAME_COUNT = 1_000_000
_MAX_SEQUENCE = (1 << 63) - 1
_HEADER_FIELDS = frozenset(
    {
        "schema_version", "tenant_id", "owner_id", "conversation_id", "sequence",
        "previous_commitment", "key_id", "model_id", "policy_id", "payload_bytes",
    }
)
_ENVELOPE_FIELDS = frozenset({"header", "nonce", "ciphertext"})


class SealedContextError(ValueError):
    """Malformed or untrustworthy context archive (never includes payload)."""


class SealedContextIntegrityError(SealedContextError):
    """Authentication or byte-level integrity was not established."""


class SealedContextReplayError(SealedContextError):
    """The stream does not match its trusted, monotonically advancing head."""


class SealedContextBoundaryError(SealedContextError):
    """A credential, model, or policy boundary does not match."""


class SealedContextLimitError(SealedContextError):
    """A bounded frame or archive limit would be exceeded."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _valid_identity(value: str, label: str) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 256 or value != value.strip():
        raise SealedContextBoundaryError(f"{label} is invalid")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise SealedContextBoundaryError(f"{label} is invalid")
    return value


def _digest(value: str, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(
        ch not in "0123456789abcdef" for ch in value
    ):
        raise SealedContextError(f"{label} is not a canonical SHA-256 digest")
    return value


def _strict_object(value: object, fields: frozenset[str], label: str) -> dict:
    if type(value) is not dict or set(value) != fields:
        raise SealedContextError(f"{label} fields are invalid")
    return value


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: object, max_bytes: int) -> bytes:
    if not isinstance(value, str) or len(value) > (max_bytes * 4 // 3) + 8:
        raise SealedContextError("invalid encoded frame")
    try:
        result = base64.b64decode(
            value + "=" * (-len(value) % 4), altchars=b"-_", validate=True
        )
    except (binascii.Error, ValueError) as exc:
        raise SealedContextError("invalid encoded frame") from exc
    if len(result) > max_bytes or _b64encode(result) != value:
        raise SealedContextError("noncanonical encoded frame")
    return result


@dataclass(frozen=True, slots=True)
class ContextBinding:
    """Authenticated identity; the caller must derive this from backend authority.

    Deliberate model/policy migrations require a new archive binding. IDs are
    metadata, not credentials. Never store secrets here.
    """

    tenant_id: str
    owner_id: str
    conversation_id: str
    model_id: str
    policy_id: str

    def __post_init__(self) -> None:
        for label in ("tenant_id", "owner_id", "conversation_id", "model_id", "policy_id"):
            _valid_identity(getattr(self, label), label)


@dataclass(frozen=True, slots=True)
class ContextHead:
    """CAS-authoritative head value, stored by the existing conversation owner."""

    sequence: int = 0
    commitment: str = GENESIS_COMMITMENT

    def __post_init__(self) -> None:
        if type(self.sequence) is not int or not 0 <= self.sequence <= _MAX_SEQUENCE:
            raise SealedContextError("invalid context sequence")
        _digest(self.commitment, "commitment")
        if self.sequence == 0 and self.commitment != GENESIS_COMMITMENT:
            raise SealedContextError("genesis commitment mismatch")
        if self.sequence != 0 and self.commitment == GENESIS_COMMITMENT:
            raise SealedContextError("non-genesis commitment is empty")


@dataclass(frozen=True, slots=True)
class ContextFrame:
    """One verified payload; sequence/commitment are authenticated evidence."""

    head: ContextHead
    payload: bytes


class ContextSandwichCodec:
    """AES-256-GCM frame codec with constant-size portable envelope headers.

    The backend injects a KMS-backed mapping of AES-256 keys and rotates keys
    before GCM invocation limits. Random 96-bit nonces are generated internally.
    No client or model ever selects a nonce or a key.
    """

    def __init__(self, keys: Mapping[str, bytes], *, active_key_id: str) -> None:
        if not isinstance(keys, Mapping) or not keys:
            raise SealedContextError("an application-managed AES-256 keyring is required")
        self._keys: dict[str, bytes] = {}
        for key_id, key in keys.items():
            _valid_identity(key_id, "key_id")
            if not isinstance(key, bytes) or len(key) != 32:
                raise SealedContextError("AES-256 keys must be exactly 32 bytes")
            self._keys[key_id] = key
        if active_key_id not in self._keys:
            raise SealedContextError("active key is unavailable")
        self._active_key_id = active_key_id

    def seal(
        self, payload: bytes, *, binding: ContextBinding, previous: ContextHead
    ) -> tuple[bytes, ContextHead]:
        """Seal one next-sequence frame. Caller must CAS commit the new head.

        Store the ciphertext and the newly committed head atomically or preserve
        the existing canonical transcript as the authority for reconstruction.
        This function does NOT claim to commit a durable write by itself.
        """
        if not isinstance(binding, ContextBinding) or not isinstance(previous, ContextHead):
            raise SealedContextBoundaryError("trusted binding and head are required")
        if not isinstance(payload, bytes):
            raise SealedContextError("payload must be raw bytes")
        if len(payload) > _MAX_FRAME_BYTES:
            raise SealedContextLimitError("context frame exceeds size bound; split into frames")
        if previous.sequence >= _MAX_SEQUENCE:
            raise SealedContextLimitError("context sequence is exhausted")
        header = {
            "schema_version": SCHEMA_VERSION,
            "tenant_id": binding.tenant_id,
            "owner_id": binding.owner_id,
            "conversation_id": binding.conversation_id,
            "model_id": binding.model_id,
            "policy_id": binding.policy_id,
            "sequence": previous.sequence + 1,
            "previous_commitment": previous.commitment,
            "key_id": self._active_key_id,
            "payload_bytes": len(payload),
        }
        aad = _DOMAIN + _canonical(header)
        nonce = secrets.token_bytes(12)
        protected = hashlib.sha256(payload).digest() + payload
        ciphertext = AESGCM(self._keys[self._active_key_id]).encrypt(nonce, protected, aad)
        wire = _canonical(
            {"header": header, "nonce": _b64encode(nonce), "ciphertext": _b64encode(ciphertext)}
        )
        commitment = _sha256(_DOMAIN + wire)
        return wire, ContextHead(previous.sequence + 1, commitment)

    def open(
        self,
        wire: bytes,
        *,
        binding: ContextBinding,
        previous: ContextHead,
    ) -> ContextFrame:
        """Check one frame against an independently obtained predecessor head."""
        if not isinstance(binding, ContextBinding) or not isinstance(previous, ContextHead):
            raise SealedContextBoundaryError("trusted binding and head are required")
        if not isinstance(wire, bytes) or len(wire) > _MAX_ENVELOPE_BYTES:
            raise SealedContextLimitError("context frame wire size exceeds bound")
        try:
            decoded = json.loads(wire)
            envelope = _strict_object(decoded, _ENVELOPE_FIELDS, "envelope")
            header = _strict_object(envelope["header"], _HEADER_FIELDS, "header")
            if _canonical(envelope) != wire:
                raise SealedContextError("noncanonical context envelope")
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise SealedContextError("invalid context envelope") from exc
        if header["schema_version"] != SCHEMA_VERSION or type(header["schema_version"]) is not int:
            raise SealedContextError("unsupported context envelope version")
        for label in ("tenant_id", "owner_id", "conversation_id", "model_id", "policy_id"):
            if header[label] != getattr(binding, label):
                raise SealedContextBoundaryError("context does not belong to this authority or model policy")
        if type(header["sequence"]) is not int or header["sequence"] != previous.sequence + 1:
            raise SealedContextReplayError("context sequence is not exact-next")
        if header["previous_commitment"] != previous.commitment:
            raise SealedContextReplayError("context predecessor commitment disagrees")
        if type(header["payload_bytes"]) is not int or not 0 <= header["payload_bytes"] <= _MAX_FRAME_BYTES:
            raise SealedContextLimitError("invalid declared context payload size")
        key_id = header["key_id"]
        if not isinstance(key_id, str) or key_id not in self._keys:
            raise SealedContextBoundaryError("context key is unavailable")
        nonce = _b64decode(envelope["nonce"], 12)
        if len(nonce) != 12:
            raise SealedContextError("invalid context nonce")
        ciphertext = _b64decode(envelope["ciphertext"], _MAX_FRAME_BYTES + 64)
        if len(ciphertext) != header["payload_bytes"] + 32 + 16:
            raise SealedContextIntegrityError("context ciphertext size mismatch")
        try:
            protected = AESGCM(self._keys[key_id]).decrypt(
                nonce, ciphertext, _DOMAIN + _canonical(header)
            )
        except (InvalidTag, ValueError) as exc:
            raise SealedContextIntegrityError("context authentication failed") from exc
        payload = protected[32:]
        if len(payload) != header["payload_bytes"] or not secrets.compare_digest(
            protected[:32], hashlib.sha256(payload).digest()
        ):
            raise SealedContextIntegrityError("context byte integrity failed")
        return ContextFrame(ContextHead(header["sequence"], _sha256(_DOMAIN + wire)), payload)

    def replay(
        self,
        wires: Iterable[bytes],
        *,
        binding: ContextBinding,
        trusted_head: ContextHead,
        starting_head: ContextHead = ContextHead(),
    ) -> tuple[ContextFrame, ...]:
        """Replay a full chain or trusted checkpoint suffix, rejecting gaps/tails.

        BOTH starting_head (if not genesis) and trusted_head must come from
        authenticated, durable state; passing a client-supplied head is unsafe.
        """
        if not isinstance(trusted_head, ContextHead) or not isinstance(starting_head, ContextHead):
            raise SealedContextReplayError("independent trusted heads are required")
        if starting_head.sequence > trusted_head.sequence:
            raise SealedContextReplayError("starting checkpoint exceeds trusted head")
        frames: list[ContextFrame] = []
        current = starting_head
        for wire in wires:
            if len(frames) >= _MAX_FRAME_COUNT:
                raise SealedContextLimitError("archive frame count exceeds bound")
            frame = self.open(wire, binding=binding, previous=current)
            current = frame.head
            frames.append(frame)
        if current != trusted_head:
            raise SealedContextReplayError("archive is incomplete, stale, or not the committed head")
        return tuple(frames)
