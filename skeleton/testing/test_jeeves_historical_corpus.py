from __future__ import annotations

import json

import pytest

from skeleton.jeeves.historical_corpus import (
    BenchmarkCatalog,
    CorpusImportPolicy,
    HistoricalCorpusAdapter,
    HistoricalCorpusError,
    summarize_import,
)
from skeleton.jeeves.historical_models import (
    BenchmarkDefinition,
    BenchmarkDomain,
    HistoricalModelError,
    HistoricalModelRegistry,
)


NOW = 1_000.0
REASON = BenchmarkDefinition("corpus-reason", "v1", BenchmarkDomain.REASONING, 0.0, 100.0)
CODE = BenchmarkDefinition("corpus-code", "v1", BenchmarkDomain.CODING, 0.0, 100.0)


def _adapter(*, require_uri=False, max_records=100):
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    catalog = BenchmarkCatalog([REASON, CODE])
    policy = CorpusImportPolicy(
        source_id="fixture-corpus",
        require_uri=require_uri,
        max_records=max_records,
    )
    return HistoricalCorpusAdapter(registry=registry, catalog=catalog, policy=policy), registry


def _row(record_id="r1", **overrides):
    row = {
        "record_id": record_id,
        "provider": "provider-a",
        "model": "model-a",
        "revision": "rev-1",
        "benchmark": REASON.key,
        "raw_score": 88.0,
        "sample_count": 100,
        "measured_at": 900.0,
        "clock_version": 1,
        "uri": "https://example.invalid/result",
    }
    row.update(overrides)
    return row


def test_import_rows_creates_provenance_bound_snapshots() -> None:
    adapter, registry = _adapter()
    report = adapter.import_rows([
        _row("reason"),
        _row("code", benchmark=CODE.key, raw_score=91.0),
    ])
    assert report.record_count == 2
    assert report.model_count == 1
    assert report.benchmark_count == 2
    assert len(registry.snapshots()) == 2
    assert all(snapshot.provenance.source_kind == "benchmark_corpus" for snapshot in registry.snapshots())


def test_unknown_benchmark_cannot_redefine_catalog() -> None:
    adapter, _ = _adapter()
    with pytest.raises(HistoricalCorpusError):
        adapter.import_rows([_row(benchmark="unknown@v9")])


def test_extra_fields_are_rejected() -> None:
    adapter, _ = _adapter()
    with pytest.raises(HistoricalCorpusError):
        adapter.import_rows([_row(untrusted_normalization={"min": -999})])


def test_missing_required_fields_are_rejected() -> None:
    adapter, _ = _adapter()
    row = _row()
    row.pop("sample_count")
    with pytest.raises(HistoricalCorpusError):
        adapter.import_rows([row])


def test_duplicate_record_ids_are_rejected_before_ingest() -> None:
    adapter, registry = _adapter()
    with pytest.raises(HistoricalCorpusError):
        adapter.import_rows([_row("same"), _row("same", benchmark=CODE.key)])
    assert registry.snapshots() == ()


def test_out_of_bounds_score_is_rejected() -> None:
    adapter, registry = _adapter()
    with pytest.raises((HistoricalCorpusError, HistoricalModelError)):
        adapter.import_rows([_row(raw_score=101.0)])
    assert registry.snapshots() == ()


def test_required_uri_policy_is_enforced() -> None:
    adapter, registry = _adapter(require_uri=True)
    row = _row()
    row.pop("uri")
    with pytest.raises(HistoricalCorpusError):
        adapter.import_rows([row])
    assert registry.snapshots() == ()


def test_jsonl_round_trip_import() -> None:
    adapter, registry = _adapter()
    payload = "\n".join(
        json.dumps(row)
        for row in [
            _row("a"),
            _row("b", benchmark=CODE.key, raw_score=92.0),
        ]
    )
    report = adapter.import_jsonl(payload)
    assert report.record_ids == ("a", "b")
    assert len(registry.snapshots()) == 2


def test_jsonl_accepts_utf8_bytes() -> None:
    adapter, registry = _adapter()
    payload = json.dumps(_row("utf8", notes="måling"), ensure_ascii=False).encode("utf-8")
    adapter.import_jsonl(payload)
    assert registry.snapshots()[0].notes == "måling"


def test_invalid_utf8_is_rejected() -> None:
    adapter, _ = _adapter()
    with pytest.raises(HistoricalCorpusError):
        adapter.import_jsonl(b"\xff\xfe")


def test_invalid_json_line_reports_failure() -> None:
    adapter, _ = _adapter()
    with pytest.raises(HistoricalCorpusError):
        adapter.import_jsonl('{"record_id":"ok"}\nnot-json')


def test_jsonl_line_must_be_object() -> None:
    adapter, _ = _adapter()
    with pytest.raises(HistoricalCorpusError):
        adapter.import_jsonl("[1, 2, 3]")


def test_record_limit_is_enforced() -> None:
    adapter, registry = _adapter(max_records=1)
    with pytest.raises(HistoricalCorpusError):
        adapter.import_rows([_row("a"), _row("b")])
    assert registry.snapshots() == ()


def test_future_snapshot_uses_registry_temporal_guard() -> None:
    adapter, registry = _adapter()
    with pytest.raises(HistoricalModelError):
        adapter.import_rows([_row(measured_at=NOW + 1.0)])
    assert registry.snapshots() == ()


def test_late_future_snapshot_keeps_batch_atomic() -> None:
    adapter, registry = _adapter()
    with pytest.raises(HistoricalModelError):
        adapter.import_rows([
            _row("valid-first", measured_at=900.0),
            _row("future-second", benchmark=CODE.key, measured_at=NOW + 1.0),
        ])
    assert registry.snapshots() == ()


def test_late_logical_contradiction_keeps_batch_atomic() -> None:
    adapter, registry = _adapter()
    with pytest.raises(HistoricalModelError):
        adapter.import_rows([
            _row("first", measured_at=900.0, raw_score=80.0),
            _row("conflict", measured_at=900.0, raw_score=81.0),
        ])
    assert registry.snapshots() == ()


def test_catalog_fingerprint_is_order_independent() -> None:
    left = BenchmarkCatalog([REASON, CODE])
    right = BenchmarkCatalog([CODE, REASON])
    assert left.fingerprint == right.fingerprint


def test_import_report_fingerprint_is_deterministic_for_same_order_independent_rows() -> None:
    adapter_a, _ = _adapter()
    adapter_b, _ = _adapter()
    rows = [_row("a"), _row("b", benchmark=CODE.key)]
    left = adapter_a.import_rows(rows)
    right = adapter_b.import_rows(list(reversed(rows)))
    assert left.evidence_fingerprint == right.evidence_fingerprint


def test_summary_is_json_friendly() -> None:
    adapter, _ = _adapter()
    report = adapter.import_rows([_row("a")])
    summary = summarize_import(report)
    assert summary["record_count"] == 1
    assert summary["models"] == ["provider-a:model-a@rev-1"]
    assert summary["evidence_fingerprint"] == report.evidence_fingerprint