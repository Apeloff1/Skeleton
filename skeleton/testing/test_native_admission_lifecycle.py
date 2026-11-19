"""Native admission must reject known replay and capacity before staging."""
import sqlite3
from dataclasses import replace

import pytest

from skeleton.ai.model_runtime import native_fair_stream_backend as native
from skeleton.ai.model_runtime import fair_stream_execution_journal as journal_module
from skeleton.ai.model_runtime.fair_stream_execution_journal import ExecutionOutcomeUnknown
from skeleton.testing.test_fair_stream_execution_journal import journal, permit
from skeleton.testing.test_native_fair_stream_backend import setup, SESSION


def test_staging_slots_are_not_lifetime_identity_budget(monkeypatch):
    monkeypatch.setattr(native, "MAX_STAGED_PROMPTS", 1)
    monkeypatch.setattr(native, "MAX_PROMPT_IDENTITIES", 4)
    runtime, registry, _ = setup()
    first = registry.claim("request-1", "alice")
    for index in range(3):
        pinned = native.pin_native_prompt(
            runtime, session_id=SESSION, request_id=f"next-{index}",
            tenant_id="alice", prompt=first.prompt, max_output_tokens=2,
        )
        registry.stage(pinned)
        registry.claim(pinned.request_id, "alice")
    assert registry.status()["consumed_or_revoked"] == 4
    with pytest.raises(native.NativeFairStreamDenied, match="identity capacity"):
        registry.stage(replace(pinned, request_id="overflow"))
    with pytest.raises(native.NativeFairStreamDenied, match="duplicate"):
        registry.stage(pinned)


def test_journal_preflight_is_read_only_and_rejects_running_identity():
    store = journal(sqlite3.connect(":memory:"))
    p = permit()
    store.assert_request_admissible(p.request_id)
    store.begin(p)
    with pytest.raises(ExecutionOutcomeUnknown, match="already executed"):
        store.assert_request_admissible(p.request_id)
    store.assert_request_admissible("unrelated")
    assert store._connection.execute(
        "SELECT COUNT(*) FROM local_fair_stream_execution_journal"
    ).fetchone()[0] == 1


def test_queued_admissions_count_against_remaining_journal_capacity(monkeypatch):
    monkeypatch.setattr(journal_module, "MAX_JOURNAL_ROWS", 2)
    store = journal(sqlite3.connect(":memory:"))
    store.assert_request_admissible("second", queued_count=1)
    store.begin(permit())
    with pytest.raises(ExecutionOutcomeUnknown, match="capacity"):
        store.assert_request_admissible("third", queued_count=1)
    assert store._connection.execute(
        "SELECT COUNT(*) FROM local_fair_stream_execution_journal"
    ).fetchone()[0] == 1
