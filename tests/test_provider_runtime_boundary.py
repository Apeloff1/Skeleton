from pathlib import Path

from scripts.check_provider_bootstrap import (
    _is_non_runtime_provider_mirror,
    discover_provider_surfaces,
    validate_provider_bootstrap,
)
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


def test_provider_bootstrap_excludes_only_external_research_mirrors(tmp_path: Path) -> None:
    external = (
        "skeleton/ai/research/external/Tutolage/backend/routes/legacy.py"
    )
    live = "skeleton/ai/research/live_provider.py"
    source = "import os\nfrom openai import AsyncOpenAI\nOPENAI_API_KEY = os.getenv('OPENAI_API_KEY')\n"

    _write(tmp_path, external, source)
    _write(tmp_path, live, source)

    discovered = discover_provider_surfaces(tmp_path)

    assert external not in discovered
    assert live in discovered
    assert _is_non_runtime_provider_mirror(external) is True
    assert _is_non_runtime_provider_mirror(live) is False


def test_provider_bootstrap_detects_aliased_credential_reads(tmp_path: Path) -> None:
    cases = {
        "backend/alias_os.py": (
            "import os as operating_system\n"
            "from openai import AsyncOpenAI\n"
            "key = operating_system.getenv('OPENAI_API_KEY')\n"
        ),
        "backend/alias_getenv.py": (
            "from os import getenv as read_env\n"
            "from openai import AsyncOpenAI\n"
            "key = read_env('OPENAI_API_KEY')\n"
        ),
        "backend/alias_environ.py": (
            "from os import environ as environment\n"
            "from openai import AsyncOpenAI\n"
            "key = environment.get('OPENAI_API_KEY')\n"
        ),
    }
    for relative, source in cases.items():
        _write(tmp_path, relative, source)

    discovered = discover_provider_surfaces(tmp_path)

    for relative in cases:
        assert relative in discovered
        assert "credential" in discovered[relative]["edge_classes"]


def test_external_research_mirror_is_not_a_runtime_provider_surface(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "skeleton/ai/research/external/Tutolage/backend/routes/legacy.py",
        "from openai import AsyncOpenAI\n",
    )

    assert audit_repository(tmp_path) == []


def test_canonical_ai_provider_copy_is_nonexecuting_mirror(tmp_path: Path) -> None:
    source = (
        "import os\n"
        "from openai import AsyncOpenAI\n"
        "key = os.getenv('OPENAI_API_KEY')\n"
    )
    _write(tmp_path, "skeleton/provider_runtime.py", source)
    _write(tmp_path, "skeleton/ai/runtime/provider_runtime.py", source)

    assert audit_repository(tmp_path) == []
    discovered = discover_provider_surfaces(tmp_path)
    assert "skeleton/provider_runtime.py" in discovered
    assert "skeleton/ai/runtime/provider_runtime.py" not in discovered


def test_live_ai_research_surface_still_rejects_provider_sdk_imports(tmp_path: Path) -> None:
    _write(tmp_path, "skeleton/ai/research/live.py", "import openai\n")

    violations = audit_repository(tmp_path)

    assert any("provider SDK import" in item for item in violations)


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


def test_lafs_has_no_shadow_or_local_provider_runtime() -> None:
    relative = "backend/routes/lafs.py"
    source = (ROOT / relative).read_text(encoding="utf-8")

    assert "EMERGENT_LLM_KEY" not in source
    assert "emergentintegrations.llm.chat" not in source
    assert "ProviderRegistry.from_env()" not in source
    assert "EngineTextRequest" not in source
    assert "execute_engine_text" not in source
    assert "EngineChat" in source
    assert "UserMessage" in source
    assert "LAFS_JEEVES_POLICY" in source
    assert 'verification_profile="evidence_required"' in source
    assert "session_id=" not in source

    discovered = discover_provider_surfaces(ROOT)
    assert relative not in discovered



def test_lafs_is_declared_engine_chat_isolation_surface() -> None:
    import json

    contract = json.loads(
        (ROOT / "machine" / "ai_app_construction.json").read_text(
            encoding="utf-8"
        )
    )
    surfaces = {
        item["path"]: item
        for item in contract["provider_surface_convergence_blueprint"][
            "application_isolation_surfaces"
        ]
    }
    entry = surfaces["backend/routes/lafs.py"]

    assert set(entry["forbidden_edge_classes"]) == {
        "credential",
        "network_transport",
        "sdk_client",
    }
    assert set(entry["required_tokens"]) == {
        "EngineChat",
        "UserMessage",
        "LAFS_JEEVES_POLICY",
        "evidence_required",
    }


def test_backend_tool_registry_is_declared_provider_isolation_surface() -> None:
    import json

    contract = json.loads(
        (ROOT / "machine" / "ai_app_construction.json").read_text(encoding="utf-8")
    )
    surfaces = {
        item["path"]: item
        for item in contract["provider_surface_convergence_blueprint"][
            "application_isolation_surfaces"
        ]
    }
    entry = surfaces["backend/services/tool_registry.py"]

    assert set(entry["forbidden_edge_classes"]) == {
        "credential",
        "network_transport",
        "sdk_client",
    }
    assert "provider_tool_retired" in entry["required_tokens"]
    assert "skeleton-engine-provider-boundary" in entry["required_tokens"]
    assert "SQLiteToolReceiptStore" in entry["required_tokens"]


def test_backend_tool_registry_has_no_provider_edge_after_llm_retirement() -> None:
    relative = "backend/services/tool_registry.py"
    source = (ROOT / relative).read_text(encoding="utf-8")

    assert "EMERGENT_LLM_KEY" not in source
    assert "OPENAI_API_KEY" not in source
    assert "emergentintegrations" not in source
    assert "LlmChat(" not in source
    assert "provider_tool_retired" in source
    assert "skeleton-engine-provider-boundary" in source

    discovered = discover_provider_surfaces(ROOT)
    assert relative not in discovered
    assert validate_provider_bootstrap(ROOT) == []
