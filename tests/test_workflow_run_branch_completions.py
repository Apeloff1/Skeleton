from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
ALL_BRANCH_GLOBS = 'branches:\n      - "*"\n      - "**"'


def _read(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def test_workflow_run_consumers_subscribe_to_every_completing_branch() -> None:
    consumers = {
        "pr-automation-index.yml": "types: [completed]",
        "repair-intake.yml": "types: [completed]",
        "idle-studio.yml": "types: [completed]",
        "pr-obsolete-run-drain.yml": "types: [requested]",
    }
    for name, event_type in consumers.items():
        text = _read(name)
        assert "workflow_run:" in text
        assert event_type in text
        assert ALL_BRANCH_GLOBS in text, f"{name} must match every completing head"
        assert "pull_requests[0]" not in text, f"{name} must not treat pull_requests[0] as identity"
    idle = _read("idle-studio.yml")
    assert "github.event.workflow_run.head_repository.full_name == github.repository" in idle
    assert "exceeded bounded identity scan" in idle
    assert 'gh api "/repos/$REPO/actions/runs?per_page=50"' not in idle
    assert r"^[0-9a-f]{40}$" in idle
    repair = _read("repair-intake.yml")
    assert "repair-intake fingerprint search exceeded bounded identity scan" in repair
    assert r"^[0-9a-f]{40}$" in repair
    assert "workflow_run head SHA must be a 40-character hex commit OID" in repair
