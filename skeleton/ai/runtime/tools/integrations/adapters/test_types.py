"""Tests for request/response/stream-chunk value types."""

from __future__ import annotations

import pytest

from .errors import InvalidRequestError, ResponseFormatError
from .types import (
    ChatRequest,
    ChatResponse,
    ChunkKind,
    FinishReason,
    Message,
    ProviderCapability,
    Role,
    StreamAccumulator,
    StreamChunk,
    ToolCall,
    ToolResult,
    ToolSpec,
    Usage,
    arguments_digest,
    canonical_json,
)


def test_role_parse_accepts_strings_and_rejects_unknown():
    assert Role.parse("USER") is Role.USER
    assert Role.parse(Role.TOOL) is Role.TOOL
    with pytest.raises(InvalidRequestError):
        Role.parse("wizard")


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("end_turn", FinishReason.STOP),
        ("max_tokens", FinishReason.LENGTH),
        ("tool_use", FinishReason.TOOL_CALLS),
        (None, FinishReason.STOP),
        ("something-new", FinishReason.STOP),
        ("content_filter", FinishReason.CONTENT_FILTER),
    ],
)
def test_finish_reason_aliases(raw, expected):
    assert FinishReason.parse(raw) is expected


def test_canonical_json_and_digest_are_order_independent():
    assert canonical_json({"b": 1, "a": 2}) == canonical_json({"a": 2, "b": 1})
    assert arguments_digest({"x": 1, "y": [1, 2]}) == arguments_digest({"y": [1, 2], "x": 1})
    assert arguments_digest({"x": 1}) != arguments_digest({"x": 2})


def test_tool_call_validation_and_json_arguments():
    call = ToolCall.from_dict({"id": "c1", "name": "clock", "arguments": '{"tz": "UTC"}'})
    assert call.arguments == {"tz": "UTC"}
    assert ToolCall.from_dict({"id": "c2", "name": "n", "arguments": ""}).arguments == {}
    with pytest.raises(ResponseFormatError):
        ToolCall.from_dict({"id": "c1", "name": "x", "arguments": "{nope"})
    with pytest.raises(ResponseFormatError):
        ToolCall.from_dict({"id": "c1", "name": "x", "arguments": "[1,2]"})
    with pytest.raises(InvalidRequestError):
        ToolCall(id="", name="x")
    with pytest.raises(InvalidRequestError):
        ToolCall(id="a", name=" ")


def test_tool_call_arguments_are_copied():
    source = {"a": 1}
    call = ToolCall("i", "n", source)
    source["a"] = 2
    assert call.arguments == {"a": 1}
    assert call.digest == arguments_digest({"a": 1})


def test_message_invariants_and_roundtrip():
    msg = Message.assistant("hi", [ToolCall("1", "t", {"k": "v"})])
    again = Message.from_dict(msg.as_dict())
    assert again == msg
    with pytest.raises(InvalidRequestError):
        Message(Role.TOOL, "x")
    with pytest.raises(InvalidRequestError):
        Message(Role.USER, "x", tool_calls=(ToolCall("1", "t"),))
    with pytest.raises(InvalidRequestError):
        Message(Role.USER, 42)  # type: ignore[arg-type]
    assert Message.from_dict({"role": "assistant", "content": None}).content == ""
    tool_msg = Message.tool("c1", "result", name="clock")
    assert tool_msg.as_dict()["tool_call_id"] == "c1"


def test_tool_spec_name_rules():
    ToolSpec("fs.read_file-v2")
    with pytest.raises(InvalidRequestError):
        ToolSpec("bad name")
    with pytest.raises(InvalidRequestError):
        ToolSpec("x" * 129)
    with pytest.raises(InvalidRequestError):
        ToolSpec("ok", parameters=[])  # type: ignore[arg-type]
    spec = ToolSpec("t", capabilities=("b", "a", "a"))
    assert spec.capabilities == ("a", "b")


def test_usage_math_and_validation():
    total = Usage(3, 4) + Usage(1, 1)
    assert total.total_tokens == 9
    assert total.as_dict()["total_tokens"] == 9
    with pytest.raises(ResponseFormatError):
        Usage(-1, 0)
    with pytest.raises(ResponseFormatError):
        Usage(True, 0)  # type: ignore[arg-type]


