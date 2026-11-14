"""Authenticated custody around the canonical offline fair-stream planner.

An unkeyed checkpoint digest is not an authenticity or anti-replay proof.
The caller must persist every returned generation and digest atomically before
dispatch, and the trusted execution owner must sign only durable results.
"""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import hmac
import json
from threading import RLock
from typing import Mapping

from .fair_stream_queue import FairStreamScheduler, MeasuredStreamBudget, StreamRequest

SCHEMA = "skeleton.ai.fair-stream-custody.v1"
RECEIPT_SCHEMA = "skeleton.ai.fair-stream-execution.v1"
TERMINAL_RECEIPT_SCHEMA = "skeleton.ai.fair-stream-execution.v2"
ABANDONMENT_SCHEMA = "skeleton.ai.fair-stream-abandonment.v1"
MAX_BYTES = 524288
ZERO = "0" * 64


def _canonical(value: object, limit: int = MAX_BYTES) -> bytes:
    try:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("invalid custody encoding") from exc
    if len(raw) > limit:
        raise ValueError("custody byte budget exceeded")
    return raw


def _key(value: object) -> bytes:
    if type(value) is not bytes or not 32 <= len(value) <= 128:
        raise ValueError("independent 32..128 byte secret key required")
    return value


def _hex(value: object, name: str, size: int = 64) -> str:
    if type(value) is not str or len(value) != size or any(
        c not in "0123456789abcdef" for c in value
    ):
        raise ValueError("invalid " + name)
    return value


def _generation(value: object) -> int:
    if type(value) is not int or not 0 <= value < (1 << 63):
        raise ValueError("invalid custody generation")
    return value


def _sign(key: bytes, body: object) -> str:
    return hmac.new(key, _canonical(body), sha256).hexdigest()


def sign_execution_result(
    *, execution_key: bytes, session_id: str, generation: int,
    checkpoint_digest: str, lease_id: str, consumed_tokens: int,
    result_digest: str, terminal: bool = False,
) -> dict[str, object]:
    """Trusted execution owner calls this AFTER durable result commit."""
    _key(execution_key)
    _hex(session_id, "session", 32)
    for label, value in (
        ("checkpoint", checkpoint_digest), ("lease", lease_id),
        ("result", result_digest),
    ):
        _hex(value, label)
    if type(consumed_tokens) is not int or not 0 <= consumed_tokens <= (1 << 24):
        raise ValueError("invalid consumed tokens")
    if type(terminal) is not bool:
        raise ValueError("explicit terminal result flag required")
    body: dict[str, object] = {
        "schema": TERMINAL_RECEIPT_SCHEMA if terminal else RECEIPT_SCHEMA, "session_id": session_id,
        "generation": _generation(generation),
        "checkpoint_digest": checkpoint_digest, "lease_id": lease_id,
        "consumed_tokens": consumed_tokens, "result_digest": result_digest,
    }
    if terminal:
        body["terminal"] = True
    return {**body, "mac": _sign(execution_key, body)}


def sign_abandonment(
    *, execution_key: bytes, session_id: str, generation: int,
    checkpoint_digest: str, lease_id: str, evidence_digest: str,
) -> dict[str, object]:
    """Distinct retirement receipt; never a successful execution result."""
    body = {
        "schema": ABANDONMENT_SCHEMA,
        "session_id": _hex(session_id, "session", 32),
        "generation": _generation(generation),
        "checkpoint_digest": _hex(checkpoint_digest, "checkpoint"),
        "lease_id": _hex(lease_id, "lease"),
        "evidence_digest": _hex(evidence_digest, "operator drainage evidence"),
    }
    return {**body, "mac": _sign(_key(execution_key), body)}


