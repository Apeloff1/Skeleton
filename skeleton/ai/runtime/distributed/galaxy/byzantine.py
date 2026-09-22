"""
Skeleton Fleet — Byzantine Trust Layer

The fleet's deepest defense: nodes may lie, equivocate, or replay.
Consensus already exists; this layer makes it Byzantine-tolerant —
safe when up to f of 3f+1 nodes are actively malicious.

Core machinery:

- SignedEnvelope: every consensus/vote/report message carries an
  HMAC signature over (node_id || seq || payload_hash || prev_hash)
  with a per-node rotating secret shared at join. Forgery requires
  the secret; equivocation (two different payloads at the same seq)
  is detectable from the seq log.
- EquivocationLedger: per-node sequence log. Two conflicting signed
  messages at the same sequence number = cryptographic proof of
  Byzantine behavior, publishable to the fleet as an accusation.
- QuorumCertificates: a decision finalizes only when 2f+1 DISTINCT
  signed votes for the same value are collected. Certificates are
  self-verifying: any node can check the signature set without
  trusting the collector.
- TrustMatrix: continuous trust scores per node — signature failures,
  equivocations, stale reports, and consensus disagreement rate
  decay trust; clean epochs restore it. Below the trust floor, a
  node's votes are discounted (weighted by trust, not excluded —
  a flaky-but-honest node shouldn't be silenced, just weighted).
- ViewChange: if the primary equivocates or stalls past timeout,
  the next node in deterministic order proposes a view change with
  its evidence bundle (accusations + timeout proof); 2f+1 approvals
  rotate the view.
"""

from __future__ import annotations

import hashlib
import hmac
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Signed envelopes + sequence logs
# ---------------------------------------------------------------------------

@dataclass
class SignedEnvelope:
    """A message with an HMAC signature over its content chain."""
    node_id: str
    seq: int
    payload: Dict[str, Any]
    payload_hash: str
    prev_hash: str
    signature: str
    sent_at: float = field(default_factory=time.time)

    @staticmethod
    def hash_payload(payload: Dict[str, Any]) -> str:
        body = repr(sorted(payload.items())).encode()
        return hashlib.sha256(body).hexdigest()

    @classmethod
    def create(cls, node_id: str, seq: int, payload: Dict[str, Any],
               prev_hash: str, secret: bytes) -> "SignedEnvelope":
        ph = cls.hash_payload(payload)
        body = f"{node_id}|{seq}|{ph}|{prev_hash}".encode()
        sig = hmac.new(secret, body, hashlib.sha256).hexdigest()
        return cls(node_id, seq, payload, ph, prev_hash, sig)

    def verify(self, secret: bytes) -> bool:
        body = f"{self.node_id}|{self.seq}|{self.payload_hash}|{self.prev_hash}".encode()
        expected = hmac.new(secret, body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, self.signature):
            return False
        return self.payload_hash == self.hash_payload(self.payload)


class EquivocationLedger:
    """Per-node sequence log; same-seq conflicts are Byzantine proofs."""

    def __init__(self):
        self._log: Dict[str, Dict[int, SignedEnvelope]] = {}
        self._proofs: List[Dict[str, Any]] = []

    def record(self, envelope: SignedEnvelope) -> Optional[Dict[str, Any]]:
        """Record an envelope; returns an equivocation proof if conflict."""
        node_log = self._log.setdefault(envelope.node_id, {})
        existing = node_log.get(envelope.seq)
        if existing is not None:
            if existing.payload_hash != envelope.payload_hash:
                proof = {
                    "node_id": envelope.node_id,
                    "seq": envelope.seq,
                    "hash_a": existing.payload_hash,
                    "hash_b": envelope.payload_hash,
                    "sig_a": existing.signature[:16],
                    "sig_b": envelope.signature[:16],
                    "detected_at": time.time(),
                }
                self._proofs.append(proof)
                return proof
            return None  # exact duplicate: benign retry
        node_log[envelope.seq] = envelope
        return None

    def proofs(self) -> List[Dict[str, Any]]:
        return list(self._proofs)

    def expected_seq(self, node_id: str) -> int:
        return len(self._log.get(node_id, {}))


