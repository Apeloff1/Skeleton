from __future__ import annotations

from pathlib import Path
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from skeleton.developer.commands import ExtensionCommand, WizardCommand
from skeleton.developer.scaffold import ScaffoldEngine


def test_scaffold_rejects_parent_path_traversal(tmp_path: Path) -> None:
    engine = ScaffoldEngine(tmp_path)

    with pytest.raises(ValueError, match="path-safe"):
        engine.scaffold("minimal-agent", "../escape")

    assert not (tmp_path.parent / "escape").exists()


def test_scaffold_rejects_nested_path_name(tmp_path: Path) -> None:
    engine = ScaffoldEngine(tmp_path)

    with pytest.raises(ValueError, match="path-safe"):
        engine.scaffold("minimal-agent", "nested/project")

    assert not (tmp_path / "nested").exists()


def test_scaffold_surface_matches_template_registry_and_validates_output(tmp_path: Path) -> None:
    engine = ScaffoldEngine(tmp_path)

    templates = engine.list_templates()
    assert "minimal-agent" in templates
    assert "api-gateway" in templates

    project = engine.scaffold("minimal-agent", "safe_project")
    validation = engine.validate_project(project)

    assert project == tmp_path.resolve() / "safe_project"
    assert validation["valid"] is True
    assert validation["missing"] == []
    assert (project / "main.py").is_file()
    assert (project / "README.md").is_file()


def test_scaffold_refuses_existing_destination_without_force(tmp_path: Path) -> None:
    engine = ScaffoldEngine(tmp_path)
    engine.scaffold("minimal-agent", "existing")

    with pytest.raises(FileExistsError):
        engine.scaffold("minimal-agent", "existing")


def test_extension_command_rejects_path_like_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = ExtensionCommand()(["../escape"])

    assert "error" in result
    assert not (tmp_path.parent / "escape").exists()
    assert not (tmp_path / "extensions").exists()


def test_extension_command_writes_only_under_extensions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = ExtensionCommand()(["safe_extension", "--type", "tool"])

    destination = tmp_path / "extensions" / "safe_extension"
    assert "error" not in result
    assert Path(result["created_at"]) == Path("extensions") / "safe_extension"
    assert (destination / "safe_extension" / "__init__.py").is_file()
    assert (destination / "tests" / "test_safe_extension.py").is_file()


def test_noninteractive_wizard_uses_canonical_scaffold_imports() -> None:
    plan = WizardCommand()(["--non-interactive"])

    assert plan["template"] == "minimal-agent"
    assert plan["project_name"] == "my-skeleton-project"
    assert plan["target"] == "json"
