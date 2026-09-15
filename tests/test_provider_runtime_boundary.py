from pathlib import Path

from scripts.check_provider_runtime_boundary import audit_repository


def _write(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_google_genai_direct_import_is_rejected(tmp_path: Path) -> None:
    _write(tmp_path, "backend/service.py", "from google import genai\n")

    violations = audit_repository(tmp_path)

    assert any("direct Google model SDK import" in item for item in violations)


def test_google_genai_dynamic_import_is_rejected(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "backend/service.py",
        "import importlib\nprovider = importlib.import_module('google.genai')\n",
    )

    violations = audit_repository(tmp_path)

    assert any("dynamic Google model SDK import" in item for item in violations)


def test_retired_emergent_import_is_rejected_outside_legacy_server(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "backend/routes/ai.py",
        "from emergentintegrations.llm.chat import LlmChat\n",
    )

    violations = audit_repository(tmp_path)

    assert any("retired Emergent model shim import" in item for item in violations)


def test_legacy_server_import_is_allowed_only_while_symbols_are_unused(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "backend/server.py",
        "from emergentintegrations.llm.chat import LlmChat, UserMessage\nvalue = 1\n",
    )

    assert audit_repository(tmp_path) == []

    _write(
        tmp_path,
        "backend/server.py",
        "from emergentintegrations.llm.chat import LlmChat, UserMessage\nclient = LlmChat()\n",
    )

    violations = audit_repository(tmp_path)
    assert any("compatibility symbols are active" in item for item in violations)


def test_frontier_and_agent_core_reject_provider_sdk_imports(tmp_path: Path) -> None:
    _write(tmp_path, "skeleton/frontier/example.py", "import openai\n")
    _write(tmp_path, "skeleton/agents/example.py", "import litellm\n")

    violations = audit_repository(tmp_path)

    assert sum("provider SDK import" in item for item in violations) == 2
