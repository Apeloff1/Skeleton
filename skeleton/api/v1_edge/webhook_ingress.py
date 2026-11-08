"""Inbound webhook signature verification (``t=<ts>,v1=<hex>`` HMAC-SHA256) with replay guard."""
from __future__ import annotations

import hashlib
import hmac
import time
import re
import threading
from collections import OrderedDict
from typing import Callable, Dict, Optional

from .envelope import EdgeError


def sign(secret: bytes, ts: int, body: bytes) -> str:
    mac = hmac.new(secret, f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={ts},v1={mac}"


class WebhookIngressVerifier:
    def __init__(self, secrets: Dict[str, bytes], tolerance_s: int = 300,
                 clock: Callable[[], float] = time.time, replay_capacity: int = 10_000):
        if (type(tolerance_s) is not int or not 1 <= tolerance_s <= 3600
                or type(replay_capacity) is not int or not 1 <= replay_capacity <= 100000):
            raise ValueError("invalid webhook replay policy")
        for src, s in secrets.items():
            if type(s) is not bytes or len(s) < 16:
                raise ValueError(f"secret for {src} too short")
        self._secrets = dict(secrets)
        self.tolerance_s = tolerance_s
        self._clock = clock
        self._seen: "OrderedDict[str, float]" = OrderedDict()
        self._cap = replay_capacity
        self._lock = threading.RLock()

    def rotate(self, source: str, new_secret: bytes) -> None:
        if type(new_secret) is not bytes or len(new_secret) < 16:
            raise ValueError("secret must be at least 16 bytes")
        with self._lock:
            self._secrets[source] = new_secret

    def verify(self, source: str, signature: Optional[str], body: bytes) -> int:
        with self._lock:
            secret = self._secrets.get(source)
        if secret is None:
            raise EdgeError(404, "EDGE.WEBHOOK.UNKNOWN_SOURCE", "unknown webhook source")
        if not signature:
            raise EdgeError(401, "EDGE.WEBHOOK.UNSIGNED", "missing signature")
        if (type(signature) is not str or len(signature) > 512
                or len(body) > 1 << 20):
            raise EdgeError(401, "EDGE.WEBHOOK.BAD_SIGNATURE", "invalid signature envelope")
        parts: Dict[str, list] = {}
        for item in signature.split(","):
            k, _, v = item.strip().partition("=")
            parts.setdefault(k, []).append(v)
        if (set(parts) != {"t", "v1"} or len(parts["t"]) != 1
                or not 1 <= len(parts["v1"]) <= 3
                or re.fullmatch(r"[0-9]{1,16}", parts["t"][0]) is None
                or any(re.fullmatch(r"[0-9a-f]{64}", x) is None for x in parts["v1"])):
            raise EdgeError(401, "EDGE.WEBHOOK.BAD_SIGNATURE", "malformed signature")
        ts = int(parts["t"][0])
        if abs(self._clock() - ts) > self.tolerance_s:
            raise EdgeError(401, "EDGE.WEBHOOK.STALE", "signature timestamp outside tolerance")
        expected = sign(secret, ts, body).split("v1=", 1)[1]
        if not any(hmac.compare_digest(expected, v) for v in parts.get("v1", [])):
            raise EdgeError(401, "EDGE.WEBHOOK.BAD_SIGNATURE", "signature mismatch")
        # Rotation must not reset replay identity for the same verified event.
        # Bind custody to the source, timestamp and body, not the current key.
        nonce = f"{source}:{ts}:{hashlib.sha256(body).hexdigest()}"
        with self._lock:
            now = self._clock()
            for key in [key for key, seen_at in self._seen.items()
                        if now - seen_at > self.tolerance_s * 2]:
                del self._seen[key]
            if nonce in self._seen:
                raise EdgeError(409, "EDGE.WEBHOOK.REPLAY", "duplicate delivery")
            if len(self._seen) >= self._cap:
                raise EdgeError(503, "EDGE.WEBHOOK.REPLAY_CAPACITY", "webhook replay admission exhausted")
            self._seen[nonce] = now
        return ts
