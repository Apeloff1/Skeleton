from pathlib import Path
import json
import pytest

from skeleton.shells.audit import AuditEvent, CompositeAuditSink, JsonlAuditSink, MemoryAuditSink, RedactingAuditSink
from skeleton.shells.redaction import RedactionPolicy, RedactionRule, SecretRedactor


def test_redacts_secret_mapping_keys_case_insensitively():
    redactor = SecretRedactor()
    out = redactor.redact({"Password": "hunter2", "nested": {"API-KEY": "abc"}})
    assert out["Password"] == "[REDACTED]"
    assert out["nested"]["API-KEY"] == "[REDACTED]"


def test_redacts_bearer_tokens_and_url_credentials():
    redactor = SecretRedactor()
    text = "Authorization: Bearer abc.def.ghi https://user:pass@example.test/path"
    cleaned = redactor.redact_text(text)
    assert "abc.def.ghi" not in cleaned
    assert "user:pass@" not in cleaned


def test_redactor_truncates_long_strings():
    redactor = SecretRedactor(RedactionPolicy(max_string_chars=10))
    cleaned = redactor.redact_text("x" * 40)
    assert cleaned.startswith("x" * 10)
    assert "TRUNCATED" in cleaned


def test_redactor_bounds_collection_depth():
    redactor = SecretRedactor(RedactionPolicy(max_depth=2))
    cleaned = redactor.redact({"a": {"b": {"c": "secret"}}})
    assert cleaned["a"]["b"] == "[DEPTH-LIMIT]"


def test_redactor_bounds_collection_items():
    redactor = SecretRedactor(RedactionPolicy(max_collection_items=2))
    cleaned = redactor.redact({"a": 1, "b": 2, "c": 3})
    assert "[TRUNCATED]" in cleaned


def test_redactor_custom_literal_is_removed():
    redactor = SecretRedactor().add_literals(["my-private-value"])
    assert "my-private-value" not in redactor.redact_text("x my-private-value y")


def test_custom_rule_compiles_at_policy_creation():
    with pytest.raises(Exception):
        RedactionPolicy(rules=(RedactionRule("["),))


def test_memory_audit_sink_bounds_ring_and_counts_drops():
    sink = MemoryAuditSink(max_events=2)
    for idx in range(4):
        sink.emit(AuditEvent.create("event", "c", data={"n": idx}))
    snapshot = sink.snapshot()
    assert len(snapshot) == 2
    assert snapshot[0].data["n"] == 2
    assert sink.dropped == 2


def test_memory_audit_sink_filters_by_correlation():
    sink = MemoryAuditSink()
    sink.emit(AuditEvent.create("event", "a"))
    sink.emit(AuditEvent.create("event", "b"))
    assert len(sink.by_correlation("a")) == 1


def test_redacting_audit_sink_scrubs_before_storage():
    memory = MemoryAuditSink()
    sink = RedactingAuditSink(memory)
    sink.emit(AuditEvent.create("event", "c", data={"token": "abc", "message": "Bearer xyz"}))
    event = memory.snapshot()[0]
    assert event.data["token"] == "[REDACTED]"
    assert "xyz" not in event.data["message"]


def test_composite_audit_sink_fans_out():
    left = MemoryAuditSink()
    right = MemoryAuditSink()
    sink = CompositeAuditSink([left, right])
    event = AuditEvent.create("event", "c")
    sink.emit(event)
    assert left.snapshot()[0].event_id == event.event_id
    assert right.snapshot()[0].event_id == event.event_id


def test_jsonl_audit_sink_appends_valid_json(tmp_path):
    path = tmp_path / "audit.jsonl"
    sink = JsonlAuditSink(path)
    sink.emit(AuditEvent.create("event", "c", data={"ok": True}))
    record = json.loads(path.read_text().strip())
    assert record["kind"] == "event"
    assert record["data"]["ok"] is True


def test_jsonl_audit_sink_rejects_symlink_target(tmp_path):
    target = tmp_path / "real.log"
    target.write_text("")
    link = tmp_path / "audit.log"
    link.symlink_to(target)
    with pytest.raises(ValueError):
        JsonlAuditSink(link)


def test_jsonl_audit_sink_rejects_oversize_event(tmp_path):
    sink = JsonlAuditSink(tmp_path / "audit.log", max_event_bytes=64)
    with pytest.raises(ValueError):
        sink.emit(AuditEvent.create("event", "c", data={"x": "y" * 100}))
