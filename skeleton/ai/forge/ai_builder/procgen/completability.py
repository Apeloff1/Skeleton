"""Adapter: the directed (room, keys-held) solver behind a CompletabilitySolver-shaped API.

Structurally matches the stand-in protocol on the quest branch (not imported)::

    CompletabilitySolver.check(rooms: Sequence[Room], start: str,
                               keys_held: frozenset[str]) -> CompletabilityVerdict

``Room`` is duck-typed: ``.key`` (room id), ``.doors`` (each with ``.to`` and
``.requires``: None, a key id, or an iterable of key ids), ``.keys`` (key ids
picked up in the room) and ``.goal`` (bool). Doors are directed, so a one-way
drop is a door with no door back. Same state search as ``keys.softlocks``.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any, Sequence


@dataclass(frozen=True)
class CompletabilityVerdict:
    completable: bool
    softlocked: bool
    reason: str


def _needs(req: Any) -> frozenset[str]:
    if req is None:
        return frozenset()
    if isinstance(req, str):
        return frozenset({req}) if req else frozenset()
    return frozenset(req)


class ProcgenCompletabilitySolver:
    """Satisfies ``CompletabilitySolver`` by structural typing."""

    def check(self, rooms: Sequence[Any], start: str, keys_held: frozenset[str]) -> CompletabilityVerdict:
        if (not isinstance(rooms, (tuple, list)) or not 1 <= len(rooms) <= 4096
                or type(start) is not str or not start or type(keys_held) is not frozenset
                or len(keys_held) > 32):
            return CompletabilityVerdict(False, True, "invalid or unbounded room/key inventory")
        try:
            if any(type(r.key) is not str or not r.key or
                   len(r.doors or ()) > 256 or len(r.keys or ()) > 32 for r in rooms):
                return CompletabilityVerdict(False, True, "invalid bounded room descriptor")
            by_id = {r.key: r for r in rooms}
        except (AttributeError, TypeError, ValueError):
            return CompletabilityVerdict(False, True, "malformed room contract")
        if len(by_id) != len(rooms):
            return CompletabilityVerdict(False, True, "duplicate room identities")
        if start not in by_id:
            return CompletabilityVerdict(False, False, f"start room {start!r} not in rooms")
        goals = {r.key for r in rooms if r.goal}
        if not goals:
            return CompletabilityVerdict(False, False, "no goal room")

        def pick(room: str, held: frozenset) -> frozenset:
            return held | frozenset(by_id[room].keys or ())

        s0 = (start, pick(start, frozenset(keys_held)))
        succ: dict = {}
        seen, q = {s0}, deque([s0])
        while q:
            cur = q.popleft()
            room, held = cur
            outs = []
            for d in by_id[room].doors or ():
                if d.to in by_id and _needs(d.requires) <= held:
                    outs.append((d.to, pick(d.to, held)))
            succ[cur] = outs
            for ns in outs:
                if ns not in seen:
                    if len(seen) >= 65536:
                        return CompletabilityVerdict(False, True, "state search budget exhausted")
                    seen.add(ns)
                    q.append(ns)
        pred: dict = {s: [] for s in seen}
        for s, outs in succ.items():
            for t in outs:
                pred[t].append(s)
        good = {s for s in seen if s[0] in goals}
        stack = list(good)
        while stack:
            for p in pred[stack.pop()]:
                if p not in good:
                    good.add(p)
                    stack.append(p)
        if not good:
            missing = sorted({k for r in rooms for d in r.doors or () for k in _needs(d.requires)}
                             - {k for s in seen for k in s[1]})
            return CompletabilityVerdict(False, False, f"no goal reachable; keys never obtained: {missing}")
        bad = sorted({s[0] for s in seen if s not in good})
        if bad:
            return CompletabilityVerdict(True, True, f"softlock: no way to a goal from rooms {bad}")
        return CompletabilityVerdict(True, False, "ok")
