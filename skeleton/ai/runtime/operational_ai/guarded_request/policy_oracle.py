"""Executable independent acceptance entrypoints for checked AI control domains.

These evaluate real gate objects, not synthetic model output. Failed policy
checks produce denial codes; unexpected exceptions propagate as test failures.
"""
from __future__ import annotations

import sqlite3
from typing import Any

from dataclasses import replace
from .signed_envelope import SignedEnvelope
from .memory_consent import MemoryConsent
from .token_floor import NativeTokenFence
from .workspace import require_leaf
from .budgets import Quota
from .context_window import ContextSlice, compose_user_context
from .evidence import Citation
from .errors import GateDenied
from .grants import ReadGrant
from .identities import Scope, require_id
from .model_pins import require_sha256
from .nonce_fence import NonceFence
from .pressure import Pressure, PressurePolicy
from .queue import FairQueue, QueueTicket
from .receipts import EffectReceipts
from .stream import StreamFence
from .transport_gate import LoopbackGate

_MODEL = "a" * 64
_TOKEN = "Z" * 48


def _evaluate(control: str, data: dict[str, Any]) -> str:
    if control == "identity":
        require_id(data["value"])
        return "admitted"
    if control == "quota":
        Quota(**data)
        return "admitted"
    if control == "model_pin":
        require_sha256(data["sha256"])
        return "admitted"
    if control == "evidence":
        citation = Citation(
            "source_1", data["sha256"], data["begin"], data["end"], data["passage"]
        )
        citation.verify(data["source"].encode("utf-8"))
        return "admitted"
    if control == "grant":
        scope = Scope("tenant", "user", "session", _MODEL)
        provided = Scope(data["selected_tenant"], "user", "session", _MODEL)
        grant = ReadGrant(scope, frozenset({"hash_text", "count_text"}), data["expires_ns"])
        grant.check(
            scope=provided, tool=data["tool"],
            now_ns=data["now_ns"], mutating=data["mutating"],
        )
        return "admitted"
    if control == "pressure":
        p = Pressure(data["memory_ratio"], data["cpu_ratio"], data["queue_ratio"], 1000)
        return PressurePolicy().decide(p, now_ms=1000 + data["age_ms"])
    if control == "stream":
        stream = StreamFence(max_bytes=data["max_bytes"], max_chunks=data["max_chunks"])
        for chunk in data["chunks"]:
            stream.push(chunk.encode("utf-8"))
        stream.finish()
        return "admitted"
    if control == "transport":
        gate = LoopbackGate(_TOKEN, max_body=8192)
        headers = {
            "content-type": data["content_type"],
            "authorization": data["authorization"],
        }
        if data["origin"] is not None:
            headers["origin"] = data["origin"]
        gate.authorize(
            peer_ip=data["peer_ip"], host=data["host"], method=data["method"],
            route=data["route"], headers=headers, body_length=data["body_length"],
        )
        return "admitted"
    if control == "nonce":
        with sqlite3.connect(":memory:", isolation_level=None) as db:
            fence = NonceFence(db)
            disposition = "admitted"
            for nonce, sequence, sha in zip(
                data["nonces"], data["sequences"], data["digests"], strict=True
            ):
                disposition = fence.reserve("scope", nonce, sequence, sha)
            return disposition
    if control == "queue":
        queue = FairQueue(capacity=data["capacity"], per_owner=data["per_owner"])
        for i, owner in enumerate(data["owners"]):
            queue.enqueue(QueueTicket("request_" + str(i), owner))
        dispatched = []
        while ticket := queue.poll():
            dispatched.append(ticket.request_id)
            queue.finish(ticket)
        if len(dispatched) != len(data["owners"]):
            raise AssertionError("queue silently dropped a request")
        return "admitted"
    if control == "effects":
        with sqlite3.connect(":memory:", isolation_level=None) as db:
            receipts = EffectReceipts(db)
            first = data["args_sha"]
            receipts.prepare(scope="scope", effect_id="effect", args_sha=first)
            receipts.close(
                scope="scope", effect_id="effect", args_sha=first,
                committed=data["committed"], verified_receipt={"sha": first},
            )
            receipts.prepare(
                scope="scope", effect_id="effect", args_sha=data["next_args_sha"]
            )
            if data["contradict"]:
                receipts.close(
                    scope="scope", effect_id="effect", args_sha=first,
                    committed=not data["committed"], verified_receipt={"sha": first},
                )
            return "admitted"
    if control == "context":
        quota = Quota(
            context_tokens=data["context_tokens"], output_tokens=data["output_tokens"]
        )
        evidence = (
            ContextSlice.from_text(
                data["source"], approved=data["approved"], cited=data["cited"]
            ),
        ) if data["source"] is not None else ()
        compose_user_context(data["question"], quota=quota, evidence=evidence)
        return "admitted"

    if control == "envelope":
        original = Scope(data["scope_tenant"], "user", "session", _MODEL)
        envelope = SignedEnvelope.sign(
            b"k" * 32, scope=original, nonce="nonce", sequence=data["sequence"],
            payload_sha256=data["payload_sha"], issued_ms=data["issued_ms"],
            expires_ms=data["expires_ms"],
        )
        if data["tamper"]:
            envelope = replace(envelope, mac_sha256="0" * 64)
        envelope.verify(
            b"k" * 32 if data["same_key"] else b"x" * 32,
            scope=Scope(data["verify_tenant"], "user", "session", _MODEL),
            payload_sha256=data["verify_payload_sha"], now_ms=data["now_ms"],
        )
        return "admitted"

    if control == "memory":
        scope = Scope(data["scope_tenant"], "user", "session", _MODEL)
        consent = MemoryConsent(
            scope=scope, consent_id="consent_1", source_sha256=data["source_sha"],
            category=data["category"], approved_by_caller=data["approved"],
            issued_ms=data["issued_ms"], expires_ms=data["expires_ms"],
        )
        consent.authorize(
            scope=Scope(data["verify_tenant"], "user", "session", _MODEL),
            source_sha256=data["verify_source_sha"], now_ms=data["now_ms"],
            caller_approved=data["caller_approved"],
        )
        return "admitted"

    if control == "tokens":
        def count_exact(value: str) -> int:
            # Deterministic test adapter, never used in production inference.
            if data["bad_counter"]:
                return True
            return len(value.split())
        gate = NativeTokenFence(
            model_sha256=_MODEL, tokenizer_sha256="b" * 64,
            counter=count_exact, max_context=data["max_context"],
        )
        gate.reserve(
            data["prompt"], model_sha256=data["model_sha"],
            tokenizer_sha256=data["tokenizer_sha"],
            output_tokens=data["output_tokens"],
            system_reserve=data["system_reserve"],
        )
        return "admitted"

    if control == "workspace":
        require_leaf(data["leaf"])
        return "admitted"

    raise AssertionError("unknown scenario domain: " + str(control))


def evaluate(control: str, data: dict[str, Any]) -> dict[str, str | bool]:
    """Allow/deny result, preserving the exact stable denial code."""
    try:
        outcome = _evaluate(control, data)
        return {"allowed": True, "code": outcome}
    except GateDenied as error:
        return {"allowed": False, "code": error.code}
