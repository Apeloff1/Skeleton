from __future__ import annotations

import json
from pathlib import Path

from scripts.verify_repository_intelligence_closure import (
    CANONICAL_EXTRACTOR,
    CANONICAL_GRAPH,
    CANONICAL_PLANNER,
    EXPECTED_CHANGED,
    EXPECTED_EDGES,
    EXPECTED_IMPACT,
    EXPECTED_OWNERS,
    EXPECTED_TESTS,
    EXTRACTION_TEST,
    GIT_INDEX_TEST,
    GRAPH_TEST,
    MIRROR_EXTRACTOR,
    MIRROR_GRAPH,
    MIRROR_PLANNER,
    WORKFLOW,
    _expected_graph_digest,
    verify_repository,
)


def _behavior() -> dict[str, object]:
    return {
        "graph_digest": _expected_graph_digest(),
        "edges": [list(edge) for edge in EXPECTED_EDGES],
        "changed_paths": list(EXPECTED_CHANGED),
        "impacted_paths": list(EXPECTED_IMPACT),
        "required_tests": list(EXPECTED_TESTS),
        "owners": list(EXPECTED_OWNERS),
        "authority_scope": "change-plan-only",
    }


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _valid_repo(tmp_path: Path) -> Path:
    graph = "\n".join(
        (
            "from skeleton.contracts.canonical import canonical_json_bytes",
            "class FileNode: pass",
            "class DependencyEdge: pass",
            "class RepositoryGraph: pass",
            "def impact(self): pass",
            "def tests_for(self): pass",
            "def owners_for(self): pass",
        )
    ) + "\n"
    extractor = "\n".join(
        (
            "class SourceFile: pass",
            "def build_repository_graph(): pass",
            '# "python"',
            '# "typescript"',
            '# "javascript"',
            '# "java"',
            '# "rust"',
            '# "go"',
        )
    ) + "\n"
    planner = "\n".join(
        (
            "class ChangePlan: pass",
            "def plan_change(): pass",
            '# authority_scope:str="change-plan-only"',
        )
    ) + "\n"

    for canonical, mirror, content in (
        (CANONICAL_GRAPH, MIRROR_GRAPH, graph),
        (CANONICAL_EXTRACTOR, MIRROR_EXTRACTOR, extractor),
        (CANONICAL_PLANNER, MIRROR_PLANNER, planner),
    ):
        _write(tmp_path / canonical, content)
        _write(tmp_path / mirror, content)

    for relative in (GRAPH_TEST, EXTRACTION_TEST, GIT_INDEX_TEST):
        _write(tmp_path / relative, "# focused test boundary\n")

    _write(
        tmp_path / WORKFLOW,
        "\n".join(
            (
                CANONICAL_GRAPH,
                MIRROR_GRAPH,
                CANONICAL_EXTRACTOR,
                MIRROR_EXTRACTOR,
                CANONICAL_PLANNER,
                MIRROR_PLANNER,
                GRAPH_TEST,
                EXTRACTION_TEST,
                GIT_INDEX_TEST,
                "scripts/verify_repository_intelligence_closure.py",
                "tests/test_repository_intelligence_independent_verifier.py",
            )
        )
        + "\n",
    )

    _write(
        tmp_path / "machine/ai_master_plan.json",
        json.dumps(
            {
                "volumes": [
                    {
                        "key": "VOL-021",
                        "requirements": [
                            "Build repository intelligence from files and imports.",
                            "Track index freshness and provenance.",
                            "Provide impact queries without false certainty.",
                        ],
                        "capabilities": [
                            "repository graph",
                            "symbol search",
                            "impact analysis",
                        ],
                        "gaps": [
                            "independent cross-language repository-graph, ownership/test impact, and change-planner verification remains pending"
                        ],
                    }
                ]
            }
        ),
    )
    return tmp_path


