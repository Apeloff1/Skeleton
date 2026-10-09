"""Owner-scoped projection over the existing, canonical Dragon crawl journal.

Trusted crawler hosts attach a session when creating a new user-authorized
crawl. The public API can only read the authenticated owner's most recent
active session. No client can bind a session or submit crawler progress.
"""
from __future__ import annotations

from dataclasses import dataclass
import sqlite3
from math import isfinite

from .dragon_journal import DragonEventJournal


@dataclass(frozen=True)
class DragonCrawlFeed:
    session_id: str | None
    active: bool
    events: tuple[dict, ...]
    next_cursor: str | None
    has_more: bool
    source: str = "canonical_crawl_journal"


class DragonSessionProjection:
    def __init__(self, connection: sqlite3.Connection):
        self.db=connection
        self.journal=DragonEventJournal(connection)
        connection.execute("""CREATE TABLE IF NOT EXISTS dragon_crawl_session_owners(
            session_id TEXT PRIMARY KEY,owner TEXT NOT NULL,
            created_at REAL NOT NULL,active INTEGER NOT NULL)""")
        connection.execute("""CREATE INDEX IF NOT EXISTS dragon_crawl_owner_feed
            ON dragon_crawl_session_owners(owner,active,created_at)""")
        connection.commit()

    @staticmethod
    def _owner(owner: str) -> None:
        if not isinstance(owner,str) or not 1<=len(owner)<=128:
            raise ValueError("invalid crawler owner")

    def attach(self,owner:str,session_id:str,*,authorized:bool,at:float) -> None:
        """Producer-only session binding, never available from the browser."""
        if not authorized:
            raise PermissionError("crawler binding requires owner authority")
        self._owner(owner)
        if not isinstance(session_id,str) or not 1<=len(session_id)<=128:
            raise ValueError("invalid crawl session")
        if isinstance(at,bool) or not isinstance(at,(int,float)) or not isfinite(at) or at<0:
            raise ValueError("invalid crawl binding time")
        with self.db:
            existing=self.db.execute("""SELECT owner FROM dragon_crawl_session_owners
                WHERE session_id=?""",(session_id,)).fetchone()
            if existing and existing[0]!=owner:
                raise PermissionError("cannot rebind a crawl to another account")
            self.db.execute("""UPDATE dragon_crawl_session_owners SET active=0
                WHERE owner=?""",(owner,))
            if existing:
                self.db.execute("""UPDATE dragon_crawl_session_owners
                    SET active=1 WHERE session_id=? AND owner=?""",(session_id,owner))
            else:
                self.db.execute("""INSERT INTO dragon_crawl_session_owners
                    VALUES(?,?,?,1)""",(session_id,owner,float(at)))

    def close(self,owner:str,session_id:str,*,authorized:bool) -> bool:
        if not authorized:
            raise PermissionError("crawler closure requires owner authority")
        self._owner(owner)
        with self.db:
            changed=self.db.execute("""UPDATE dragon_crawl_session_owners SET active=0
                WHERE session_id=? AND owner=?""",(session_id,owner))
            return changed.rowcount==1

    def read(self,owner:str,*,authorized:bool,
             after_sequence:int=0,limit:int=100) -> DragonCrawlFeed:
        self._owner(owner)
        if not authorized:
            raise PermissionError("crawler feed requires owner authority")
        if not isinstance(after_sequence,int) or isinstance(after_sequence,bool) or after_sequence<0:
            raise ValueError("invalid feed cursor")
        if not isinstance(limit,int) or isinstance(limit,bool) or not 1<=limit<=250:
            raise ValueError("invalid feed page limit")
        row=self.db.execute("""SELECT session_id FROM dragon_crawl_session_owners
            WHERE owner=? AND active=1 ORDER BY created_at DESC,session_id LIMIT 1""",
            (owner,)).fetchone()
        if not row:
            return DragonCrawlFeed(None,False,(),None,False)
        session_id=row[0]
        # The journal is hash chained but not signed. Verify it rather than
        # blindly turning a corrupted replay into UI-visible achievements.
        if not self.journal.verify(session_id):
            raise ValueError("crawler journal integrity check failed")
        p=self.journal.page(session_id,after=after_sequence,limit=limit)
        return DragonCrawlFeed(session_id,True,tuple(p["events"]),
                              p["nextCursor"],p["hasMore"])
