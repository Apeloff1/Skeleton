"""On-call rotation — schedule-based pager rotation with overrides.

Defines rotations (weekly/daily handoffs across a member list),
computes who is on call at any moment, supports temporary overrides
(swap shifts, vacation cover), and tracks handoff history. Escalation
policies resolve targets through this rotation.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Override:
    member: str
    start_ns: int
    end_ns: int
    reason: str


@dataclass
class Rotation:
    name: str
    members: List[str]
    shift_s: float = 604800.0
    anchor_ns: int = 0
    overrides: List[Override] = field(default_factory=list)


class OnCallRotation:
    """Schedule-based on-call resolution with overrides."""

    def __init__(self):
        self._rotations: Dict[str, Rotation] = {}
        self._handoffs: List[Dict[str, Any]] = []

    def define(self, name: str, members: List[str],
               shift_s: float = 604800.0,
               anchor_ns: Optional[int] = None) -> Rotation:
        rot = Rotation(name=name, members=members, shift_s=shift_s,
                       anchor_ns=anchor_ns or time.time_ns())
        self._rotations[name] = rot
        return rot

    def add_member(self, rotation: str, member: str) -> bool:
        rot = self._rotations.get(rotation)
        if not rot or member in rot.members:
            return False
        rot.members.append(member)
        return True

    def remove_member(self, rotation: str, member: str) -> bool:
        rot = self._rotations.get(rotation)
        if not rot or member not in rot.members or len(rot.members) <= 1:
            return False
        rot.members.remove(member)
        return True

    def add_override(self, rotation: str, member: str,
                     start_ns: int, end_ns: int, reason: str = "") -> bool:
        rot = self._rotations.get(rotation)
        if not rot:
            return False
        rot.overrides.append(Override(member=member, start_ns=start_ns, end_ns=end_ns, reason=reason))
        return True

    def who_is_oncall(self, rotation: str, at_ns: Optional[int] = None) -> Optional[str]:
        rot = self._rotations.get(rotation)
        if not rot or not rot.members:
            return None
        now = at_ns if at_ns is not None else time.time_ns()
        for ov in rot.overrides:
            if ov.start_ns <= now < ov.end_ns:
                return ov.member
        elapsed_s = (now - rot.anchor_ns) / 1e9
        if elapsed_s < 0:
            return rot.members[0]
        index = int(elapsed_s // rot.shift_s) % len(rot.members)
        return rot.members[index]

    def schedule(self, rotation: str, shifts: int = 4) -> List[Dict[str, Any]]:
        rot = self._rotations.get(rotation)
        if not rot or not rot.members:
            return []
        now = time.time_ns()
        out = []
        current_start = rot.anchor_ns + int((now - rot.anchor_ns) // int(rot.shift_s * 1e9)) * int(rot.shift_s * 1e9)
        for i in range(shifts):
            start = current_start + i * int(rot.shift_s * 1e9)
            end = start + int(rot.shift_s * 1e9)
            out.append({
                "member": self.who_is_oncall(rotation, at_ns=start),
                "start_ns": start,
                "end_ns": end,
            })
        return out

    def handoff(self, rotation: str, notes: str = "") -> Dict[str, Any]:
        current = self.who_is_oncall(rotation)
        record = {"rotation": rotation, "member": current, "notes": notes, "timestamp_ns": time.time_ns()}
        self._handoffs.append(record)
        return record

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "oncall-card",
            "rotations": {n: {
                "members": r.members,
                "shift_s": r.shift_s,
                "current": self.who_is_oncall(n),
                "overrides": len(r.overrides),
            } for n, r in self._rotations.items()},
            "handoffs": len(self._handoffs),
        }
