from __future__ import annotations

from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "night-shift.yml"
LEGACY_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "night-shift-bots.yml"
SCRIPT = REPO_ROOT / "skeleton" / "automation" / "night_shift.py"


def test_night_shift_has_one_canonical_scheduler() -> None:
    assert WORKFLOW.is_file()
    assert not LEGACY_WORKFLOW.exists()


def test_night_shift_workflow_bypasses_root_package_imports() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    # This scheduled runner intentionally installs no project dependencies.
    # Executing with `-m skeleton...` imports skeleton/__init__.py first and
    # can pull dependency-bearing subsystems into this lightweight job.
    assert "run: python skeleton/automation/night_shift.py" in text
    assert "python -m skeleton.automation.night_shift" not in text


def test_night_shift_script_starts_as_a_standalone_stdlib_entrypoint() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "--repo" in completed.stdout


def test_night_shift_report_reuses_closed_machine_ledger() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert '"--state", "all"' in text
    assert '"--search", f"{title} in:title"' in text
    assert 'str(item.get("title", "")) == title' in text
    assert '"api", "--method", "PATCH"' in text
    assert '"-f", "state=closed"' in text
    assert "updated the closed report ledger" in text
    assert "created and closed the report ledger" in text


def test_new_night_report_closes_identity_returned_by_create() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert "def create_issue(self, title: str, body: str, labels: Sequence[str]) -> int:" in text
    assert 'created.rstrip("/").rsplit("/", 1)[-1]' in text
    assert "created_number = gh.create_issue(title, body, ())" in text
    assert "gh.close_issue(created_number)" in text
    assert "issue was created but could not be resolved" not in text
