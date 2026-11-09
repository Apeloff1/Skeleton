"""Signed outbound callbacks (Standard Webhooks compatible).

Every delivery carries::

    webhook-id:        <message id>      stable across retries (receiver dedup key)
    webhook-timestamp: <unix seconds>    of *this* attempt
    webhook-signature: v1,<base64 HMAC-SHA256(secret, "<id>.<timestamp>.<body>")> [v1,<...>]

Multiple signatures are emitted during secret rotation (old and new), so a
receiver that only knows one of them keeps verifying. Secrets use the
``whsec_<base64>`` convention; raw bytes are accepted too. The
:class:`WebhookVerifier` is provided for receivers (and for our own tests and
inbound callback endpoints): constant-time compare, timestamp tolerance, and
an optional replay cache on ``webhook-id``.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import re
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union

from skeleton.gate_plane.s2s.clock import Clock, system_clock

ID_HEADER = "webhook-id"
TIMESTAMP_HEADER = "webhook-timestamp"
SIGNATURE_HEADER = "webhook-signature"
SECRET_PREFIX = "whsec_"
MIN_SECRET_BYTES = 24
MAX_SECRET_BYTES = 64
DEFAULT_TOLERANCE_S = 300
_MSG_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")

SecretLike = Union[str, bytes]


class WebhookSignatureError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def decode_secret(secret: SecretLike) -> bytes:
    if isinstance(secret, bytes):
        raw = secret
    elif isinstance(secret, str):
        text = secret[len(SECRET_PREFIX):] if secret.startswith(SECRET_PREFIX) else secret
        try:
            raw = base64.b64decode(text, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("webhook secret must be whsec_<base64> or raw bytes") from exc
    else:
        raise TypeError("webhook secret must be str or bytes")
    if not MIN_SECRET_BYTES <= len(raw) <= MAX_SECRET_BYTES:
        raise ValueError(f"webhook secret must be {MIN_SECRET_BYTES}-{MAX_SECRET_BYTES} bytes")
    return raw


def encode_secret(raw: bytes) -> str:
    decode_secret(raw)
    return SECRET_PREFIX + base64.b64encode(raw).decode("ascii")


def validate_message_id(msg_id: str) -> str:
    if not isinstance(msg_id, str) or not _MSG_ID_RE.match(msg_id):
        raise ValueError(f"invalid webhook message id {msg_id!r}")
    return msg_id


def _sign(secret: bytes, msg_id: str, timestamp: int, body: bytes) -> str:
    signed = f"{msg_id}.{int(timestamp)}.".encode("ascii") + (body or b"")
    return base64.b64encode(hmac.new(secret, signed, hashlib.sha256).digest()).decode("ascii")


@dataclass(frozen=True)
class SecretSet:
    """Current secret plus secrets still honoured during rotation."""

    current: bytes = field(repr=False)
    previous: Tuple[bytes, ...] = field(default=(), repr=False)

    @classmethod
    def of(cls, current: SecretLike, previous: Iterable[SecretLike] = ()) -> "SecretSet":
        return cls(decode_secret(current), tuple(decode_secret(p) for p in previous))

    def rotate(self, new: SecretLike, *, keep: int = 1) -> "SecretSet":
        prev = (self.current,) + self.previous
        return SecretSet(decode_secret(new), prev[: max(0, keep)])

    def all(self) -> Tuple[bytes, ...]:
        return (self.current,) + self.previous

    def fingerprint(self) -> str:
        return hashlib.sha256(b"whsec-fp\x00" + self.current).hexdigest()[:12]


class WebhookSigner:
    def __init__(self, *, clock: Optional[Clock] = None, sign_with_previous: bool = True) -> None:
        self.clock: Clock = clock or system_clock()
        self.sign_with_previous = bool(sign_with_previous)

    def headers(self, secrets: SecretSet, msg_id: str, body: bytes, *, timestamp: Optional[int] = None) -> Dict[str, str]:
        validate_message_id(msg_id)
        ts = int(self.clock.now()) if timestamp is None else int(timestamp)
        keys: Sequence[bytes] = secrets.all() if self.sign_with_previous else (secrets.current,)
        sigs = " ".join(f"v1,{_sign(k, msg_id, ts, body)}" for k in keys)
        return {ID_HEADER: msg_id, TIMESTAMP_HEADER: str(ts), SIGNATURE_HEADER: sigs}


class _IdCache:
    def __init__(self, capacity: int) -> None:
        self.capacity = capacity
        self._seen: "OrderedDict[str, float]" = OrderedDict()
        self._lock = threading.Lock()

    def add(self, msg_id: str, expires_at: float, now: float) -> bool:
        with self._lock:
            for k in [k for k, exp in self._seen.items() if exp <= now]:
                del self._seen[k]
            if msg_id in self._seen:
                return False
            self._seen[msg_id] = expires_at
            while len(self._seen) > self.capacity:
                self._seen.popitem(last=False)
            return True


class WebhookVerifier:
    """Receiver-side verification of :class:`WebhookSigner` headers."""

    def __init__(
        self,
        secrets: SecretSet,
        *,
        clock: Optional[Clock] = None,
        tolerance_s: int = DEFAULT_TOLERANCE_S,
        replay_capacity: Optional[int] = 10_000,
    ) -> None:
        if tolerance_s <= 0:
            raise ValueError("tolerance_s must be > 0")
        self.secrets = secrets
        self.clock: Clock = clock or system_clock()
        self.tolerance_s = int(tolerance_s)
        self._ids = None if replay_capacity is None else _IdCache(int(replay_capacity))

    def verify(self, headers: Mapping[str, str], body: bytes) -> str:
        """Return the message id; raise :class:`WebhookSignatureError` otherwise."""
        low = {str(k).lower(): str(v) for k, v in headers.items()}
        msg_id = low.get(ID_HEADER)
        ts_raw = low.get(TIMESTAMP_HEADER)
        sig_raw = low.get(SIGNATURE_HEADER)
        if not msg_id or not ts_raw or not sig_raw:
            raise WebhookSignatureError("missing_headers")
        try:
            validate_message_id(msg_id)
        except ValueError:
            raise WebhookSignatureError("bad_message_id") from None
        if not ts_raw.isdigit():
            raise WebhookSignatureError("bad_timestamp")
        ts = int(ts_raw)
        now = self.clock.now()
        if abs(now - ts) > self.tolerance_s:
            raise WebhookSignatureError("timestamp_out_of_tolerance")
        presented: List[str] = []
        for part in sig_raw.split():
            version, _, value = part.partition(",")
            if version == "v1" and value:
                presented.append(value)
        if not presented:
            raise WebhookSignatureError("no_v1_signature")
        expected = [_sign(k, msg_id, ts, body) for k in self.secrets.all()]
        if not any(hmac.compare_digest(p, e) for p in presented for e in expected):
            raise WebhookSignatureError("signature_mismatch")
        if self._ids is not None and not self._ids.add(msg_id, ts + self.tolerance_s, now):
            raise WebhookSignatureError("replayed")
        return msg_id


__all__ = [
    "DEFAULT_TOLERANCE_S",
    "ID_HEADER",
    "SECRET_PREFIX",
    "SIGNATURE_HEADER",
    "SecretSet",
    "TIMESTAMP_HEADER",
    "WebhookSignatureError",
    "WebhookSigner",
    "WebhookVerifier",
    "decode_secret",
    "encode_secret",
    "validate_message_id",
]
