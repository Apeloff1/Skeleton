from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from enum import Enum
import uuid


class DiaryKind(str, Enum):
    MEMORY = "memory"
    INTROSPECT = "introspect"
    OUTROSPECT = "outrospect"
    RETROSPECT = "retrospect"


@dataclass
class DiaryEntry:
    entry_id: str
    kind: DiaryKind
    user_id: str
    title: str
    body: str
    tags: List[str] = field(default_factory=list)
    mood: Optional[float] = None
    intensity: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    source: str = "user"

    @staticmethod
    def create(
        *,
        kind: DiaryKind,
        user_id: str,
        title: str,
        body: str,
        tags: Optional[List[str]] = None,
        mood: Optional[float] = None,
        intensity: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
        source: str = "user",
    ) -> "DiaryEntry":
        return DiaryEntry(
            entry_id=str(uuid.uuid4())[:12],
            kind=kind,
            user_id=user_id,
            title=title,
            body=body,
            tags=tags or [],
            mood=mood,
            intensity=intensity,
            metadata=metadata or {},
            source=source,
        )


class DiaryBase:
    kind: DiaryKind = DiaryKind.MEMORY

    def __init__(self, user_id: str, encryptor=None):
        self.user_id = user_id
        self.encryptor = encryptor
        self.short_buffer: List[DiaryEntry] = []
        self.medium_buffer: List[DiaryEntry] = []
        self.long_buffer: List[DiaryEntry] = []
        self.max_short = 20
        self.max_medium = 60
        self.max_long = 200
        self._vector = None
        self._store = None
        self.tenant_id = "local"
        self.workspace_id = "default"

    async def add(
        self,
        title: str,
        body: str,
        *,
        tags: Optional[List[str]] = None,
        mood: Optional[float] = None,
        intensity: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
        source: str = "user",
    ) -> DiaryEntry:
        entry = DiaryEntry.create(
            kind=self.kind,
            user_id=self.user_id,
            title=title,
            body=body,
            tags=tags,
            mood=mood,
            intensity=intensity,
            metadata=metadata,
            source=source,
        )
        self.short_buffer.append(entry)
        await self._maybe_offload()
        await self._vector_upsert(entry)
        await self._persist(entry)
        return entry

    async def attach_store(self, store, tenant_id: str = "local", workspace_id: str = "default"):
        self._store = store
        self.tenant_id = tenant_id
        self.workspace_id = workspace_id

    async def _maybe_offload(self):
        if len(self.short_buffer) > self.max_short:
            overflow = self.short_buffer[: -self.max_short]
            self.short_buffer = self.short_buffer[-self.max_short :]
            self.medium_buffer.extend(overflow)
        if len(self.medium_buffer) > self.max_medium:
            overflow = self.medium_buffer[: -self.max_medium]
            self.medium_buffer = self.medium_buffer[-self.max_medium :]
            self.long_buffer.extend(overflow)
        if len(self.long_buffer) > self.max_long:
            self.long_buffer = self.long_buffer[-self.max_long :]

    def recent(self, n: int = 10) -> List[DiaryEntry]:
        return list(reversed((self.short_buffer + self.medium_buffer)[-n:]))

    def all_in_memory(self) -> List[DiaryEntry]:
        return list(self.long_buffer + self.medium_buffer + self.short_buffer)

    async def search(self, query: str, k: int = 5) -> List[DiaryEntry]:
        if self._vector is not None:
            try:
                return await self._vector_search(query, k=k)
            except Exception:
                pass
        q = query.lower()
        scored = []
        for e in self.all_in_memory():
            hay = f"{e.title} {e.body} {' '.join(e.tags)}".lower()
            score = sum(1 for token in q.split() if token in hay)
            if score:
                scored.append((score, e))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in scored[:k]]

    def mood_trend(self, n: int = 20) -> Dict[str, Any]:
        entries = [e for e in self.recent(n) if e.mood is not None]
        if not entries:
            return {"count": 0, "avg_mood": None}
        avg = sum(e.mood for e in entries) / len(entries)
        return {"count": len(entries), "avg_mood": avg, "kind": self.kind.value}

    def tag_frequency(self, n: int = 50) -> Dict[str, int]:
        freq: Dict[str, int] = {}
        for e in self.recent(n):
            for t in e.tags:
                freq[t] = freq.get(t, 0) + 1
        return dict(sorted(freq.items(), key=lambda kv: kv[1], reverse=True))

    def export_context(self, n: int = 8) -> str:
        lines = [f"[{self.kind.value.upper()} DIARY — last {n}]"]
        for e in self.recent(n):
            mood = f" mood={e.mood:.2f}" if e.mood is not None else ""
            lines.append(f"- ({e.created_at.isoformat()}) {e.title}{mood}: {e.body[:240]}")
        return "\n".join(lines)

    async def _vector_upsert(self, entry: DiaryEntry):
        if self._vector is None:
            return
        text = f"{entry.title}\n{entry.body}"
        add = getattr(self._vector, "add", None) or getattr(self._vector, "upsert", None)
        if add:
            await add(
                entry.entry_id,
                text,
                {"kind": entry.kind.value, "user_id": entry.user_id, "tags": entry.tags},
            )

    async def _vector_search(self, query: str, k: int = 5) -> List[DiaryEntry]:
        hits = await self._vector.search(query, k=k)
        by_id = {e.entry_id: e for e in self.all_in_memory()}
        out = []
        for h in hits:
            eid = h.get("id") if isinstance(h, dict) else getattr(h, "id", None)
            if eid in by_id:
                out.append(by_id[eid])
        return out

    async def _persist(self, entry: DiaryEntry):
        if self._store is None:
            return
        await self._store.save_entry(
            entry,
            tenant_id=getattr(self, "tenant_id", "local"),
            workspace_id=getattr(self, "workspace_id", "default"),
        )

    async def hydrate_from_store(self, limit: int = 80):
        if self._store is None:
            return
        rows = await self._store.list_entries(
            tenant_id=getattr(self, "tenant_id", "local"),
            user_id=self.user_id,
            kind=self.kind,
            limit=limit,
        )
        rows = list(reversed(rows))
        self.long_buffer = rows[: -self.max_medium] if len(rows) > self.max_medium else []
        mid = rows[-self.max_medium :] if len(rows) > self.max_medium else rows
        self.medium_buffer = mid[: -self.max_short] if len(mid) > self.max_short else []
        self.short_buffer = mid[-self.max_short :]
