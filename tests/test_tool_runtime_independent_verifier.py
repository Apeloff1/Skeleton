from __future__ import annotations

import json
from pathlib import Path

from scripts.verify_tool_runtime_closure import (
    BOUNDARIES,
    EXPECTED_DEPENDENCIES,
    MIRROR_PAIRS,
    verify_repository,
)


def _write_handoff(root: Path) -> None:
    machine = root / "machine"
    machine.mkdir(parents=True, exist_ok=True)
    payload = {
        "entries": [
            {
                "gap": "gap-tool-runtime-convergence",
                "depends_on": sorted(EXPECTED_DEPENDENCIES),
                "closure_gate": (
                    "every model-callable tool is declared, minimally projected, "
                    "policy-admitted, idempotency-aware and receipt-backed, with "
                    "no executable shadow registry or nested provider credential path"
                ),
            }
        ]
    }
    (machine / "ai_implementation_handoff.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )


def _valid_repo(tmp_path: Path) -> Path:
    root = tmp_path
    for rel, tokens in BOUNDARIES.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join(f"# {token}" for token in tokens) + "\n",
            encoding="utf-8",
        )

    for source_rel, mirror_rel in MIRROR_PAIRS:
        source = root / source_rel
        mirror = root / mirror_rel
        mirror.parent.mkdir(parents=True, exist_ok=True)
        mirror.write_bytes(source.read_bytes())

    _write_handoff(root)
    return root


def test_independent_tool_runtime_verifier_accepts_canonical_boundaries(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = _valid_repo(tmp_path)
    monkeypatch.setenv("GITHUB_SHA", "tool-head")

    receipt = verify_repository(root)

    assert receipt["valid"] is True
    assert receipt["errors"] == []
    assert receipt["head_sha"] == "tool-head"
    assert len(receipt["boundary_digests"]) == len(BOUNDARIES)
    assert len(receipt["mirror_pairs"]) == len(MIRROR_PAIRS)
    assert set(receipt["dependency_graph"]) == EXPECTED_DEPENDENCIES


def test_independent_tool_runtime_verifier_rejects_privileged_registry_drift(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    registry = root / "backend" / "services" / "tool_registry.py"
    registry.write_text(
        registry.read_text(encoding="utf-8")
        + "\nimport subprocess\n",
        encoding="utf-8",
    )

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "backend tool registry regained privileged execution body: import subprocess"
        in error
        for error in receipt["errors"]
    )


def test_independent_tool_runtime_verifier_rejects_lineage_contract_loss(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    contract = root / "skeleton" / "skills" / "tool_contract.py"
    contract.write_text(
        "# ToolAuthorityClass\n# ToolRiskClass\n",
        encoding="utf-8",
    )

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "skeleton/skills/tool_contract.py lost tool-runtime token: execution_id"
        in error
        for error in receipt["errors"]
    )


def test_independent_tool_runtime_verifier_rejects_dependency_drift(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    handoff_path = root / "machine" / "ai_implementation_handoff.json"
    payload = json.loads(handoff_path.read_text(encoding="utf-8"))
    payload["entries"][0]["depends_on"] = ["gap-cost-admission"]
    handoff_path.write_text(json.dumps(payload), encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "tool-runtime dependency graph mismatch" in error
        for error in receipt["errors"]
    )


def test_independent_tool_runtime_verifier_rejects_ai_mirror_drift(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    mirror = (
        root
        / "skeleton"
        / "ai"
        / "runtime"
        / "skills"
        / "tool_runtime.py"
    )
    mirror.write_text("# drift\n", encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "canonical AI mirror drift: skeleton/skills/tool_runtime.py"
        in error
        for error in receipt["errors"]
    )
