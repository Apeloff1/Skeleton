from __future__ import annotations
"""
DNA Board — Bloody Roar style transformation/planning board for Boardroom.

Extended planning & organization:
  - Step-by-step room → room progress tracking
  - Each task branches into 3 tier-sets (Tier A / B / C)
  - Each tier-set has progressive ranks (DNA strands)
  - Boardroom always issues 3 consecutive directions per room
  - Inter-room sandbox for idea melding
  - Consensus voting across rooms
  - Conglomerate-grade audit + VOX hooks
"""

import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


class TierSet(str, Enum):
    """Three branching DNA tier-sets per task."""
    ALPHA = "alpha"    # aggressive / speed path
    BETA = "beta"      # balanced / quality path
    GAMMA = "gamma"    # defensive / thorough path


class StrandRank(str, Enum):
    """Progress ranks within a tier-set (Bloody Roar DNA-style ascent)."""
    DORMANT = "dormant"
    AWAKENED = "awakened"
    BEAST = "beast"
    HYPER = "hyper"
    COMPLETE = "complete"


RANK_ORDER = [
    StrandRank.DORMANT,
    StrandRank.AWAKENED,
    StrandRank.BEAST,
    StrandRank.HYPER,
    StrandRank.COMPLETE,
]


@dataclass
class Direction:
    """One of the 3 consecutive directions Boardroom issues to a room."""
    direction_id: str
    sequence: int  # 1, 2, 3 — must complete in order
    title: str
    brief: str
    tier_hint: str = TierSet.BETA.value  # preferred branch
    status: str = "pending"  # pending | active | done | blocked
    result: Optional[Dict[str, Any]] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DNABranch:
    """One tier-set branch on a task."""
    tier: str
    rank: str = StrandRank.DORMANT.value
    notes: List[str] = field(default_factory=list)
    score: float = 0.0  # quality score 0..100 from sandbox/meld

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DNATask:
    """Task tracked on the DNA Board with 3 branching tier-sets."""
    task_id: str
    room_id: str
    title: str
    branches: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    active_tier: Optional[str] = None
    progress_pct: float = 0.0
    created_at: str = field(default_factory=_ts)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class VoteBallot:
    vote_id: str
    subject: str
    options: List[str]
    ballots: Dict[str, str] = field(default_factory=dict)  # room_id -> option
    status: str = "open"  # open | closed
    winner: Optional[str] = None
    created_at: str = field(default_factory=_ts)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SandboxMeld:
    """Inter-room idea sandbox — meld proposals for best result."""
    meld_id: str
    rooms: List[str]
    proposals: Dict[str, str] = field(default_factory=dict)  # room_id -> idea
    melded: Optional[str] = None
    score: float = 0.0
    status: str = "open"  # open | melded
    created_at: str = field(default_factory=_ts)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RoomTrack:
    """Room-to-room progress tracker."""
    room_id: str
    directions: List[Dict[str, Any]] = field(default_factory=list)
    tasks: List[str] = field(default_factory=list)
    completed_directions: int = 0
    reputation_delta: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


