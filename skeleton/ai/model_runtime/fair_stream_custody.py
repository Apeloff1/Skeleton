"""Authenticated custody around the canonical offline fair-stream planner.

An unkeyed checkpoint digest is not an authenticity or anti-replay proof.
The caller must persist every returned generation and digest atomically before
dispatch, and the trusted execution owner must sign only durable results.
"""
from __future__ import annotations

from hashlib import sha256
import hmac
import json
from threading import RLock
from typing import Mapping

from .fair_stream_admission import validate_request_identity
from .fair_stream_queue import FairStreamScheduler, MeasuredStreamBudget, StreamRequest

SCHEMA = "skeleton.ai.fair-stream-custody.v1"
RECEIPT_SCHEMA = "skeleton.ai.fair-stream-execution.v1"
CANCELLATION_SCHEMA = "skeleton.ai.fair-stream-unstarted-cancellation.v1"
ABANDONMENT_SCHEMA = "skeleton.ai.fair-stream-abandonment.v1"
MAX_BYTES = 524288
ZERO = "0" * 64


def _canonical(value: object, limit: int = MAX_BYTES) -> bytes:
    try:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
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
    result_digest: str,
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
    body: dict[str, object] = {
        "schema": RECEIPT_SCHEMA, "session_id": session_id,
        "generation": _generation(generation),
        "checkpoint_digest": checkpoint_digest, "lease_id": lease_id,
        "consumed_tokens": consumed_tokens, "result_digest": result_digest,
    }
    return {**body, "mac": _sign(execution_key, body)}


