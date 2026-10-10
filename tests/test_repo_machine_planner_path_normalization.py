from skeleton.repo_machine.planner import _normalize_finding_path


def test_normalize_finding_path_converts_windows_separators() -> None:
    assert _normalize_finding_path(r".\skeleton\integrations\adapters\client.py") == (
        "skeleton/integrations/adapters/client.py"
    )


def test_normalize_finding_path_preserves_repository_relative_posix_path() -> None:
    assert _normalize_finding_path("./skeleton/repo_machine/planner.py") == (
        "skeleton/repo_machine/planner.py"
    )
