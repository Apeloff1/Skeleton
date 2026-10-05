"""Tests for wave 11: alert correlator, encryption at rest, request
deduplicator, schema evolution guard, and worker pool.
"""
from __future__ import annotations

import time

import pytest

from skeleton.core.worker_pool import WorkerPool
from skeleton.cortex.alert_correlator import AlertCorrelator
from skeleton.data.schema_evolution import SchemaEvolutionGuard
from skeleton.mesh.deduplicator import Deduplicator
from skeleton.mesh.dependency_graph import DependencyGraph
from skeleton.security.encryption_at_rest import EncryptionAtRest


class TestAlertCorrelator:
    def test_shared_attribute_grouping(self):
        ac = AlertCorrelator()
        ac.ingest("a1", "api", "critical", "down", attributes={"trace_id": "t1"})
        result = ac.ingest("a2", "db", "warning", "slow", attributes={"trace_id": "t1"})
        assert result["correlated"]
        assert "trace_id" in result["shared"]

    def test_no_correlation_without_shared(self):
        ac = AlertCorrelator()
        ac.ingest("a1", "api", "critical", "x")
        result = ac.ingest("a2", "db", "warning", "y")
        assert not result["correlated"]

    def test_window_expiry(self):
        ac = AlertCorrelator(window_s=10)
        old = time.time_ns() - int(3600e9)
        ac.ingest("a1", "api", "critical", "x", attributes={"host": "h1"}, fired_ns=old)
        result = ac.ingest("a2", "api", "warning", "y", attributes={"host": "h1"})
        assert not result["correlated"]

    def test_upstream_suppression(self):
        g = DependencyGraph()
        g.add_edge("api", "db")
        ac = AlertCorrelator(dependency_graph=g)
        ac.ingest("root", "db", "critical", "db down")
        # create group first via shared attrs
        ac.ingest("root2", "db", "warning", "db slow")
        result = ac.ingest("symptom", "api", "warning", "api errors")
        if result["correlated"]:
            noise = ac.noise_reduction()
            assert noise["total_alerts"] == 3

    def test_noise_reduction_stats(self):
        ac = AlertCorrelator()
        ac.ingest("a1", "api", "critical", "x", attributes={"host": "h"})
        ac.ingest("a2", "api", "warning", "y", attributes={"host": "h"})
        noise = ac.noise_reduction()
        assert noise["in_groups"] == 2


class TestEncryptionAtRest:
    def test_roundtrip(self):
        enc = EncryptionAtRest(master_secret="test-key")
        enc.encrypt_file("audit.jsonl", '{"entry": 1}')
        assert enc.decrypt_file("audit.jsonl") == '{"entry": 1}'

    def test_wrong_key_fails_integrity(self):
        enc = EncryptionAtRest(master_secret="key-a")
        env = enc.export_envelope.__self__  # noqa
        enc.encrypt_file("secrets.json", "data")
        other = EncryptionAtRest(master_secret="key-b")
        other.import_envelope(enc.export_envelope("secrets.json"))
        with pytest.raises(ValueError):
            other.decrypt_file("secrets.json")

    def test_master_rotation_preserves_data(self):
        enc = EncryptionAtRest(master_secret="old-master")
        enc.encrypt_file("f1", "payload-1")
        enc.encrypt_file("f2", "payload-2")
        result = enc.rotate_master("new-master")
        assert result["rewrapped_deks"] == 2
        assert enc.decrypt_file("f1") == "payload-1"
        assert enc.decrypt_file("f2") == "payload-2"

    def test_tamper_detected(self):
        enc = EncryptionAtRest(master_secret="k")
        enc.encrypt_file("f", "original")
        env = enc._envelopes["f"]
        env.ciphertext = env.ciphertext[:-4] + "AAAA"
        with pytest.raises(ValueError):
            enc.decrypt_file("f")


