"""court — PBFT-style quorum gate (gameforge-rs quorum::Court port).

f is the number of byzantine nodes the court tolerates; a proposal needs
``2f+1`` matching attestations (by SHA-256 ``value_hash``) before it is
``Decided``. Attesters that diverge from the decided value are recorded
as suspects — byzantine means fault-tolerant, not trusting.

F1 contract: decision keys are SHA-256 of compact canonical JSON. A
byzantine attester cannot precompute a colliding value to win a verdict
under another value's identity.

This module is the hex PBFT quorum court. It does **not** replace
``skeleton.kernel.court_attest`` (ed25519 / Keyholder signed envelopes) —
that path stays untouched. Callers that need both: verify the envelope
via ``court_attest``, then feed the proposal into :class:`Court`.

Sibling source: ``Apeloff1/gameforge-rs``
``crates/gf-gameforge/src/lib.rs`` ``pub mod quorum``.
"""

from __future__ import annotations

import hashlib
import json
import threading
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, Tuple, Union

JsonLike = Union[None, bool, int, float, str, list, dict, Mapping]


class Verdict(str, Enum):
    """Outcome of one ``attest`` call. Names match gameforge-rs ``quorum::Verdict``."""

    PENDING = "Pending"
    DECIDED = "Decided"
    DEADLOCKED = "Deadlocked"


def value_hash(value: JsonLike) -> str:
    """SHA-256 hex of compact canonical JSON (RS ``Court::value_hash``).

    Keys are sorted so two equal mappings hash identically regardless of
    insertion order. Separators match serde_json's compact ``to_string``.
    """
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class Court:
    """PBFT-style novelty gate. Quorum size is ``2f+1``; electorate ``3f+1``."""

    def __init__(self, name: str, f: int) -> None:
        if f < 0:
            raise ValueError("f must be >= 0")
        self.name = name
        self.f = int(f)
        self._lock = threading.RLock()
        # proposal_id -> [(attester, value_hash)]
        self._attestations: Dict[str, List[Tuple[str, str]]] = {}
        self._suspects: Dict[str, int] = {}

    def quorum_size(self) -> int:
        """Votes needed for a matching value: ``2f+1``."""
        return 2 * self.f + 1

    def electorate(self) -> int:
        """Classic PBFT cluster size: ``3f+1``."""
        return 3 * self.f + 1

    @staticmethod
    def value_hash(value: JsonLike) -> str:
        """Content hash — fabric decisions are on values, not identity."""
        return value_hash(value)

    def attest(
        self,
        proposal_id: str,
        attester: str,
        value: JsonLike,
    ) -> Verdict:
        """Cast one attestation. One voice per attester per proposal.

        Returns:
            ``DECIDED`` once ``2f+1`` matching hashes exist (divergent
            attesters are suspect-counted and the proposal lane is cleared),
            ``DEADLOCKED`` when remaining votes cannot reach quorum,
            else ``PENDING``.
        """
        h = value_hash(value)
        with self._lock:
            entry = self._attestations.setdefault(proposal_id, [])
            if any(a == attester for a, _ in entry):
                return Verdict.PENDING  # one voice per attester

            entry.append((attester, h))

            counts: Dict[str, int] = {}
            for _, vh in entry:
                counts[vh] = counts.get(vh, 0) + 1

            quorum = self.quorum_size()
            winning: Optional[str] = None
            for cand, n in counts.items():
                if n >= quorum:
                    winning = cand
                    break

            if winning is not None:
                for a, vh in entry:
                    if vh != winning:
                        self._suspects[a] = self._suspects.get(a, 0) + 1
                del self._attestations[proposal_id]
                return Verdict.DECIDED

            remaining = self.electorate() - len(entry)
            if remaining < 0:
                remaining = 0
            if all(n + remaining < quorum for n in counts.values()):
                del self._attestations[proposal_id]
                return Verdict.DEADLOCKED

            return Verdict.PENDING

    def suspects(self) -> Dict[str, int]:
        """Attester id → divergence count (RS ``Court::suspects`` JSON object)."""
        with self._lock:
            return dict(self._suspects)

    def pending_attestations(self, proposal_id: str) -> List[Tuple[str, str]]:
        """Debug/test helper: current (attester, hash) pairs for a proposal."""
        with self._lock:
            return list(self._attestations.get(proposal_id, ()))

    def snapshot(self) -> Dict[str, Any]:
        """Lightweight status for ops / tests."""
        with self._lock:
            return {
                "name": self.name,
                "f": self.f,
                "quorum_size": self.quorum_size(),
                "electorate": self.electorate(),
                "open_proposals": sorted(self._attestations.keys()),
                "suspects": dict(self._suspects),
            }
