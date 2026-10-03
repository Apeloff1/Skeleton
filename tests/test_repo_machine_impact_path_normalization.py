from skeleton.repo_machine.impact import _normalize_path


def test_impact_normalizes_windows_path_separators() -> None:
    assert _normalize_path(r".\\alpha\\nested\\module.py") == "alpha/nested/module.py"


def test_impact_normalization_is_idempotent_for_canonical_paths() -> None:
    canonical = "alpha/nested/module.py"
    assert _normalize_path(canonical) == canonical
    assert _normalize_path(_normalize_path(canonical)) == canonical
