"""Lossless sealing, recovery and deliberate fail-closed adversarial coverage."""

from __future__ import annotations

from dataclasses import replace
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from skeleton.context.sealed_conversation import (
    canonical_history_events,
    export_canonical_conversation,
    verify_export_against_canonical_conversation,
)
from skeleton.context.sealed_events import (
    ContextEvent, decode_event, encode_event, require_model_window,
    restore_events, seal_event,
)
from skeleton.context.sealed_sandwich import (
    ContextBinding, ContextHead, ContextSandwichCodec,
    SealedContextBoundaryError, SealedContextError, SealedContextIntegrityError,
    SealedContextLimitError, SealedContextReplayError,
)


@pytest.fixture
def binding() -> ContextBinding:
    return ContextBinding("tenant-one", "owner-one", str(uuid4()), "local-model-v1", "policy-v7")


@pytest.fixture
def codec() -> ContextSandwichCodec:
    return ContextSandwichCodec({"key-2026": b"x" * 32, "old-key": b"y" * 32}, active_key_id="key-2026")


def _mutate_frame(wire: bytes, field: str, value: object) -> bytes:
    obj = json.loads(wire)
    obj[field] = value
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def test_lossless_multiturn_binary_and_unicode(codec, binding):
    original = [b"\x00\x01\xff\n", "café \U0001f40d\r\n".encode(), b"", b"   "]
    head = ContextHead()
    frames = []
    for source in original:
        wire, head = codec.seal(source, binding=binding, previous=head)
        frames.append(wire)
    restored = codec.replay(frames, binding=binding, trusted_head=head)
    assert [frame.payload for frame in restored] == original
    assert len({frame.head.commitment for frame in restored}) == len(original)


def test_ciphertext_is_randomized(codec, binding):
    one, _ = codec.seal(b"private prompt", binding=binding, previous=ContextHead())
    two, _ = codec.seal(b"private prompt", binding=binding, previous=ContextHead())
    assert one != two
    assert b"private prompt" not in one


def test_reject_wrong_tenant_owner_model_policy(codec, binding):
    wire, _ = codec.seal(b"x", binding=binding, previous=ContextHead())
    for field in ("tenant_id", "owner_id", "conversation_id", "model_id", "policy_id"):
        with pytest.raises(SealedContextBoundaryError):
            codec.open(wire, binding=replace(binding, **{field: "other"}), previous=ContextHead())


def test_gcm_detects_ciphertext_mutation(codec, binding):
    wire, _ = codec.seal(b"secret", binding=binding, previous=ContextHead())
    obj = json.loads(wire)
    encrypted = obj["ciphertext"]
    obj["ciphertext"] = ("A" if encrypted[0] != "A" else "B") + encrypted[1:]
    forged = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
    with pytest.raises(SealedContextIntegrityError):
        codec.open(forged, binding=binding, previous=ContextHead())


def test_header_tamper_and_missing_key_are_rejected(codec, binding):
    wire, _ = codec.seal(b"ok", binding=binding, previous=ContextHead())
    obj = json.loads(wire)
    obj["header"]["key_id"] = "unavailable"
    tampered = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
    with pytest.raises(SealedContextBoundaryError):
        codec.open(tampered, binding=binding, previous=ContextHead())
    obj["header"]["key_id"] = "old-key"
    tampered = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
    with pytest.raises(SealedContextIntegrityError):
        codec.open(tampered, binding=binding, previous=ContextHead())


def test_reject_gaps_duplicates_reordering_and_truncated_tail(codec, binding):
    first, h1 = codec.seal(b"one", binding=binding, previous=ContextHead())
    second, h2 = codec.seal(b"two", binding=binding, previous=h1)
    third, h3 = codec.seal(b"three", binding=binding, previous=h2)
    for frames in ([first, third], [first, first, second, third], [second, first, third], [first, second]):
        with pytest.raises(SealedContextReplayError):
            codec.replay(frames, binding=binding, trusted_head=h3)
    assert codec.replay([first, second, third], binding=binding, trusted_head=h3)[-1].payload == b"three"


def test_trusted_checkpoint_suffix(codec, binding):
    first, h1 = codec.seal(b"one", binding=binding, previous=ContextHead())
    second, h2 = codec.seal(b"two", binding=binding, previous=h1)
    assert codec.replay((second,), binding=binding, starting_head=h1, trusted_head=h2)[0].payload == b"two"
    with pytest.raises(SealedContextReplayError):
        codec.replay((first, second), binding=binding, starting_head=h1, trusted_head=h2)


