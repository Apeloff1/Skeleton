from __future__ import annotations
import os


async def build_diary_store():
    dsn = os.getenv("GAMEFORGE_DATABASE_URL")
    if dsn and dsn.startswith(("postgres://", "postgresql://")):
        try:
            from gameforge.enterprise.pg_diary_store import PostgresDiaryStore

            store = PostgresDiaryStore(dsn)
            await store.connect()
            return store
        except Exception:
            pass
    from gameforge.personal.diaries.store import DiaryStore

    store = DiaryStore()
    await store.initialize()
    return store
