#!/usr/bin/env python3
"""
Persistent + encrypted Boardroom Vault (Tier-1 storage & security).

Same interface as BoardroomVault, but:
  • Stored in MongoDB (survives restarts) instead of ephemeral /tmp.
  • File bytes encrypted at rest with Fernet (AES-128-CBC + HMAC).
  • Full version history + rollback (error-recovery).

Key: env GAMEFORGE_VAULT_KEY if set, else a key is generated once and persisted
in `gameforge_vault_meta` so decryption works across restarts.
"""
from __future__ import annotations

import base64
import hashlib
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from cryptography.fernet import Fernet


@dataclass
class VaultEntry:
    file_id: str
    filename: str
    content_hash: str
    version: int
    timestamp: float
    metadata: Dict[str, Any]
    previous_version: Optional[str] = None


class PersistentVault:
    def __init__(self):
        self._fernet: Optional[Fernet] = None

    def _db(self):
        from core.databases import get_sync_db
        return get_sync_db()

    def _col(self):
        return self._db()["gameforge_vault"]

    def _key(self) -> bytes:
        env = os.getenv("GAMEFORGE_VAULT_KEY")
        if env:
            return env.encode() if len(env) >= 44 else base64.urlsafe_b64encode(env.encode().ljust(32)[:32])
        meta = self._db()["gameforge_vault_meta"]
        doc = meta.find_one({"_id": "fernet_key"})
        if doc and doc.get("key"):
            return doc["key"].encode()
        key = Fernet.generate_key()
        meta.update_one({"_id": "fernet_key"}, {"$set": {"key": key.decode(), "at": time.time()}}, upsert=True)
        return key

    def _f(self) -> Fernet:
        if self._fernet is None:
            self._fernet = Fernet(self._key())
        return self._fernet

    # ── API (mirrors BoardroomVault) ──
    def put_file(self, filename: str, content: bytes, metadata: Dict = None) -> VaultEntry:
        file_id = hashlib.sha256(filename.encode()).hexdigest()[:16]
        col = self._col()
        version = col.count_documents({"file_id": file_id}) + 1
        content_hash = hashlib.sha256(content).hexdigest()
        prev = None
        if version > 1:
            last = col.find({"file_id": file_id}).sort("version", -1).limit(1)
            last = list(last)
            prev = last[0]["file_id"] if last else None
        enc = self._f().encrypt(content).decode()
        entry = VaultEntry(file_id=file_id, filename=filename, content_hash=content_hash,
                           version=version, timestamp=time.time(), metadata=metadata or {},
                           previous_version=prev)
        col.insert_one({**entry.__dict__, "enc_content": enc, "encrypted": True})
        return entry

    def get_file(self, file_id: str, version: Optional[int] = None) -> Optional[bytes]:
        col = self._col()
        if version is None:
            docs = list(col.find({"file_id": file_id}).sort("version", -1).limit(1))
        else:
            docs = list(col.find({"file_id": file_id, "version": version}))
        if not docs:
            return None
        enc = docs[0].get("enc_content")
        if not enc:
            return None
        try:
            return self._f().decrypt(enc.encode())
        except Exception:  # noqa: BLE001
            return None

    def edit_file(self, file_id: str, new_content: bytes, metadata: Dict = None) -> Optional[VaultEntry]:
        docs = list(self._col().find({"file_id": file_id}).sort("version", -1).limit(1))
        if not docs:
            return None
        return self.put_file(docs[0]["filename"], new_content, metadata)

    def list_files(self) -> List[Dict]:
        col = self._col()
        result: List[Dict] = []
        for file_id in col.distinct("file_id"):
            versions = list(col.find({"file_id": file_id}, {"_id": 0, "enc_content": 0}).sort("version", -1))
            if versions:
                latest = versions[0]
                result.append({
                    "file_id": file_id, "filename": latest["filename"],
                    "latest_version": latest["version"], "last_updated": latest["timestamp"],
                    "total_versions": len(versions), "encrypted": True,
                })
        return result

    def get_versions(self, file_id: str) -> List[Dict]:
        return list(self._col().find({"file_id": file_id}, {"_id": 0, "enc_content": 0}).sort("version", 1))

    def rollback(self, file_id: str, to_version: int) -> Optional[VaultEntry]:
        """Error-recovery: restore an older version as a new latest version."""
        content = self.get_file(file_id, to_version)
        if content is None:
            return None
        docs = list(self._col().find({"file_id": file_id, "version": to_version}))
        meta = dict(docs[0].get("metadata", {})) if docs else {}
        meta["rolled_back_from"] = to_version
        return self.edit_file(file_id, content, meta)


# Global persistent, encrypted vault instance
boardroom_vault = PersistentVault()
