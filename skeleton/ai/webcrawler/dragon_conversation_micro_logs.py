"""Ten-step derived conversation checkpoints, never a second transcript owner.

Caller supplies an authorized canonical committed window. Bullets are explicit
game-topic signals and source references, not hidden reasoning or truth labels.
Training consent is separate; retrieval still requires current authorization.
"""
from __future__ import annotations

from hashlib import sha256
import json
from math import isfinite
import sqlite3

from skeleton.contracts.conversation import ConversationMessage, ConversationThread

from .dragon_microknowledge import _id, _terms, FACTORS


class DragonConversationMicroLogs:
    def __init__(self, db: sqlite3.Connection):
        self.db = db
        db.execute("""CREATE TABLE IF NOT EXISTS dragon_conversation_micro_logs(
            tenant TEXT NOT NULL,owner TEXT NOT NULL,thread TEXT NOT NULL,
            branch TEXT NOT NULL,end_sequence INTEGER NOT NULL,payload TEXT NOT NULL,
            digest TEXT NOT NULL,expires_at REAL NOT NULL,
            PRIMARY KEY(tenant,owner,thread,branch,end_sequence))""")
        db.execute("""CREATE TABLE IF NOT EXISTS dragon_conversation_micro_terms(
            tenant TEXT NOT NULL,owner TEXT NOT NULL,thread TEXT NOT NULL,
            branch TEXT NOT NULL,end_sequence INTEGER NOT NULL,term TEXT NOT NULL,
            PRIMARY KEY(tenant,owner,thread,branch,term,end_sequence))""")
        db.commit()

    def checkpoint(self, thread: ConversationThread, messages: tuple[ConversationMessage, ...],
                   factors: dict[str, str], *, tenant: str, owner: str,
                   expires_at: float, authorized: bool, retention_consent: bool,
                   training_consent: bool = False) -> str | None:
        if authorized is not True or retention_consent is not True:
            raise PermissionError("conversation projection requires authorization and retention consent")
        if not isinstance(training_consent, bool):
            raise ValueError("invalid training consent")
        if (thread.tenant_id, thread.owner_id) != (tenant, owner):
            raise PermissionError("conversation principal mismatch")
        if len(messages) != 10:
            raise ValueError("checkpoint requires exactly ten committed steps")
        end = messages[-1].sequence
        if end % 10:
            return None
        if [m.sequence for m in messages] != list(range(end - 9, end + 1)):
            raise ValueError("noncontiguous conversation window")
        if any(m.thread_id != thread.thread_id or m.branch_id != thread.active_branch_id
               or m.sequence > thread.message_sequence for m in messages):
            raise ValueError("uncommitted or foreign conversation window")
        if isinstance(expires_at, bool) or not isfinite(expires_at):
            raise ValueError("invalid retention expiry")
        if len(factors) > len(FACTORS) or any(k not in FACTORS for k in factors):
            raise ValueError("invalid conversation game factors")
        for v in factors.values():
            _id(v)
        # Do not copy arbitrary transcript text into an independent store.
        # These manually/context-adapter bound facets retain original references.
        payload = json.dumps({"bullets": [f"{k}: {v}" for k, v in sorted(factors.items())],
            "message_refs": [m.message_id for m in messages],
            "training_eligible": training_consent,
            "trust": "conversation_interest_not_verified_knowledge"},
            sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        if len(payload.encode()) > 4096:
            raise ValueError("conversation micro log exceeds byte budget")
        digest = sha256(payload.encode()).hexdigest()
        key = (tenant, owner, thread.thread_id, thread.active_branch_id, end)
        with self.db:
            # Serialize capacity/identity decisions across SQLite connections.
            self.db.execute("UPDATE dragon_conversation_micro_logs SET digest=digest WHERE tenant=? AND owner=? AND thread=? AND branch=? AND end_sequence=?", key)
            prior = self.db.execute("SELECT digest FROM dragon_conversation_micro_logs WHERE tenant=? AND owner=? AND thread=? AND branch=? AND end_sequence=?", key).fetchone()
            if prior:
                if prior[0] != digest:
                    raise ValueError("immutable conversation checkpoint conflict")
                return digest
            if self.db.execute("SELECT count(*) FROM dragon_conversation_micro_logs WHERE tenant=? AND owner=?", (tenant, owner)).fetchone()[0] >= 1000:
                raise ValueError("conversation checkpoint capacity reached")
            self.db.execute("INSERT INTO dragon_conversation_micro_logs VALUES(?,?,?,?,?,?,?,?)",
                            (*key, payload, digest, expires_at))
            self.db.executemany("INSERT INTO dragon_conversation_micro_terms VALUES(?,?,?,?,?,?)",
                ((*key, term) for term in _terms(" ".join(factors.values()))))
        return digest

    def retrieve(self, thread: ConversationThread, query: str, *, tenant: str,
                 owner: str, now: float, authorized: bool, limit: int = 3) -> tuple[dict, ...]:
        if authorized is not True or (thread.tenant_id, thread.owner_id) != (tenant, owner):
            raise PermissionError("conversation context access denied")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 10:
            raise ValueError("invalid micro log limit")
        if not isinstance(query, str) or len(query) > 512 or isinstance(now, bool) or not isfinite(now):
            raise ValueError("invalid context query")
        terms = _terms(query)[:16]
        if not terms:
            return ()
        rows = self.db.execute(f"""SELECT DISTINCT l.payload,l.digest FROM dragon_conversation_micro_logs l
            JOIN dragon_conversation_micro_terms t ON t.tenant=l.tenant AND t.owner=l.owner
            AND t.thread=l.thread AND t.branch=l.branch AND t.end_sequence=l.end_sequence
            WHERE l.tenant=? AND l.owner=? AND l.thread=? AND l.branch=? AND l.expires_at>?
            AND l.end_sequence<=? AND t.term IN ({','.join('?' for _ in terms)})
            ORDER BY l.end_sequence DESC LIMIT ?""", (tenant, owner, thread.thread_id,
            thread.active_branch_id, now, thread.message_sequence, *terms, limit)).fetchall()
        result = []
        for payload, digest in rows:
            if sha256(payload.encode()).hexdigest() != digest:
                raise ValueError("conversation micro log integrity failure")
            result.append(json.loads(payload))
        return tuple(result)

    def delete_thread(self, tenant: str, owner: str, thread: str, *, authorized: bool) -> None:
        if authorized is not True:
            raise PermissionError("conversation projection deletion denied")
        for value in (tenant, owner, thread):
            _id(value)
        with self.db:
            for table in ("dragon_conversation_micro_logs", "dragon_conversation_micro_terms"):
                self.db.execute(f"DELETE FROM {table} WHERE tenant=? AND owner=? AND thread=?", (tenant, owner, thread))

    def expire(self, *, now: float) -> int:
        if isinstance(now, bool) or not isfinite(now):
            raise ValueError("invalid expiry timestamp")
        with self.db:
            count = self.db.execute("DELETE FROM dragon_conversation_micro_logs WHERE expires_at<=?", (now,)).rowcount
            self.db.execute("""DELETE FROM dragon_conversation_micro_terms AS t WHERE NOT EXISTS(
                SELECT 1 FROM dragon_conversation_micro_logs l WHERE l.tenant=t.tenant AND l.owner=t.owner
                AND l.thread=t.thread AND l.branch=t.branch AND l.end_sequence=t.end_sequence)""")
        return count