class DNABoard:
    """
    Boardroom DNA Board — conglomerate planning engine.
    """

    def __init__(self):
        self.rooms: Dict[str, RoomTrack] = {}
        self.tasks: Dict[str, DNATask] = {}
        self.votes: Dict[str, VoteBallot] = {}
        self.sandboxes: Dict[str, SandboxMeld] = {}
        self.sequence_log: List[dict] = []  # room-to-room ordered events
        self.audit: List[dict] = []

    def _audit(self, event: str, **kw):
        self.audit.append({"ts": _ts(), "event": event, **kw})
        if len(self.audit) > 10000:
            self.audit = self.audit[-10000:]

    def ensure_room(self, room_id: str) -> RoomTrack:
        if room_id not in self.rooms:
            self.rooms[room_id] = RoomTrack(room_id=room_id)
            self._audit("room_register", room_id=room_id)
        return self.rooms[room_id]

    # ----- Boardroom: always 3 consecutive directions per room ---------------

    def issue_directions(
        self,
        room_id: str,
        directions: List[Tuple[str, str]],
        tier_hints: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Boardroom MUST issue exactly 3 consecutive directions.
        directions: list of (title, brief) length 3
        """
        if len(directions) != 3:
            return {"ok": False, "error": "boardroom_requires_exactly_3_directions"}
        room = self.ensure_room(room_id)
        # clear prior pending chain if fully done; else reject
        pending = [d for d in room.directions if d.get("status") in ("pending", "active")]
        if pending:
            return {"ok": False, "error": "room_has_active_direction_chain", "pending": pending}

        hints = tier_hints or [TierSet.ALPHA.value, TierSet.BETA.value, TierSet.GAMMA.value]
        issued = []
        for i, (title, brief) in enumerate(directions, start=1):
            d = Direction(
                direction_id=str(uuid.uuid4())[:10],
                sequence=i,
                title=title,
                brief=brief,
                tier_hint=hints[(i - 1) % 3],
                status="active" if i == 1 else "pending",
            )
            issued.append(d.to_dict())
            room.directions.append(d.to_dict())
        self.sequence_log.append(
            {"ts": _ts(), "event": "issue_directions", "room_id": room_id, "count": 3}
        )
        self._audit("issue_directions", room_id=room_id, directions=issued)
        return {"ok": True, "room_id": room_id, "directions": issued}

    def complete_direction(self, room_id: str, direction_id: str, result: Optional[dict] = None) -> Dict[str, Any]:
        room = self.ensure_room(room_id)
        found = None
        for d in room.directions:
            if d["direction_id"] == direction_id:
                found = d
                break
        if not found:
            return {"ok": False, "error": "direction_not_found"}
        if found["status"] != "active":
            return {"ok": False, "error": "direction_not_active", "status": found["status"]}
        # enforce consecutive: all lower sequence must be done
        for d in room.directions:
            if d["sequence"] < found["sequence"] and d["status"] != "done":
                return {"ok": False, "error": "prior_direction_incomplete", "blocking": d["direction_id"]}
        found["status"] = "done"
        found["result"] = result or {}
        room.completed_directions += 1
        # activate next
        nxt = None
        for d in room.directions:
            if d["sequence"] == found["sequence"] + 1 and d["status"] == "pending":
                d["status"] = "active"
                nxt = d
                break
        self.sequence_log.append(
            {"ts": _ts(), "event": "complete_direction", "room_id": room_id, "direction_id": direction_id}
        )
        self._audit("complete_direction", room_id=room_id, direction_id=direction_id, next=nxt)
        return {"ok": True, "completed": found, "next_active": nxt, "room_progress": room.completed_directions}

    # ----- DNA tasks: 3 branching tier-sets ----------------------------------

    def create_task(self, room_id: str, title: str) -> DNATask:
        self.ensure_room(room_id)
        branches = {
            TierSet.ALPHA.value: DNABranch(tier=TierSet.ALPHA.value).to_dict(),
            TierSet.BETA.value: DNABranch(tier=TierSet.BETA.value).to_dict(),
            TierSet.GAMMA.value: DNABranch(tier=TierSet.GAMMA.value).to_dict(),
        }
        task = DNATask(
            task_id=str(uuid.uuid4())[:10],
            room_id=room_id,
            title=title,
            branches=branches,
            active_tier=TierSet.BETA.value,
        )
        self.tasks[task.task_id] = task
        self.rooms[room_id].tasks.append(task.task_id)
        self._audit("create_task", task=task.to_dict())
        return task

    def advance_branch(self, task_id: str, tier: str, note: str = "", score_delta: float = 10.0) -> Dict[str, Any]:
        task = self.tasks.get(task_id)
        if not task:
            return {"ok": False, "error": "task_not_found"}
        if tier not in task.branches:
            return {"ok": False, "error": "invalid_tier"}
        br = task.branches[tier]
        rank = br.get("rank", StrandRank.DORMANT.value)
        try:
            idx = [r.value for r in RANK_ORDER].index(rank)
        except ValueError:
            idx = 0
        if idx < len(RANK_ORDER) - 1:
            br["rank"] = RANK_ORDER[idx + 1].value
        if note:
            br.setdefault("notes", []).append(note)
        br["score"] = min(100.0, float(br.get("score", 0)) + score_delta)
        task.active_tier = tier
        # progress = average rank index across branches
        total = 0
        for b in task.branches.values():
            try:
                total += [r.value for r in RANK_ORDER].index(b.get("rank", "dormant"))
            except ValueError:
                pass
        task.progress_pct = round(100.0 * total / (3 * (len(RANK_ORDER) - 1)), 2)
        self._audit("advance_branch", task_id=task_id, tier=tier, rank=br["rank"])
        return {"ok": True, "branch": br, "progress_pct": task.progress_pct, "task": task.to_dict()}

    def select_tier(self, task_id: str, tier: str) -> Dict[str, Any]:
        task = self.tasks.get(task_id)
        if not task or tier not in task.branches:
            return {"ok": False, "error": "invalid"}
        task.active_tier = tier
        return {"ok": True, "active_tier": tier}

    # ----- Consensus vote ----------------------------------------------------

    def open_vote(self, subject: str, options: List[str], room_ids: List[str]) -> VoteBallot:
        if len(options) < 2:
            raise ValueError("need >=2 options")
        v = VoteBallot(
            vote_id=str(uuid.uuid4())[:10],
            subject=subject,
            options=options,
        )
        # pre-register eligible rooms
        for rid in room_ids:
            self.ensure_room(rid)
        self.votes[v.vote_id] = v
        self._audit("open_vote", vote=v.to_dict(), rooms=room_ids)
        return v

    def cast_vote(self, vote_id: str, room_id: str, option: str) -> Dict[str, Any]:
        v = self.votes.get(vote_id)
        if not v or v.status != "open":
            return {"ok": False, "error": "vote_closed_or_missing"}
        if option not in v.options:
            return {"ok": False, "error": "invalid_option"}
        v.ballots[room_id] = option
        self._audit("cast_vote", vote_id=vote_id, room_id=room_id, option=option)
        return {"ok": True, "ballots": dict(v.ballots)}

    def close_vote(self, vote_id: str) -> Dict[str, Any]:
        v = self.votes.get(vote_id)
        if not v:
            return {"ok": False, "error": "not_found"}
        counts: Dict[str, int] = {o: 0 for o in v.options}
        for opt in v.ballots.values():
            counts[opt] = counts.get(opt, 0) + 1
        # consensus = strict majority; else plurality with flag
        total = max(1, len(v.ballots))
        winner = max(counts, key=counts.get)
        consensus = counts[winner] > total / 2
        v.winner = winner
        v.status = "closed"
        self._audit("close_vote", vote_id=vote_id, winner=winner, consensus=consensus, counts=counts)
        return {
            "ok": True,
            "winner": winner,
            "consensus": consensus,
            "counts": counts,
            "ballots": dict(v.ballots),
        }

    # ----- Inter-room sandbox / idea meld ------------------------------------

    def open_sandbox(self, room_ids: List[str]) -> SandboxMeld:
        if len(room_ids) < 2:
            raise ValueError("sandbox needs >=2 rooms")
        for r in room_ids:
            self.ensure_room(r)
        m = SandboxMeld(meld_id=str(uuid.uuid4())[:10], rooms=list(room_ids))
        self.sandboxes[m.meld_id] = m
        self._audit("open_sandbox", meld_id=m.meld_id, rooms=room_ids)
        return m

    def propose(self, meld_id: str, room_id: str, idea: str) -> Dict[str, Any]:
        m = self.sandboxes.get(meld_id)
        if not m or m.status != "open":
            return {"ok": False, "error": "sandbox_closed_or_missing"}
        if room_id not in m.rooms:
            return {"ok": False, "error": "room_not_in_sandbox"}
        m.proposals[room_id] = idea
        self._audit("propose", meld_id=meld_id, room_id=room_id)
        return {"ok": True, "proposals": dict(m.proposals)}

    def meld(self, meld_id: str, strategy: str = "concatenate") -> Dict[str, Any]:
        """
        Meld ideas for best result.
        strategies: concatenate | vote_longest | manual (uses longest as proxy quality)
        """
        m = self.sandboxes.get(meld_id)
        if not m:
            return {"ok": False, "error": "not_found"}
        if not m.proposals:
            return {"ok": False, "error": "no_proposals"}
        ideas = list(m.proposals.values())
        if strategy == "vote_longest" or strategy == "concatenate":
            # deterministic meld: rank by length as quality proxy + join unique clauses
            ranked = sorted(ideas, key=len, reverse=True)
            melded = " || ".join(ranked)
            score = min(100.0, 40.0 + 10.0 * len(ideas) + 0.05 * len(melded))
        else:
            melded = ideas[0]
            score = 50.0
        m.melded = melded
        m.score = round(score, 2)
        m.status = "melded"
        self._audit("meld", meld_id=meld_id, score=m.score)
        return {"ok": True, "melded": melded, "score": m.score, "proposals": dict(m.proposals)}

    # ----- Room-to-room progress ---------------------------------------------

    def room_to_room_progress(self) -> Dict[str, Any]:
        """Ordered view of progress across all rooms."""
        tracks = []
        for rid, room in self.rooms.items():
            active = next((d for d in room.directions if d.get("status") == "active"), None)
            tracks.append(
                {
                    "room_id": rid,
                    "completed_directions": room.completed_directions,
                    "active_direction": active,
                    "tasks": room.tasks,
                    "direction_statuses": [d.get("status") for d in room.directions[-3:]],
                }
            )
        return {
            "rooms": tracks,
            "sequence_log_tail": self.sequence_log[-20:],
            "open_votes": sum(1 for v in self.votes.values() if v.status == "open"),
            "open_sandboxes": sum(1 for s in self.sandboxes.values() if s.status == "open"),
            "tasks_total": len(self.tasks),
        }

    def status(self) -> Dict[str, Any]:
        return {
            "rooms": {k: v.to_dict() for k, v in self.rooms.items()},
            "tasks": {k: v.to_dict() for k, v in self.tasks.items()},
            "votes_open": [v.to_dict() for v in self.votes.values() if v.status == "open"],
            "sandboxes_open": [s.to_dict() for s in self.sandboxes.values() if s.status == "open"],
            "progress": self.room_to_room_progress(),
            "audit_tail": self.audit[-15:],
        }
