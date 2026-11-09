from __future__ import annotations

import py_compile
from pathlib import Path


def test_local_deployment_modules_compile() -> None:
    root=Path(__file__).resolve().parents[2]
    for relative in (
        "skeleton/ai/runtime/inference/deployment.py",
        "skeleton/ai/runtime/inference/llama_cpp.py",
    ):
        py_compile.compile(str(root/relative),doraise=True)
