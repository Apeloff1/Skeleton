"""The authored 43 Jeeves lenses: per-run native-cue coverage, not fake evidence."""
from __future__ import annotations

import pytest

from skeleton.jeeves import game_emulator_triangle_lens_coverage as coverage
from skeleton.jeeves.game_learning import _digest


def _episode(ident: str, *, optical: int, probes: int) -> dict:
    return {
        "source_trace_sha256": ident * 64,
        "source_receipt_sha256": (chr(ord(ident) + 2)) * 64,
        "companion_viewing": {"native_rgb24_frames_optically_inspected": optical},
        "ai_playing": {"counterfactual_native_probes": probes},
    }


def _mock_router(episode, *, max_lenses, requested_keys):
    assert max_lenses == 43
    assert requested_keys == ()
    good = episode["companion_viewing"]["native_rgb24_frames_optically_inspected"] > 0
    rows = []
    for i in range(43):
        support = good and i < 22
        rows.append({
            "lens_key": f"canonical_authored_{i:02d}",
            "lens_family": "game",
            "governance_grade": "theory",
            "governance_fingerprint": (f"{i + (10 if good else 100):064x}"),
            "question": f"What new real native evidence supports lens {i}?",
            "native_evidence_support_class": (
                "measured_native_cue_present" if support
                else "hypothesis_only_without_matching_native_cue"
            ),
            "matched_native_observation_cues": ["pixel"] if support else [],
            "native_observation_cue_provenance": (
                [{"native_observation_id": "native-frame"}] if support else []
            ),
            "new_independent_evidence": 0,
            "training_ground_truth_label_available": False,
            "factual_claims_allowed": False,
            "causal_claims_allowed": False,
        })
    result = {
        "actually_routed_lenses": 43, "routes": rows,
        "source_native_trace_sha256": episode["source_trace_sha256"],
        "source_native_receipt_sha256": episode["source_receipt_sha256"],
        "canonical_catalog_sha256": "c" * 64,
        "route_digest": _digest(rows),
        "governance_fingerprint": "d" * 64,
        "factual_assertions_authorized": False,
        "causal_assertions_authorized": False,
    }
    return result


def _inputs(monkeypatch):
    monkeypatch.setattr(coverage, "verify_training_triangle", lambda *_: None)
    monkeypatch.setattr(coverage, "route_episode_semantic_lenses", _mock_router)
    evidence = {"report_digest": "a" * 64}
    triangle = {
        "triangle_digest": "b" * 64,
        "episode_lens_references": [
            _episode("1", optical=0, probes=0),
            _episode("2", optical=4, probes=3),
        ],
    }
    return evidence, triangle


def test_43_canonical_lenses_are_audited_across_native_episodes(monkeypatch):
    evidence, triangle = _inputs(monkeypatch)
    result = coverage.audit_43_lens_coverage(evidence, triangle, limit=8)
    assert result["episodes_audited"] == 2
    assert result["unique_canonical_lenses_routed"] == 43
    assert result["native_cue_supported_lens_exposures"] == 22
    assert result["hypothesis_only_lens_exposures"] == 64
    assert result["independent_sample_multiplication"] == 0
    assert result["semantic_model_generations_executed"] == 0
    assert result["production_jeeves_weight_updates"] == 0
    assert "capture_native_rgb24_frames_with_dragon_consent" in (
        result["episode_coverage"][0]["next_measurement_suggestions"]
    )
    assert result["episode_coverage"][1]["next_measurement_suggestions"] == [
        "gather_independent_positive_native_observation_cues",
    ]
    assert result["lens_coverage"][0]["native_cue_supported_episodes"] == 1
    # Governance grades/decision fingerprints are allowed to differ by
    # episode; those changes must be retained, not treated as made-up truth.
    assert len(result["lens_coverage"][0]["governance_fingerprints"]) == 2
    coverage.verify_43_lens_coverage(evidence, triangle, result)


def test_43_lens_coverage_paginates_without_multiplying_gameplay(monkeypatch):
    evidence, triangle = _inputs(monkeypatch)
    first = coverage.audit_43_lens_coverage(evidence, triangle, limit=1)
    second = coverage.audit_43_lens_coverage(
        evidence, triangle, start_episode=first["next_episode_index"], limit=1
    )
    assert first["next_episode_index"] == 1
    assert second["next_episode_index"] is None
    assert first["native_cue_supported_lens_exposures"] == 0
    assert second["native_cue_supported_lens_exposures"] == 22
    assert first["native_gameplay_episodes_created"] == 0


def test_43_lens_coverage_detects_resealed_forged_cue_or_report(monkeypatch):
    evidence, triangle = _inputs(monkeypatch)
    first = coverage.audit_43_lens_coverage(evidence, triangle)
    first["lens_coverage"][0]["native_cue_supported_episodes"] = 99
    first["audit_digest"] = _digest({
        k: v for k, v in first.items() if k != "audit_digest"
    })
    with pytest.raises(coverage.TriangleCoverageError, match="reproducible"):
        coverage.verify_43_lens_coverage(evidence, triangle, first)


def test_43_lens_coverage_rejects_invalid_page(monkeypatch):
    evidence, triangle = _inputs(monkeypatch)
    with pytest.raises(coverage.TriangleCoverageError, match="page"):
        coverage.audit_43_lens_coverage(evidence, triangle, start_episode=2)
    with pytest.raises(coverage.TriangleCoverageError, match="page"):
        coverage.audit_43_lens_coverage(evidence, triangle, limit=17)


def test_rom_cli_exposes_cross_episode_lens_audit():
    from scripts.training.rom_study import parser
    args = parser().parse_args([
        "triangle-lens-audit", "--receipt", "/tmp/source.json",
        "--source-sha256", "f" * 64, "--start-episode", "4",
        "--limit", "16",
    ])
    assert args.operation == "triangle-lens-audit"
    assert args.start_episode == 4
    assert args.limit == 16
