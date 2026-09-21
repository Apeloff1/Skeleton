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
