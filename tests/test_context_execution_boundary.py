from pathlib import Path

from scripts.check_context_execution_boundary import audit_repository


ROOT = Path(__file__).resolve().parents[1]


def _write(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_repository_context_execution_boundary_is_clean() -> None:
    assert audit_repository(ROOT) == []


def test_route_cannot_construct_provider_request_directly(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "backend/routes/feature.py",
        "from skeleton.provider_runtime import ProviderRequest\n"
        "request = ProviderRequest(instructions='x', prompt='y')\n",
    )

    violations = audit_repository(tmp_path)

    assert any("ProviderRequest" in item for item in violations)


def test_service_cannot_activate_provider_registry(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "backend/services/feature.py",
        "from skeleton.provider_runtime import ProviderRegistry\n"
        "registry = ProviderRegistry.from_env()\n",
    )

    violations = audit_repository(tmp_path)

    assert any("ProviderRegistry" in item for item in violations)


def test_product_code_cannot_use_legacy_llm_chat(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "backend/gameforge/feature.py",
        "from emergentintegrations.llm.chat import LlmChat\n",
    )

    violations = audit_repository(tmp_path)

    assert any("legacy LlmChat" in item for item in violations)


def test_engine_text_and_context_compiler_boundaries_are_allowed(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "backend/routes/feature.py",
        "from core.engine_text import EngineTextRequest, execute_engine_text\n"
        "from skeleton.context.compiler import ContextCompiler\n"
        "compiler = ContextCompiler()\n",
    )

    assert audit_repository(tmp_path) == []


def test_backend_core_provider_compatibility_owner_is_out_of_product_scope(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "backend/core/ai_provider.py",
        "from skeleton.provider_runtime import ProviderRequest\n",
    )

    assert audit_repository(tmp_path) == []
