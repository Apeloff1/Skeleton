from __future__ import annotations

import json
from collections import Counter

from scripts import check_ai_edge_case_catalog as checker


def test_edge_case_catalog_passes_validator() -> None:
    assert checker.validate() == []


def test_edge_case_catalog_has_required_depth_and_valid_volume_links() -> None:
    data = json.loads(checker.CATALOG.read_text(encoding="utf-8"))
    master = json.loads(checker.MASTER.read_text(encoding="utf-8"))
    valid_volumes = {v["id"] for v in master["volumes"]}
    valid_wps = set(master["p0_work_packages"])
    counts = Counter(e["type"] for e in data["entries"])
    assert counts["historical"] >= 50
    assert counts["edge_case"] >= 100
    assert counts["obscure_pattern"] >= 25
    assert len(data["entries"]) >= 175
    assert all(e["mapped_volumes"] for e in data["entries"])
    assert all(set(e["mapped_volumes"]) <= valid_volumes for e in data["entries"])
    assert all(e["recommended_test_modes"] for e in data["entries"])
    assert all(e["work_package_refs"] for e in data["entries"])
    assert all(set(e["work_package_refs"]) <= valid_wps for e in data["entries"])
