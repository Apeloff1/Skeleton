"""Webhook signatures.

Header ``Skeleton-Signature: t=<unix>,v1=<hex>[,v1=<hex>]`` where each v1 is
HMAC-SHA256(secret, f"{t}.{body}"). During secret rotation both the new and
the previous secret sign, so receivers can roll over without downtime.
Verification enforces a timestamp tolerance to bound replay.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets as _secrets
from typing import Iterable

HEADER = "Skeleton-Signature"
DEFAULT_TOLERANCE = 300
SECRET_PREFIX = "whsec_"


def new_secret() -> str:
    return SECRET_PREFIX + _secrets.token_urlsafe(32)


def secret_bytes(secret: str) -> bytes:
    if not secret.startswith(SECRET_PREFIX) or len(secret) < len(SECRET_PREFIX) + 32:
        raise ValueError("malformed webhook secret")
    return secret.encode()


def _mac(secret: bytes, timestamp: int, body: bytes) -> str:
    return hmac.new(secret, f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()


def sign(body: bytes, secrets: Iterable[bytes], timestamp: int) -> str:
    sigs = [f"v1={_mac(s, timestamp, body)}" for s in secrets]
    if not sigs:
        raise ValueError("at least one secret is required")
    return ",".join([f"t={timestamp}", *sigs])


def parse(header: str) -> tuple[int, list[str]]:
    ts, sigs = None, []
    for part in header.split(","):
        k, _, v = part.strip().partition("=")
        if k == "t" and v.isdigit():
            ts = int(v)
        elif k == "v1" and v:
            sigs.append(v)
    if ts is None or not sigs:
        raise ValueError("malformed signature header")
    return ts, sigs


def verify(header: str, body: bytes, secret: bytes, now: float,
           tolerance: int = DEFAULT_TOLERANCE) -> bool:
    try:
        ts, sigs = parse(header)
    except ValueError:
        return False
    if abs(now - ts) > tolerance:
        return False
    expected = _mac(secret, ts, body)
    return any(hmac.compare_digest(expected, s) for s in sigs)
