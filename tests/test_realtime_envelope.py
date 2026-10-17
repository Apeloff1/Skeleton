"""Envelope v1 contract (ADR-realtime-transport, PR #4101)."""

from __future__ import annotations

import json

import pytest

from skeleton.realtime.envelope import (
    CHANNELS,
    ControlEvent,
    EnvelopeError,
    RealtimeEvent,
    parse_cursor,
    parse_ts,
    ts_from_ms,
)
from skeleton.realtime.sse import SSEParser, format_retry, format_sse, sse_message_to_frame


def _event(**overrides):
    body = dict(id="42", ts="2026-10-17T16:00:00.123Z", channel="build", type="build.progress", payload={"pct": 50})
    body.update(overrides)
    return RealtimeEvent(**body)


def test_channels_are_exactly_the_v1_set():
    assert CHANNELS == ("build", "agent", "presence")


def test_round_trip_snake_case_fields_and_optional_ids():
    ev = _event(job_id="job-7", correlation_id="corr-1")
    wire = ev.to_dict()
    assert set(wire) == {"v", "id", "ts", "channel", "type", "payload", "job_id", "correlation_id"}
    assert wire["v"] == 1 and wire["id"] == "42" and isinstance(wire["id"], str)
    assert RealtimeEvent.from_json(ev.to_json()) == ev
    assert "job_id" not in _event().to_dict()


def test_unknown_fields_are_ignored_for_additive_evolution():
    raw = _event().to_dict()
    raw["future_field"] = {"x": 1}
    assert RealtimeEvent.from_dict(raw) == _event()


def test_integer_ids_from_producers_are_normalised_to_strings():
    raw = _event().to_dict()
    raw["id"] = 42
    assert RealtimeEvent.from_dict(raw).id == "42"


@pytest.mark.parametrize(
    "overrides",
    [
        {"channel": "chat"},
        {"type": "agent.step"},
        {"type": "Build.Progress"},
        {"id": "0"},
        {"id": "abc"},
        {"ts": "yesterday"},
        {"payload": ["not", "an", "object"]},
        {"job_id": "has spaces"},
        {"v": 2},
        {"payload": {"blob": "x" * 70_000}},
    ],
)
def test_invalid_envelopes_are_rejected(overrides):
    with pytest.raises(EnvelopeError):
        _event(**overrides)


def test_ts_is_rfc3339_utc():
    ts = ts_from_ms(1_792_252_800_123)
    assert ts.endswith("Z") and "T" in ts
    assert parse_ts(ts).utcoffset().total_seconds() == 0


def test_cursor_parsing():
    assert parse_cursor(None) is None
    assert parse_cursor("  ") is None
    assert parse_cursor("17") == 17
    with pytest.raises(EnvelopeError):
        parse_cursor("17; drop")


def test_sse_frame_id_equals_envelope_id_and_event_equals_type():
    ev = _event()
    text = format_sse(ev)
    lines = text.splitlines()
    assert lines[0] == "id: 42"
    assert lines[1] == "event: build.progress"
    assert json.loads(lines[2][len("data: "):])["id"] == "42"
    parser = SSEParser()
    (msg,) = list(parser.feed(format_retry(1500) + ": hb\n\n" + text))
    assert parser.retry_ms == 1500 and parser.comments == 1
    assert parser.last_event_id == "42"
    assert sse_message_to_frame(msg) == ev


def test_control_events_have_no_id_line():
    lagged = ControlEvent(type="stream.lagged", ts=ts_from_ms(0), payload={"dropped": 3})
    text = format_sse(lagged)
    assert not text.startswith("id:") and "\nid:" not in text
    parser = SSEParser()
    (msg,) = list(parser.feed(text))
    assert parser.last_event_id is None
    assert sse_message_to_frame(msg) == lagged


def test_mismatched_sse_id_is_a_protocol_error():
    parser = SSEParser()
    (msg,) = list(parser.feed(format_sse(_event()).replace("id: 42", "id: 41")))
    with pytest.raises(EnvelopeError):
        sse_message_to_frame(msg)
