from pathlib import Path

from scripts.check_instruction_policy_boundary import audit_repository


ROOT = Path(__file__).resolve().parents[1]


def _write(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_repository_instruction_policy_boundary_is_clean() -> None:
    assert audit_repository(ROOT) == []


def test_product_engine_chat_requires_explicit_instruction_policy(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "backend/routes/feature.py",
        "from core.engine_chat import EngineChat\n"
        "chat = EngineChat(session_id='x')\n",
    )

    violations = audit_repository(tmp_path)

    assert any("must bind instruction_policy" in item for item in violations)


def test_product_engine_chat_rejects_anonymous_system_message(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "backend/services/feature.py",
        "from core.engine_chat import EngineChat\n"
        "policy = object()\n"
        "chat = EngineChat(\n"
        "    session_id='x',\n"
        "    instruction_policy=policy,\n"
        "    system_message='anonymous override',\n"
        ")\n",
    )

    violations = audit_repository(tmp_path)

    assert any("must not own anonymous system_message" in item for item in violations)


def test_product_engine_chat_with_versioned_policy_is_allowed(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "backend/gameforge/feature.py",
        "from core.engine_chat import EngineChat\n"
        "policy = object()\n"
        "chat = EngineChat(session_id='x', instruction_policy=policy)\n",
    )

    assert audit_repository(tmp_path) == []


def test_aliased_engine_chat_import_is_enforced(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "backend/routes/feature.py",
        "from core.engine_chat import EngineChat as Chat\n"
        "chat = Chat(session_id='x')\n",
    )

    violations = audit_repository(tmp_path)

    assert any("must bind instruction_policy" in item for item in violations)


def test_backend_core_compatibility_layer_is_out_of_product_scope(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "backend/core/ai_provider_compat.py",
        "from core.engine_chat import EngineChat\n"
        "chat = EngineChat(session_id='legacy')\n",
    )

    assert audit_repository(tmp_path) == []
