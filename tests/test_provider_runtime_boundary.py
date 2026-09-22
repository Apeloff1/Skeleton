from pathlib import Path

from scripts.check_provider_runtime_boundary import audit_repository


ROOT = Path(__file__).resolve().parents[1]


def _write(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_repository_provider_runtime_boundary_is_clean() -> None:
    assert audit_repository(ROOT) == []


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


def test_local_compat_static_import_is_allowed_in_backend(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "backend/routes/ai.py",
        "from emergentintegrations.llm.chat import LlmChat, UserMessage\n"
        "chat = LlmChat(system_message='rules')\n"
        "message = UserMessage(text='hello')\n",
    )

    assert audit_repository(tmp_path) == []


def test_local_compat_import_is_rejected_outside_backend(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "skeleton/service.py",
        "from emergentintegrations.llm.chat import LlmChat\n",
    )

    violations = audit_repository(tmp_path)

    assert any("backend-only provider compatibility import" in item for item in violations)


def test_dynamic_compat_import_is_rejected(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "backend/service.py",
        "import importlib\n"
        "provider = importlib.import_module('emergentintegrations.llm.chat')\n",
    )

    violations = audit_repository(tmp_path)

    assert any("dynamic provider compatibility import" in item for item in violations)


def test_frontier_and_agent_core_reject_provider_sdk_imports(tmp_path: Path) -> None:
    _write(tmp_path, "skeleton/frontier/example.py", "import openai\n")
    _write(tmp_path, "skeleton/agents/example.py", "import litellm\n")

    violations = audit_repository(tmp_path)

    assert sum("provider SDK import" in item for item in violations) == 2


def test_backend_openai_sdk_import_is_rejected(tmp_path: Path) -> None:
    _write(tmp_path, "backend/routes/feature.py", "from openai import AsyncOpenAI\n")

    violations = audit_repository(tmp_path)

    assert any(
        "provider SDK import from 'openai' outside canonical runtime" in item
        for item in violations
    )


def test_canonical_provider_runtime_may_import_declared_vendor_sdk(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "skeleton/provider_runtime.py",
        "from openai import AsyncOpenAI\n",
    )

    assert audit_repository(tmp_path) == []
