from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / "scripts/check_ai_assistant_control_plane.py"


def _module():
    spec = importlib.util.spec_from_file_location("check_ai_assistant_control_plane", CHECK)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ai_assistant_control_plane_manifest_is_valid() -> None:
    assert _module().validate() == []


def test_ai_assistant_tree_is_clean_room_and_provider_neutral() -> None:
    root = ROOT / "skeleton/ai/assistant"
    sources = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(root.glob("*.py"))
    )
    assert "OPENAI_API_KEY" not in sources
    assert "api.openai.com" not in sources
    assert "from openai import" not in sources
    assert "import openai" not in sources