class AuthenticatedFairStreamCustody:
    """Copy-on-write scheduler state, externally fenced by durable generation CAS.

    This is not itself a durable database or physical execution owner.
    A plan cannot be dispatched until its returned state is durably stored.
    """
    def __init__(
        self, *, custody_key: bytes, execution_key: bytes, session_id: str,
        scheduler: FairStreamScheduler | None = None, generation: int = 0,
        previous_digest: str = ZERO,
    ) -> None:
        self._custody_key = _key(custody_key)
        self._execution_key = _key(execution_key)
        if hmac.compare_digest(self._custody_key, self._execution_key):
            raise ValueError("independent execution and custody keys required")
        self.session_id = _hex(session_id, "session", 32)
        self.generation = _generation(generation)
        self.previous_digest = _hex(previous_digest, "previous digest")
        self._scheduler = scheduler if scheduler is not None else FairStreamScheduler()
        if not isinstance(self._scheduler, FairStreamScheduler):
            raise ValueError("canonical scheduler required")
        self._lock = RLock()

    @property
    def pending_ids(self) -> tuple[str, ...]:
        with self._lock:
            return self._scheduler.pending_ids

    def export(self) -> dict[str, object]:
        with self._lock:
            checkpoint = self._scheduler.checkpoint()
            body: dict[str, object] = {
                "schema": SCHEMA, "session_id": self.session_id,
                "generation": self.generation,
                "previous_digest": self.previous_digest,
                "checkpoint_digest": checkpoint["digest"],
                "checkpoint": checkpoint,
            }
            digest = sha256(_canonical(body)).hexdigest()
            signed = {**body, "digest": digest}
            return {**signed, "mac": _sign(self._custody_key, signed)}

    @classmethod
    def restore(
        cls, envelope: Mapping[str, object], *, custody_key: bytes,
        execution_key: bytes, expected_generation: int,
        expected_digest: str,
    ) -> "AuthenticatedFairStreamCustody":
        _key(custody_key)
        _key(execution_key)
        fields = {
            "schema", "session_id", "generation", "previous_digest",
            "checkpoint", "checkpoint_digest", "digest", "mac",
        }
        if not isinstance(envelope, Mapping) or set(envelope) != fields:
            raise ValueError("invalid custody envelope")
        if envelope["schema"] != SCHEMA:
            raise ValueError("unsupported custody schema")
        if _generation(envelope["generation"]) != _generation(expected_generation):
            raise ValueError("stale or rolled-back custody generation")
        digest = _hex(envelope["digest"], "digest")
        if not hmac.compare_digest(digest, _hex(expected_digest, "high-watermark")):
            raise ValueError("custody high-watermark mismatch")
        signed = {k: envelope[k] for k in fields if k != "mac"}
        if not hmac.compare_digest(
            _hex(envelope["mac"], "MAC"), _sign(custody_key, signed),
        ):
            raise ValueError("custody authentication failed")
        body = {k: signed[k] for k in signed if k != "digest"}
        if not hmac.compare_digest(digest, sha256(_canonical(body)).hexdigest()):
            raise ValueError("custody digest mismatch")
        checkpoint = envelope["checkpoint"]
        if not isinstance(checkpoint, Mapping) or not hmac.compare_digest(
            _hex(envelope["checkpoint_digest"], "checkpoint digest"),
            _hex(checkpoint.get("digest"), "checkpoint binding"),
        ):
            raise ValueError("custody checkpoint binding mismatch")
        return cls(
            custody_key=custody_key, execution_key=execution_key,
            session_id=envelope["session_id"],
            scheduler=FairStreamScheduler.restore(checkpoint),
            generation=envelope["generation"],
            previous_digest=envelope["previous_digest"],
        )

    def transition(
        self, *, expected_generation: int, action: str,
        request: StreamRequest | None = None,
        request_id: str | None = None,
        budget: MeasuredStreamBudget | None = None,
        receipt: Mapping[str, object] | None = None,
        whole_request: bool = False,
    ) -> tuple[object | None, dict[str, object]]:
        with self._lock:
            if _generation(expected_generation) != self.generation:
                raise ValueError("stale custody generation")
            if self.generation == (1 << 63) - 1:
                raise ValueError("custody generation exhausted")
            # A receipt consumes exactly one generation and checkpoint. No
            # unrelated mutation may invalidate a previously issued permit.
            if self._scheduler.pending_ids and action not in ("acknowledge", "abandon"):
                raise ValueError("pending leases require execution reconciliation")
            # Restore before modifying, so any invalid operation is atomic.
            trial = FairStreamScheduler.restore(self._scheduler.checkpoint())
            plan = None
            if action == "submit":
                if not isinstance(request, StreamRequest):
                    raise ValueError("typed stream request required")
                trial.submit(request)
            elif action == "cancel":
                if type(request_id) is not str:
                    raise ValueError("request identity required")
                trial.cancel(request_id)
            elif action == "plan":
                if not isinstance(budget, MeasuredStreamBudget):
                    raise ValueError("typed measured budget required")
                # The authenticated protocol has a single-receipt CAS, not
                # an atomic batch receipt. Keep the standalone planner's
                # multi-stream API, but never issue multiple durable permits.
                single = replace(budget, stream_slots=min(1, budget.stream_slots))
                plan = trial.plan(single, whole_request=whole_request)
            elif action == "abandon":
                required = {"schema", "session_id", "generation", "checkpoint_digest",
                            "lease_id", "evidence_digest", "mac"}
                if not isinstance(receipt, Mapping) or set(receipt) != required:
                    raise ValueError("signed abandonment receipt required")
                expected = sign_abandonment(
                    execution_key=self._execution_key, session_id=self.session_id,
                    generation=self.generation, checkpoint_digest=self._scheduler.checkpoint()["digest"],
                    lease_id=receipt["lease_id"], evidence_digest=receipt["evidence_digest"],
                )
                if dict(receipt) != expected or type(receipt["generation"]) is not int:
                    raise ValueError("unauthenticated or stale abandonment receipt")
                trial.abandon_pending(receipt["lease_id"])
            elif action == "acknowledge":
                required = {
                    "schema", "session_id", "generation", "checkpoint_digest",
                    "lease_id", "consumed_tokens", "result_digest", "mac",
                }
                if not isinstance(receipt, Mapping):
                    raise ValueError("signed execution receipt required")
                terminal = receipt.get("schema") == TERMINAL_RECEIPT_SCHEMA
                if terminal:
                    required.add("terminal")
                if set(receipt) != required or (terminal and receipt["terminal"] is not True):
                    raise ValueError("invalid execution receipt shape")
                body = {k: receipt[k] for k in required if k != "mac"}
                if body["schema"] not in (RECEIPT_SCHEMA, TERMINAL_RECEIPT_SCHEMA) or not hmac.compare_digest(
                    _hex(receipt["mac"], "receipt MAC"),
                    _sign(self._execution_key, body),
                ):
                    raise ValueError("unauthenticated execution receipt")
                checkpoint = self._scheduler.checkpoint()
                if (receipt["session_id"] != self.session_id
                        or receipt["generation"] != self.generation
                        or receipt["checkpoint_digest"] != checkpoint["digest"]
                        or receipt["lease_id"] not in self._scheduler.pending_ids):
                    raise ValueError("stale or unbound execution receipt")
                _hex(receipt["result_digest"], "result digest")
                trial.acknowledge(
                    receipt["lease_id"], consumed_tokens=receipt["consumed_tokens"], terminal=terminal,
                )
            else:
                raise ValueError("unsupported custody transition")
            prior = self.export()["digest"]
            self._scheduler = trial
            self.previous_digest = prior
            self.generation += 1
            return plan, self.export()
