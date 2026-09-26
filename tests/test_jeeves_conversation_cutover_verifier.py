from __future__ import annotations

from pathlib import Path

from scripts.verify_jeeves_conversation_cutover import verify_repository


def _write_valid_repo(root: Path) -> Path:
    files = {
        "backend/routes/jeeves_compose.py": """
def _chat_col():
    return core_db["jeeves_chat"]

def _canonical_authority():
    pass

def _ensure_canonical_thread():
    pass

async def _append_canonical_user_turn():
    pass

async def _commit_canonical_assistant_turn():
    pass

async def _canonical_existing_turn():
    pass

async def _load_canonical_history():
    pass

async def _legacy_complete_rows():
    rows = _chat_col().find({})
    return rows

async def _import_legacy_rows_to_canonical():
    pass

# ConversationThread/ConversationMessage is the only mutable authority.
""",
        "backend/core/conversations.py": """
class MongoConversationAuthority:
    async def append_user_message(self):
        pass

    async def commit_assistant_message(self):
        pass

    async def active_transcript(self):
        pass

# idempotency_key
""",
        "skeleton/contracts/conversation.py": """
class ConversationThread:
    pass

class ConversationMessage:
    pass

class ConversationAuthorType:
    pass

# idempotency_key causal_user_message_id operation_id ai_result_id
""",
        "tests/test_jeeves_chat_workspace.py": """
def test_jeeves_chat_legacy_collection_is_migration_read_only():
    pass

def test_stable_client_message_id_replays_without_second_generation():
    pass

def test_client_message_id_conflict_is_rejected():
    pass

def test_canonical_jeeves_mode_migrates_legacy_then_owns_new_turns():
    pass
""",
    }
    for rel, source in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source.strip() + "\n", encoding="utf-8")
    return root


def test_cutover_verifier_accepts_migration_read_only_legacy_store(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = _write_valid_repo(tmp_path)
    monkeypatch.setenv("GITHUB_SHA", "conversation-head")

    receipt = verify_repository(root)

    assert receipt["valid"] is True
    assert receipt["errors"] == []
    assert receipt["head_sha"] == "conversation-head"
    assert receipt["legacy_read_accesses"] == 1
    assert len(receipt["digests"]) == 4


def test_cutover_verifier_rejects_legacy_write(tmp_path: Path) -> None:
    root = _write_valid_repo(tmp_path)
    path = root / "backend" / "routes" / "jeeves_compose.py"
    source = path.read_text(encoding="utf-8")
    source += '\nasync def bad():\n    await _chat_col().insert_one({})\n'
    path.write_text(source, encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "regained legacy authority token" in error
        or "escaped migration reader" in error
        for error in receipt["errors"]
    )


def test_cutover_verifier_rejects_feature_flag_regression(
    tmp_path: Path,
) -> None:
    root = _write_valid_repo(tmp_path)
    path = root / "backend" / "routes" / "jeeves_compose.py"
    source = path.read_text(encoding="utf-8")
    source += '\nFLAG = "SKL_JEEVES_CANONICAL_CONVERSATIONS"\n'
    path.write_text(source, encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "SKL_JEEVES_CANONICAL_CONVERSATIONS" in error
        for error in receipt["errors"]
    )


def test_cutover_verifier_rejects_extra_legacy_reader(tmp_path: Path) -> None:
    root = _write_valid_repo(tmp_path)
    path = root / "backend" / "routes" / "jeeves_compose.py"
    source = path.read_text(encoding="utf-8")
    source += '\ndef rogue_read():\n    return _chat_col().find({})\n'
    path.write_text(source, encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "escaped migration reader: rogue_read" in error
        for error in receipt["errors"]
    )
