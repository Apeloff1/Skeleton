"""Output classification and retention regressions."""

from __future__ import annotations

import pytest

from skeleton.shells.output_policy import (
    ClassifiedOutput,
    OutputClass,
    OutputClassifier,
    OutputRetention,
    OutputRetentionPolicy,
)
from skeleton.shells.retention import OutputRetentionStore


def test_classifier_default_internal():
    classifier = OutputClassifier()
    assert classifier.classify(b"hello") is OutputClass.INTERNAL


def test_classifier_secret_pattern():
    classifier = OutputClassifier(secret_patterns=(r"token=",))
    assert classifier.classify(b"TOKEN=abc") is OutputClass.SECRET


def test_classifier_sensitive_pattern():
    classifier = OutputClassifier(sensitive_patterns=(r"email",))
    assert classifier.classify(b"user email found") is OutputClass.SENSITIVE


def test_classifier_secret_precedes_sensitive():
    classifier = OutputClassifier(
        secret_patterns=(r"secret",),
        sensitive_patterns=(r"secret",),
    )
    assert classifier.classify(b"secret") is OutputClass.SECRET


def test_retention_policy_internal_keeps_bounded_bytes():
    policy = OutputRetentionPolicy()
    data = b"x" * (70 * 1024)
    result = policy.apply(data, OutputClass.INTERNAL)
    assert len(result.retained) == 64 * 1024
    assert result.truncated
    assert result.original_bytes == len(data)
    assert result.digest


def test_retention_policy_sensitive_keeps_no_bytes():
    policy = OutputRetentionPolicy()
    result = policy.apply(b"secret-ish", OutputClass.SENSITIVE)
    assert result.retained == b""
    assert result.digest
    assert not result.truncated


def test_retention_policy_secret_keeps_no_bytes():
    result = OutputRetentionPolicy().apply(b"top secret", OutputClass.SECRET)
    assert result.retained == b""
    assert result.digest


def test_retention_policy_public_keeps_larger_budget():
    data = b"x" * (100 * 1024)
    result = OutputRetentionPolicy().apply(data, OutputClass.PUBLIC)
    assert result.retained == data
    assert not result.truncated


def test_custom_retention_rule_can_disable_digest():
    rules = {
        value: OutputRetention(value, False, False, 0, 0)
        for value in OutputClass
    }
    result = OutputRetentionPolicy(rules).apply(b"x", OutputClass.INTERNAL)
    assert result.digest == ""


def test_retention_rules_must_cover_all_classes():
    with pytest.raises(ValueError):
        OutputRetentionPolicy({OutputClass.PUBLIC: OutputRetention(OutputClass.PUBLIC, True)})


def classified(payload=b"x", classification=OutputClass.INTERNAL):
    return ClassifiedOutput(
        classification,
        payload,
        len(payload),
        "digest",
        False,
    )


def test_store_put_and_get():
    store = OutputRetentionStore()
    item = store.put("x", classified(b"abc"), retention_seconds=10)
    assert store.get("x") == item


def test_store_replaces_same_key_without_item_growth():
    store = OutputRetentionStore(max_items=1)
    store.put("x", classified(b"a"), retention_seconds=10)
    store.put("x", classified(b"b"), retention_seconds=10)
    assert len(store.snapshot()) == 1
    assert store.get("x").payload == b"b"


def test_store_item_capacity():
    store = OutputRetentionStore(max_items=1)
    store.put("x", classified(), retention_seconds=10)
    with pytest.raises(RuntimeError):
        store.put("y", classified(), retention_seconds=10)


def test_store_byte_capacity():
    store = OutputRetentionStore(max_total_bytes=2)
    store.put("x", classified(b"ab"), retention_seconds=10)
    with pytest.raises(RuntimeError):
        store.put("y", classified(b"c"), retention_seconds=10)


def test_store_replacement_accounts_existing_bytes():
    store = OutputRetentionStore(max_total_bytes=3)
    store.put("x", classified(b"abc"), retention_seconds=10)
    store.put("x", classified(b"a"), retention_seconds=10)
    store.put("y", classified(b"bc"), retention_seconds=10)
    assert len(store.snapshot()) == 2


def test_store_expiry():
    now = [0.0]
    store = OutputRetentionStore(clock=lambda: now[0])
    store.put("x", classified(), retention_seconds=5)
    now[0] = 5
    assert store.get("x") is None


def test_store_prune_count():
    now = [0.0]
    store = OutputRetentionStore(clock=lambda: now[0])
    store.put("a", classified(), retention_seconds=1)
    store.put("b", classified(), retention_seconds=10)
    now[0] = 2
    assert store.prune() == 1
    assert store.get("b") is not None


def test_store_remove():
    store = OutputRetentionStore()
    store.put("x", classified(), retention_seconds=10)
    assert store.remove("x")
    assert not store.remove("x")
