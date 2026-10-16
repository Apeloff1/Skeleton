"""Fail-closed regression suite for Jeeves commercial and render-quality gates.

Fixture names/metrics are synthetic; never treat tests as real sales evidence.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from skeleton.developer.game_cli import run_game_cli
from skeleton.developer import jeeves_game_authoring as authoring
from skeleton.developer.jeeves_game_quality import SCHEMA, ASSET_SCHEMA


def _workspace(tmp_path: Path) -> Path:
    result = run_game_cli(["init", "quality-lab", "--dir", str(tmp_path),
                           "--vision", "Original original-generation action role-playing"])
    assert result["ok"], result
    return tmp_path / "quality-lab"


def _benchmark_row(i: int) -> dict:
    return {
        "id": "fixture-title-" + str(i), "release_year": 2018,
        "sales_units": (9-i) * 100000, "sales_basis": "reported_units",
        "sales_scope": "global_lifetime",
        "critic_score": 97-i, "critic_reviews": 35,
        "sales_source": {
            "url": f"https://publisher.example.com/ir/title-{i}",
            "issuer": "Fixture publisher", "kind": "publisher_filing",
            "published": "2026-07-01"
        },
        "rating_source": {
            "url": f"https://reviews.example.org/critics/title-{i}",
            "issuer": "Fixture review site", "kind": "critic_aggregate",
            "published": "2026-07-02"
        },
    }


def _write(root: Path, rows=None, *, period="2015-2019") -> Path:
    rows = [_benchmark_row(i) for i in range(1,9)] if rows is None else rows
    path = root / "design" / "market_benchmarks.json"
    value = {"schema": SCHEMA, "cohorts": [{
        "era": "extraction_now", "console": "PC", "genre": "RPG",
        "period": period, "records": rows,
    }]}
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")
    return path


def _rank(root: Path, *, console="PC", genre="RPG", period="2015-2019") -> dict:
    return run_game_cli(["jeeves", "benchmark", "--project", str(root),
                         "--console", console, "--genre", genre, "--period", period])


def test_dual_sales_and_review_top_quartile_requires_exact_cohort(tmp_path):
    root = _workspace(tmp_path)
    _write(root)
    ranked = _rank(root)
    assert ranked["ok"], ranked
    assert ranked["cohort_size"] == 8
    assert ranked["top_quartile_cutoff_rank"] == 2
    assert ranked["qualifying_count"] == 2
    assert [r["id"] for r in ranked["leaders"]] == ["fixture-title-1", "fixture-title-2"]
    assert ranked["asset_quality_proven"] is False
    assert ranked["evidence_status"] == "operator_supplied_not_independently_verified"
    assert not _rank(root, console="PlayStation")["ok"]
    assert not _rank(root, genre="Platformer")["ok"]
    assert not _rank(root, period="1990-1994")["ok"]


def test_review_and_sales_conflict_yields_no_top_tier(tmp_path):
    root = _workspace(tmp_path)
    rows = [_benchmark_row(i) for i in range(1,9)]
    for i, rec in enumerate(rows):
        rec["critic_score"] = 89+i
    _write(root, rows)
    ranked = _rank(root)
    assert ranked["ok"] is False
    assert ranked["qualifying_count"] == 0
    assert ranked["eligible_for_inspiration"] is False


@pytest.mark.parametrize("mutate", [
    lambda rows: rows[:4],
    lambda rows: [dict(rows[0], sales_basis="shipments"), *rows[1:]],
    lambda rows: [dict(rows[0], sales_scope="regional_lifetime"), *rows[1:]],
    lambda rows: [dict(rows[0], critic_reviews=0), *rows[1:]],
    lambda rows: [dict(rows[0], critic_score=101), *rows[1:]],
    lambda rows: [dict(rows[0], sales_units=-1), *rows[1:]],
    lambda rows: [dict(rows[0], sales_source=rows[0]["rating_source"]), *rows[1:]],
    lambda rows: [dict(rows[0], rating_source=rows[0]["sales_source"]), *rows[1:]],
    lambda rows: [dict(rows[0], id=rows[1]["id"]), *rows[1:]],
    lambda rows: [dict(rows[0], release_year=2001), *rows[1:]],
])
def test_unsafe_or_noncomparable_market_evidence_fails(tmp_path, mutate):
    root = _workspace(tmp_path)
    rows = mutate([_benchmark_row(i) for i in range(1,9)])
    _write(root, rows)
    assert _rank(root)["ok"] is False


def test_product_proposal_requires_market_evidence_and_excludes_copyright_titles(tmp_path, monkeypatch):
    root = _workspace(tmp_path)
    without = run_game_cli(["jeeves", "propose", "--project", str(root),
                            "--kind", "asset", "--brief", "Character sprite"])
    assert without["ok"] is False
    _write(root)
    observed = []
    async def infer(prompt):
        observed.append(json.loads(prompt))
        return json.dumps({
            "kind":"asset", "slug":"original-sprite", "title":"Original sprite",
            "summary":"Original 2D character silhouette", "body":"Create a distinct palette and posture",
            "rationale":"Supports readable pixel art within the target hardware envelope",
        }), {"provider":"fixture-provider", "model":"fixture-model", "request_id":None}
    monkeypatch.setattr(authoring, "_infer", infer)
    proposed = run_game_cli(["jeeves", "propose", "--project", str(root),
                             "--kind", "asset", "--brief", "Original sprite",
                             "--console", "PC", "--genre", "RPG", "--period", "2015-2019"])
    assert proposed["ok"], proposed
    market = observed[0]["quality_cohort"]
    assert market["qualified_reference_count"] == 2
    assert "fixture-title-" not in json.dumps(market)
    assert "source_status" in market
    digest = proposed["proposal_sha256"]
    checked = run_game_cli(["jeeves", "review", "--project", str(root), "--digest", digest])
    assert checked["ok"] and checked["market_benchmark"]["profile_sha256"]


def test_benchmark_file_drift_blocks_proposal_acceptance(tmp_path, monkeypatch):
    root = _workspace(tmp_path)
    profile = _write(root)
    async def infer(prompt):
        return json.dumps({
            "kind":"asset","slug":"sprite","title":"Sprite","summary":"New character",
            "body":"Create original high-readability art", "rationale":"Clear visual language",
        }), {"provider":"fixture","model":"fixture","request_id":None}
    monkeypatch.setattr(authoring, "_infer", infer)
    result = run_game_cli(["jeeves", "propose", "--project", str(root),
                           "--kind", "asset", "--brief", "original character",
                           "--console", "PC", "--genre", "RPG", "--period", "2015-2019"])
    assert result["ok"], result
    old = json.loads(profile.read_text())
    old["cohorts"][0]["records"][0]["sales_units"] += 100
    profile.write_text(json.dumps(old))
    reviewed = run_game_cli(["jeeves", "review", "--project", str(root),
                             "--digest", result["proposal_sha256"]])
    assert not reviewed["ok"]


def test_symlink_market_evidence_cannot_escape_workspace(tmp_path):
    root = _workspace(tmp_path)
    outside = tmp_path / "market.json"
    outside.write_text(json.dumps({"schema": SCHEMA, "cohorts": []}))
    (root / "design" / "market_benchmarks.json").symlink_to(outside)
    assert not _rank(root)["ok"]


def test_render_gate_requires_actual_file_hash_and_distinct_reviewers(tmp_path):
    root = _workspace(tmp_path)
    _write(root)
    target = root / "assets" / "original-texture.png"
    target.write_bytes(b"demo-fixture-pixel-data")
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    scores = {
        "silhouette":94, "readability":94, "era_fidelity":93,
        "material_detail":91, "art_direction":95, "accessibility":94,
        "originality":92,
    }
    path = root / "design" / "asset_qa.json"
    receipt = {
        "schema": ASSET_SCHEMA, "kind": "asset",
        "asset_path": "assets/original-texture.png", "sha256": digest,
        "originality": "original", "qa_scores": scores,
        "reviewers": ["Reviewer A", "Reviewer B"],
        "performance": {"measured_ms": 1.0, "budget_ms": 2.0, "platform": "PC"},
    }
    path.write_text(json.dumps(receipt))
    def gate():
        return run_game_cli(["jeeves", "asset-gate", "--project", str(root),
                             "--console", "PC", "--genre", "RPG", "--period", "2015-2019",
                             "--evidence", "design/asset_qa.json"])
    first = gate()
    assert first["ok"] and first["static_checks_passed"]
    assert first["peak_quality_proven"] is False
    assert first["performance_measurement_independently_verified"] is False
    receipt["reviewers"] = ["Reviewer A", "Reviewer A"]
    path.write_text(json.dumps(receipt))
    assert not gate()["ok"]
    receipt["reviewers"] = ["Reviewer A", "Reviewer B"]
    receipt["qa_scores"]["silhouette"] = 89
    path.write_text(json.dumps(receipt))
    assert not gate()["ok"]
    receipt["qa_scores"]["silhouette"] = 95
    receipt["performance"]["measured_ms"] = 3.0
    path.write_text(json.dumps(receipt))
    assert not gate()["ok"]
    receipt["performance"]["measured_ms"] = 1.0
    target.write_bytes(b"tampered")
    path.write_text(json.dumps(receipt))
    assert not gate()["ok"]