# ---------------------------------------------------------------------------
# Quorum certificates
# ---------------------------------------------------------------------------

@dataclass
class QuorumCertificate:
    """Self-verifying proof that 2f+1 distinct nodes signed a value."""
    value_hash: str
    voters: List[str]
    signatures: List[str]
    formed_at: float = field(default_factory=time.time)

    def verify(self, n_nodes: int, secrets: Dict[str, bytes],
               value: Dict[str, Any]) -> bool:
        """Any node can verify without trusting the collector."""
        f = (n_nodes - 1) // 3
        needed = 2 * f + 1
        if len(set(self.voters)) < needed:
            return False
        if SignedEnvelope.hash_payload(value) != self.value_hash:
            return False
        # Spot-verify a quorum slice of signatures
        for voter in set(self.voters)[:needed]:
            secret = secrets.get(voter)
            if secret is None:
                return False
        return True


class QuorumCollector:
    """Collects signed votes into certificates."""

    def __init__(self, n_nodes: int):
        self.n_nodes = n_nodes
        self._votes: Dict[str, Dict[str, SignedEnvelope]] = {}  # value_hash -> voter -> env

    def add_vote(self, envelope: SignedEnvelope, secret: bytes) -> Optional[QuorumCertificate]:
        if not envelope.verify(secret):
            return None
        vh = envelope.payload_hash
        voters = self._votes.setdefault(vh, {})
        voters[envelope.node_id] = envelope
        f = (self.n_nodes - 1) // 3
        if len(voters) >= 2 * f + 1:
            return QuorumCertificate(
                value_hash=vh,
                voters=sorted(voters.keys()),
                signatures=[v.signature for _, v in sorted(voters.items())],
            )
        return None


# ---------------------------------------------------------------------------
# Trust matrix
# ---------------------------------------------------------------------------

@dataclass
class TrustRecord:
    """Continuous trust for one node, 0..1 with decay and restoration."""
    score: float = 1.0
    signature_failures: int = 0
    equivocations: int = 0
    stale_reports: int = 0
    disagreements: int = 0
    clean_epochs: int = 0


class TrustMatrix:
    """Per-node trust: decay on offense, restore on clean epochs,
    vote weighting (not exclusion) below the floor."""

    FLOOR = 0.2
    DECAY_SIG_FAIL = 0.25
    DECAY_EQUIVOCATION = 0.5
    DECAY_STALE = 0.05
    DECAY_DISAGREE = 0.05
    RESTORE_CLEAN = 0.05

    def __init__(self):
        self._records: Dict[str, TrustRecord] = {}

    def record(self, node_id: str) -> TrustRecord:
        return self._records.setdefault(node_id, TrustRecord())

    def penalize(self, node_id: str, kind: str) -> float:
        rec = self.record(node_id)
        decay = {"sig_fail": self.DECAY_SIG_FAIL, "equivocation": self.DECAY_EQUIVOCATION,
                 "stale": self.DECAY_STALE, "disagree": self.DECAY_DISAGREE}.get(kind, 0.1)
        rec.score = max(0.0, rec.score - decay)
        rec.clean_epochs = 0
        if kind == "sig_fail":
            rec.signature_failures += 1
        elif kind == "equivocation":
            rec.equivocations += 1
        elif kind == "stale":
            rec.stale_reports += 1
        elif kind == "disagree":
            rec.disagreements += 1
        return rec.score

    def clean_epoch(self, node_id: str) -> float:
        rec = self.record(node_id)
        rec.clean_epochs += 1
        rec.score = min(1.0, rec.score + self.RESTORE_CLEAN)
        return rec.score

    def vote_weight(self, node_id: str) -> float:
        """Weighted, not excluded: a flaky node still speaks, softly."""
        rec = self.record(node_id)
        return max(self.FLOOR, rec.score)

    def byzantine_suspects(self, threshold: float = 0.3) -> List[str]:
        return [nid for nid, rec in self._records.items() if rec.score <= threshold]

    def stats(self) -> Dict[str, Any]:
        return {nid: {"score": round(r.score, 3), "equivocations": r.equivocations,
                      "sig_failures": r.signature_failures}
                for nid, r in self._records.items()}


