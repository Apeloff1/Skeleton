from __future__ import annotations

import json

from scripts import check_ai_full_edge_case_matrix as checker


def test_full_edge_case_matrix_passes_validator() -> None:
    assert checker.validate() == []


def test_every_catalog_case_has_at_least_one_w00_w30_owner() -> None:
    catalog = json.loads(checker.CATALOG.read_text(encoding="utf-8"))
    matrix = json.loads(checker.FULL.read_text(encoding="utf-8"))
    owners: dict[str, set[str]] = {e["id"]: set() for e in catalog["entries"]}
    for pkg in matrix["packages"]:
        for entry_id in pkg["historical_ids"] + pkg["edge_case_ids"] + pkg["obscure_ids"]:
            owners[entry_id].add(pkg["id"])
    assert all(owners.values())
    assert len(matrix["packages"]) == 31
    assert matrix["coverage"]["orphan_total"] == 0


def test_critical_and_high_cases_have_executable_evidence_modes() -> None:
    catalog = json.loads(checker.CATALOG.read_text(encoding="utf-8"))
    concrete = [
        e for e in catalog["entries"]
        if e["criticality"] in {"critical", "high"} and e["type"] != "historical"
    ]
    assert concrete
    assert all(set(e["recommended_test_modes"]) - {"design_review"} for e in concrete)


def test_build_queue_inherits_full_program_risk_counts() -> None:
    queue = json.loads(checker.QUEUE.read_text(encoding="utf-8"))
    assert queue["tasks"]
    for task in queue["tasks"]:
        assert "full_program_edge_case_matrix" in task["acceptance_overlays"]
        stats = task["edge_case_inheritance"]
        assert stats["catalog_total"] > 0
        assert stats["critical"] >= 0
        assert stats["high"] >= 0


def test_priority_queue_exactly_matches_critical_and_high_catalog() -> None:
    catalog = json.loads(checker.CATALOG.read_text(encoding="utf-8"))
    priority = json.loads(checker.PRIORITY.read_text(encoding="utf-8"))
    expected = {
        e["id"] for e in catalog["entries"]
        if e["criticality"] in {"critical", "high"}
    }
    actual = {item["id"] for item in priority["items"]}
    assert actual == expected
    assert priority["counts"]["total"] == len(expected)
    assert priority["counts"]["P0"] == sum(
        e["criticality"] == "critical" for e in catalog["entries"]
    )
    assert priority["counts"]["P1"] == sum(
        e["criticality"] == "high" for e in catalog["entries"]
    )


def test_full_edge_case_matrix_main_success_path() -> None:
    assert checker.main() == 0
