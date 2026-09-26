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

    async def governed_record_ids_for_thread(self):
        pass

    async def delete_thread_with_governance(self):
        pass

# idempotency_key memory_refs governance_engine_target_executor
""",
        "skeleton/contracts/conversation.py": """
class ConversationThread:
    pass

class ConversationMessage:
    pass

class ConversationAuthorType:
    pass

# idempotency_key causal_user_message_id operation_id ai_result_id memory_refs
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
        "frontend/features/Jeeves/WorkspaceController.ts": """
export type HistoryTransport = unknown;
function projectCanonicalHistory() {}
class WorkspaceController {
  rehydrateServerTranscripts() {
    throw new Error('canonical conversation history unavailable');
  }
  refreshCanonical() {
    return projectCanonicalHistory();
  }
  commit(response) {
    return {
      id: response.canonical_message_id,
      thread: response.canonical_thread_id,
      sessionUpdatedAt: Date.now(),
    };
  }
}
""",
        "frontend/features/Jeeves/workspace.ts": """
function sessionIdentity(value: unknown) { return value; }
const sessionId = sessionIdentity('session');
const restored = {
  sessionId,
  sessionUpdatedAt: sessionId ? sessionUpdatedAt : 0,
};
// The browser cache never sends its transcript back as provider context.
export function buildChatBody() {
  return { session_id: sessionId };
}
function canonicalTurnText() {}
export function projectCanonicalHistory() {}
""",
        "frontend/features/Jeeves/ChatWorkspace.tsx": """
type ChatHistoryResponse = unknown;
const path = '/api/jeeves/chat/' + sessionId + '?limit=50';
controller.refreshCanonical();
""",
        "frontend/scripts/test-jeeves-workspace.cjs": """
test('remount replaces stale device transcript with canonical server history', () => {});
test('remount keeps device cache with notice when canonical history is unavailable', () => {});
test('durable backend session identity survives timestamp age and skew', () => {});
test('outgoing Jeeves requests never serialize the device-local transcript', () => {});
test('canonical projection preserves unresolved local user work only', () => {});
test('successful send caches canonical thread and assistant identities', () => {});
""",
        "backend/routes/conversations.py": """
@router.post("/{thread_id}/messages/{message_id}/regenerate")
async def regenerate_assistant_message():
    command_from_context()
    _compile_chat_context()
    _provider_history()
    EngineClient.from_env()
    conversation_authority.regenerate_assistant_message()
    ai_result_id = "engine-result:" + result.execution_id
    payload = {
        "regenerated_from": target.message_id,
        "causal_user_message_id": causal.message_id,
    }
""",
        "backend/tests/test_conversation_regeneration_route.py": """
async def test_regenerate_route_runs_engine_then_commits_new_branch():
    pass

async def test_regenerate_route_never_commits_when_engine_unavailable():
    pass

async def test_regenerate_route_rejects_stale_version_before_engine_resolution():
    pass
""",
        "backend/tests/test_conversation_governance.py": """
def test_thread_governance_selection_includes_only_explicit_linked_records():
    pass

def test_governed_deletion_removes_message_before_thread_and_acks():
    pass
""",
        "backend/tests/test_conversations_api.py": """
def test_delete_executes_governed_propagation_before_claiming_completion():
    pass

def test_delete_never_claims_completion_when_governance_propagation_fails():
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
    assert len(receipt["digests"]) == 12


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


def test_cutover_verifier_rejects_ttl_session_expiry_regression(
    tmp_path: Path,
) -> None:
    root = _write_valid_repo(tmp_path)
    path = root / "frontend" / "features" / "Jeeves" / "workspace.ts"
    source = path.read_text(encoding="utf-8")
    source += "\nconst sessionFresh = false;\n"
    path.write_text(source, encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert "workspace model regained TTL-based canonical session expiry" in receipt["errors"]

def test_cutover_verifier_rejects_client_transcript_authority(
    tmp_path: Path,
) -> None:
    root = _write_valid_repo(tmp_path)
    path = root / "frontend" / "features" / "Jeeves" / "workspace.ts"
    source = path.read_text(encoding="utf-8")
    source = source.replace(
        "return { session_id: sessionId };",
        "return { session_id: sessionId, history: [] };",
    )
    path.write_text(source, encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert (
        "Jeeves buildChatBody regained caller transcript authority"
        in receipt["errors"]
    )
