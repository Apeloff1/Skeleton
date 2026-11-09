from __future__ import annotations

import ast
from pathlib import Path

from skeleton.ubuntu.operations import ubuntu_contract_9000


def test_operations_module_is_complete_python_source() -> None:
    path = Path(__file__).parents[1] / "skeleton" / "ubuntu" / "operations.py"
    ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_final_generated_contract_is_callable() -> None:
    assert ubuntu_contract_9000("health") == "ubuntu-9000:health"


def test_final_generated_contract_rejects_absolute_identity() -> None:
    try:
        ubuntu_contract_9000("/etc/passwd")
    except ValueError as exc:
        assert "absolute identity rejected" in str(exc)
    else:
        raise AssertionError("absolute identity must fail closed")
