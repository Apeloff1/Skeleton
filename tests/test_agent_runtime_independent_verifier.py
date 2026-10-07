from __future__ import annotations

import json
from pathlib import Path

from scripts.verify_agent_runtime_closure import (
    AUTO02_WORKFLOW,
    CANONICAL,
    FACADE,
    MIRROR,
    REQUIRED_TOKENS,
    RUNTIME_TEST,
    verify_repository,
)


def _write_masterplan(root: Path) -> None:
    machine = root / "machine"
    machine.mkdir(parents=True, exist_ok=True)
    (machine / "ai_master_plan.json").write_text(
        json.dumps(
            {
                "volumes": [
                    {
                        "key": "VOL-016",
                        "requirements": [
                            "Define agent identity and bounded runtime authority.",
                            "Require delegated authority to remain a subset.",
                            "Persist lifecycle checkpoint state for recovery.",
                        ],
                        "capabilities": [
                            "agent lifecycle",
                            "delegation",
                            "agent checkpointing",
                        ],
                        "gaps": [
                            "durable agent supervisor needs implementation",
                            "agent resource accounting needs convergence",
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def _valid_repo(tmp_path: Path) -> Path:
    root = tmp_path
    canonical = root / CANONICAL
    canonical.parent.mkdir(parents=True, exist_ok=True)
    canonical.write_text(
        "\n".join(f"# {token}" for token in REQUIRED_TOKENS) + "\n",
        encoding="utf-8",
    )

    mirror = root / MIRROR
    mirror.parent.mkdir(parents=True, exist_ok=True)
    mirror.write_bytes(canonical.read_bytes())

    facade = root / FACADE
    facade.parent.mkdir(parents=True, exist_ok=True)
    facade.write_text(
        "from skeleton.automation.agents.agent_runtime import *  # noqa: F401,F403\n",
        encoding="utf-8",
    )

    runtime_test = root / RUNTIME_TEST
    runtime_test.parent.mkdir(parents=True, exist_ok=True)
    runtime_test.write_text("# durable runtime tests\n", encoding="utf-8")

    workflow = root / AUTO02_WORKFLOW
    workflow.parent.mkdir(parents=True, exist_ok=True)
    workflow.write_text(
        "\n".join(
            (
                "skeleton/automation/agents/agent_runtime.py",
                "skeleton/ai/agents/core/agent_runtime.py",
                "skeleton/testing/test_agent_runtime_durable.py",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    _write_masterplan(root)
    return root


def test_independent_agent_runtime_verifier_accepts_boundaries(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = _valid_repo(tmp_path)
    monkeypatch.setenv("GITHUB_SHA", "agent-head")

    receipt = verify_repository(root)

    assert receipt["valid"] is True
    assert receipt["errors"] == []
    assert receipt["head_sha"] == "agent-head"
    assert receipt["canonical_digest"] == receipt["mirror_digest"]
    assert len(receipt["boundary_digests"]) == 5


def test_independent_agent_runtime_verifier_rejects_missing_durability_token(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    canonical = root / CANONICAL
    canonical.write_text(
        canonical.read_text(encoding="utf-8").replace(
            "# checkpoint_digest\n",
            "",
        ),
        encoding="utf-8",
    )
    (root / MIRROR).write_bytes(canonical.read_bytes())

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "lost durable runtime token: checkpoint_digest" in error
        for error in receipt["errors"]
    )


def test_independent_agent_runtime_verifier_rejects_ai_mirror_drift(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    (root / MIRROR).write_text("# mirror drift\n", encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any("canonical AI mirror drift" in error for error in receipt["errors"])


def test_independent_agent_runtime_verifier_rejects_facade_ownership(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    (root / FACADE).write_text(
        "class ShadowSupervisor:\n    pass\n",
        encoding="utf-8",
    )

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "facade does not delegate canonically" in error
        or "facade regained implementation ownership" in error
        for error in receipt["errors"]
    )


def test_independent_agent_runtime_verifier_rejects_workflow_coverage_loss(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    workflow = root / AUTO02_WORKFLOW
    workflow.write_text(
        workflow.read_text(encoding="utf-8").replace(
            "skeleton/testing/test_agent_runtime_durable.py\n",
            "",
        ),
        encoding="utf-8",
    )

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "AUTO-02 workflow does not bind durable agent runtime" in error
        for error in receipt["errors"]
    )


def test_independent_agent_runtime_verifier_rejects_masterplan_contract_drift(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    masterplan = root / "machine" / "ai_master_plan.json"
    payload = json.loads(masterplan.read_text(encoding="utf-8"))
    payload["volumes"][0]["capabilities"] = ["delegation"]
    masterplan.write_text(json.dumps(payload), encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any("VOL-016 capability drift" in error for error in receipt["errors"])