def sign_unstarted_cancellation(
    *, execution_key: bytes, session_id: str, generation: int,
    checkpoint_digest: str, lease_id: str, request_id: str,
) -> dict[str, object]:
    """Distinct from a result receipt: journal has fenced execution permanently."""
    _key(execution_key)
    _hex(session_id, "session", 32)
    _hex(checkpoint_digest, "checkpoint")
    _hex(lease_id, "lease")
    validate_request_identity(request_id)
    body = {
        "schema": CANCELLATION_SCHEMA, "session_id": session_id,
        "generation": _generation(generation), "checkpoint_digest": checkpoint_digest,
        "lease_id": lease_id, "request_id": request_id,
    }
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
        if scheduler is not None and type(scheduler) is not FairStreamScheduler:
            raise ValueError("canonical scheduler required")
        # Never sign mutable state owned by the caller. Adopt a detached,
        # validated snapshot once, leaving all subsequent edits to transition.
        self._scheduler = (
            FairStreamScheduler.restore(scheduler.checkpoint())
            if scheduler is not None else FairStreamScheduler()
        )
        self._lock = RLock()

    @property
    def whole_request(self) -> bool:
        return self._scheduler.whole_request

    @property
    def pending_ids(self) -> tuple[str, ...]:
        with self._lock:
            return self._scheduler.pending_ids

    def _envelope(self, scheduler: FairStreamScheduler, generation: int,
                  previous_digest: str) -> dict[str, object]:
        checkpoint = scheduler.checkpoint()
        body: dict[str, object] = {
            "schema": SCHEMA, "session_id": self.session_id,
            "generation": _generation(generation),
            "previous_digest": _hex(previous_digest, "previous digest"),
            "checkpoint_digest": checkpoint["digest"],
            "checkpoint": checkpoint,
        }
        digest = sha256(_canonical(body)).hexdigest()
        signed = {**body, "digest": digest}
        envelope = {**signed, "mac": _sign(self._custody_key, signed)}
        # The final MAC itself counts against the durable byte ceiling.
        _canonical(envelope)
        return envelope

    def export(self) -> dict[str, object]:
        with self._lock:
            return self._envelope(self._scheduler, self.generation, self.previous_digest)

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
        if type(envelope) is not dict or set(envelope) != fields:
            raise ValueError("invalid custody envelope")
        if type(envelope["schema"]) is not str or envelope["schema"] != SCHEMA:
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
        if type(checkpoint) is not dict or not hmac.compare_digest(
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
        tenant_id: str | None = None,
        budget: MeasuredStreamBudget | None = None,
        receipt: Mapping[str, object] | None = None,
        whole_request: bool | None = None,
    ) -> tuple[object | None, dict[str, object]]:
        allowed = {
            "submit": {"request"}, "cancel": {"request_id", "tenant_id"},
            "plan": {"budget"}, "cancel_unstarted": {"receipt", "tenant_id"},
            "abandon": {"receipt"}, "acknowledge": {"receipt"},
        }
        if type(action) is not str or action not in allowed:
            raise ValueError("unsupported custody transition")
        supplied = {name for name, value in (
            ("request", request), ("request_id", request_id), ("tenant_id", tenant_id),
            ("budget", budget), ("receipt", receipt),
        ) if value is not None}
        if supplied - allowed[action]:
            raise ValueError("irrelevant custody transition arguments")
        if whole_request is not None and (
            type(whole_request) is not bool or action not in {"plan", "acknowledge"}
            or whole_request != self.whole_request
        ):
            raise ValueError("execution policy differs from checkpoint")
        with self._lock:
            if _generation(expected_generation) != self.generation:
                raise ValueError("stale custody generation")
            if self.generation == (1 << 63) - 1:
                raise ValueError("custody generation exhausted")
            # Restore before modifying, so any invalid operation is atomic.
            trial = FairStreamScheduler.restore(self._scheduler.checkpoint())
            plan = None
            if action == "submit":
                if type(request) is not StreamRequest:
                    raise ValueError("typed stream request required")
                trial.submit(request)
            elif action == "cancel":
                if type(request_id) is not str:
                    raise ValueError("request identity required")
                trial.cancel(request_id, tenant_id=tenant_id)
            elif action == "plan":
                if type(budget) is not MeasuredStreamBudget:
                    raise ValueError("typed measured budget required")
                plan = trial.plan(budget, whole_request=whole_request)
            elif action == "cancel_unstarted":
                fields = {"schema", "session_id", "generation", "checkpoint_digest",
                          "lease_id", "request_id", "mac"}
                if not self.whole_request or type(receipt) is not dict or set(receipt) != fields:
                    raise ValueError("signed native cancellation required")
                expected = sign_unstarted_cancellation(
                    execution_key=self._execution_key, session_id=self.session_id,
                    generation=self.generation,
                    checkpoint_digest=self._scheduler.checkpoint()["digest"],
                    lease_id=receipt["lease_id"], request_id=receipt["request_id"],
                )
                if not hmac.compare_digest(_canonical(receipt), _canonical(expected)):
                    raise ValueError("cancellation authentication or binding failed")
                trial.cancel_unstarted(receipt["lease_id"], receipt["request_id"], tenant_id=tenant_id)
            elif action == "abandon":
                fields = {"schema", "session_id", "generation", "checkpoint_digest",
                          "lease_id", "evidence_digest", "mac"}
                if type(receipt) is not dict or set(receipt) != fields:
                    raise ValueError("signed abandonment receipt required")
                expected = sign_abandonment(
                    execution_key=self._execution_key, session_id=self.session_id,
                    generation=self.generation,
                    checkpoint_digest=self._scheduler.checkpoint()["digest"],
                    lease_id=receipt["lease_id"], evidence_digest=receipt["evidence_digest"],
                )
                if not hmac.compare_digest(_canonical(receipt), _canonical(expected)):
                    raise ValueError("abandonment authentication or binding failed")
                trial.abandon_pending(receipt["lease_id"])
            elif action == "acknowledge":
                required = {
                    "schema", "session_id", "generation", "checkpoint_digest",
                    "lease_id", "consumed_tokens", "result_digest", "mac",
                }
                if type(receipt) is not dict or set(receipt) != required:
                    raise ValueError("signed execution receipt required")
                body = {k: receipt[k] for k in required if k != "mac"}
                if body["schema"] != RECEIPT_SCHEMA or not hmac.compare_digest(
                    _hex(receipt["mac"], "receipt MAC"),
                    _sign(self._execution_key, body),
                ):
                    raise ValueError("unauthenticated execution receipt")
                checkpoint = self._scheduler.checkpoint()
                if (_hex(receipt["session_id"], "session", 32) != self.session_id
                        or _generation(receipt["generation"]) != self.generation
                        or receipt["checkpoint_digest"] != checkpoint["digest"]
                        or receipt["lease_id"] not in self._scheduler.pending_ids):
                    raise ValueError("stale or unbound execution receipt")
                _hex(receipt["result_digest"], "result digest")
                trial.acknowledge(
                    receipt["lease_id"], consumed_tokens=receipt["consumed_tokens"],
                    whole_request=whole_request,
                )
            else:
                raise ValueError("unsupported custody transition")
            prior = self.export()["digest"]
            successor = self._envelope(trial, self.generation + 1, prior)
            # Every operation, including final encoding and MAC construction,
            # must succeed before publishing any in-memory successor fields.
            self._scheduler = trial
            self.previous_digest = prior
            self.generation += 1
            return plan, successor
