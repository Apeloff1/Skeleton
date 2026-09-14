from __future__ import annotations

from pathlib import Path

from scripts.check_artifact_policy import MODEL_LFS_PATTERNS, attribute_violations, tracked_path_violations


def test_artifact_policy_requires_all_model_lfs_rules(tmp_path: Path) -> None:
    attributes = tmp_path / ".gitattributes"
    attributes.write_text("*.safetensors filter=lfs diff=lfs merge=lfs -text\n", encoding="utf-8")
    findings = attribute_violations(attributes)
    assert len(findings) == len(MODEL_LFS_PATTERNS) - 1
    assert any("*.gguf" in finding for finding in findings)


def test_artifact_policy_accepts_complete_lfs_rules(tmp_path: Path) -> None:
    attributes = tmp_path / ".gitattributes"
    attributes.write_text(
        "\n".join(f"{pattern} filter=lfs diff=lfs merge=lfs -text" for pattern in sorted(MODEL_LFS_PATTERNS)) + "\n",
        encoding="utf-8",
    )
    assert attribute_violations(attributes) == []


def test_artifact_policy_rejects_tracked_caches_and_compiled_python() -> None:
    findings = tracked_path_violations(
        [
            "backend/__pycache__/server.cpython-311.pyc",
            "frontend/node_modules/pkg/index.js",
            "backend/.ruff_cache/state",
            "backend/module.pyo",
        ]
    )
    assert len(findings) == 4


def test_artifact_policy_rejects_os_metadata() -> None:
    findings = tracked_path_violations(["frontend/assets/.DS_Store", "docs/Thumbs.db"])
    assert len(findings) == 2


def test_artifact_policy_allows_normal_source_and_docs() -> None:
    assert tracked_path_violations(["backend/server.py", "frontend/package.json", "docs/README.md"]) == []
