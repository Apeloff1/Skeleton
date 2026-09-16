from __future__ import annotations

from pathlib import Path


def test_core_package_resolves_to_repository_tree() -> None:
    import core
    import core.activation_security as activation_security

    repo_root = Path(__file__).resolve().parents[1]
    assert Path(core.__file__).resolve() == repo_root / "core" / "__init__.py"
    assert Path(activation_security.__file__).resolve() == repo_root / "core" / "activation_security.py"
