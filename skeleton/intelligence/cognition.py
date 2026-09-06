"""Cognition — the empire's belief engine.

Port of gameforge-rs ``cognition.rs``: beliefs are claims with confidence;
evidence moves confidence in log-odds space so no single witness can flip
the mind, but many independent witnesses can. Claims sharing a predicate
with opposite polarity and high confidence are flagged as **schisms**.

Pure domain — sync Python (threading.Lock), optional injected clock for tests.
No FastAPI / lifespan.
"""
from __future__ import annotations

import math
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

WITNESS_STEP: float = 1.2
CONVICTION: float = 0.3
DECAY_PER_DAY: float = 0.05
LEDGER_CAP: int = 8192


@dataclass
class Evidence:
    witness: str
    polarity: bool  # True = supports, False = refutes
    weight: float  # 0.0..=1.0 witness reliability
    at: float  # unix seconds


@dataclass
class Belief:
    id: str
    predicate: str
    polarity: bool
    lodds: float = 0.0
    evidence: List[Evidence] = field(default_factory=list)
    created: float = 0.0
    touched: float = 0.0

    def confidence(self) -> float:
        return 1.0 / (1.0 + math.exp(-self.lodds))


@dataclass
class Schism:
    predicate: str
    supporting: List[str]  # belief ids
    refuting: List[str]
    detected: float  # unix seconds


class Cognition:
    """Hold beliefs, ingest witness evidence, detect and resolve schisms."""

    def __init__(self, *, clock: Optional[Callable[[], float]] = None) -> None:
        self._clock: Callable[[], float] = clock if clock is not None else time.time
        self._beliefs: Dict[str, Belief] = {}
        self._schisms: List[Schism] = []
        self._lock = threading.Lock()

    def _now(self) -> float:
        return float(self._clock())

    def hold(self, predicate: str, polarity: bool) -> str:
        """Hold a new belief (or locate the existing one on predicate+polarity)."""
        with self._lock:
            for b in self._beliefs.values():
                if b.predicate == predicate and b.polarity == polarity:
                    return b.id
            if len(self._beliefs) >= LEDGER_CAP:
                by_conviction = sorted(
                    ((bid, abs(b.lodds)) for bid, b in self._beliefs.items()),
                    key=lambda kv: kv[1],
                )
                for bid, _ in by_conviction[: LEDGER_CAP // 4]:
                    self._beliefs.pop(bid, None)
            now = self._now()
            bid = str(uuid.uuid4())
            self._beliefs[bid] = Belief(
                id=bid,
                predicate=predicate,
                polarity=polarity,
                lodds=0.0,
                evidence=[],
                created=now,
                touched=now,
            )
            return bid

    def testify(
        self,
        belief_id: str,
        witness: str,
        supports: bool,
        weight: float,
    ) -> Optional[float]:
        """Add witness evidence; updates log-odds and re-scans for schisms."""
        weight = max(0.0, min(1.0, float(weight)))
        with self._lock:
            b = self._beliefs.get(belief_id)
            if b is None:
                return None
            now = self._now()
            days = (now - b.touched) / 86400.0
            if days > 0.0:
                b.lodds *= max(0.0, 1.0 - DECAY_PER_DAY * days)
            prior = sum(1 for e in b.evidence if e.witness == witness)
            voice = weight / (1.0 + prior)
            step = WITNESS_STEP * voice * (1.0 if supports else -1.0)
            b.lodds = max(-8.0, min(8.0, b.lodds + step))
            b.evidence.append(
                Evidence(witness=witness, polarity=supports, weight=weight, at=now)
            )
            b.touched = now
            predicate = b.predicate
            confidence = b.confidence()
        self.scan_schism(predicate)
        return confidence

    def scan_schism(self, predicate: str) -> None:
        """Contradiction scan on one predicate. Schism needs conviction on both sides."""
        with self._lock:
            supporting = [
                b.id
                for b in self._beliefs.values()
                if b.predicate == predicate
                and b.polarity
                and b.confidence() >= 0.5 + CONVICTION
            ]
            refuting = [
                b.id
                for b in self._beliefs.values()
                if b.predicate == predicate
                and not b.polarity
                and b.confidence() >= 0.5 + CONVICTION
            ]
            if not supporting or not refuting:
                return
            if any(s.predicate == predicate for s in self._schisms):
                return
            self._schisms.append(
                Schism(
                    predicate=predicate,
                    supporting=list(supporting),
                    refuting=list(refuting),
                    detected=self._now(),
                )
            )
            if len(self._schisms) > 256:
                n = len(self._schisms) - 256
                del self._schisms[:n]

    def resolve_schism(self, predicate: str, winning_polarity: bool) -> bool:
        """Court decision: clear losing polarity lodds and strike the schism."""
        with self._lock:
            idx = next(
                (i for i, s in enumerate(self._schisms) if s.predicate == predicate),
                None,
            )
            if idx is None:
                return False
            self._schisms.pop(idx)
            for b in self._beliefs.values():
                if b.predicate == predicate and b.polarity != winning_polarity:
                    b.lodds = 0.0
            return True

    def belief(self, belief_id: str) -> Optional[Belief]:
        with self._lock:
            b = self._beliefs.get(belief_id)
            if b is None:
                return None
            return Belief(
                id=b.id,
                predicate=b.predicate,
                polarity=b.polarity,
                lodds=b.lodds,
                evidence=list(b.evidence),
                created=b.created,
                touched=b.touched,
            )

    def schisms(self) -> List[Schism]:
        with self._lock:
            return [
                Schism(
                    predicate=s.predicate,
                    supporting=list(s.supporting),
                    refuting=list(s.refuting),
                    detected=s.detected,
                )
                for s in self._schisms
            ]

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            convinced = sum(1 for b in self._beliefs.values() if abs(b.lodds) > WITNESS_STEP)
            return {
                "beliefs": len(self._beliefs),
                "convinced": convinced,
                "open_schisms": len(self._schisms),
            }

    def assert_plan_claims(
        self,
        claims: Sequence[Mapping[str, Any]],
    ) -> List[Schism]:
        """Hold + testify each plan claim (witness=plan, weight=1); return open schisms.

        For each ``{predicate, polarity}``, holds the belief and testifies once with
        witness ``"plan"`` / weight 1.0 supporting the claim. Returns currently open
        schisms whose predicate appears in the claim set (newly opened or pre-existing).
        """
        predicates: List[str] = []
        for raw in claims:
            pred = str(raw.get("predicate") or "").strip()
            if not pred:
                continue
            polarity = bool(raw.get("polarity", True))
            predicates.append(pred)
            bid = self.hold(pred, polarity)
            self.testify(bid, "plan", True, 1.0)
        wanted = set(predicates)
        return [s for s in self.schisms() if s.predicate in wanted]
