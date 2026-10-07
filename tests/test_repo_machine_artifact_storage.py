from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "repo-machine-index.yml"
GITIGNORE = ROOT / ".gitignore"

UPLOAD_ARTIFACT_PIN = "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a"


def test_repo_machine_indexes_publish_outside_source_git() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert UPLOAD_ARTIFACT_PIN in workflow
    assert "contents: write" not in workflow
    assert "gh api --method PATCH" not in workflow
    assert ".machine/repository-machine.json" in workflow
    assert ".machine/code-search-index.json" in workflow
    assert "include-hidden-files: true" in workflow
    assert "if-no-files-found: error" in workflow


def test_repo_machine_generated_directory_is_ignored() -> None:
    ignored = {
        line.strip()
        for line in GITIGNORE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    assert "/.machine/" in ignored
