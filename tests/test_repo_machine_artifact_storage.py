from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "repo-machine-index.yml"
GITIGNORE = ROOT / ".gitignore"

UPLOAD_ARTIFACT_PIN = "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a"
GENERATED_INDEXES = {
    "/.machine/repository-machine.json",
    "/.machine/code-search-index.json",
    "/.machine/index-artifact-manifest.json",
}


def test_repo_machine_indexes_publish_outside_source_git() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert UPLOAD_ARTIFACT_PIN in workflow
    assert "contents: write" not in workflow
    assert "gh api --method PATCH" not in workflow
    assert "ref: main" not in workflow
    assert ".machine/repository-machine.json" in workflow
    assert ".machine/code-search-index.json" in workflow
    assert ".machine/index-artifact-manifest.json" in workflow
    assert "skeleton.repository-machine-artifact.v1" in workflow
    assert '"source_commit": checked_out_sha' in workflow
    assert '"repository_fingerprint": manifest["fingerprint"]' in workflow
    assert "artifact source mismatch" in workflow
    assert "include-hidden-files: true" in workflow
    assert "if-no-files-found: error" in workflow


def test_repo_machine_ignores_only_generated_snapshots() -> None:
    ignored = {
        line.strip()
        for line in GITIGNORE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    assert GENERATED_INDEXES <= ignored
    assert "/.machine/" not in ignored
    assert "/.machine/README.md" not in ignored
    assert "/.machine/repository.toml" not in ignored
