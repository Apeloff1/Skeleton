from __future__ import annotations

from pathlib import Path

import core
import core.activation_security as activation_security


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_core_imports_resolve_from_repository_checkout() -> None:
    core_path = Path(core.__file__).resolve()
    activation_path = Path(activation_security.__file__).resolve()

    assert core_path == REPO_ROOT / "core" / "__init__.py"
    assert activation_path == REPO_ROOT / "core" / "activation_security.py"
