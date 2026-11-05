"""Versioned envelope format for secrets at rest (AES-256-GCM, two layers).

Layout of format version 1 (all integers big-endian)::

    magic      4  b"CSE\\x01"            (format + version byte)
    kid_len    1  1..32
    key_id     kid_len  ASCII KEK id
    wrap_nonce 12 nonce for the DEK wrap
    wrapped    48 AES-GCM(KEK, DEK) = 32-byte DEK + 16-byte tag
    data_nonce 12 nonce for the payload
    ciphertext n  AES-GCM(DEK, plaintext) incl. 16-byte tag

Associated data binds the envelope to its row: callers pass e.g.
``tenant_id|secret_id`` so a ciphertext copied to another row or tenant
fails authentication. The header (magic + key id) is also authenticated, so
the key id cannot be swapped.

Re-wrapping (KEK rotation) only replaces ``key_id``/``wrap_nonce``/
``wrapped``; the payload ciphertext and DEK are untouched.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .keys import KEY_ID_RE, KeyProvider, KeyProviderError

MAGIC = b"CSE\x01"
FORMAT_VERSION = 1
NONCE = 12
DEK = 32
WRAPPED = DEK + 16
MAX_PLAINTEXT = 4096


class EnvelopeError(ValueError):
    """Malformed, tampered, or undecryptable envelope. Message is caller-safe."""


@dataclass(frozen=True)
class Envelope:
    key_id: str
    wrap_nonce: bytes
    wrapped_dek: bytes
    data_nonce: bytes
    ciphertext: bytes

    def header(self) -> bytes:
        kid = self.key_id.encode("ascii")
        return MAGIC + bytes([len(kid)]) + kid

    def to_bytes(self) -> bytes:
        return self.header() + self.wrap_nonce + self.wrapped_dek + self.data_nonce + self.ciphertext


def is_envelope(blob: bytes | None) -> bool:
    """Cheap structural check (does not authenticate)."""
    if not blob or len(blob) < len(MAGIC) + 2 or bytes(blob[:4]) != MAGIC:
        return False
    try:
        parse(bytes(blob))
    except EnvelopeError:
        return False
    return True


def parse(blob: bytes) -> Envelope:
    b = bytes(blob)
    if b[:3] != MAGIC[:3]:
        raise EnvelopeError("not an envelope")
    if b[3] != FORMAT_VERSION:
        raise EnvelopeError(f"unsupported envelope version {b[3]}")
    if len(b) < 5:
        raise EnvelopeError("truncated envelope")
    n = b[4]
    pos = 5
    if not 1 <= n <= 32 or len(b) < pos + n + NONCE + WRAPPED + NONCE + 16:
        raise EnvelopeError("truncated envelope")
    try:
        kid = b[pos:pos + n].decode("ascii")
    except UnicodeDecodeError:
        raise EnvelopeError("invalid key id") from None
    if not KEY_ID_RE.match(kid):
        raise EnvelopeError("invalid key id")
    pos += n
    wn = b[pos:pos + NONCE]; pos += NONCE
    wd = b[pos:pos + WRAPPED]; pos += WRAPPED
    dn = b[pos:pos + NONCE]; pos += NONCE
    return Envelope(kid, wn, wd, dn, b[pos:])


def key_id_of(blob: bytes) -> str:
    return parse(blob).key_id


def _wrap_aad(header: bytes, aad: bytes) -> bytes:
    return b"wrap|" + header + b"|" + aad


def _data_aad(header: bytes, aad: bytes) -> bytes:
    return b"data|" + header[:4] + b"|" + aad  # data layer independent of key id -> cheap rewrap


def _kek(provider: KeyProvider, key_id: str) -> bytes:
    try:
        return provider.get(key_id)
    except KeyProviderError:
        raise EnvelopeError(f"key {key_id!r} is not available") from None


def seal(provider: KeyProvider, plaintext: bytes, aad: bytes, *, key_id: str | None = None) -> bytes:
    if not isinstance(plaintext, (bytes, bytearray)) or not plaintext:
        raise EnvelopeError("plaintext must be non-empty bytes")
    if len(plaintext) > MAX_PLAINTEXT:
        raise EnvelopeError("plaintext too large")
    kid = key_id or provider.active_key_id()
    kek = _kek(provider, kid)
    dek = AESGCM.generate_key(bit_length=256)
    head = Envelope(kid, b"", b"", b"", b"").header()
    wn, dn = os.urandom(NONCE), os.urandom(NONCE)
    wrapped = AESGCM(kek).encrypt(wn, dek, _wrap_aad(head, aad))
    ct = AESGCM(dek).encrypt(dn, bytes(plaintext), _data_aad(head, aad))
    return Envelope(kid, wn, wrapped, dn, ct).to_bytes()


def _unwrap(provider: KeyProvider, env: Envelope, aad: bytes) -> bytes:
    kek = _kek(provider, env.key_id)
    try:
        return AESGCM(kek).decrypt(env.wrap_nonce, env.wrapped_dek, _wrap_aad(env.header(), aad))
    except InvalidTag:
        raise EnvelopeError("envelope authentication failed") from None


def open_(provider: KeyProvider, blob: bytes, aad: bytes) -> bytes:
    env = parse(blob)
    dek = _unwrap(provider, env, aad)
    try:
        return AESGCM(dek).decrypt(env.data_nonce, env.ciphertext, _data_aad(env.header(), aad))
    except InvalidTag:
        raise EnvelopeError("envelope authentication failed") from None


def rewrap(provider: KeyProvider, blob: bytes, aad: bytes, *, to_key_id: str | None = None) -> bytes:
    """Re-wrap the DEK under ``to_key_id`` (default: active). Payload is untouched."""
    env = parse(blob)
    target = to_key_id or provider.active_key_id()
    if env.key_id == target:
        return bytes(blob)
    dek = _unwrap(provider, env, aad)
    # also prove the payload still authenticates before committing to the new wrap
    try:
        AESGCM(dek).decrypt(env.data_nonce, env.ciphertext, _data_aad(env.header(), aad))
    except InvalidTag:
        raise EnvelopeError("envelope authentication failed") from None
    kek = _kek(provider, target)
    head = Envelope(target, b"", b"", b"", b"").header()
    wn = os.urandom(NONCE)
    wrapped = AESGCM(kek).encrypt(wn, dek, _wrap_aad(head, aad))
    return Envelope(target, wn, wrapped, env.data_nonce, env.ciphertext).to_bytes()


def secret_aad(tenant_id: str, secret_id: str) -> bytes:
    return f"core_v1.webhook_secret|{tenant_id}|{secret_id}".encode()


__all__ = ["seal", "open_", "rewrap", "parse", "is_envelope", "key_id_of", "secret_aad",
           "Envelope", "EnvelopeError", "FORMAT_VERSION", "MAGIC"]
