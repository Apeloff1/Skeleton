"""B088: authz, rate limits, input bounds, idempotency and replay controls at a boundary."""
from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass, field

from ._core import canonical


@dataclass
class Boundary:
    key: bytes
    roles: dict[str, frozenset[str]]
    rate_per_window: int = 5
    window_ticks: int = 10
    max_body: int = 4096
    replay_window: int = 30
    _hits: dict[str, list[int]] = field(default_factory=dict)
    _nonces: dict[str, int] = field(default_factory=dict)
    _idem: dict[str, tuple[int, str]] = field(default_factory=dict)

    def sign(self, body: dict, nonce: str, ts: int) -> str:
        msg = f"{nonce}:{ts}:{canonical(body)}".encode()
        return hmac.new(self.key, msg, hashlib.sha256).hexdigest()

    def handle(self, *, principal: str, action: str, body: dict, nonce: str, ts: int, now: int,
               sig: str, idem_key: str | None = None) -> tuple[int, str]:
        if action not in self.roles.get(principal, frozenset()):
            return 403, "forbidden"
        if len(canonical(body)) > self.max_body:
            return 413, "too_large"
        if not hmac.compare_digest(sig, self.sign(body, nonce, ts)):
            return 401, "bad_signature"
        if abs(now - ts) > self.replay_window or nonce in self._nonces:
            return 409, "replay"
        hits = [t for t in self._hits.get(principal, []) if t > now - self.window_ticks]
        if len(hits) >= self.rate_per_window:
            self._hits[principal] = hits
            return 429, "rate_limited"
        self._nonces[nonce] = now
        self._hits[principal] = hits + [now]
        if idem_key is not None:
            key = f"{principal}:{idem_key}"
            if key in self._idem:
                return self._idem[key]
            result = (200, hashlib.sha256(canonical(body).encode()).hexdigest()[:16])
            self._idem[key] = result
            return result
        return 200, hashlib.sha256(canonical(body).encode()).hexdigest()[:16]