def test_noncanonical_and_malformed_envelopes_fail(codec, binding):
    wire, _ = codec.seal(b"payload", binding=binding, previous=ContextHead())
    invalid_frames = (
        wire + b" ", b"{}", b"{bad",
        wire.replace(b'"schema_version":1', b'"schema_version":true'),
    )
    for invalid in invalid_frames:
        with pytest.raises(SealedContextError):
            codec.open(invalid, binding=binding, previous=ContextHead())
    with pytest.raises(SealedContextLimitError):
        codec.seal(b"k" * (4 * 1024 * 1024 + 1), binding=binding, previous=ContextHead())
    with pytest.raises(SealedContextError):
        ContextSandwichCodec({"bad": b"short"}, active_key_id="bad")


def test_key_rotation_reads_old_frames(binding):
    old = ContextSandwichCodec({"v1": b"1" * 32}, active_key_id="v1")
    new = ContextSandwichCodec({"v1": b"1" * 32, "v2": b"2" * 32}, active_key_id="v2")
    one, h1 = old.seal(b"old", binding=binding, previous=ContextHead())
    two, h2 = new.seal(b"new", binding=binding, previous=h1)
    assert [f.payload for f in new.replay((one, two), binding=binding, trusted_head=h2)] == [b"old", b"new"]


def test_events_retain_binary_exact_and_refuse_oversize(codec, binding):
    events = (ContextEvent("evt-1", "system", b"abc\x00\xff"), ContextEvent("evt-2", "user", b"\n"))
    assert all(decode_event(encode_event(event)) == event for event in events)
    frames = []
    head = ContextHead()
    for event in events:
        wire, head = seal_event(codec, event, binding=binding, previous=head)
        frames.append(wire)
    assert restore_events(codec, frames, binding=binding, trusted_head=head) == events
    with pytest.raises(SealedContextLimitError):
        require_model_window(events, max_input_bytes=1)
    assert require_model_window(events, max_input_bytes=7) == events
    with pytest.raises(SealedContextError):
        decode_event(b'not-json')
    with pytest.raises(SealedContextError):
        ContextEvent("evt-3", "pretend-system-authority", b"x")


def test_duplicate_event_id_rejected(codec, binding):
    head = ContextHead()
    frames = []
    for _ in range(2):
        frame, head = seal_event(codec, ContextEvent("dup", "user", b"x"), binding=binding, previous=head)
        frames.append(frame)
    with pytest.raises(SealedContextError, match="duplicate"):
        restore_events(codec, frames, binding=binding, trusted_head=head)


class _Reader:
    def __init__(self, binding: ContextBinding):
        self.thread = SimpleNamespace(
            thread_id=binding.conversation_id, version=2, message_sequence=2,
            as_dict=lambda: {"thread_id": binding.conversation_id, "version": 2, "message_sequence": 2},
        )
        self.messages = (
            SimpleNamespace(
                thread_id=binding.conversation_id, sequence=1, message_id="a",
                author_type=SimpleNamespace(value="user"),
                as_dict=lambda: {"sequence": 1, "content": "hello"},
            ),
            SimpleNamespace(
                thread_id=binding.conversation_id, sequence=2, message_id="b",
                author_type=SimpleNamespace(value="assistant"),
                as_dict=lambda: {"sequence": 2, "content": "world"},
            ),
        )

    def get_thread(self, thread_id, *, tenant_id, owner_id):
        return self.thread

    def list_messages(self, thread_id, *, tenant_id, owner_id, after_sequence=0, limit=500):
        return tuple(msg for msg in self.messages if msg.sequence > after_sequence)[:limit]


def test_canonical_conversation_roundtrip_and_stale_detection(codec, binding):
    reader = _Reader(binding)
    artifact = export_canonical_conversation(reader, codec, binding=binding)
    assert artifact.message_count == 2 and artifact.head.sequence == 3
    verify_export_against_canonical_conversation(reader, codec, artifact, binding=binding)
    assert len(canonical_history_events(reader, binding=binding)[0]) == 3
    reader.thread = SimpleNamespace(
        thread_id=binding.conversation_id, version=3, message_sequence=2,
        as_dict=lambda: {"thread_id": binding.conversation_id, "version": 3, "message_sequence": 2},
    )
    with pytest.raises(SealedContextReplayError):
        verify_export_against_canonical_conversation(reader, codec, artifact, binding=binding)


def test_canonical_missing_message_detected(binding):
    reader = _Reader(binding)
    reader.messages = (reader.messages[1],)
    with pytest.raises(SealedContextReplayError):
        canonical_history_events(reader, binding=binding)
