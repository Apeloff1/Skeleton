from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import repo_intel_test_evidence as evidence  # noqa: E402


def _snapshot() -> dict:
    return {
        "files": [
            {"path": "pkg/core.py", "role": "python-source", "flags": {"test": False}},
            {"path": "pkg/service.py", "role": "python-source", "flags": {"test": False}},
            {"path": "tests/test_service.py", "role": "python-source", "flags": {"test": True}},
            {"path": "tests/test_core_name.py", "role": "python-source", "flags": {"test": True}},
        ],
        "graph": {
            "edges": [
                {
                    "from": "file:tests/test_service.py",
                    "to": "file:pkg/service.py",
                    "type": "imports",
                    "precision": "ast",
                },
                {
                    "from": "file:pkg/service.py",
                    "to": "file:pkg/core.py",
                    "type": "imports",
                    "precision": "ast",
                },
                {
                    "from": "file:tests/test_core_name.py",
                    "to": "file:pkg/core.py",
                    "type": "tests",
                    "precision": "structural",
                },
            ]
        },
    }


def test_build_ranks_direct_over_transitive_and_preserves_explicit_test_edge() -> None:
    result = evidence.build(_snapshot())
    service = result["by_source"]["pkg/service.py"]
    core = result["by_source"]["pkg/core.py"]
    assert service[0]["test"] == "tests/test_service.py"
    assert service[0]["confidence"] == 0.98
    assert {item["reason"] for item in core} == {"explicit-test-edge", "transitive-test-import"}
    explicit = next(item for item in core if item["reason"] == "explicit-test-edge")
    transitive = next(item for item in core if item["reason"] == "transitive-test-import")
    assert explicit["confidence"] > transitive["confidence"]
    assert result["source_evidence_ratio"] == 1.0


def test_select_for_impact_aggregates_reasons_and_reverse_candidates() -> None:
    test_evidence = evidence.build(_snapshot())
    selected = evidence.select_for_impact(
        {
            "affected_files": ["pkg/core.py", "pkg/service.py"],
            "candidate_tests": ["tests/test_extra.py"],
        },
        test_evidence,
    )
    by_test = {item["test"]: item for item in selected}
    assert by_test["tests/test_service.py"]["confidence"] == 0.98
    assert "pkg/core.py:transitive-test-import:ast:d2" in by_test["tests/test_service.py"]["reasons"]
    assert by_test["tests/test_extra.py"]["confidence"] == 0.75
    assert by_test["tests/test_extra.py"]["reasons"] == ["reverse-impact-candidate"]


def test_contract_is_explicit_about_structural_semantics() -> None:
    evidence.check_contracts()