def test_chat_request_derives_required_capabilities():
    plain = ChatRequest.from_prompt("hi")
    assert plain.required_capabilities == frozenset({ProviderCapability.CHAT})
    rich = ChatRequest.from_prompt(
        "hi",
        tools=(ToolSpec("t"),),
        json_mode=True,
        required_capabilities=frozenset({ProviderCapability.VISION}),
    )
    assert {
        ProviderCapability.CHAT,
        ProviderCapability.TOOLS,
        ProviderCapability.JSON_MODE,
        ProviderCapability.VISION,
    } == set(rich.required_capabilities)


def test_chat_request_validation():
    with pytest.raises(InvalidRequestError):
        ChatRequest(messages=())
    with pytest.raises(InvalidRequestError):
        ChatRequest.from_prompt("x", temperature=3.0)
    with pytest.raises(InvalidRequestError):
        ChatRequest.from_prompt("x", max_tokens=0)
    with pytest.raises(InvalidRequestError):
        ChatRequest.from_prompt("x", tools=(ToolSpec("t"), ToolSpec("t")))


def test_chat_request_accepts_dict_messages_and_helpers():
    req = ChatRequest(messages=({"role": "system", "content": "sys"}, {"role": "user", "content": "q"}))
    assert req.system_text == "sys"
    assert req.last_user_text == "q"
    extended = req.with_messages([Message.assistant("a")])
    assert len(extended.messages) == 3
    assert req.with_model("m").model == "m"
    assert req.as_dict()["required_capabilities"] == ["chat"]


def test_fingerprint_ignores_metadata_but_tracks_content():
    a = ChatRequest.from_prompt("x", metadata={"trace": 1})
    b = ChatRequest.from_prompt("x", metadata={"trace": 2})
    c = ChatRequest.from_prompt("y")
    assert a.fingerprint() == b.fingerprint()
    assert a.fingerprint() != c.fingerprint()


def test_chat_response_infers_tool_calls_finish():
    resp = ChatResponse(text="", provider="p", model="m", tool_calls=(ToolCall("1", "t"),))
    assert resp.finish_reason is FinishReason.TOOL_CALLS
    assert resp.as_message().tool_calls[0].name == "t"
    assert resp.as_dict()["usage"]["total_tokens"] == 0


def test_stream_chunk_validation():
    with pytest.raises(ResponseFormatError):
        StreamChunk(ChunkKind.TEXT, -1, text="x")
    with pytest.raises(ResponseFormatError):
        StreamChunk(ChunkKind.TOOL_CALL, 0)
    with pytest.raises(ResponseFormatError):
        StreamChunk(ChunkKind.USAGE, 0)
    fin = StreamChunk(ChunkKind.FINISH, 3)
    assert fin.finish_reason is FinishReason.STOP
    assert StreamChunk.text_delta(0, "a", provider="p").as_dict() == {
        "kind": "text",
        "index": 0,
        "text": "a",
        "provider": "p",
    }


def test_stream_accumulator_builds_response():
    acc = StreamAccumulator()
    acc.add(StreamChunk.text_delta(0, "Hel", provider="p", model="m"))
    acc.add(StreamChunk.text_delta(1, "lo"))
    acc.add(StreamChunk(ChunkKind.TOOL_CALL, 2, tool_call=ToolCall("1", "t")))
    acc.add(StreamChunk(ChunkKind.USAGE, 3, usage=Usage(2, 3)))
    acc.add(StreamChunk.finish(4, "tool_calls"))
    resp = acc.build(attempts=2)
    assert resp.text == "Hello"
    assert resp.provider == "p" and resp.model == "m"
    assert resp.usage.total_tokens == 5
    assert resp.finish_reason is FinishReason.TOOL_CALLS
    assert resp.attempts == 2


def test_stream_accumulator_rejects_gaps_and_post_finish_chunks():
    acc = StreamAccumulator()
    with pytest.raises(ResponseFormatError):
        acc.add(StreamChunk.text_delta(1, "x"))
    acc.add(StreamChunk.finish(0))
    with pytest.raises(ResponseFormatError):
        acc.add(StreamChunk.text_delta(1, "late"))


def test_tool_result_rendering():
    ok = ToolResult("c", "t", {"b": 1, "a": 2})
    assert ok.as_text() == '{"a":2,"b":1}'
    assert ok.as_message().role is Role.TOOL
    assert ToolResult("c", "t", "plain").as_text() == "plain"
    assert ToolResult("c", "t", None, duration_ms=1.23456).as_dict()["duration_ms"] == 1.235
