"""Importing swarm/collection support must not initialize MongoDB."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys


def test_collection_agents_import_never_opens_mongo() -> None:
    script = """
from core import databases
def forbidden():
    raise AssertionError('Mongo client initialized during module import')
databases.get_sync_db = forbidden
from core import collection_agents
assert collection_agents._db is None
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_collection_agents_obtain_shared_mongo_only_on_first_read(monkeypatch):
    from core import collection_agents

    class Database:
        def list_collection_names(self):
            return ["academy_decks", "system.local", "games_worlds"]

    fake = Database()
    calls = []
    monkeypatch.setattr(collection_agents, "_db", None)
    monkeypatch.setattr(collection_agents, "load_dotenv", lambda: None)

    def connect():
        calls.append("opened")
        return fake

    monkeypatch.setattr(collection_agents, "get_sync_db", connect)
    assert collection_agents.all_collection_names() == ["academy_decks", "games_worlds"]
    assert collection_agents.all_collection_names() == ["academy_decks", "games_worlds"]
    assert calls == ["opened"]
