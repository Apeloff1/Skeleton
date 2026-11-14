"""GF-G: GF-P0-149 edit receipts, GF-P0-166 telemetry adapters, GF-P0-164 reconciliation."""
from __future__ import annotations

import copy

import pytest

from skeleton.jeeves import game_frontier_chunk_telemetry as jeeves_mod
from skeleton.ai.agents.jeeves import game_frontier_chunk_telemetry as ai_mod
from skeleton.jeeves.game_frontier_chunk_telemetry import (
    ChunkTelemetryError, TelemetryAdapter, build_edit_receipts, ingest_telemetry,
    reconcile_chunk_evidence, verify_edit_receipts, verify_sealed,
)

EDIT = {
    "edit_id": "e1",
    "chunks": {
        "c0": {
            "sources": {"shader": [{"id": "sh.water", "content": "void main(){}"}],
                        "weather": [{"id": "rain", "content": {"rate": 0.4}}]},
            "vertices_before": [[0, 0, 0], [1, 0, 0]],
            "vertices_after": [[0, 0, 0], [1, 0.5, 0], [2, 0, 0]],
        },
        "c1": {"sources": {"light": [{"id": "sun", "content": {"lux": 1000}}]}},
    },
}


def test_mirrored_modules_identical() -> None:
    assert jeeves_mod.__all__ == ai_mod.__all__
    assert jeeves_mod.build_edit_receipts(EDIT) == ai_mod.build_edit_receipts(EDIT)


def test_149_edit_receipts_pin_sources_and_vertex_diff() -> None:
    doc = build_edit_receipts(EDIT)
    c0 = doc["receipts"][0]
    assert c0["chunk_id"] == "c0"
    assert [r["id"] for r in c0["sources"]["shader"]] == ["sh.water"]
    assert c0["sources"]["terrain"] == []
    assert c0["vertex_diff"]["moved"] == [1] and c0["vertex_diff"]["added"] == 1
    assert c0["vertex_diff"]["max_displacement"] == 0.5
    assert verify_edit_receipts(doc, EDIT)
    assert build_edit_receipts(copy.deepcopy(EDIT)) == doc


def test_149_verifier_recomputes_and_rejects_tamper() -> None:
    doc = build_edit_receipts(EDIT)
    changed = copy.deepcopy(EDIT)
    changed["chunks"]["c1"]["sources"]["light"][0]["content"]["lux"] = 5
    assert not verify_edit_receipts(doc, changed)
    forged = copy.deepcopy(doc)
    forged["receipts"][0]["vertex_diff"]["moved"] = []
    assert not verify_edit_receipts(forged, EDIT)


@pytest.mark.parametrize("bad", [
    {"edit_id": "", "chunks": {"c": {"sources": {"light": [{"id": "x", "content": 1}]}}}},
    {"edit_id": "e", "chunks": {}},
    {"edit_id": "e", "chunks": {"c": {"sources": {"fog": [{"id": "x", "content": 1}]}}}},
    {"edit_id": "e", "chunks": {"c": {}}},
    {"edit_id": "e", "chunks": {"c": {"vertices_before": [[0, 0]], "vertices_after": [[1, 1]]}}},
    {"edit_id": "e", "chunks": {"c": {"vertices_before": [], "vertices_after": [[float("nan"), 0, 0]]}}},
])
def test_149_invalid_edits_fail_closed(bad: dict) -> None:
    with pytest.raises(ChunkTelemetryError):
        build_edit_receipts(bad)


SAMPLES = {
    "c0": {
        "collision": {"normal": [0, 1, 0], "force": [0, 9.8, 0]},
        "lighting": {"luminance": 120.0, "light_ids": ["sun"]},
        "audio": {"rms_db": -18.0, "bus": "sfx"},
        "mesh_lod": {"lod": 1, "triangles": 2048},
    }
}


def test_166_native_adapter_is_authoritative_candidate_otherwise() -> None:
    native = ingest_telemetry(TelemetryAdapter("godot.native", "godot", True), 7, SAMPLES)
    est = ingest_telemetry(TelemetryAdapter("estimator", "source", False), 7, SAMPLES)
    assert native["authority"] == "authoritative" and est["authority"] == "candidate"
    assert native["chunks"][0]["channels"]["mesh_lod"] == {"lod": 1, "triangles": 2048}
    assert verify_sealed(native)


@pytest.mark.parametrize("sample", [
    {"collision": {"normal": [0, 2, 0], "force": [0, 0, 0]}},
    {"collision": {"normal": [0, 1], "force": [0, 0, 0]}},
    {"lighting": {"luminance": -1}},
    {"audio": {"rms_db": float("inf")}},
    {"mesh_lod": {"lod": -1, "triangles": 3}},
])
def test_166_invalid_samples_fail_closed(sample: dict) -> None:
    with pytest.raises(ChunkTelemetryError):
        ingest_telemetry(TelemetryAdapter("a", "godot", True), 0, {"c0": sample})


def test_166_undeclared_channel_rejected() -> None:
    adapter = TelemetryAdapter("audio-only", "godot", True, channels=("audio",))
    with pytest.raises(ChunkTelemetryError):
        ingest_telemetry(adapter, 0, SAMPLES)


def _planes(d="h1"):
    return {"rendered": {"c0": d}, "capture": {"chunks": {"c0": d}}, "journal": {"c0": d}, "evidence": {"c0": d}}


def test_164_all_match_without_hardware_is_unattested() -> None:
    out = reconcile_chunk_evidence(**_planes())
    assert out["status"] == "matched_unattested" and out["hardware"] is None
    assert verify_sealed(out)


def test_164_hardware_attested_match_is_verified() -> None:
    p = _planes()
    p["capture"]["hardware"] = {"device": "RTX 4070", "driver": "550.1"}
    assert reconcile_chunk_evidence(**p)["status"] == "verified"


def test_164_mismatch_and_missing_fail() -> None:
    p = _planes()
    p["journal"] = {"c0": "other"}
    p["evidence"]["c1"] = "h2"
    out = reconcile_chunk_evidence(**p)
    states = {r["chunk_id"]: r["state"] for r in out["chunks"]}
    assert out["status"] == "failed" and states == {"c0": "mismatch", "c1": "missing"}
    tampered = copy.deepcopy(out)
    tampered["status"] = "verified"
    assert not verify_sealed(tampered)


def test_164_empty_input_fails_closed() -> None:
    out = reconcile_chunk_evidence(rendered={}, capture={}, journal={}, evidence={})
    assert out["status"] == "failed"
