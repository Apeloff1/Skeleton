"""Source-audit regressions for realtime custody and parser boundaries."""
import pytest

from skeleton.realtime.envelope import EnvelopeError
from skeleton.realtime.guard import PayloadSecretGuard, RealtimeSecretError
from skeleton.realtime.hub import RealtimeHub, RealtimeLimitError, sealed_principal_authorizer
from skeleton.realtime.sse import SSEParser, MAX_SSE_LINE_CHARS, MAX_SSE_DATA_LINES


def test_ambiguous_embedded_json_is_not_republished():
    guard = PayloadSecretGuard()
    clean, hits = guard.scrub({"event": '{"duplicate":1,"duplicate":2}'})
    assert hits == 1
    assert "duplicate" not in clean["event"]
    with pytest.raises(RealtimeSecretError):
        PayloadSecretGuard("reject").scrub({"event": '{"duplicate":1,"duplicate":2}'})


def test_secret_shaped_mapping_key_is_refused():
    with pytest.raises(RealtimeSecretError, match="unsafe payload key"):
        PayloadSecretGuard().scrub({"ghp_" + "A" * 36: "value"})


def test_fragmented_crlf_keeps_one_frame():
    parser = SSEParser()
    assert list(parser.feed("data: first\r")) == []
    assert list(parser.feed("\n")) == []
    assert list(parser.feed("data: second\r")) == []
    assert list(parser.feed("\n\r"))[0].data == "first\nsecond"
    assert list(parser.feed("\n")) == []


def test_parser_rejects_unbounded_lines_and_data_fields():
    parser = SSEParser()
    with pytest.raises(EnvelopeError):
        list(parser.feed("x" * (MAX_SSE_LINE_CHARS + 1)))
    parser = SSEParser()
    with pytest.raises(EnvelopeError):
        list(parser.feed("data: x\n" * (MAX_SSE_DATA_LINES + 1)))


def test_published_and_delivered_payloads_cannot_mutate_replay():
    hub = RealtimeHub(authorizer=sealed_principal_authorizer)
    first = hub.subscribe(["build"], principal="owner")
    second = hub.subscribe(["build"], principal="owner")
    published = hub.publish("build", "build.progress", {"nested": {"value": 1}}, owner="owner")
    published.payload["nested"]["value"] = 2
    first.drain()[0].payload["nested"]["value"] = 3
    received = second.drain()[0]
    assert received.payload["nested"]["value"] == 1
    received.to_dict()["payload"]["nested"]["value"] = 4
    assert received.payload["nested"]["value"] == 1


def test_global_presence_capacity_applies_across_scopes():
    hub = RealtimeHub(authorizer=sealed_principal_authorizer, max_presence_members=1)
    hub.presence("join", client_id="a", principal="owner", scope="one")
    with pytest.raises(RealtimeLimitError, match="presence capacity"):
        hub.presence("join", client_id="b", principal="owner", scope="two")
