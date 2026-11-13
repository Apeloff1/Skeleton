"""B087: least-privilege runtime capabilities with revocation and audit."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from ._core import ContractError, require, require_str


@dataclass(frozen=True)
class Capability:
    token: str
    holder: str
    action: str
    resource: str


class CapabilityRegistry:
    """Deterministic: tokens derive from (seed, counter), never from wall-clock or RNG."""

    def __init__(self, seed: str) -> None:
        self._seed = require_str(seed, "seed")
        self._n = 0
        self._live: dict[str, Capability] = {}
        self.audit: list[tuple[str, str]] = []

    def grant(self, holder: str, action: str, resource: str) -> Capability:
        require("*" not in action and "*" not in resource, "wildcards are not least-privilege")
        self._n += 1
        tok = hashlib.sha256(f"{self._seed}:{self._n}:{holder}:{action}:{resource}".encode()).hexdigest()[:32]
        cap = Capability(tok, holder, action, resource)
        self._live[tok] = cap
        self.audit.append(("grant", tok))
        return cap

    def check(self, token: str, holder: str, action: str, resource: str) -> bool:
        cap = self._live.get(token)
        ok = cap is not None and (cap.holder, cap.action, cap.resource) == (holder, action, resource)
        self.audit.append(("check_ok" if ok else "check_deny", token))
        return ok

    def revoke(self, token: str) -> None:
        if token not in self._live:
            raise ContractError("unknown or already revoked token")
        del self._live[token]
        self.audit.append(("revoke", token))

    def revoke_holder(self, holder: str) -> int:
        toks = sorted(t for t, c in self._live.items() if c.holder == holder)
        for t in toks:
            self.revoke(t)
        return len(toks)

    @property
    def live(self) -> int:
        return len(self._live)
