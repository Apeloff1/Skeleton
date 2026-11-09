"""Operator-approved multi-turn real GGUF acceptance and durable cold replay.

This is a runnable production acceptance path. Every fresh turn passes through
the existing NativeJeevesChat -> TurnBridge -> SupervisedAI -> ExecutionSpine.
The model must already be source-verified and installed; this module neither
loads an unapproved model nor replaces the backend. Source-only CI exercises
the protocol using a plainly SYNTHETIC generator and real SQLite/WAL.

A successful replay alone is not physical hardware or native cancellation
qualification. In particular, no model-created content certifies its own
quality, rights, latency requirements or inference safety.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import math
import secrets
import time
from typing import Any, Callable, Sequence

from skeleton.ai.runtime.operational_ai.laptop_runtime.identity import ActiveModel
from .native_chat import NativeJeevesChat


class NativeSessionHold(ValueError):
    """Native session acceptance was refused or cannot be proved."""


def _text(value: object, *, maximum_bytes: int = 32768) -> str:
    if type(value) is not str or not value.strip():
        raise NativeSessionHold("nonempty typed native prompt required")
    try:
        raw = value.encode("utf-8", "strict")
    except UnicodeError as exc:
        raise NativeSessionHold("invalid prompt Unicode") from exc
    if len(raw) > maximum_bytes or b"\x00" in raw:
        raise NativeSessionHold("native prompt exceeds private admission contract")
    return value


def _id(value: object, *, name: str = "case") -> str:
    from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import identifier
    if type(value) is not str:
        raise NativeSessionHold("typed " + name + " identity required")
    try:
        return identifier(value, name)
    except ValueError as exc:
        raise NativeSessionHold("invalid " + name) from exc


@dataclass(frozen=True, slots=True)
class SessionCase:
    case_id: str
    prompt: str
    expected_output_sha256: str | None = None

    def __post_init__(self):
        _id(self.case_id)
        _text(self.prompt)
        if self.expected_output_sha256 is not None:
            from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import identity_hash
            identity_hash(self.expected_output_sha256)

    @property
    def input_sha256(self) -> str:
        return sha256(self.prompt.encode("utf-8", "strict")).hexdigest()


@dataclass(frozen=True, slots=True)
class SessionBudget:
    maximum_turns: int = 8
    maximum_reserved_output_tokens: int = 8192
    maximum_prompt_bytes: int = 65536
    maximum_wall_seconds: float = 900.0
    maximum_single_turn_ms: int = 300000

    def __post_init__(self):
        for name, lo, hi in (
            ("maximum_turns", 1, 32),
            ("maximum_reserved_output_tokens", 1, 262144),
            ("maximum_prompt_bytes", 1, 1048576),
            ("maximum_single_turn_ms", 1, 600000),
        ):
            v = getattr(self, name)
            if type(v) is not int or not lo <= v <= hi:
                raise NativeSessionHold("session budget exceeds bounded policy")
        if (type(self.maximum_wall_seconds) not in (int, float)
            or not math.isfinite(self.maximum_wall_seconds)
            or not 0 < self.maximum_wall_seconds <= 3600):
            raise NativeSessionHold("session wall-time must be finite and bounded")


@dataclass(frozen=True, slots=True)
class SessionTurnProof:
    case_id: str
    request_id: str
    prompt_sha256: str
    output_sha256: str
    model_sha256: str
    tokenizer_sha256: str
    prompt_tokens: int
    generated_tokens: int
    wall_ms: int
    replayed: bool
    exact_predicate_passed: bool | None

    def public_record(self) -> dict[str, object]:
        return {
            "schema": "jeeves.native_multiturn_proof.v1",
            "case_id": self.case_id,
            "request_id": self.request_id,
            "prompt_sha256": self.prompt_sha256,
            "output_sha256": self.output_sha256,
            "model_sha256": self.model_sha256,
            "tokenizer_sha256": self.tokenizer_sha256,
            "prompt_tokens": self.prompt_tokens,
            "generated_tokens": self.generated_tokens,
            "wall_ms": self.wall_ms,
            "replayed": self.replayed,
            "exact_predicate_passed": self.exact_predicate_passed,
            "source_only_fixture": False,
            "physical_device_qualified": False,
            "model_rights_independent_review": False,
            "release_certified": False,
        }


@dataclass(frozen=True, slots=True)
class SessionAcceptance:
    session_id: str
    scope_model_sha256: str
    scope_tokenizer_sha256: str
    turns: tuple[SessionTurnProof, ...]
    complete: bool
    cold_replay_verified: bool = False

    def to_record(self) -> dict[str, object]:
        return {
            "schema": "jeeves.native_session_acceptance.v1",
            "session_id": self.session_id,
            "model_sha256": self.scope_model_sha256,
            "tokenizer_sha256": self.scope_tokenizer_sha256,
            "turns": [t.public_record() for t in self.turns],
            "committed_turns": len(self.turns),
            "all_committed_without_retry": self.complete,
            "cold_replay_verified": self.cold_replay_verified,
            "native_cancellation_qualified": False,
            "device_pressure_qualified": False,
            "clean_windows_install_qualified": False,
            "release_certified": False,
        }


def _admit_cases(cases: Sequence[SessionCase], budget: SessionBudget, worker: Any) -> tuple:
    if not isinstance(budget, SessionBudget):
        raise NativeSessionHold("typed finite acceptance budget required")
    if type(cases) not in (tuple, list) or not 1 <= len(cases) <= budget.maximum_turns:
        raise NativeSessionHold("bounded nonempty session acceptance casebook required")
    if any(not isinstance(x, SessionCase) for x in cases):
        raise NativeSessionHold("typed native session cases required")
    if len({x.case_id for x in cases}) != len(cases):
        raise NativeSessionHold("duplicate case identity")
    if sum(len(x.prompt.encode("utf-8", "strict")) for x in cases) > budget.maximum_prompt_bytes:
        raise NativeSessionHold("multi-turn input capacity exceeded")
    native = worker.spine.limits
    if native.max_output_tokens * len(cases) > budget.maximum_reserved_output_tokens:
        raise NativeSessionHold("multi-turn full native output reservation exceeded")
    identity = ActiveModel.from_supervisor(worker)
    return tuple(cases), identity


def run_native_session(
    worker: Any, cases: Sequence[SessionCase], *,
    approved: bool,
    budget: SessionBudget | None = None,
    monotonic: Callable[[], float] = time.monotonic,
) -> SessionAcceptance:
    """Execute one finite real-native conversation with no speculative retries."""
    if approved is not True:
        raise NativeSessionHold("explicit real-model multi-turn approval required")
    cases, identity = _admit_cases(cases, budget or SessionBudget(), worker)
    resolved_budget = budget or SessionBudget()
    if not callable(monotonic):
        raise NativeSessionHold("monotonic clock required")
    started = monotonic()
    chat = NativeJeevesChat(worker)
    proofs = []
    for case in cases:
        if monotonic() - started >= resolved_budget.maximum_wall_seconds:
            raise NativeSessionHold("finite model acceptance wall clock exhausted")
        request_id = "ns_" + secrets.token_hex(16)
        began = monotonic()
        turn = chat.turn(case.prompt, request_id=request_id)
        elapsed = monotonic() - began
        if not math.isfinite(elapsed) or elapsed < 0:
            raise NativeSessionHold("nonmonotonic turn measurement")
        millis = int(math.ceil(elapsed * 1000))
        if millis > resolved_budget.maximum_single_turn_ms:
            raise NativeSessionHold("native single-turn duration breached approved limit")
        if (turn.model_sha256 != identity.model_sha256
            or turn.tokenizer_sha256 != identity.tokenizer_sha256
            or turn.replayed):
            raise NativeSessionHold("unexpected native model identity or replay at first execution")
        if sha256(turn.text.encode("utf-8", "strict")).hexdigest() != turn.output_sha256:
            raise NativeSessionHold("native committed output bytes changed")
        exact = (
            turn.output_sha256 == case.expected_output_sha256
            if case.expected_output_sha256 is not None else None
        )
        # A failed objective criterion is not a pass, but the durable native
        # result itself remains committed and must never be regenerated.
        proofs.append(SessionTurnProof(
            case_id=case.case_id,
            request_id=request_id,
            prompt_sha256=case.input_sha256,
            output_sha256=turn.output_sha256,
            model_sha256=turn.model_sha256,
            tokenizer_sha256=turn.tokenizer_sha256,
            prompt_tokens=turn.prompt_tokens,
            generated_tokens=turn.generated_tokens,
            wall_ms=millis,
            replayed=turn.replayed,
            exact_predicate_passed=exact,
        ))
        if exact is False:
            raise NativeSessionHold("operator exact-answer criterion was not satisfied")
    history = chat.history(maximum_messages=max(2, len(cases) * 2))
    if len(history) != 2 * len(cases):
        raise NativeSessionHold("canonical conversation history lost committed turns")
    if any(history[i]["role"] != "user"
           or history[i + 1]["role"] != "assistant"
           for i in range(0, len(history), 2)):
        raise NativeSessionHold("authoritative transcript role ordering changed")
    return SessionAcceptance(
        session_id=chat.session_id,
        scope_model_sha256=identity.model_sha256,
        scope_tokenizer_sha256=identity.tokenizer_sha256,
        turns=tuple(proofs), complete=True,
    )


def verify_cold_session_replay(
    worker: Any, cases: Sequence[SessionCase],
    original: SessionAcceptance, *,
    approved: bool,
) -> SessionAcceptance:
    """Reopen each exact prior request from new installed model epoch; NO inference."""
    if approved is not True:
        raise NativeSessionHold("explicit operator cold replay approval required")
    if not isinstance(original, SessionAcceptance) or not original.complete:
        raise NativeSessionHold("original verified native acceptance receipt required")
    if type(cases) not in (tuple, list) or len(cases) != len(original.turns):
        raise NativeSessionHold("cold replay case count changed")
    identity = ActiveModel.from_supervisor(worker)
    if (identity.model_sha256 != original.scope_model_sha256
        or identity.tokenizer_sha256 != original.scope_tokenizer_sha256):
        raise NativeSessionHold("restarted native model or tokenizer identity mismatch")
    chat = NativeJeevesChat(worker, session_id=original.session_id)
    reopened = []
    for case, prior in zip(cases, original.turns):
        if not isinstance(case, SessionCase) or case.case_id != prior.case_id:
            raise NativeSessionHold("cold replay casebook identity changed")
        if case.input_sha256 != prior.prompt_sha256:
            raise NativeSessionHold("cold replay prompt bytes changed")
        turn = chat.turn(case.prompt, request_id=prior.request_id)
        if (turn.replayed is not True
            or turn.output_sha256 != prior.output_sha256
            or turn.model_sha256 != prior.model_sha256
            or turn.tokenizer_sha256 != prior.tokenizer_sha256):
            raise NativeSessionHold("cold replay requires exactly the old SQLite result")
        reopened.append(prior)
    history = chat.history(maximum_messages=max(2, len(cases) * 2))
    if len(history) != len(cases) * 2:
        raise NativeSessionHold("committed history changed across native restart")
    return SessionAcceptance(
        session_id=original.session_id,
        scope_model_sha256=identity.model_sha256,
        scope_tokenizer_sha256=identity.tokenizer_sha256,
        turns=tuple(reopened), complete=True,
        cold_replay_verified=True,
    )


__all__ = [
    "NativeSessionHold", "SessionCase", "SessionBudget",
    "SessionTurnProof", "SessionAcceptance",
    "run_native_session", "verify_cold_session_replay",
]