def test_independent_repository_intelligence_verifier_accepts_exact_contract(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = _valid_repo(tmp_path)
    monkeypatch.setenv("GITHUB_SHA", "repo-intel-head")

    receipt = verify_repository(root, behavior=_behavior())

    assert receipt["valid"] is True
    assert receipt["errors"] == []
    assert receipt["head_sha"] == "repo-intel-head"
    assert receipt["fixture"]["authority_scope"] == "change-plan-only"
    assert len(receipt["mirror_digests"]) == 3


def test_verifier_rejects_cross_language_edge_loss(tmp_path: Path) -> None:
    root = _valid_repo(tmp_path)
    behavior = _behavior()
    behavior["edges"] = behavior["edges"][:-1]

    receipt = verify_repository(root, behavior=behavior)

    assert receipt["valid"] is False
    assert any(
        "cross-language dependency graph mismatch" in error
        for error in receipt["errors"]
    )


def test_verifier_rejects_impact_test_and_owner_drift(tmp_path: Path) -> None:
    root = _valid_repo(tmp_path)
    behavior = _behavior()
    behavior["impacted_paths"] = ["pkg/core.py"]
    behavior["required_tests"] = []
    behavior["owners"] = ["core"]

    receipt = verify_repository(root, behavior=behavior)

    assert receipt["valid"] is False
    assert any("impacted_paths mismatch" in error for error in receipt["errors"])
    assert any("required_tests mismatch" in error for error in receipt["errors"])
    assert any("owners mismatch" in error for error in receipt["errors"])


def test_verifier_rejects_change_plan_authority_escalation(tmp_path: Path) -> None:
    root = _valid_repo(tmp_path)
    behavior = _behavior()
    behavior["authority_scope"] = "mutation-authority"

    receipt = verify_repository(root, behavior=behavior)

    assert receipt["valid"] is False
    assert any(
        "widened mutation authority" in error
        for error in receipt["errors"]
    )


def test_verifier_rejects_graph_mirror_drift(tmp_path: Path) -> None:
    root = _valid_repo(tmp_path)
    _write(tmp_path / MIRROR_GRAPH, "# drift\n")

    receipt = verify_repository(root, behavior=_behavior())

    assert receipt["valid"] is False
    assert any("canonical AI mirror drift" in error for error in receipt["errors"])


def test_verifier_rejects_private_graph_serializer_regression(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    graph = (root / CANONICAL_GRAPH).read_text(encoding="utf-8")
    graph = graph.replace(
        "from skeleton.contracts.canonical import canonical_json_bytes",
        "import json\n# canonical_json_bytes",
    )
    graph += "x = json.dumps({})\n"
    _write(root / CANONICAL_GRAPH, graph)
    _write(root / MIRROR_GRAPH, graph)

    receipt = verify_repository(root, behavior=_behavior())

    assert receipt["valid"] is False
    assert any("private JSON identity serializer" in error for error in receipt["errors"])


def test_verifier_rejects_masterplan_contract_drift(tmp_path: Path) -> None:
    root = _valid_repo(tmp_path)
    plan_path = root / "machine/ai_master_plan.json"
    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    payload["volumes"][0]["capabilities"] = ["repository graph"]
    plan_path.write_text(json.dumps(payload), encoding="utf-8")

    receipt = verify_repository(root, behavior=_behavior())

    assert receipt["valid"] is False
    assert any("VOL-021 capability drift" in error for error in receipt["errors"])


def test_verifier_rejects_noncanonical_graph_identity(tmp_path: Path) -> None:
    root = _valid_repo(tmp_path)
    behavior = _behavior()
    behavior["graph_digest"] = "0" * 64

    receipt = verify_repository(root, behavior=behavior)

    assert receipt["valid"] is False
    assert any("shared-canonical identity" in error for error in receipt["errors"])


def test_verifier_rejects_workflow_coverage_loss(tmp_path: Path) -> None:
    root = _valid_repo(tmp_path)
    workflow = root / WORKFLOW
    workflow.write_text(
        workflow.read_text(encoding="utf-8").replace(
            GIT_INDEX_TEST + "\n",
            "",
        ),
        encoding="utf-8",
    )

    receipt = verify_repository(root, behavior=_behavior())

    assert receipt["valid"] is False
    assert any(
        "lost repository-intelligence coverage" in error
        and GIT_INDEX_TEST in error
        for error in receipt["errors"]
    )
