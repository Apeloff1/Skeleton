from __future__ import annotations

import json

from scripts import check_ai_master_build_sequence as checker


def test_master_build_sequence_passes_validator() -> None:
    assert checker.validate() == []


def test_every_work_package_has_exactly_one_primary_wave() -> None:
    seq = json.loads(checker.SEQUENCE.read_text(encoding="utf-8"))
    owners: dict[str, list[str]] = {wp: [] for wp in checker.EXPECTED_WPS}
    for wave in seq["waves"]:
        for wp in wave["work_packages"]:
            owners[wp].append(wave["id"])
    assert all(len(v) == 1 for v in owners.values())


def test_wave_dependency_graph_is_acyclic() -> None:
    seq = json.loads(checker.SEQUENCE.read_text(encoding="utf-8"))
    graph = {w["id"]: set(w["hard_dependencies"]) for w in seq["waves"]}
    done: set[str] = set()
    while graph:
        ready = {node for node, deps in graph.items() if deps <= done}
        assert ready
        for node in ready:
            graph.pop(node)
        done |= ready


def test_all_critical_high_risks_have_wave_ownership() -> None:
    seq = json.loads(checker.SEQUENCE.read_text(encoding="utf-8"))
    priority = json.loads(checker.PRIORITY.read_text(encoding="utf-8"))
    wp_to_wave = {
        wp: wave["id"]
        for wave in seq["waves"]
        for wp in wave["work_packages"]
    }
    for item in priority["items"]:
        assert any(wp in wp_to_wave for wp in item["work_package_refs"])


def test_wave_completion_has_no_manual_checkbox() -> None:
    seq = json.loads(checker.SEQUENCE.read_text(encoding="utf-8"))
    forbidden = {"checkbox", "checkbox_mark", "completion_checkbox", "manual_complete"}
    assert seq["completion_semantics"]["mode"] == "derived_from_existing_accountability"
    assert all(not forbidden.intersection(wave) for wave in seq["waves"])


def test_master_build_sequence_main_success_path() -> None:
    assert checker.main() == 0
