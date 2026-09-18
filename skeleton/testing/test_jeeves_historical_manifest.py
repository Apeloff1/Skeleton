from __future__ import annotations

import json

import pytest

from skeleton.jeeves.historical_manifest import (
    MANIFEST_SCHEMA_VERSION,
    HistoricalBenchmarkManifest,
    HistoricalManifestError,
    dumps_manifest,
    loads_manifest,
    manifest_from_registry,
    registry_from_manifest,
)
from skeleton.jeeves.historical_models import (
    BenchmarkDefinition,
    BenchmarkDomain,
    BenchmarkSnapshot,
    HistoricalModelRegistry,
    MetricDirection,
    ModelIdentity,
    make_benchmark_provenance,
)


NOW = 7_000_000.0


def _snapshot(
    snapshot_id: str = "s1",
    *,
    score: float = 88.0,
    measured_at: float = NOW - 10.0,
    direction: MetricDirection = MetricDirection.HIGHER_IS_BETTER,
) -> BenchmarkSnapshot:
    model = ModelIdentity("provider", "model", "r1")
    benchmark = BenchmarkDefinition(
        benchmark_id="reasoning",
        revision="v1",
        domain=BenchmarkDomain.REASONING,
        raw_min=0.0,
        raw_max=100.0,
        direction=direction,
    )
    provenance = make_benchmark_provenance(
        source_id=f"fixture:{snapshot_id}",
        source_kind="benchmark",
        measured_at=measured_at,
        clock_version=1,
        snapshot_id=snapshot_id,
        model=model,
        benchmark=benchmark,
        raw_score=score,
        sample_count=100,
        uri=f"fixture://{snapshot_id}",
    )
    return BenchmarkSnapshot(
        snapshot_id=snapshot_id,
        model=model,
        benchmark=benchmark,
        raw_score=score,
        sample_count=100,
        measured_at=measured_at,
        provenance=provenance,
        notes="fixture",
    )


def _manifest(*snapshots: BenchmarkSnapshot) -> HistoricalBenchmarkManifest:
    return HistoricalBenchmarkManifest(
        dataset_id="jeeves-history",
        created_at=NOW,
        snapshots=tuple(snapshots),
    )


def test_manifest_round_trip_preserves_snapshot() -> None:
    original = _manifest(_snapshot())
    restored = loads_manifest(dumps_manifest(original))
    assert restored == original
    assert restored.fingerprint == original.fingerprint


def test_manifest_bytes_round_trip() -> None:
    original = _manifest(_snapshot())
    restored = loads_manifest(dumps_manifest(original).encode("utf-8"))
    assert restored == original


def test_serialization_is_deterministic() -> None:
    manifest = _manifest(_snapshot())
    assert dumps_manifest(manifest) == dumps_manifest(manifest)


def test_manifest_orders_snapshots_deterministically() -> None:
    late = _snapshot("late", measured_at=NOW - 10.0)
    early = _snapshot("early", measured_at=NOW - 20.0)
    manifest = _manifest(late, early)
    assert [item.snapshot_id for item in manifest.snapshots] == ["early", "late"]


def test_manifest_rejects_duplicate_snapshot_ids() -> None:
    with pytest.raises(HistoricalManifestError) as exc:
        _manifest(_snapshot("same"), _snapshot("same", measured_at=NOW - 20.0))
    assert exc.value.context["reason"] == "duplicate_snapshot_id"


def test_tampered_score_fails_manifest_fingerprint_before_ingest() -> None:
    payload = json.loads(dumps_manifest(_manifest(_snapshot())))
    payload["snapshots"][0]["raw_score"] = 1.0
    tampered = json.dumps(payload)
    with pytest.raises(HistoricalManifestError) as exc:
        loads_manifest(tampered)
    assert exc.value.context["reason"] == "manifest_fingerprint_mismatch"


def test_tampered_provenance_with_recomputed_manifest_still_fails_snapshot_contract() -> None:
    payload = json.loads(dumps_manifest(_manifest(_snapshot())))
    payload["snapshots"][0]["provenance"]["fingerprint"] = "0" * 64
    unsigned = {key: value for key, value in payload.items() if key != "manifest_fingerprint"}
    from skeleton.jeeves.historical_models import canonical_fingerprint

    payload["manifest_fingerprint"] = canonical_fingerprint(unsigned)
    with pytest.raises(Exception) as exc:
        loads_manifest(json.dumps(payload))
    assert "fingerprint" in str(exc.value).lower()


def test_unknown_root_key_is_rejected() -> None:
    payload = json.loads(dumps_manifest(_manifest(_snapshot())))
    payload["unexpected"] = True
    with pytest.raises(HistoricalManifestError) as exc:
        loads_manifest(json.dumps(payload))
    assert exc.value.context["reason"] == "schema_keys"


def test_missing_root_key_is_rejected() -> None:
    payload = json.loads(dumps_manifest(_manifest(_snapshot())))
    payload.pop("created_at")
    with pytest.raises(HistoricalManifestError) as exc:
        loads_manifest(json.dumps(payload))
    assert exc.value.context["reason"] == "schema_keys"


def test_unknown_snapshot_key_is_rejected_after_valid_fingerprint() -> None:
    payload = json.loads(dumps_manifest(_manifest(_snapshot())))
    payload["snapshots"][0]["unexpected"] = "x"
    from skeleton.jeeves.historical_models import canonical_fingerprint

    unsigned = {key: value for key, value in payload.items() if key != "manifest_fingerprint"}
    payload["manifest_fingerprint"] = canonical_fingerprint(unsigned)
    with pytest.raises(HistoricalManifestError) as exc:
        loads_manifest(json.dumps(payload))
    assert exc.value.context["reason"] == "schema_keys"


