from __future__ import annotations

import json

from scripts import check_ai_p0_edge_case_matrix as checker


def test_p0_edge_case_matrix_is_valid() -> None:
    assert checker.validate() == []


def test_p0_edge_case_matrix_covers_w00_through_w11_in_order() -> None:
    data = json.loads(checker.MATRIX.read_text(encoding="utf-8"))
    assert [pkg["id"] for pkg in data["packages"]] == [f"WP-W{i:02d}" for i in range(12)]
    assert data["coverage"]["unique_catalog_ids"] >= 100
    assert all(len(pkg["invariants"]) >= 4 for pkg in data["packages"])
    assert all(len(pkg["test_targets"]) >= 4 for pkg in data["packages"])


def test_atomic_build_queue_inherits_p0_edge_case_overlay() -> None:
    queue = json.loads(checker.BUILD_QUEUE.read_text(encoding="utf-8"))
    master = json.loads(checker.MASTER.read_text(encoding="utf-8"))
    valid_wps = set(master["p0_work_packages"])
    assert queue["acceptance_overlays"]["p0_edge_case_matrix"]["contract"] == (
        "machine/ai_p0_edge_case_matrix.json"
    )
    assert queue["tasks"]
    for task in queue["tasks"]:
        assert task["acceptance_overlay"] == "p0_edge_case_matrix"
        assert task["work_package_refs"]
        assert set(task["work_package_refs"]) <= valid_wps
