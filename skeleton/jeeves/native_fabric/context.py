"""Host-owned context packing, trust boundaries and explicit omission receipts.

This code does not claim zero information loss. It assembles exact source
receipts into a bounded context with deterministic token budgets, treats all
retrieved content as untrusted, and reports every omitted or clipped segment
rather than hiding truncation from the caller or LLM.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
import math
from typing import Callable, Mapping, Sequence

from .contracts import (
    ContractHold, canonical_bytes, exact_integer, fingerprint, identifier,
    text, digest,
)


@dataclass(frozen=True, slots=True)
class Segment:
    segment_id: str
    content: str
    kind: str
    source_sha256: str
    scope_sha256: str
    priority: int = 0
    tokens: int = 0
    mandatory: bool = False
    trusted_instruction: bool = False

    def __post_init__(self):
        identifier(self.segment_id, "segment")
        if self.kind not in ("system", "operator", "user", "memory", "source", "tool", "history"):
            raise ContractHold("unknown context segment kind")
        text(self.content, maximum_bytes=131072, may_be_empty=False)
        digest(self.source_sha256)
        digest(self.scope_sha256)
        exact_integer(self.priority, maximum=1000000)
        exact_integer(self.tokens, maximum=131072)
        if type(self.mandatory) is not bool or type(self.trusted_instruction) is not bool:
            raise ContractHold("typed trust boundaries required")
        if self.trusted_instruction and self.kind not in ("system", "operator"):
            raise ContractHold("retrieval and model text cannot become system instructions")
        if self.kind == "system" and not self.trusted_instruction:
            raise ContractHold("system instructions must be explicitly host-bound")
        if sha256(self.content.encode("utf-8", "strict")).hexdigest() != self.source_sha256:
            raise ContractHold("context text does not match source sha256")

    @property
    def fingerprint(self) -> str:
        return fingerprint({
            "id": self.segment_id, "kind": self.kind,
            "sha256": self.source_sha256, "scope": self.scope_sha256,
            "tokens": self.tokens, "priority": self.priority,
            "mandatory": self.mandatory, "trusted": self.trusted_instruction,
        })


@dataclass(frozen=True, slots=True)
class ContextEnvelope:
    scope_sha256: str
    selected: tuple[Segment, ...]
    omitted: tuple[str, ...]
    input_ceiling_tokens: int
    reserved_output_tokens: int
    measured_tokens: int
    prompt_sha256: str
    has_loss: bool

    def __post_init__(self):
        digest(self.scope_sha256)
        exact_integer(self.input_ceiling_tokens, minimum=128, maximum=131072)
        exact_integer(self.reserved_output_tokens, minimum=1, maximum=8192)
        exact_integer(self.measured_tokens, maximum=131072)
        digest(self.prompt_sha256)
        if type(self.has_loss) is not bool or self.has_loss != bool(self.omitted):
            raise ContractHold("context omission evidence inconsistent")
        if self.measured_tokens + self.reserved_output_tokens > self.input_ceiling_tokens:
            raise ContractHold("context exceeds full native window")
        if len({s.segment_id for s in self.selected}) != len(self.selected):
            raise ContractHold("duplicate selected segment")
        if any(s.scope_sha256 != self.scope_sha256 for s in self.selected):
            raise ContractHold("cross-scope context selection")
        if any(s.segment_id in self.omitted for s in self.selected):
            raise ContractHold("segment both selected and omitted")

    def to_public_record(self) -> dict[str, object]:
        return {
            "schema": "jeeves.fabric.context_receipt.v1",
            "scope_sha256": self.scope_sha256,
            "included": [
                {"id": s.segment_id, "sha256": s.source_sha256,
                 "tokens": s.tokens, "kind": s.kind}
                for s in self.selected
            ],
            "omitted": list(self.omitted),
            "has_loss": self.has_loss,
            "input_ceiling_tokens": self.input_ceiling_tokens,
            "reserved_output_tokens": self.reserved_output_tokens,
            "measured_tokens": self.measured_tokens,
            "prompt_sha256": self.prompt_sha256,
            "model_context_loss_free": not self.has_loss,
            "device_qualified": False,
        }


def estimate_tokens(text_: str) -> int:
    """Conservative source-only estimate; not tokenizer attestation.

    Never use this estimate alone for real native generation admission:
    actual backend token counts must independently prove the final window.
    """
    text(text_, maximum_bytes=131072)
    return max(1, len(text_.encode("utf-8", "strict")))


def build_context(
    segments: Sequence[Segment], *, scope_sha256: str,
    input_ceiling_tokens: int, reserved_output_tokens: int,
    maximum_segments: int = 256,
    estimator: Callable[[str], int] = estimate_tokens,
) -> ContextEnvelope:
    digest(scope_sha256)
    exact_integer(input_ceiling_tokens, minimum=128, maximum=131072)
    exact_integer(reserved_output_tokens, minimum=1, maximum=8192)
    exact_integer(maximum_segments, minimum=1, maximum=2048)
    if reserved_output_tokens >= input_ceiling_tokens:
        raise ContractHold("output reservation consumes entire context")
    if (type(segments) not in (tuple, list) or
        not 1 <= len(segments) <= maximum_segments or
        not callable(estimator)):
        raise ContractHold("finite typed context segment inventory required")
    known = set()
    verified: list[Segment] = []
    for segment in segments:
        if not isinstance(segment, Segment) or segment.scope_sha256 != scope_sha256:
            raise ContractHold("untrusted foreign context segment")
        if segment.segment_id in known:
            raise ContractHold("ambiguous duplicate context source")
        known.add(segment.segment_id)
        measured = estimator(segment.content)
        exact_integer(measured, minimum=1, maximum=131072)
        if segment.tokens and segment.tokens != measured:
            raise ContractHold("context token measurement changed")
        verified.append(segment)
    reserved = input_ceiling_tokens - reserved_output_tokens
    mandatory = sorted(
        (x for x in verified if x.mandatory),
        key=lambda s: (s.kind != "system", s.segment_id),
    )
    optional = sorted(
        (x for x in verified if not x.mandatory),
        key=lambda s: (-s.priority, s.segment_id),
    )
    chosen: list[Segment] = []
    omitted: list[str] = []
    total = 0
    for entry in (*mandatory, *optional):
        cost = estimator(entry.content)
        if total + cost > reserved:
            if entry.mandatory:
                raise ContractHold("mandatory host context cannot fit native budget")
            omitted.append(entry.segment_id)
            continue
        chosen.append(entry)
        total += cost
    if not any(x.kind == "system" for x in chosen):
        raise ContractHold("no trusted system instruction admitted")
    chosen.sort(key=lambda s: (
        0 if s.kind == "system" else 1 if s.kind == "operator"
        else 2 if s.kind == "history" else 3,
        s.segment_id,
    ))
    body = "\n".join(
        f"[{item.kind}:{item.segment_id}:{item.source_sha256}]\n{item.content}"
        for item in chosen
    )
    return ContextEnvelope(
        scope_sha256=scope_sha256,
        selected=tuple(chosen),
        omitted=tuple(omitted),
        input_ceiling_tokens=input_ceiling_tokens,
        reserved_output_tokens=reserved_output_tokens,
        measured_tokens=total,
        prompt_sha256=sha256(body.encode("utf-8", "strict")).hexdigest(),
        has_loss=bool(omitted),
    )


def verify_context_receipt(envelope: ContextEnvelope) -> None:
    if not isinstance(envelope, ContextEnvelope):
        raise ContractHold("typed context receipt required")
    rebuilt = build_context(
        envelope.selected,
        scope_sha256=envelope.scope_sha256,
        input_ceiling_tokens=envelope.input_ceiling_tokens,
        reserved_output_tokens=envelope.reserved_output_tokens,
        estimator=lambda raw: len(raw.encode("utf-8", "strict")),
    )
    if (rebuilt.prompt_sha256 != envelope.prompt_sha256
        or rebuilt.measured_tokens != envelope.measured_tokens):
        raise ContractHold("context receipt no longer reflects selected bytes")


__all__ = ["Segment", "ContextEnvelope", "estimate_tokens",
           "build_context", "verify_context_receipt"]