def test_unknown_domain_enum_is_rejected() -> None:
    payload = json.loads(dumps_manifest(_manifest(_snapshot())))
    payload["snapshots"][0]["benchmark"]["domain"] = "telepathy"
    from skeleton.jeeves.historical_models import canonical_fingerprint

    unsigned = {key: value for key, value in payload.items() if key != "manifest_fingerprint"}
    payload["manifest_fingerprint"] = canonical_fingerprint(unsigned)
    with pytest.raises(HistoricalManifestError) as exc:
        loads_manifest(json.dumps(payload))
    assert exc.value.context["reason"] == "invalid_enum"


def test_unknown_direction_enum_is_rejected() -> None:
    payload = json.loads(dumps_manifest(_manifest(_snapshot())))
    payload["snapshots"][0]["benchmark"]["direction"] = "sideways"
    from skeleton.jeeves.historical_models import canonical_fingerprint

    unsigned = {key: value for key, value in payload.items() if key != "manifest_fingerprint"}
    payload["manifest_fingerprint"] = canonical_fingerprint(unsigned)
    with pytest.raises(HistoricalManifestError) as exc:
        loads_manifest(json.dumps(payload))
    assert exc.value.context["reason"] == "invalid_enum"


def test_unsupported_schema_version_is_rejected() -> None:
    payload = json.loads(dumps_manifest(_manifest(_snapshot())))
    payload["schema_version"] = MANIFEST_SCHEMA_VERSION + 1
    from skeleton.jeeves.historical_models import canonical_fingerprint

    unsigned = {key: value for key, value in payload.items() if key != "manifest_fingerprint"}
    payload["manifest_fingerprint"] = canonical_fingerprint(unsigned)
    with pytest.raises(HistoricalManifestError) as exc:
        loads_manifest(json.dumps(payload))
    assert exc.value.context["reason"] == "unsupported_schema"


def test_invalid_json_is_rejected() -> None:
    with pytest.raises(HistoricalManifestError) as exc:
        loads_manifest("{not-json")
    assert exc.value.context["reason"] == "invalid_json"


def test_invalid_utf8_is_rejected() -> None:
    with pytest.raises(HistoricalManifestError) as exc:
        loads_manifest(b"\xff\xfe")
    assert exc.value.context["reason"] == "invalid_encoding"


def test_non_string_or_bytes_input_is_rejected() -> None:
    with pytest.raises(HistoricalManifestError) as exc:
        loads_manifest(123)  # type: ignore[arg-type]
    assert exc.value.context["reason"] == "invalid_manifest_input"


def test_registry_manifest_round_trip_preserves_registry_evidence() -> None:
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    first = _snapshot("a", measured_at=NOW - 20.0)
    second = _snapshot("b", score=89.0, measured_at=NOW - 10.0)
    registry.ingest(first)
    registry.ingest(second)
    manifest = manifest_from_registry(registry, dataset_id="dataset", created_at=NOW)
    restored = registry_from_manifest(manifest, clock=lambda: NOW)
    assert restored.snapshots() == registry.snapshots()


def test_registry_import_reapplies_future_snapshot_guard() -> None:
    future = _snapshot("future", measured_at=NOW + 10.0)
    manifest = _manifest(future)
    with pytest.raises(Exception) as exc:
        registry_from_manifest(manifest, clock=lambda: NOW)
    assert "future" in str(exc.value).lower()


def test_registry_import_reapplies_history_limit() -> None:
    manifest = _manifest(
        _snapshot("a", measured_at=NOW - 30.0),
        _snapshot("b", score=89.0, measured_at=NOW - 20.0),
    )
    with pytest.raises(Exception) as exc:
        registry_from_manifest(manifest, clock=lambda: NOW, max_snapshots_per_benchmark=1)
    assert "history" in str(exc.value).lower()


def test_lower_is_better_definition_round_trips() -> None:
    snapshot = _snapshot(direction=MetricDirection.LOWER_IS_BETTER)
    restored = loads_manifest(dumps_manifest(_manifest(snapshot))).snapshots[0]
    assert restored.benchmark.direction is MetricDirection.LOWER_IS_BETTER


def test_manifest_fingerprint_changes_when_dataset_identity_changes() -> None:
    snapshot = _snapshot()
    left = HistoricalBenchmarkManifest(dataset_id="left", created_at=NOW, snapshots=(snapshot,))
    right = HistoricalBenchmarkManifest(dataset_id="right", created_at=NOW, snapshots=(snapshot,))
    assert left.fingerprint != right.fingerprint


def test_manifest_fingerprint_changes_when_snapshot_set_changes() -> None:
    one = _manifest(_snapshot("a"))
    two = _manifest(_snapshot("a"), _snapshot("b", score=89.0, measured_at=NOW - 20.0))
    assert one.fingerprint != two.fingerprint


def test_noncanonical_text_is_rejected_even_with_matching_raw_fingerprint() -> None:
    payload = json.loads(dumps_manifest(_manifest(_snapshot())))
    payload["dataset_id"] = "  jeeves-history  "
    from skeleton.jeeves.historical_models import canonical_fingerprint

    unsigned = {key: value for key, value in payload.items() if key != "manifest_fingerprint"}
    payload["manifest_fingerprint"] = canonical_fingerprint(unsigned)
    with pytest.raises(HistoricalManifestError) as exc:
        loads_manifest(json.dumps(payload))
    assert exc.value.context["reason"] == "noncanonical_manifest"