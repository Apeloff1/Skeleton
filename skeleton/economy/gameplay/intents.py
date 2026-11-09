"""B024 untrusted player input -> validated economy commands.

Client payloads are hostile by default. :class:`IntentGate` turns a raw
mapping into an :class:`~skeleton.economy.gameplay.replay.EconomyCommand`
only when:

* the op is in the player-facing allowlist (no minting ops, no ``trade`` that
  would let one player spend another's money),
* every field is present, of the right type (``bool`` is not an int), within
  bounds, and no unknown keys are present,
* the acting owner is the authenticated session owner,
* the client nonce has not been seen (idempotent resubmits are reported, not
  re-executed), and
* the actor's token bucket has budget at that tick.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping

from skeleton.economy.gameplay.replay import EconomyCommand
from skeleton.simulation.economy.sim import EconomySimError, _req_int

MAX_QTY = 10_000
MAX_BASE = 10**12
_ID = re.compile(r"^[a-z][a-z0-9_.:-]{0,63}$")
_NONCE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")

# op -> {field: kind}. "self" fields must equal the session owner.
PLAYER_OPS: dict[str, dict[str, str]] = {
    "vendor_buy": {"owner": "self", "item_id": "id", "qty": "qty"},
    "vendor_sell": {"owner": "self", "item_id": "id", "qty": "qty"},
    "charge": {"sink_id": "id", "owner": "self", "base": "base"},
    "grant": {"faucet_id": "id", "owner": "self"},
    "consume_items": {"sink": "id", "owner": "self", "item_id": "id", "qty": "qty"},
    "move_items": {"src": "self", "dst": "id", "item_id": "id", "qty": "qty"},
    "bind": {"owner": "self", "item_id": "id", "qty": "qty"},
}


class IntentError(EconomySimError):
    code = "ECO.INTENT"


@dataclass
class _Bucket:
    tokens: int
    last_tick: int


@dataclass
class IntentGate:
    """Validate, authorise, dedupe and rate-limit player economy intents."""

    capacity: int = 10
    refill_per_tick: int = 1
    max_nonces: int = 4096
    _buckets: dict[str, _Bucket] = field(default_factory=dict)
    _nonces: dict[str, None] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _req_int(self.capacity, "capacity", minimum=1)
        _req_int(self.refill_per_tick, "refill_per_tick")
        _req_int(self.max_nonces, "max_nonces", minimum=1)

    def parse(self, session_owner: str, payload: Mapping[str, Any], tick: int) -> EconomyCommand | None:
        """Return a command, or ``None`` for an already-accepted nonce. Raises on refusal."""
        _req_int(tick, "tick")
        if not isinstance(payload, Mapping):
            raise IntentError("payload must be an object")
        op = payload.get("op")
        if op not in PLAYER_OPS:
            raise IntentError("op not allowed")
        schema = PLAYER_OPS[op]
        allowed = set(schema) | {"op", "nonce"}
        unknown = set(payload) - allowed
        if unknown:
            raise IntentError(f"unknown fields {sorted(unknown)}")
        nonce = payload.get("nonce")
        if not isinstance(nonce, str) or not _NONCE.match(nonce):
            raise IntentError("invalid nonce")
        args: dict[str, Any] = {}
        for name, kind in schema.items():
            if kind == "self":
                value = payload.get(name, session_owner)
                if value != session_owner:
                    raise IntentError(f"{name} must be the session owner")
            else:
                if name not in payload:
                    if kind == "qty":
                        args[name] = 1
                        continue
                    if kind == "base":
                        args[name] = 0
                        continue
                    raise IntentError(f"missing {name}")
                value = payload[name]
                self._check(name, kind, value)
            args[name] = value
        if op == "grant":
            args["tick"] = tick
        key = f"{session_owner}/{nonce}"
        if key in self._nonces:
            return None
        self._spend(session_owner, tick)
        self._nonces[key] = None
        while len(self._nonces) > self.max_nonces:
            self._nonces.pop(next(iter(self._nonces)))
        return EconomyCommand(tick=tick, op=op, args=args)

    @staticmethod
    def _check(name: str, kind: str, value: Any) -> None:
        if kind == "id":
            if not isinstance(value, str) or not _ID.match(value):
                raise IntentError(f"invalid {name}")
            return
        if isinstance(value, bool) or not isinstance(value, int):
            raise IntentError(f"{name} must be an integer")
        limit = MAX_QTY if kind == "qty" else MAX_BASE
        lower = 1 if kind == "qty" else 0
        if not lower <= value <= limit:
            raise IntentError(f"{name} out of range")

    def _spend(self, owner: str, tick: int) -> None:
        bucket = self._buckets.get(owner)
        if bucket is None:
            bucket = self._buckets[owner] = _Bucket(tokens=self.capacity, last_tick=tick)
        if tick < bucket.last_tick:
            raise IntentError("tick went backwards")
        bucket.tokens = min(self.capacity, bucket.tokens + (tick - bucket.last_tick) * self.refill_per_tick)
        bucket.last_tick = tick
        if bucket.tokens < 1:
            raise IntentError("rate limited")
        bucket.tokens -= 1


__all__ = ["MAX_QTY", "PLAYER_OPS", "IntentError", "IntentGate"]
