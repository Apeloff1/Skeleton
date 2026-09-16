from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import repo_intel_sota as sota  # noqa: E402


def test_python_semantics_are_ast_derived() -> None:
    record = sota._extract_python(
        "pkg/example.py",
        "import os\nfrom pkg import helper\n\nclass Forge:\n    def build(self):\n        return 1\n\ndef test_contract():\n    assert True\n",
    )
    names = {item["qualified_name"] for item in record["symbols"]}
    modules = {item["module"] for item in record["imports"]}
    assert record["precision"] == "ast"
    assert record["parse_error"] is None
    assert {"Forge", "Forge.build", "test_contract"}.issubset(names)
    assert {"os", "pkg"}.issubset(modules)
    assert "test_contract" in record["tests"]


def test_python_parse_failure_is_explicit_not_silent() -> None:
    record = sota._extract_python("broken.py", "def nope(:\n")
    assert record["parse_error"]
    assert record["symbols"] == []


def test_js_semantics_mark_lexical_precision() -> None:
    record = sota._extract_js(
        "frontend/a.ts",
        "import {b} from './b';\nexport class Alpha {}\nexport const beta = 1;\n",
    )
    assert record["precision"] == "lexical"
    assert record["imports"] == [{"module": "./b", "level": 0, "precision": "lexical"}]
    assert {s["name"] for s in record["symbols"]} == {"Alpha", "beta"}


def test_python_local_import_resolution_prefers_repo_modules() -> None:
    modules = {
        "backend.gameforge": "backend/gameforge/__init__.py",
        "backend.gameforge.engine": "backend/gameforge/engine.py",
    }
    target = sota._resolve_python_import(
        "backend/gameforge/api.py",
        {"module": "backend.gameforge.engine", "level": 0, "precision": "ast"},
        modules,
    )
    assert target == "backend/gameforge/engine.py"


def test_js_relative_resolution_checks_extensions_and_index() -> None:
    paths = {"frontend/lib/x.ts", "frontend/widgets/index.tsx"}
    assert sota._resolve_js_import("frontend/app/main.ts", "../lib/x", paths) == "frontend/lib/x.ts"
    assert sota._resolve_js_import("frontend/app/main.ts", "../widgets", paths) == "frontend/widgets/index.tsx"
    assert sota._resolve_js_import("frontend/app/main.ts", "react", paths) is None


def test_reverse_graph_preserves_edge_precision() -> None:
    reverse = sota._reverse_edges([
        {"from": "file:a.py", "to": "file:b.py", "type": "imports", "precision": "ast"},
        {"from": "file:t.py", "to": "file:b.py", "type": "tests", "precision": "structural"},
    ])
    assert reverse["file:b.py"] == [
        {"from": "file:a.py", "type": "imports", "precision": "ast"},
        {"from": "file:t.py", "type": "tests", "precision": "structural"},
    ]


def test_dependency_cycle_detection_finds_strong_component() -> None:
    edges = [
        {"from": "file:a.py", "to": "file:b.py", "type": "imports"},
        {"from": "file:b.py", "to": "file:c.py", "type": "imports"},
        {"from": "file:c.py", "to": "file:a.py", "type": "imports"},
        {"from": "file:d.py", "to": "file:a.py", "type": "imports"},
    ]
    assert sota._dependency_cycles(edges) == [["a.py", "b.py", "c.py"]]


def test_ownership_uses_most_specific_prefix() -> None:
    ownership = {
        "zones": [
            {"id": "backend", "risk": "high", "prefixes": ["backend/"]},
            {"id": "game", "risk": "critical", "prefixes": ["backend/gameforge/"]},
        ]
    }
    assert sota._owner_for("backend/gameforge/core.py", ownership) == {"id": "game", "risk": "critical"}


def test_impact_traverses_reverse_dependencies_and_surfaces_tests(monkeypatch) -> None:
    snapshot = {
        "files": [
            {"path": "core.py", "subsystem": "core", "flags": {"test": False, "workflow": False}, "owner": {"id": "core-runtime", "risk": "high"}},
            {"path": "consumer.py", "subsystem": "core", "flags": {"test": False, "workflow": False}, "owner": {"id": "core-runtime", "risk": "high"}},
            {"path": "tests/test_core.py", "subsystem": "tests", "flags": {"test": True, "workflow": False}, "owner": {"id": "tests", "risk": "medium"}},
        ],
        "graph": {
            "reverse_edges": {
                "file:core.py": [{"from": "file:consumer.py", "type": "imports", "precision": "ast"}],
                "file:consumer.py": [{"from": "file:tests/test_core.py", "type": "imports", "precision": "ast"}],
            }
        },
    }
    monkeypatch.setattr(sota.base, "feature_gaps", lambda _snapshot: {"capabilities": []})
    impact = sota._impact_from_paths(snapshot, ["core.py"])
    assert impact["affected_files"] == ["consumer.py", "core.py", "tests/test_core.py"]
    assert impact["candidate_tests"] == ["tests/test_core.py"]
    assert impact["subsystems"] == ["core", "tests"]
    assert impact["security_zones"] == ["core-runtime"]


def test_all_extended_contracts_are_valid_json() -> None:
    names = [
        "ownership.json",
        "query-contract.json",
        "quality-budgets.json",
        "index-schema.json",
        "export-contract.json",
        "telemetry-contract.json",
        "precision-policy.json",
        "evidence-levels.json",
    ]
    for name in names:
        payload = json.loads((ROOT / "repo-intel" / name).read_text(encoding="utf-8"))
        assert payload["schema"] >= 1 or "$schema" in payload


def test_quality_budgets_are_targets_not_claims() -> None:
    payload = json.loads((ROOT / "repo-intel" / "quality-budgets.json").read_text(encoding="utf-8"))
    assert "not achieved-performance claims" in payload["note"]
    assert 0 < payload["index_performance_targets"]["cache_hit_ratio_target"] <= 1


def test_query_contract_has_bidirectional_dependency_queries() -> None:
    payload = json.loads((ROOT / "repo-intel" / "query-contract.json").read_text(encoding="utf-8"))
    assert {"deps", "rdeps", "impact", "file", "symbol"}.issubset(payload["queries"])
    assert "imports" in payload["edge_types"]