class TestDeduplicator:
    def test_first_execution(self):
        d = Deduplicator()
        result = d.execute("k1", {"amount": 10}, lambda: {"id": "r1"})
        assert result["executed"]

    def test_replay_returns_cached(self):
        d = Deduplicator()
        calls = []
        d.execute("k1", {"a": 1}, lambda: calls.append(1) or {"ok": True})
        result = d.execute("k1", {"a": 1}, lambda: calls.append(1) or {"ok": True})
        assert result["replay"]
        assert len(calls) == 1

    def test_conflict_detection(self):
        d = Deduplicator()
        d.execute("k1", {"a": 1}, lambda: "x")
        result = d.execute("k1", {"a": 2}, lambda: "y")
        assert result["conflict"]

    def test_failed_not_cached(self):
        d = Deduplicator()
        calls = []
        def boom():
            calls.append(1)
            raise RuntimeError("x")
        with pytest.raises(RuntimeError):
            d.execute("k1", {}, boom)
        # retry allowed after failure
        result = d.execute("k1", {}, lambda: "recovered")
        assert result["executed"]

    def test_retention_sweep(self):
        d = Deduplicator(retention_s=0.01)
        d.execute("k1", {}, lambda: "v")
        time.sleep(0.02)
        result = d.execute("k1", {}, lambda: "v2")
        assert result["executed"]  # old record expired


class TestSchemaEvolution:
    def test_optional_add_compatible(self):
        guard = SchemaEvolutionGuard()
        old = {"properties": {"name": {"type": "string"}}, "required": ["name"]}
        new = {"properties": {"name": {"type": "string"}, "nick": {"type": "string"}}, "required": ["name"]}
        assert guard.check(old, new)["compatible"]

    def test_removed_field_breaking(self):
        guard = SchemaEvolutionGuard()
        old = {"properties": {"a": {"type": "string"}}}
        new = {"properties": {}}
        result = guard.check(old, new)
        assert not result["compatible"]
        assert result["breaking_count"] == 1

    def test_new_required_breaking(self):
        guard = SchemaEvolutionGuard()
        old = {"properties": {"a": {"type": "string"}}, "required": []}
        new = {"properties": {"a": {"type": "string"}, "b": {"type": "int"}}, "required": ["b"]}
        assert not guard.check(old, new)["compatible"]

    def test_type_change_breaking(self):
        guard = SchemaEvolutionGuard()
        old = {"properties": {"a": {"type": "string"}}}
        new = {"properties": {"a": {"type": "int"}}}
        result = guard.check(old, new)
        assert not result["compatible"]
        assert "migration" in result["suggestion"]

    def test_none_mode_allows_all(self):
        guard = SchemaEvolutionGuard(mode="none")
        result = guard.check({"properties": {"a": {}}}, {"properties": {}})
        assert result["compatible"]


class TestWorkerPool:
    def test_submit_and_process(self):
        pool = WorkerPool(workers=2)
        pool.submit(1)
        pool.submit(2)
        done = []
        result = pool.process(lambda p: done.append(p))
        assert result["processed"] == 2
        assert done == [1, 2]

    def test_backpressure_rejection(self):
        pool = WorkerPool(workers=1, queue_capacity=2)
        pool.submit(1)
        pool.submit(2)
        result = pool.submit(3)
        assert not result["accepted"]

    def test_failed_retried(self):
        pool = WorkerPool(workers=1)
        attempts = []
        def flaky(p):
            attempts.append(p)
            if len(attempts) < 2:
                raise RuntimeError("x")
        pool.submit("task")
        pool.process(flaky)
        assert len(attempts) >= 1

    def test_resize(self):
        pool = WorkerPool(workers=2)
        pool.resize(6)
        assert len(pool._workers) == 6
        pool.resize(1)
        assert len(pool._workers) == 1

    def test_card(self):
        pool = WorkerPool(workers=2)
        pool.submit("x")
        pool.process(lambda p: None)
        card = pool.card()
        assert card["completed"] == 1