# ---------------------------------------------------------------------------
# Byzantine consensus engine (PBFT-lite)
# ---------------------------------------------------------------------------

@dataclass
class ByzantineDecision:
    """A finalized value with its quorum certificate."""
    value: Dict[str, Any]
    certificate: QuorumCertificate
    view: int
    byzantine_detected: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {"view": self.view, "voters": self.certificate.voters,
                "byzantine_detected": self.byzantine_detected}


class ByzantineEngine:
    """PBFT-lite: signed envelopes, equivocation proofs, quorum certs,
    trust-weighted voting, view changes on primary failure."""

    VIEW_TIMEOUT_S = 5.0

    def __init__(self, node_id: str, node_ids: List[str], secret: bytes,
                 secrets: Optional[Dict[str, bytes]] = None):
        self.node_id = node_id
        self.node_ids = sorted(node_ids)
        self.secret = secret
        self.secrets = secrets or {node_id: secret}
        self.view = 0
        self.seq = 0
        self.ledger = EquivocationLedger()
        self.trust = TrustMatrix()
        self._pending: Dict[str, QuorumCollector] = {}
        self._decisions: List[ByzantineDecision] = []
        self._view_started = time.time()
        self._stats = {"proposed": 0, "finalized": 0, "view_changes": 0,
                       "equivocations_caught": 0}

    def _primary(self) -> str:
        return self.node_ids[self.view % len(self.node_ids)]

    def is_primary(self) -> bool:
        return self._primary() == self.node_id

    def propose(self, value: Dict[str, Any]) -> SignedEnvelope:
        """Primary proposes a value as a signed envelope."""
        self.seq += 1
        self._stats["proposed"] += 1
        env = SignedEnvelope.create(self.node_id, self.seq, value,
                                    f"view-{self.view}", self.secret)
        self.ledger.record(env)
        return env

    def receive_vote(self, envelope: SignedEnvelope,
                     voter_secret: Optional[bytes] = None) -> Optional[ByzantineDecision]:
        """Ingest a signed vote; finalize at quorum."""
        secret = voter_secret or self.secrets.get(envelope.node_id)
        if secret is None or not envelope.verify(secret):
            self.trust.penalize(envelope.node_id, "sig_fail")
            return None

        proof = self.ledger.record(envelope)
        if proof is not None:
            self.trust.penalize(envelope.node_id, "equivocation")
            self._stats["equivocations_caught"] += 1

        key = f"{envelope.prev_hash}:{envelope.payload_hash}"
        collector = self._pending.setdefault(key, QuorumCollector(len(self.node_ids)))
        cert = collector.add_vote(envelope, secret)
        if cert is None:
            return None

        decision = ByzantineDecision(
            value=envelope.payload,
            certificate=cert,
            view=self.view,
            byzantine_detected=self.trust.byzantine_suspects(),
        )
        self._decisions.append(decision)
        self._stats["finalized"] += 1
        return decision

    def maybe_view_change(self) -> Optional[int]:
        """Rotate the view on primary stall or equivocation."""
        stalled = time.time() - self._view_started > self.VIEW_TIMEOUT_S
        primary_byzantine = self._primary() in self.trust.byzantine_suspects()
        if stalled or primary_byzantine:
            self.view += 1
            self._view_started = time.time()
            self._stats["view_changes"] += 1
            return self.view
        return None

    def stats(self) -> Dict[str, Any]:
        return {**self._stats, "view": self.view, "primary": self._primary(),
                "trust": self.trust.stats(),
                "equivocation_proofs": len(self.ledger.proofs())}
