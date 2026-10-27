"""Three cryptographically correlated archives for prompt, response and delivered work.

Canonical conversation/execution persistence remains authoritative. Candidate
heads must be committed together by the owning storage transaction.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Callable, Iterable

from skeleton.context.sealed_events import ContextEvent, decode_event, encode_event
from skeleton.context.sealed_sandwich import (
    ContextBinding,
    ContextHead,
    ContextSandwichCodec,
    SealedContextBoundaryError,
    SealedContextError,
    SealedContextLimitError,
    SealedContextReplayError,
)

ARCHIVE_WINDOW_MESSAGES = 2000
_STREAMS = ("user", "llm", "work")
_GENESIS = "0" * 64
_DOMAIN = b"skeleton.sealed.memento.global.v1\x00"
_MAX_RECORD_BYTES = 2 * 1024 * 1024
_WORD = re.compile(r"\w+", re.UNICODE)


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _hash(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _digest(value: str) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        ch in "0123456789abcdef" for ch in value
    )


@dataclass(frozen=True, slots=True)
class MementoRecord:
    """One verbatim, labeled payload; a work item requires external proof."""

    serial: int
    stream: str
    payload: bytes
    causal_serial: int | None = None
    evidence_digest: str | None = None
    evidence_ref: str | None = None

    def __post_init__(self) -> None:
        if type(self.serial) is not int or not 1 <= self.serial <= 2**63 - 1:
            raise SealedContextError("invalid global serial")
        if self.stream not in _STREAMS:
            raise SealedContextError("invalid memento stream")
        if not isinstance(self.payload, bytes) or len(self.payload) > _MAX_RECORD_BYTES:
            raise SealedContextLimitError("memento payload exceeds limit")
        if self.causal_serial is not None and (
            type(self.causal_serial) is not int or not 1 <= self.causal_serial < self.serial
        ):
            raise SealedContextReplayError("memento causal serial is not historical")
        if self.stream == "work":
            if not _digest(self.evidence_digest):
                raise SealedContextError("delivered work requires a proof digest")
            if (not isinstance(self.evidence_ref, str) or not self.evidence_ref
                    or len(self.evidence_ref) > 256):
                raise SealedContextError("delivered work requires a provenance reference")
        elif self.evidence_digest is not None or self.evidence_ref is not None:
            raise SealedContextError("response/prompt is not a delivered-work receipt")


def _event(record: MementoRecord) -> ContextEvent:
    body = {
        "v": 1, "serial": record.serial, "stream": record.stream,
        "causal_serial": record.causal_serial,
        "evidence_digest": record.evidence_digest, "evidence_ref": record.evidence_ref,
        "payload_b64": base64.b64encode(record.payload).decode("ascii"),
    }
    kind = {"user": "user", "llm": "assistant", "work": "receipt"}[record.stream]
    return ContextEvent(f"memento:{record.serial:020d}", kind, _canonical(body),
                        f"memento:{record.stream}")


def _parse(payload: bytes) -> MementoRecord:
    event = decode_event(payload)
    try:
        body = json.loads(event.content)
        if (type(body) is not dict or set(body) != {
            "v", "serial", "stream", "causal_serial", "evidence_digest",
            "evidence_ref", "payload_b64"
        } or body["v"] != 1 or type(body["v"]) is not int):
            raise ValueError("invalid memento envelope")
        raw = body["payload_b64"]
        if not isinstance(raw, str) or len(raw) > (_MAX_RECORD_BYTES * 4 // 3 + 8):
            raise ValueError("invalid encoded content")
        content = base64.b64decode(raw, validate=True)
        if base64.b64encode(content).decode("ascii") != raw:
            raise ValueError("noncanonical content")
        record = MementoRecord(
            serial=body["serial"], stream=body["stream"], payload=content,
            causal_serial=body["causal_serial"],
            evidence_digest=body["evidence_digest"], evidence_ref=body["evidence_ref"],
        )
        if encode_event(_event(record)) != payload:
            raise ValueError("noncanonical memento event")
        return record
    except (ValueError, TypeError, KeyError, UnicodeError) as exc:
        raise SealedContextError("invalid sealed memento") from exc


@dataclass(frozen=True, slots=True)
class MementoCatalogHead:
    """Global and per-stream heads, requiring one independent authoritative CAS."""

    serial: int = 0
    commitment: str = _GENESIS
    user: ContextHead = ContextHead()
    llm: ContextHead = ContextHead()
    work: ContextHead = ContextHead()

    def __post_init__(self) -> None:
        if type(self.serial) is not int or not 0 <= self.serial <= 2**63 - 1:
            raise SealedContextError("invalid memento catalog serial")
        if not _digest(self.commitment) or (self.serial == 0) != (self.commitment == _GENESIS):
            raise SealedContextError("invalid memento catalog commitment")
        if any(not isinstance(getattr(self, stream), ContextHead) for stream in _STREAMS):
            raise SealedContextError("invalid stream head")
        if self.user.sequence + self.llm.sequence + self.work.sequence != self.serial:
            raise SealedContextReplayError("stream heads do not account for global serial")

    def stream_head(self, stream: str) -> ContextHead:
        if stream not in _STREAMS:
            raise SealedContextError("invalid stream")
        return getattr(self, stream)


def stream_binding(binding: ContextBinding, stream: str) -> ContextBinding:
    """AES-GCM AAD namespaces are disjoint for all three archives."""
    if not isinstance(binding, ContextBinding) or stream not in _STREAMS:
        raise SealedContextBoundaryError("invalid memento binding")
    return ContextBinding(binding.tenant_id, binding.owner_id,
                          binding.conversation_id, binding.model_id,
                          f"{binding.policy_id}:memento:{stream}")


def _advance(previous: MementoCatalogHead, stream: str, stream_head: ContextHead,
             wire: bytes) -> MementoCatalogHead:
    serial = previous.serial + 1
    record = _canonical({
        "serial": serial, "stream": stream, "previous": previous.commitment,
        "stream_head": stream_head.commitment, "wire_sha256": _hash(wire),
    })
    heads = {s: getattr(previous, s) for s in _STREAMS}
    heads[stream] = stream_head
    return MementoCatalogHead(serial, _hash(_DOMAIN + record), **heads)


class SealedMementoArchive:
    """Produces candidates; publication belongs to existing canonical authority."""

    def __init__(self, codec: ContextSandwichCodec, binding: ContextBinding,
                 *, work_verifier: Callable[[str, str, bytes], bool] | None = None):
        self.codec = codec
        self.binding = binding
        self.work_verifier = work_verifier

    def seal(self, record: MementoRecord, *, previous: MementoCatalogHead,
             known_causal_serials: frozenset[int] | None = None) -> tuple[bytes, MementoCatalogHead]:
        if not isinstance(previous, MementoCatalogHead):
            raise SealedContextError("a catalog head is required")
        if record.serial != previous.serial + 1:
            raise SealedContextReplayError("memento global serial must be exact-next")
        if record.causal_serial is not None and known_causal_serials is not None:
            if record.causal_serial not in known_causal_serials:
                raise SealedContextReplayError("missing historical causal reference")
        if record.stream == "work":
            if _hash(record.payload) != record.evidence_digest:
                raise SealedContextBoundaryError("work bytes differ from referenced evidence digest")
            if self.work_verifier is None or not self.work_verifier(
                record.evidence_ref, record.evidence_digest, record.payload
            ):
                raise SealedContextBoundaryError("delivered work lacks trusted execution proof")
        wire, stream_head = self.codec.seal(
            encode_event(_event(record)), binding=stream_binding(self.binding, record.stream),
            previous=previous.stream_head(record.stream),
        )
        return wire, _advance(previous, record.stream, stream_head, wire)

    def replay(self, entries: Iterable[tuple[str, bytes]], *,
               trusted_head: MementoCatalogHead,
               starting_head: MementoCatalogHead = MementoCatalogHead(),
               max_messages: int = ARCHIVE_WINDOW_MESSAGES) -> tuple[MementoRecord, ...]:
        """Bounded retrieval window, with externally pinned head and stream order."""
        if type(max_messages) is not int or not 1 <= max_messages <= ARCHIVE_WINDOW_MESSAGES:
            raise SealedContextLimitError("retrieval window is capped at 2000 messages")
        if starting_head.serial > trusted_head.serial:
            raise SealedContextReplayError("starting head is newer than trusted head")
        current = starting_head
        records: list[MementoRecord] = []
        for stream, wire in entries:
            if len(records) >= max_messages:
                raise SealedContextLimitError("archive window exceeded; page with trusted checkpoint")
            frame = self.codec.open(
                wire, binding=stream_binding(self.binding, stream),
                previous=current.stream_head(stream),
            )
            record = _parse(frame.payload)
            if record.stream != stream or record.serial != current.serial + 1:
                raise SealedContextReplayError("cross-stream ordering or identity mismatch")
            if record.causal_serial is not None and record.causal_serial >= record.serial:
                raise SealedContextReplayError("forward causal reference")
            current = _advance(current, stream, frame.head, wire)
            records.append(record)
        if current != trusted_head:
            raise SealedContextReplayError("memento archive tail or trusted commitment differs")
        return tuple(records)


def lexical_correlate(records: Iterable[MementoRecord], *, query: str,
                      serial: int | None = None, limit: int = 12) -> tuple[MementoRecord, ...]:
    """Naive deterministic lexical RAG over VERIFIED plaintext, never model authority."""
    if (not isinstance(query, str) or len(query) > 2048 or type(limit) is not int
            or not 1 <= limit <= 100 or (serial is not None and
            (type(serial) is not int or serial < 1))):
        raise ValueError("invalid bounded memento retrieval request")
    values = tuple(records)
    if len(values) > ARCHIVE_WINDOW_MESSAGES:
        raise SealedContextLimitError("lexical retrieval requires 2000-record verified page")
    if any(not isinstance(value, MementoRecord) for value in values):
        raise SealedContextError("unverified record type")
    terms = set(word.casefold() for word in _WORD.findall(query))
    scored = []
    for item in values:
        words = set(word.casefold() for word in _WORD.findall(
            item.payload[:32768].decode("utf-8", errors="replace")
        ))
        score = len(words & terms)
        if serial is not None and (item.serial == serial or item.causal_serial == serial):
            score += 1000
        if score:
            scored.append((-score, item.serial, item))
    scored.sort(key=lambda item: (item[0], item[1]))
    return tuple(item for _, _, item in scored[:limit])


def encode_catalog_head(head: MementoCatalogHead) -> bytes:
    """Canonical metadata for the authoritative store's CAS record.

    Encoding is not a signature: only the trusted persistence owner may
    promote or read this value as authoritative.
    """
    if not isinstance(head, MementoCatalogHead):
        raise SealedContextError("memento catalog head required")
    return _canonical({
        "schema_version": 1, "global_serial": head.serial,
        "global_commitment": head.commitment,
        "stream_heads": {
            stream: {"sequence": head.stream_head(stream).sequence,
                     "commitment": head.stream_head(stream).commitment}
            for stream in _STREAMS
        },
    })


def decode_catalog_head(data: bytes) -> MementoCatalogHead:
    """Refuse noncanonical/corrupt CAS metadata before using it for recovery."""
    if not isinstance(data, bytes) or len(data) > 4096:
        raise SealedContextLimitError("invalid catalog metadata size")
    try:
        value = json.loads(data)
        if type(value) is not dict or set(value) != {
            "schema_version", "global_serial", "global_commitment", "stream_heads"
        } or type(value["schema_version"]) is not int or value["schema_version"] != 1:
            raise ValueError("invalid catalog schema")
        streams = value["stream_heads"]
        if type(streams) is not dict or set(streams) != set(_STREAMS):
            raise ValueError("invalid stream names")
        heads = {}
        for stream in _STREAMS:
            item = streams[stream]
            if type(item) is not dict or set(item) != {"sequence", "commitment"}:
                raise ValueError("invalid stream head shape")
            heads[stream] = ContextHead(item["sequence"], item["commitment"])
        head = MementoCatalogHead(
            value["global_serial"], value["global_commitment"], **heads
        )
        if encode_catalog_head(head) != data:
            raise ValueError("noncanonical catalog metadata")
        return head
    except (ValueError, TypeError, KeyError, UnicodeError) as exc:
        raise SealedContextError("invalid memento catalog metadata") from exc
