"""Inbound webhook signature verification (``t=<ts>,v1=<hex>`` HMAC-SHA256) with replay guard."""
from __future__ import annotations

import hashlib
import hmac
import time
from collections import OrderedDict
from typing import Callable, Dict, Optional

from .envelope import EdgeError


def sign(secret: bytes, ts: int, body: bytes) -> str:
    mac = hmac.new(secret, f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={ts},v1={mac}"


class WebhookIngressVerifier:
    def __init__(self, secrets: Dict[str, bytes], tolerance_s: int = 300,
                 clock: Callable[[], float] = time.time, replay_capacity: int = 10_000):
        for src, s in secrets.items():
            if len(s) < 16:
                raise ValueError(f"secret for {src} too short")
        self._secrets = dict(secrets)
        self.tolerance_s = tolerance_s
        self._clock = clock
        self._seen: "OrderedDict[str, float]" = OrderedDict()
        self._cap = replay_capacity

    def rotate(self, source: str, new_secret: bytes) -> None:
        if len(new_secret) < 16:
            raise ValueError("secret too short")
        self._secrets[source] = new_secret

    def verify(self, source: str, signature: Optional[str], body: bytes) -> int:
        secret = self._secrets.get(source)
        if secret is None:
            raise EdgeError(404, "EDGE.WEBHOOK.UNKNOWN_SOURCE", "unknown webhook source")
        if not signature:
            raise EdgeError(401, "EDGE.WEBHOOK.UNSIGNED", "missing signature")
        parts: Dict[str, list] = {}
        for item in signature.split(","):
            k, _, v = item.strip().partition("=")
            parts.setdefault(k, []).append(v)
        try:
            ts = int(parts.get("t", [""])[0])
        except ValueError:
            raise EdgeError(401, "EDGE.WEBHOOK.BAD_SIGNATURE", "malformed signature") from None
        if abs(self._clock() - ts) > self.tolerance_s:
            raise EdgeError(401, "EDGE.WEBHOOK.STALE", "signature timestamp outside tolerance")
        expected = sign(secret, ts, body).split("v1=", 1)[1]
        if not any(hmac.compare_digest(expected, v) for v in parts.get("v1", [])):
            raise EdgeError(401, "EDGE.WEBHOOK.BAD_SIGNATURE", "signature mismatch")
        nonce = f"{source}:{ts}:{expected}"
        if nonce in self._seen:
            raise EdgeError(409, "EDGE.WEBHOOK.REPLAY", "duplicate delivery")
        self._seen[nonce] = self._clock()
        while len(self._seen) > self._cap:
            self._seen.popitem(last=False)
        return ts
