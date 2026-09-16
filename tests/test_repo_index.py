from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import repo_index  # noqa: E402
import repo_intel_supply_chain as supply  # noqa: E402


def test_requirements_parser_extracts_names_and_specs() -> None:
    deps = supply.parse_requirements(
        "requirements.txt",
        "# comment\nfastapi==1.2.3\nuvicorn[standard]>=0.30\n-r other.txt\n",
    )
    assert [(d["name"], d["spec"]) for d in deps] == [
        ("fastapi", "==1.2.3"),
        ("uvicorn", "[standard]>=0.30"),
    ]
    assert all(d["ecosystem"] == "pypi" for d in deps)


def test_pyproject_parser_separates_runtime_optional_and_build() -> None:
    deps = supply.parse_pyproject(
        "pyproject.toml",
        """
[build-system]
requires = ["setuptools==80"]
[project]
dependencies = ["fastapi>=0.100"]
[project.optional-dependencies]
dev = ["pytest>=8"]
""",
    )
    by_name = {d["name"]: d for d in deps}
    assert by_name["fastapi"]["scope"] == "runtime"
    assert by_name["pytest"]["scope"] == "optional:dev"
    assert by_name["setuptools"]["scope"] == "build"


def test_package_json_parser_indexes_runtime_dev_and_resolution() -> None:
    deps = supply.parse_package_json(
        "frontend/package.json",
        json.dumps({
            "dependencies": {"react": "19.1.0"},
            "devDependencies": {"typescript": "~5.9.3"},
            "resolutions": {"tar": "7.5.21"},
        }),
    )
    by_name = {d["name"]: d for d in deps}
    assert by_name["react"]["scope"] == "runtime"
    assert by_name["typescript"]["scope"] == "development"
    assert by_name["tar"]["scope"] == "resolution"


def test_docker_and_workflow_dependencies_are_manifest_precision_inputs() -> None:
    docker = supply.parse_dockerfile("Dockerfile", "FROM python:3.11-slim\nFROM scratch\n")
    assert len(docker) == 1
    assert docker[0]["ecosystem"] == "oci"
    assert docker[0]["name"] == "python"

    actions = supply.parse_workflow_actions(
        ".github/workflows/ci.yml",
        "steps:\n  - uses: actions/checkout@abc123\n  - uses: ./local-action\n",
    )
    assert actions == [{
        "ecosystem": "github-actions",
        "name": "actions/checkout",
        "spec": "@abc123",
        "scope": "workflow-action",
        "source": ".github/workflows/ci.yml",
        "id": "dependency:github-actions:actions/checkout",
    }]


def test_supply_chain_graph_deduplicates_components_but_keeps_declarations(monkeypatch) -> None:
    monkeypatch.setattr(
        supply,
        "dependency_records",
        lambda _files: [
            {"ecosystem": "pypi", "name": "fastapi", "spec": ">=1", "scope": "runtime", "source": "pyproject.toml", "id": "dependency:pypi:fastapi"},
            {"ecosystem": "pypi", "name": "fastapi", "spec": "==1.2", "scope": "runtime", "source": "backend/requirements.txt", "id": "dependency:pypi:fastapi"},
        ],
    )
    graph = supply.supply_chain_graph([])
    assert graph["component_count"] == 1
    assert graph["declaration_count"] == 2
    assert graph["nodes"][0]["sources"] == ["backend/requirements.txt", "pyproject.toml"]


def test_codeowners_parser_keeps_last_match_capable_rule_order() -> None:
    rules = supply.parse_codeowners(
        ".github/CODEOWNERS",
        "# owner\n* @all\n/backend/ @backend @security\n",
    )
    assert rules == [
        {"pattern": "*", "owners": ["@all"], "line": 2},
        {"pattern": "/backend/", "owners": ["@backend", "@security"], "line": 3},
    ]


def test_boundary_detector_reports_forbidden_cross_subsystem_import() -> None:
    snapshot = {
        "files": [
            {"path": "skeleton/core.py", "subsystem": "skeleton"},
            {"path": "backend/service.py", "subsystem": "backend"},
        ],
        "graph": {
            "edges": [
                {"from": "file:skeleton/core.py", "to": "file:backend/service.py", "type": "imports", "precision": "ast"}
            ]
        },
    }
    rules = {
        "rules": [{
            "id": "core",
            "from_subsystems": ["skeleton"],
            "deny_to_subsystems": ["backend"],
            "edge_types": ["imports"],
            "severity": "high",
            "reason": "core isolation",
        }]
    }
    violations = supply.boundary_violations(snapshot, rules)
    assert violations == [{
        "rule": "core",
        "severity": "high",
        "source": "skeleton/core.py",
        "target": "backend/service.py",
        "edge_type": "imports",
        "precision": "ast",
        "reason": "core isolation",
    }]


def test_graph_adjacency_supports_external_dependencies() -> None:
    snapshot = {
        "graph": {
            "edges": [
                {"from": "file:pyproject.toml", "to": "dependency:pypi:fastapi", "type": "declares-dependency", "precision": "manifest"}
            ]
        }
    }
    adjacency = repo_index.graph_adjacency(snapshot, {"declares-dependency"})
    assert adjacency["file:pyproject.toml"][0]["node"] == "dependency:pypi:fastapi"
    assert adjacency["file:pyproject.toml"][0]["precision"] == "manifest"


def test_traverse_can_be_direct_or_transitive() -> None:
    adjacency = {
        "file:a": [{"node": "file:b", "type": "imports", "precision": "ast"}],
        "file:b": [{"node": "file:c", "type": "imports", "precision": "ast"}],
    }
    direct = repo_index.traverse(adjacency, "file:a", False)
    transitive = repo_index.traverse(adjacency, "file:a", True)
    assert [x["node"] for x in direct] == ["file:b"]
    assert [x["node"] for x in transitive] == ["file:b", "file:c"]


def test_boundary_contract_is_machine_validatable() -> None:
    payload = json.loads((ROOT / "repo-intel" / "boundaries.json").read_text(encoding="utf-8"))
    ids = [rule["id"] for rule in payload["rules"]]
    assert len(ids) == len(set(ids))
    assert all(rule["from_subsystems"] for rule in payload["rules"])
    assert all(rule["deny_to_subsystems"] for rule in payload["rules"])


def test_canonical_cli_contract_validation_passes() -> None:
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "repo_index.py"), "check"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "contracts valid" in proc.stdout
