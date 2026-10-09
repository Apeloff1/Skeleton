"""Local SQLite recovery, cross-process CAS and no-cloud transcript durability."""
from __future__ import annotations

import asyncio
from pathlib import Path
import sqlite3

import pytest

from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.runtime.inference.native_runtime import NativeRuntimeLocalModel
from skeleton.app.local_ai import OfflineAISession
from skeleton.app.offline_workspace import (
    DurableOfflineSession, OfflineWorkspace, OfflineWorkspaceConflict,
    OfflineWorkspaceError,
)
from skeleton.cortex.transformer import TinyTransformer


MODEL = "a" * 64
INITIAL = (("user", "hello"), ("assistant", "answer"))


def _native(seed: int = 41) -> OfflineAISession:
    model = TinyTransformer(
        vocab=("system:", "user:", "assistant:", "hello", "world", "answer"),
        dim=8, ctx=64, seed=seed, n_heads=2, n_layers=2, d_ff=16,
    )
    return OfflineAISession(NativeRuntimeLocalModel(NativeLLMRuntime(model)))


def test_workspace_stores_complete_turns_and_restores_across_connections(tmp_path: Path) -> None:
    path = tmp_path / "workspace.db"
    with OfflineWorkspace(path) as first:
        revision, history = first.open("default", MODEL)
        assert revision == 0 and history == ()
        assert first.save("default", MODEL, 0, INITIAL) == 1
        assert first.list_sessions() == ("default",)
    with OfflineWorkspace(path) as reopened:
        assert reopened.open("default", MODEL) == (1, INITIAL)
        assert reopened.save("default", MODEL, 1, ()) == 2
    with OfflineWorkspace(path) as again:
        assert again.open("default", MODEL) == (2, ())


def test_workspace_conflicting_writer_is_rejected_not_overwritten(tmp_path: Path) -> None:
    path = tmp_path / "workspace.db"
    with OfflineWorkspace(path) as a, OfflineWorkspace(path) as b:
        assert a.open("default", MODEL)[0] == 0
        assert b.open("default", MODEL)[0] == 0
        assert a.save("default", MODEL, 0, INITIAL) == 1
        with pytest.raises(OfflineWorkspaceConflict, match="revision conflict"):
            b.save("default", MODEL, 0, ())
        assert a.open("default", MODEL) == (1, INITIAL)


def test_model_swap_never_resumes_prior_model_context(tmp_path: Path) -> None:
    with OfflineWorkspace(tmp_path / "workspace.db") as store:
        store.open("default", MODEL)
        store.save("default", MODEL, 0, INITIAL)
        with pytest.raises(OfflineWorkspaceError, match="different model"):
            store.open("default", "b" * 64)
        with pytest.raises(OfflineWorkspaceConflict):
            store.save("default", "b" * 64, 1, ())


def test_storage_corruption_never_enters_model_context(tmp_path: Path) -> None:
    path = tmp_path / "workspace.db"
    with OfflineWorkspace(path) as store:
        store.open("default", MODEL)
        store.save("default", MODEL, 0, INITIAL)
    connection = sqlite3.connect(path)
    connection.execute(
        "UPDATE offline_conversations SET history_json=? WHERE session_id=?",
        ('[["user","corrupted"],["assistant","answer"]]', "default"),
    )
    connection.commit()
    connection.close()
    with OfflineWorkspace(path) as store:
        with pytest.raises(OfflineWorkspaceError, match="integrity"):
            store.open("default", MODEL)


def test_session_ids_and_partial_turns_are_rejected(tmp_path: Path) -> None:
    with OfflineWorkspace(tmp_path / "workspace.db") as store:
        with pytest.raises(OfflineWorkspaceError, match="session id"):
            store.open("../escape", MODEL)
        store.open("valid", MODEL)
        with pytest.raises(ValueError, match="complete"):
            store.save("valid", MODEL, 0, (("user", "incomplete"),))
        assert store.open("valid", MODEL) == (0, ())


@pytest.mark.asyncio
async def test_durable_native_chat_survives_restart(tmp_path: Path) -> None:
    db = tmp_path / "workspace.db"
    session = _native()
    durable = DurableOfflineSession(session, db)
    first = await durable.ask("hello", max_output_tokens=2)
    assert first.text
    assert durable.revision == 1
    snapshot = session.history
    durable.close()

    resumed = _native()
    continuation = DurableOfflineSession(resumed, db)
    assert continuation.history == snapshot
    await continuation.ask("world", max_output_tokens=2)
    assert continuation.revision == 2
    continuation.close()

    with OfflineWorkspace(db) as store:
        revision, history = store.open("default", resumed.model_digest)
        assert revision == 2 and len(history) == 4


@pytest.mark.asyncio
async def test_stale_durable_chat_restores_memory_after_write_denial(tmp_path: Path) -> None:
    db = tmp_path / "workspace.db"
    first, stale = DurableOfflineSession(_native(), db), DurableOfflineSession(_native(), db)
    await first.ask("hello", max_output_tokens=2)
    with pytest.raises(OfflineWorkspaceConflict, match="revision conflict"):
        await stale.ask("hello", max_output_tokens=2)
    assert stale.history == ()
    assert stale.revision == 0
    first.close()
    stale.close()


def test_existing_nonworkspace_file_and_symlink_are_rejected(tmp_path: Path) -> None:
    target = tmp_path / "file.db"
    target.write_bytes(b"not a SQLite database")
    with pytest.raises(OfflineWorkspaceError):
        OfflineWorkspace(target)
    link = tmp_path / "link.db"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlink unsupported")
    with pytest.raises(OfflineWorkspaceError, match="non-symlink"):
        OfflineWorkspace(link)
