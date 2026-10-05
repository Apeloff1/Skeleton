from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/p1-world-model-simulation.yml"


def workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_gate_installs_package_runtime_needed_by_skeleton_tests() -> None:
    text = workflow_text()
    assert '"pytest>=8,<9"' in text
    assert '"pydantic>=2.5,<3"' in text
    assert '"pydantic-settings>=2.1,<3"' in text
    assert '"fastapi>=0.110,<1"' in text


def test_gate_keeps_exact_head_checkout_and_no_persisted_credentials() -> None:
    text = workflow_text()
    assert 'ref: ${{ github.event.pull_request.head.sha || github.sha }}' in text
    assert "persist-credentials: false" in text
    assert 'EXPECTED_SHA: "${{ github.event.pull_request.head.sha || github.sha }}"' in text


def test_gate_runs_all_simulation_contract_suites() -> None:
    text = workflow_text()
    assert "skeleton/testing/test_simulation_authority_boundary.py" in text
    assert "skeleton/testing/test_simulation_determinism.py" in text
    assert "skeleton/testing/test_simulation_ecs_world_contracts.py" in text
    assert "tests/test_p1_world_model_simulation_workflow.py" in text
