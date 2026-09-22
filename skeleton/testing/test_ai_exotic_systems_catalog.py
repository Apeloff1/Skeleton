from __future__ import annotations

import json

from scripts import check_ai_exotic_systems_catalog as checker


def test_exotic_systems_catalog_passes_validator() -> None:
    assert checker.validate() == []


def test_exotic_candidates_are_breadth_frozen_and_fallback_safe() -> None:
    data = json.loads(checker.CATALOG.read_text(encoding="utf-8"))
    master = json.loads(checker.MASTER.read_text(encoding="utf-8"))
    valid_volumes = {v["id"] for v in master["volumes"]}
    valid_wps = set(master["p0_work_packages"])

    assert len(data["entries"]) >= 60
    assert len({e["category"] for e in data["entries"]}) >= 12
    assert data["breadth_freeze_compatible"] is True
    assert all(e["production_authority"] is False for e in data["entries"])
    assert all(e["mapped_volumes"] for e in data["entries"])
    assert all(set(e["mapped_volumes"]) <= valid_volumes for e in data["entries"])
    assert all(e["work_package_refs"] for e in data["entries"])
    assert all(set(e["work_package_refs"]) <= valid_wps for e in data["entries"])
    assert all(e["kill_switch"].strip() for e in data["entries"])
    assert all(e["fallback"].strip() for e in data["entries"])
    assert all(len(e["required_evidence"]) >= 2 for e in data["entries"])
