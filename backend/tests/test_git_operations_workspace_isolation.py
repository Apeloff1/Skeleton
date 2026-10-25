"""Regression coverage for private, lazy Git-operation workspace allocation (#4133).

The route must never create /app during import, overwrite sentinel files,
or fall back to a shared/predictable directory on read-only installations.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os
import stat
from pathlib import Path

import pytest

from routes import git_operations


@pytest.fixture
def routes(monkeypatch: pytest.MonkeyPatch):
    # A new workspace must be resolved independently for each test.
    monkeypatch.setattr(git_operations, "_workspace_base", None)
    return git_operations


def test_workspace_probe_never_clobbers_existing_sentinel(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, routes
) -> None:
    workspace = tmp_path / "repos"
    workspace.mkdir()
    victim = tmp_path / "important-source.txt"
    victim.write_text("preserve", encoding="utf-8")
    sentinel = workspace / ".writable"
    sentinel.symlink_to(victim)
    monkeypatch.setenv("GIT_WORKSPACE_BASE", str(workspace))

    assert routes.workspace_base() == workspace.resolve()
    assert victim.read_text(encoding="utf-8") == "preserve"
    assert sentinel.is_symlink()
    assert not list(workspace.glob(".writable-*"))


def test_readonly_default_uses_private_unique_fallbacks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, routes
) -> None:
    monkeypatch.delenv("GIT_WORKSPACE_BASE", raising=False)
    monkeypatch.setattr(routes.tempfile, "tempdir", str(tmp_path))
    original_mkdir = Path.mkdir

    def readonly_app(path: Path, *args, **kwargs) -> None:
        if path == Path("/app/backend/.git_workspaces"):
            raise PermissionError("read-only application installation")
        original_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", readonly_app)
    first = routes.workspace_base()
    assert first.parent == tmp_path.resolve()
    assert first.name.startswith("skeleton-git-workspaces-")
    assert first.is_dir()
    assert routes.workspace_base() == first
    assert routes._repo_dir("safe-project").parent == first
    if os.name == "posix":
        assert stat.S_IMODE(first.stat().st_mode) == 0o700

    monkeypatch.setattr(routes, "_workspace_base", None)
    second = routes.workspace_base()
    assert second != first
    assert second.parent == first.parent
    if os.name == "posix":
        assert stat.S_IMODE(second.stat().st_mode) == 0o700


def test_explicit_workspace_path_failure_never_diverts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, routes
) -> None:
    configured = tmp_path / "denied"
    monkeypatch.setenv("GIT_WORKSPACE_BASE", str(configured))
    original_mkdir = Path.mkdir

    def denied(path: Path, *args, **kwargs) -> None:
        if path == configured:
            raise PermissionError("configured workspace unavailable")
        original_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", denied)
    with pytest.raises(PermissionError, match="configured workspace unavailable"):
        routes.workspace_base()
    assert routes._workspace_base is None
    assert not configured.exists()


def test_concurrent_first_use_has_one_process_wide_workspace(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, routes
) -> None:
    monkeypatch.delenv("GIT_WORKSPACE_BASE", raising=False)
    monkeypatch.setattr(routes.tempfile, "tempdir", str(tmp_path))
    original_mkdir = Path.mkdir

    def readonly_app(path: Path, *args, **kwargs) -> None:
        if path == Path("/app/backend/.git_workspaces"):
            raise PermissionError("read-only application installation")
        original_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", readonly_app)
    with ThreadPoolExecutor(max_workers=12) as pool:
        roots = list(pool.map(lambda _: routes.workspace_base(), range(48)))

    assert len(set(roots)) == 1
    root = roots[0]
    assert root.is_dir()
    assert root.parent == tmp_path.resolve()
    assert list(tmp_path.iterdir()) == [root]
    if os.name == "posix":
        assert stat.S_IMODE(root.stat().st_mode) == 0o700
