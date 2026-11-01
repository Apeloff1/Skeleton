"""Ingest filter: deterministic sampling, opt-out, pseudonymous ids, no PII.

Raw player/session ids never leave ``Collector.ingest``: they are replaced by a
keyed HMAC pseudonym. Opted-out players are dropped (default) or anonymised:
every event gets player ``anon`` and a per-session pseudonym, so their
sessions still count towards level stats but cannot be linked to each other
or back to the player. Coordinates and free attrs are removed when anonymised.
"""
from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass, field, replace
from typing import Any, Iterable, Mapping

from .events import EventError, GameplayEvent

ANON = "anon"
MAX_RAW_ID_CHARS = 256


def _raw_identity(value: str, label: str) -> str:
    """Bound opaque identities before hashing; forbid ambiguous separators."""
    if (type(value) is not str or not 1 <= len(value) <= MAX_RAW_ID_CHARS
            or any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in value)):
        raise EventError(f"{label} must be a bounded non-control string")
    return value


class EventCapacityError(EventError):
    """Collector reached its bounded event custody; no silent data loss."""


@dataclass(frozen=True)
class PrivacyPolicy:
    salt: bytes
    sample_rate: float = 1.0
    opt_out: str = "drop"  # "drop" | "anonymise"

    def __post_init__(self) -> None:
        if not isinstance(self.salt, bytes) or len(self.salt) < 16:
            raise ValueError("salt must be at least 16 bytes")
        if not 0.0 <= self.sample_rate <= 1.0:
            raise ValueError("sample_rate must be in [0, 1]")
        if self.opt_out not in ("drop", "anonymise"):
            raise ValueError("opt_out must be 'drop' or 'anonymise'")

    def pseudonym(self, kind: str, raw: str) -> str:
        if kind not in ("player", "session", "anon_session"):
            raise EventError("unsupported pseudonym domain")
        raw = _raw_identity(raw, "raw identity")
        return kind[0] + hmac.new(self.salt, f"{kind}\x00{raw}".encode(), hashlib.sha256).hexdigest()[:20]

    def sampled(self, raw_player: str) -> bool:
        """Per-player (not per-event) so a sampled player's whole history is kept."""
        raw_player = _raw_identity(raw_player, "player identity")
        if self.sample_rate >= 1.0:
            return True
        h = hmac.new(self.salt, f"sample\x00{raw_player}".encode(), hashlib.sha256).digest()
        return int.from_bytes(h[:8], "big") / 2**64 < self.sample_rate


@dataclass
class Collector:
    policy: PrivacyPolicy
    max_events: int = 100_000
    opted_out: set[str] = field(default_factory=set)  # raw ids, held in memory only
    events: list[GameplayEvent] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=lambda: {"kept": 0, "anonymised": 0, "opted_out_dropped": 0,
                                                            "unsampled": 0, "rejected": 0})

    def __post_init__(self) -> None:
        if type(self.max_events) is not int or not 1 <= self.max_events <= 1_000_000:
            raise ValueError("max_events must be an integer in [1, 1000000]")
        if len(self.events) > self.max_events:
            raise ValueError("initial events exceed bounded collector capacity")

    def opt_out(self, raw_player: str) -> None:
        """Record opt-out and purge (or anonymise) what was already stored for the player."""
        raw_player = _raw_identity(raw_player, "player identity")
        self.opted_out.add(raw_player)
        mine = self.policy.pseudonym("player", raw_player)
        kept: list[GameplayEvent] = []
        for e in self.events:
            if e.player != mine:
                kept.append(e)
            elif self.policy.opt_out == "anonymise":
                kept.append(self._anon(e))
        self.events = kept

    def _anon(self, e: GameplayEvent) -> GameplayEvent:
        return replace(e, player=ANON, session_id=self.policy.pseudonym("anon_session", e.session_id),
                       x=None, y=None, attrs=())

    def ingest(self, raw_player: str, raw_session: str, event: Mapping[str, Any]) -> GameplayEvent | None:
        """Validate one event. ``event`` must not carry ids; they are passed separately."""
        try:
            raw_player = _raw_identity(raw_player, "player identity")
            raw_session = _raw_identity(raw_session, "session identity")
        except EventError:
            self.counts["rejected"] += 1
            raise
        if not isinstance(event, Mapping):
            raise EventError("analytics event must be a mapping")
        if "player" in event or "session_id" in event:
            raise EventError("pass raw ids as arguments, not inside the event")
        if raw_player in self.opted_out and self.policy.opt_out == "drop":
            self.counts["opted_out_dropped"] += 1
            return None
        if not self.policy.sampled(raw_player):
            self.counts["unsampled"] += 1
            return None
        try:
            ev = GameplayEvent.from_dict({**event, "player": self.policy.pseudonym("player", raw_player),
                                          "session_id": self.policy.pseudonym(
                                              "session", f"{len(raw_player)}:{raw_player}{raw_session}")})
        except EventError:
            self.counts["rejected"] += 1
            raise
        if len(self.events) >= self.max_events:
            self.counts["rejected"] += 1
            raise EventCapacityError("analytics event retention capacity exhausted")
        if raw_player in self.opted_out:
            ev = self._anon(ev)
            self.counts["anonymised"] += 1
        else:
            self.counts["kept"] += 1
        self.events.append(ev)
        return ev

    def ingest_many(self, rows: Iterable[tuple[str, str, Mapping[str, Any]]]) -> int:
        n = 0
        for p, s, ev in rows:
            try:
                n += self.ingest(p, s, ev) is not None
            except EventCapacityError:
                raise
            except EventError:
                continue
        return n
