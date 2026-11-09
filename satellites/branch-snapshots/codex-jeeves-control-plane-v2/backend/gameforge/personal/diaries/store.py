from __future__ import annotations
import json
import aiosqlite
from datetime import datetime
from typing import Any, Dict, List, Optional
from pathlib import Path

from gameforge.personal.diaries.base import DiaryEntry, DiaryKind
from gameforge.enterprise.crypto import EnvelopeEncryptor


def _default_db_path() -> str:
    root = Path(os.getenv("GAMEFORGE_DATA_DIR", "/tmp/gameforge_data"))
    root.mkdir(parents=True, exist_ok=True)
    return str(root / "gameforge_diaries.db")


import os


class DiaryStore:
    def __init__(self, sqlite_path: str | None = None):
        self.db_path = sqlite_path or _default_db_path()
        self.crypto = EnvelopeEncryptor()

    async def initialize(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS diary_entries (
                    entry_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL DEFAULT 'local',
                    workspace_id TEXT NOT NULL DEFAULT 'default',
                    user_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    tags JSON NOT NULL,
                    mood REAL,
                    intensity REAL,
                    metadata JSON NOT NULL,
                    source TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, entry_id)
                )
                """
            )
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_diary_user_kind_ts
                ON diary_entries(tenant_id, user_id, kind, created_at)
                """
            )
            await db.commit()

    async def save_entry(
        self,
        entry: DiaryEntry,
        *,
        tenant_id: str = "local",
        workspace_id: str = "default",
    ):
        title_env = self.crypto.encrypt(tenant_id, entry.title.encode("utf-8"))
        body_env = self.crypto.encrypt(tenant_id, entry.body.encode("utf-8"))
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO diary_entries
                (entry_id, tenant_id, workspace_id, user_id, kind, title, body,
                 tags, mood, intensity, metadata, source, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.entry_id,
                    tenant_id,
                    workspace_id,
                    entry.user_id,
                    entry.kind.value,
                    json.dumps({"envelope": title_env}),
                    json.dumps({"envelope": body_env}),
                    json.dumps(entry.tags or []),
                    entry.mood,
                    entry.intensity,
                    json.dumps(entry.metadata or {}),
                    entry.source,
                    entry.created_at.isoformat(),
                ),
            )
            await db.commit()

    def _dec_text(self, tenant_id: str, blob: str) -> str:
        data = json.loads(blob) if isinstance(blob, str) else blob
        if isinstance(data, dict) and "envelope" in data:
            return self.crypto.decrypt(tenant_id, data["envelope"]).decode("utf-8")
        return str(data)

    def _row_to_entry(self, tenant_id: str, row: aiosqlite.Row) -> DiaryEntry:
        return DiaryEntry(
            entry_id=row["entry_id"],
            kind=DiaryKind(row["kind"]),
            user_id=row["user_id"],
            title=self._dec_text(tenant_id, row["title"]),
            body=self._dec_text(tenant_id, row["body"]),
            tags=json.loads(row["tags"] or "[]"),
            mood=row["mood"],
            intensity=row["intensity"],
            metadata=json.loads(row["metadata"] or "{}"),
            created_at=datetime.fromisoformat(row["created_at"]),
            source=row["source"],
        )

    async def list_entries(
        self,
        *,
        tenant_id: str,
        user_id: str,
        kind: Optional[DiaryKind] = None,
        limit: int = 50,
    ) -> List[DiaryEntry]:
        q = "SELECT * FROM diary_entries WHERE tenant_id=? AND user_id=?"
        params: List[Any] = [tenant_id, user_id]
        if kind is not None:
            q += " AND kind=?"
            params.append(kind.value)
        q += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(q, params) as cur:
                rows = await cur.fetchall()
                return [self._row_to_entry(tenant_id, r) for r in rows]

    async def get_entry(self, tenant_id: str, entry_id: str) -> Optional[DiaryEntry]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM diary_entries WHERE tenant_id=? AND entry_id=?",
                (tenant_id, entry_id),
            ) as cur:
                row = await cur.fetchone()
                if not row:
                    return None
                return self._row_to_entry(tenant_id, row)

    async def delete_entry(self, tenant_id: str, entry_id: str) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                "DELETE FROM diary_entries WHERE tenant_id=? AND entry_id=?",
                (tenant_id, entry_id),
            )
            await db.commit()
            return (cur.rowcount or 0) > 0

    async def keyword_search(
        self,
        *,
        tenant_id: str,
        user_id: str,
        query: str,
        kind: Optional[DiaryKind] = None,
        limit: int = 20,
    ) -> List[DiaryEntry]:
        window = await self.list_entries(
            tenant_id=tenant_id, user_id=user_id, kind=kind, limit=300
        )
        q = query.lower().split()
        scored = []
        for e in window:
            hay = f"{e.title} {e.body} {' '.join(e.tags)}".lower()
            score = sum(1 for t in q if t in hay)
            if score:
                scored.append((score, e))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in scored[:limit]]
