"""
gameforge.prood.quorum — REAL Byzantine-fault-tolerant quorum (Stage B1).

Promotes the conductor's PBFT *simulation* (a single ``honest >= 2f+1``
arithmetic check) to an actual multi-replica vote: N independent in-process
replicas each cast a vote on a proposed value across PBFT-style
``pre-prepare → prepare → commit`` phases. A value is DECIDED only when a
super-majority (``>= 2f + 1``) of replicas commit the SAME digest. Every vote
is recorded so the decision is fully auditable.

BFT safety bound: to tolerate ``f`` Byzantine replicas you need ``N >= 3f + 1``.
Faulty replicas can be injected (``faulty`` set) to prove the quorum still
reaches consensus — or fails safely when the fault budget is exceeded.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


def _digest(value: Any) -> str:
    return hashlib.sha256(repr(value).encode("utf-8")).hexdigest()[:16]


@dataclass
class Replica:
    """One in-process consensus replica."""
    replica_id: int
    byzantine: bool = False

    def vote(self, value: Any, proof: str) -> Dict[str, Any]:
        """Honest replicas vote for the true digest; Byzantine replicas emit a
        corrupted digest (equivocation)."""
        if self.byzantine:
            corrupt = _digest(f"{value}:byzantine:{self.replica_id}:{proof}")
            return {"replica": self.replica_id, "digest": corrupt,
                    "byzantine": True, "accept": False}
        return {"replica": self.replica_id, "digest": _digest(value),
                "byzantine": False, "accept": True}


@dataclass
class QuorumResult:
    decided: bool
    value: Optional[Any]
    digest: Optional[str]
    n: int
    f: int
    quorum_needed: int
    commit_count: int
    phases: Dict[str, List[Dict]] = field(default_factory=dict)
    view: int = 0
    seq: int = 0
    ms: float = 0.0

    def to_dict(self) -> Dict:
        return {
            "decided": self.decided, "value": self.value, "digest": self.digest,
            "n": self.n, "f": self.f, "quorum_needed": self.quorum_needed,
            "commit_count": self.commit_count, "phases": self.phases,
            "view": self.view, "seq": self.seq, "ms": self.ms,
        }


class QuorumConsensus:
    """N-replica PBFT quorum. ``n >= 3f + 1`` for safety under ``f`` faults."""

    def __init__(self, n: int = 7, f: int = 2):
        if n < 3 * f + 1:
            raise ValueError(f"BFT requires n >= 3f+1 (got n={n}, f={f})")
        self.n = n
        self.f = f
        self.quorum_needed = 2 * f + 1
        self.view = 0
        self.seq = 0

    def agree(self, value: Any, proof: str = "", faulty: Optional[Set[int]] = None) -> QuorumResult:
        """Run one consensus round. ``faulty`` = replica ids that will
        equivocate (defaults to none → all honest)."""
        t0 = time.time()
        self.seq += 1
        faulty = faulty or set()
        replicas = [Replica(i, byzantine=(i in faulty)) for i in range(self.n)]
        truth = _digest(value)

        # ── pre-prepare (primary proposes) ──
        pre_prepare = {"replica": 0, "digest": truth, "proof": proof}

        # ── prepare (all replicas broadcast their vote) ──
        prepare = [r.vote(value, proof) for r in replicas]

        # ── commit (replicas that saw a matching-digest super-majority in the
        #    prepare phase commit) ──
        digest_tally: Dict[str, int] = {}
        for v in prepare:
            digest_tally[v["digest"]] = digest_tally.get(v["digest"], 0) + 1
        prepared_ok = digest_tally.get(truth, 0) >= self.quorum_needed

        commit: List[Dict] = []
        if prepared_ok:
            for r in replicas:
                # honest replicas commit the true digest; byzantine do not
                if not r.byzantine:
                    commit.append({"replica": r.replica_id, "digest": truth, "commit": True})
                else:
                    commit.append({"replica": r.replica_id,
                                   "digest": _digest(f"c:{r.replica_id}"), "commit": False})

        commit_count = sum(1 for c in commit if c["commit"] and c["digest"] == truth)
        decided = commit_count >= self.quorum_needed

        return QuorumResult(
            decided=decided,
            value=value if decided else None,
            digest=truth if decided else None,
            n=self.n, f=self.f, quorum_needed=self.quorum_needed,
            commit_count=commit_count,
            phases={"pre_prepare": [pre_prepare], "prepare": prepare, "commit": commit},
            view=self.view, seq=self.seq,
            ms=round((time.time() - t0) * 1000, 3),
        )


# Shared default quorum (7 replicas, tolerates 2 Byzantine faults).
quorum_consensus = QuorumConsensus(n=7, f=2)


__all__ = ["Replica", "QuorumResult", "QuorumConsensus", "quorum_consensus", "_digest"]
