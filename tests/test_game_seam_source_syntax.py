"""Regression guard for restored Python seam modules.

These modules previously contained literal backslash-n sequences and escaped
quote delimiters in the checked-in source, causing architecture scans to fail.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

SEAM_NAMES = (
    "absolute_final",
    "cutting_edge_history",
    "final_history_confirmation",
    "giga_ultra_mega_hyper_ultimate_supreme",
    "hive_merkle_gossip_accelerator",
    "hyper_ultimate_supreme",
    "mega_hyper_ultimate_supreme",
    "peta_tera_giga_ultra_mega_hyper_ultimate_supreme",
    "supreme_final",
    "tera_giga_ultra_mega_hyper_ultimate_supreme",
    "ultimate_supreme",
    "ultra_mega_hyper_ultimate_supreme",
)
SEAM_ROOT = Path(__file__).resolve().parents[1] / "skeleton" / "game" / "seams"


@pytest.mark.parametrize("name", SEAM_NAMES)
def test_restored_seam_is_parseable_python(name: str) -> None:
    path = SEAM_ROOT / f"{name}.py"
    source = path.read_text(encoding="utf-8")
    assert "\\n" not in source, f"{path} contains literal escaped newlines"
    assert '\\"' not in source, f"{path} contains escaped quote delimiters"
    tree = ast.parse(source, filename=str(path))
    assert tree.body, f"{path} is empty"
