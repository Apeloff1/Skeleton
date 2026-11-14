"""Explicit forward-only repair of the SQLite COMMIT / external anchor CAS gap.

Requires independent operator authorization and a quiescent deployment.
No scheduler transition, receipt, backend invocation or lease reissue occurs.
A stale database, missing anchor, gap larger than one, or nonmatching lineage
is never repaired here. The anchor must enforce atomic durable CAS itself.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hmac
import json

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey,
)

from .fair_stream_session import DurableFairStreamSession, TrustedHighWatermark
from .fair_stream_sqlite import DurableFairStreamStore

SCHEMA = "skeleton.ai.fair-stream-anchor-forward-v1"
MAX_GENERATION = (1 << 63) - 1


class AnchorRecoveryDenied(RuntimeError):
    """No recovery authorization or independently verifiable lineage."""


def _hex(value: object, size: int) -> None:
    if type(value) is not str or len(value) != size or any(
        char not in "0123456789abcdef" for char in value
    ):
        raise AnchorRecoveryDenied("invalid recovery identity")


@dataclass(frozen=True, slots=True)
class ForwardCandidate:
    session_id: str
    prior_generation: int
    prior_digest: str
    next_generation: int
    next_digest: str
    checkpoint_digest: str
    queued_requests: int
    pending_leases: int

    def __post_init__(self) -> None:
        _hex(self.session_id, 32)
        for digest in (self.prior_digest, self.next_digest, self.checkpoint_digest):
            _hex(digest, 64)
        if (
            type(self.prior_generation) is not int
            or type(self.next_generation) is not int
            or not 0 <= self.prior_generation < MAX_GENERATION
            or self.next_generation != self.prior_generation + 1
            or hmac.compare_digest(self.prior_digest, self.next_digest)
            or type(self.queued_requests) is not int
            or not 0 <= self.queued_requests <= 4096
            or type(self.pending_leases) is not int
            or not 0 <= self.pending_leases <= min(64, self.queued_requests)
        ):
            raise AnchorRecoveryDenied("invalid one-step recovery descriptor")


@dataclass(frozen=True, slots=True)
class ForwardApproval:
    candidate: ForwardCandidate
    nonce: str
    signature: str


def _message(candidate: ForwardCandidate, nonce: str) -> bytes:
    if type(candidate) is not ForwardCandidate:
        raise AnchorRecoveryDenied("canonical recovery candidate required")
    _hex(nonce, 32)
    candidate.__post_init__()
    return json.dumps(
        {"schema": SCHEMA, "candidate": asdict(candidate), "nonce": nonce},
        sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False,
    ).encode("ascii")


def issue_forward_approval(
    candidate: ForwardCandidate, *, nonce: str, signing_key: Ed25519PrivateKey,
) -> ForwardApproval:
    """Operator-only signer. Keep its private key outside the executor."""
    if not isinstance(signing_key, Ed25519PrivateKey):
        raise AnchorRecoveryDenied("independent operator signing key required")
    return ForwardApproval(
        candidate, nonce, signing_key.sign(_message(candidate, nonce)).hex(),
    )


def _verify(approval: ForwardApproval, key: Ed25519PublicKey) -> None:
    if type(approval) is not ForwardApproval or not isinstance(key, Ed25519PublicKey):
        raise AnchorRecoveryDenied("pinned operator approval required")
    _hex(approval.signature, 128)
    try:
        key.verify(bytes.fromhex(approval.signature), _message(approval.candidate, approval.nonce))
    except (InvalidSignature, ValueError) as exc:
        raise AnchorRecoveryDenied("operator approval signature invalid") from exc


def _anchor(watermark: TrustedHighWatermark) -> tuple[int, str]:
    generation, digest = watermark.read()
    if type(generation) is not int or not 0 <= generation <= MAX_GENERATION:
        raise AnchorRecoveryDenied("invalid independent anchor generation")
    _hex(digest, 64)
    return generation, digest


def _candidate_locked(
    store: DurableFairStreamStore, watermark: TrustedHighWatermark,
) -> ForwardCandidate:
    prior_generation, prior_digest = _anchor(watermark)
    row = store._read()
    if row is None or row[0] != prior_generation + 1:
        raise AnchorRecoveryDenied("only a one-generation forward gap can be repaired")
    # Verify canonical encoding, HMAC, checkpoint and session binding, without
    # treating the row's self-reported digest as independent authority.
    owner = store._restore(row, expected_generation=row[0], expected_digest=row[1])
    state = owner.export()
    if not hmac.compare_digest(state["previous_digest"], prior_digest):
        raise AnchorRecoveryDenied("candidate does not descend from independent anchor")
    checkpoint = state["checkpoint"]
    return ForwardCandidate(
        store.session_id, prior_generation, prior_digest, row[0], row[1],
        state["checkpoint_digest"], len(checkpoint["requests"]), len(checkpoint["pending"]),
    )


def inspect_forward_candidate(
    store: DurableFairStreamStore, watermark: TrustedHighWatermark,
) -> ForwardCandidate:
    """Content-free candidate for separate operator review; no anchor mutation."""
    if type(store) is not DurableFairStreamStore:
        raise AnchorRecoveryDenied("canonical custody store required")
    store._require_owner_process()
    with store._lock:
        store._begin()
        try:
            return _candidate_locked(store, watermark)
        finally:
            store._connection.rollback()


def recover_forward_anchor(
    store: DurableFairStreamStore, watermark: TrustedHighWatermark, *,
    approval: ForwardApproval, operator_public_key: Ed25519PublicKey,
) -> DurableFairStreamSession:
    """Advance only the exact approved successor; return a freshly verified session.

    The process must have exclusive operational ownership with old dispatchers
    stopped. BEGIN IMMEDIATE blocks other SQLite writers while the independent
    CAS executes. If CAS throws after committing, no session is returned; a
    normal verified reopen determines whether the anchor actually advanced.
    """
    _verify(approval, operator_public_key)
    if type(store) is not DurableFairStreamStore:
        raise AnchorRecoveryDenied("canonical custody store required")
    store._require_owner_process()
    with store._lock:
        store._begin()
        try:
            candidate = _candidate_locked(store, watermark)
            if candidate != approval.candidate:
                raise AnchorRecoveryDenied("approval does not bind current forward candidate")
            store._assert_private()
            watermark.advance(
                expected_generation=candidate.prior_generation,
                expected_digest=candidate.prior_digest,
                generation=candidate.next_generation,
                digest=candidate.next_digest,
            )
            if _anchor(watermark) != (candidate.next_generation, candidate.next_digest):
                raise AnchorRecoveryDenied("independent anchor did not confirm advance")
            store._assert_private()
        finally:
            # This transaction performs no SQL writes. Release the writer
            # reservation even when the CAS outcome is uncertain.
            store._connection.rollback()
    return DurableFairStreamSession(store, watermark)
