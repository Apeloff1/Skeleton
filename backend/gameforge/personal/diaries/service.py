from __future__ import annotations
from typing import Dict, Any, List
from gameforge.personal.diaries.kinds import (
    MemoryDiary,
    IntrospectDiary,
    OutrospectDiary,
    RetrospectDiary,
)
from gameforge.personal.diaries.base import DiaryKind, DiaryEntry
from gameforge.personal.diaries.vector_index import DiaryVectorIndex


class DiaryService:
    def __init__(
        self,
        user_id: str,
        encryptor=None,
        tenant_id: str = "local",
        workspace_id: str = "default",
    ):
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.workspace_id = workspace_id
        self.store = None
        self.memory = MemoryDiary(user_id, encryptor=encryptor)
        self.introspect = IntrospectDiary(user_id, encryptor=encryptor)
        self.outrospect = OutrospectDiary(user_id, encryptor=encryptor)
        self.retrospect = RetrospectDiary(user_id, encryptor=encryptor)
        self._by_kind = {
            DiaryKind.MEMORY: self.memory,
            DiaryKind.INTROSPECT: self.introspect,
            DiaryKind.OUTROSPECT: self.outrospect,
            DiaryKind.RETROSPECT: self.retrospect,
        }

    def get(self, kind: DiaryKind):
        return self._by_kind[kind]

    async def initialize(self):
        try:
            from gameforge.personal.diaries.store_factory import build_diary_store

            self.store = await build_diary_store()
        except Exception:
            self.store = None
        shared_index = DiaryVectorIndex(dim=128)
        for d in self._by_kind.values():
            if self.store is not None:
                await d.attach_store(self.store, self.tenant_id, self.workspace_id)
                await d.hydrate_from_store(limit=80)
            d._vector = shared_index
            for e in d.all_in_memory():
                await d._vector_upsert(e)

    async def add(self, kind: DiaryKind, title: str, body: str, **kwargs) -> DiaryEntry:
        return await self.get(kind).add(title, body, **kwargs)

    async def search_all(self, query: str, k: int = 5) -> Dict[str, List[DiaryEntry]]:
        return {kind.value: await diary.search(query, k=k) for kind, diary in self._by_kind.items()}

    def export_all_context(self, n: int = 5) -> str:
        return "\n\n".join(d.export_context(n=n) for d in self._by_kind.values())

    def mood_dashboard(self) -> Dict[str, Any]:
        return {kind.value: d.mood_trend() for kind, d in self._by_kind.items()}
