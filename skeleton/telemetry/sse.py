"""SSE formatter and optional stream. Default off. Mobile skips."""

from __future__ import annotations

from skeleton.telemetry.law import DEFAULT_ON, PATH
from skeleton.telemetry.store import EventStore


class Stream:
    def __init__(self, store: EventStore | None = None, *, enabled: bool | None = None, mobile: bool = False) -> None:
        self.store = store or EventStore()
        self.enabled = DEFAULT_ON == 1 if enabled is None else enabled
        self.mobile = mobile

    def open(self) -> bool:
        if self.mobile:
            return False
        return bool(self.enabled)

    def frames(self) -> list[str]:
        if not self.open():
            return []
        out = []
        for rec in self.store.events:
            out.append("event: %s\ndata: {\"seq\":%d}\n\n" % (rec["kind"], rec["seq"]))
        return out

    def client_read(self, n: int) -> list[str]:
        return self.frames()[:n]


ROUTE = PATH
